#!/usr/bin/env python3
"""Fetch and build proxy-11 through proxy-14 from official ALFRED/FRED vintages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from proxy_factory import dump, materialize_pair


ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
RETRIEVED = "2026-10-03"
LICENSE = "Underlying U.S. government data; source and vintage recorded via FRED/ALFRED"
CLAIMS = (
    ("ICSA", "Initial claims, seasonally adjusted", 1.0),
    ("ICNSA", "Initial claims, not seasonally adjusted", 1.0),
    ("CCSA", "Continuing claims, seasonally adjusted", 1.0),
    ("CCNSA", "Continuing claims, not seasonally adjusted", 1.0),
    ("IURSA", "Insured unemployment rate, seasonally adjusted", 0.001),
    ("IURNSA", "Insured unemployment rate, not seasonally adjusted", 0.001),
)
PCE = (
    ("PCEPI", "Headline PCE price index"),
    ("PCEPILFE", "Core PCE price index"),
    ("DGDSRG3M086SBEA", "PCE goods price index"),
    ("DDURRG3M086SBEA", "PCE durable-goods price index"),
    ("DNDGRG3M086SBEA", "PCE nondurable-goods price index"),
    ("DSERRG3M086SBEA", "PCE services price index"),
    ("DNRGRG3M086SBEA", "PCE energy goods and services price index"),
    ("DFXARG3M086SBEA", "PCE food price index"),
)
GDP = (
    ("A191RL1Q225SBEA", "Real GDP"),
    ("A006RL1Q225SBEA", "Real personal consumption expenditures"),
    ("A007RL1Q225SBEA", "Real goods consumption"),
    ("A008RL1Q225SBEA", "Real services consumption"),
    ("A011RL1Q225SBEA", "Real gross private domestic investment"),
    ("A822RL1Q225SBEA", "Real government consumption and investment"),
)
YIELDS = (("DGS2", "2-year", 24), ("DGS3", "3-year", 36), ("DGS5", "5-year", 60),
          ("DGS7", "7-year", 84), ("DGS10", "10-year", 120),
          ("DGS20", "20-year", 240), ("DGS30", "30-year", 360))
CROSS = (
    ("DEXUSEU", "Euro exchange rate", "fx"), ("DEXJPUS", "Japanese yen exchange rate", "fx"),
    ("DEXUSUK", "British pound exchange rate", "fx"), ("DEXCAUS", "Canadian dollar exchange rate", "fx"),
    ("DEXCHUS", "Chinese yuan exchange rate", "fx"), ("DEXKOUS", "South Korean won exchange rate", "fx"),
    ("DEXMXUS", "Mexican peso exchange rate", "fx"), ("DEXBZUS", "Brazilian real exchange rate", "fx"),
    ("DEXINUS", "Indian rupee exchange rate", "fx"), ("DEXSFUS", "South African rand exchange rate", "fx"),
    *((series, f"Treasury {name} yield", "rates") for series, name, _ in YIELDS),
    ("DCOILWTICO", "WTI crude spot price", "commodity"),
    ("DCOILBRENTEU", "Brent crude spot price", "commodity"),
    ("DHHNGSP", "Henry Hub natural gas spot price", "commodity"),
)


def fetch(series: str, start: str, end: str, vintage: str | None) -> dict[str, Any]:
    base = ALFRED if vintage else FRED
    params = {"id": series, "cosd": start, "coed": end}
    if vintage:
        params["vintage_date"] = vintage
    url = base + "?" + urlencode(params)
    raw = urlopen(url, timeout=30).read()
    rows = []
    for row in csv.DictReader(io.StringIO(raw.decode())):
        value = next(value for key, value in row.items() if key != "observation_date")
        if value not in ("", "."):
            rows.append({"date": row["observation_date"], "value": float(value)})
    return {"series_id": series, "url": url, "sha256": hashlib.sha256(raw).hexdigest(), "rows": rows}


def parallel(requests: list[tuple[str, str, str, str | None]]) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda args: fetch(*args), requests))


def snapshot(path: Path, generator: str, payload: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    dump(path, {"snapshot_version": "1.0.0", "retrieved_at": RETRIEVED,
                "generator": generator, "license": LICENSE,
                "raw_sources": [{"series_id": x["series_id"], "url": x["url"],
                                 "sha256": x["sha256"]} for x in sources], **payload})


def fetch_all(root: Path) -> None:
    claim_sources = parallel([
        (series, "2022-01-01", "2023-10-07", vintage)
        for series, _, _ in CLAIMS for vintage in ("2023-09-29", "2023-10-05")
    ])
    snapshot(root / "proxy-11-claims-2023.json", "proxy-benchmark/build_macro_proxies.py",
             {"cutoff": "2023-09-29", "resolution": "2023-10-05", "sources": claim_sources}, claim_sources)
    pce_sources = parallel([
        (series, "2022-01-01", "2023-07-01", vintage)
        for series, _ in PCE for vintage in ("2023-08-30", "2023-08-31")
    ])
    snapshot(root / "proxy-12-pce-2023.json", "proxy-benchmark/build_macro_proxies.py",
             {"cutoff": "2023-08-30", "resolution": "2023-08-31", "sources": pce_sources}, pce_sources)
    gdp_sources = parallel([
        (series, "2021-01-01", "2023-04-01", vintage)
        for series, _ in GDP for vintage in ("2023-08-29", "2023-08-30")
    ])
    snapshot(root / "proxy-13-gdp-2023.json", "proxy-benchmark/build_macro_proxies.py",
             {"cutoff": "2023-08-29", "resolution": "2023-08-30", "sources": gdp_sources}, gdp_sources)
    yield_sources = parallel([(series, "2022-01-01", "2023-11-30", None) for series, _, _ in YIELDS])
    snapshot(root / "proxy-14-yields-2023.json", "proxy-benchmark/build_macro_proxies.py",
             {"cutoff": "2023-09-29", "sources": yield_sources}, yield_sources)
    cross_sources = parallel([(series, "2022-01-01", "2023-11-30", None) for series, _, _ in CROSS])
    snapshot(root / "proxy-20-cross-asset-2023.json", "proxy-benchmark/build_macro_proxies.py",
             {"cutoff": "2023-09-29", "sources": cross_sources}, cross_sources)


def paired(data: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source in data["sources"]:
        grouped.setdefault(source["series_id"], []).append(source)
    return {key: (values[0], values[1]) for key, values in grouped.items()}


def build_claims(root: Path, units: Path) -> None:
    path = root / "proxy-11-claims-2023.json"; data = json.loads(path.read_text()); rows = []
    for series, name, scale in CLAIMS:
        old, new = paired(data)[series]
        visible = old["rows"][-26:]; last_date = visible[-1]["date"]
        new_rows = [row for row in new["rows"] if row["date"] > last_date]
        if not new_rows: raise ValueError(f"no first-print claims outcome for {series}")
        target = new_rows[0]; new_map = {row["date"]: row["value"] for row in new["rows"]}
        prior_dates = sorted(day for day in new_map if day < target["date"]); change = target["value"] - new_map[prior_dates[-1]]
        label = "increase" if change > 0 else "decrease" if change < 0 else "flat"
        changes = [b["value"] - a["value"] for a, b in zip(visible, visible[1:])]
        text = "\n".join([f"{name} ({series}); ALFRED vintage 2023-09-29.", "week | value",
                          *(f"{x['date']} | {x['value']:.6f}" for x in visible)])
        rows.append({"entity_id": f"CLAIMS_{series}_20231005", "name": name,
                     "explicit": {"series_id": series, "latest_level": visible[-1]["value"] * scale,
                                  "latest_change": changes[-1] * scale, "display_unit": "thousands_or_pp"},
                     "transformed": {"measure_code": f"UI-{len(rows)+31}", "terminal_value_raw": visible[-1]["value"],
                                     "one_period_delta_raw": changes[-1], "raw_scale": scale},
                     "corpus_explicit": text, "corpus_transformed": text.replace("value", "raw_measure"),
                     "truth": label, "naive_label": "flat", "naive_point": 0.0, "naive_half": 1.0})
    materialize_pair(root=units, snapshot_path=path, question_id="proxy-11-initial-claims-direction",
                     origin="20230929", cutoff=data["cutoff"], resolution=data["resolution"], split="time_forward_test",
                     target_type="classification", target_names={"explicit":"initial_claims_wow_direction","transformed":"next_ui_measure_direction"},
                     family_names={"explicit":"weekly_claims_direction","transformed":"weekly_labor_flow_class"},
                     unit="label", prompt="Classify the next first-published weekly change as increase, flat, or decrease.",
                     license_text=LICENSE, source_name="U.S. Department of Labor via ALFRED", rows=rows,
                     labels=["increase","flat","decrease"])


def build_pce(root: Path, units: Path) -> None:
    path=root/"proxy-12-pce-2023.json"; data=json.loads(path.read_text()); rows=[]
    for series,name in PCE:
        old,new=paired(data)[series]; visible=old["rows"]
        if visible[-1]["date"] >= "2023-07-01": raise ValueError(f"cutoff leaks July {series}")
        m={x["date"]:x["value"] for x in new["rows"]}; truth=100*(m["2023-07-01"]/m["2023-06-01"]-1)
        changes=[100*(b["value"]/a["value"]-1) for a,b in zip(visible,visible[1:])]
        naive=statistics.fmean(changes[-3:]); half=max(.05,1.65*statistics.pstdev(changes[-12:]))
        hist=visible[-18:]; text="\n".join([f"{name} ({series}); cutoff ALFRED vintage 2023-08-30.","month | index",*(f"{x['date']} | {x['value']:.6f}" for x in hist)])
        rows.append({"entity_id":f"PCE_{series}_202307","name":name,
                     "explicit":{"series_id":series,"latest_index":hist[-1]["value"],"recent_3m_mean_pct":naive,"unit":"monthly_percent"},
                     "transformed":{"component_key":f"PI-{len(rows)+41}","terminal_index_scaled":hist[-1]["value"]*1000,"recent_drift_fraction":naive/100,"scale":"index_x1000"},
                     "corpus_explicit":text,"corpus_transformed":text.replace("index","scaled_index"),
                     "truth":truth,"naive_point":naive,"naive_half":half})
    materialize_pair(root=units,snapshot_path=path,question_id="proxy-12-pce-component-nowcast",origin="20230830",
                     cutoff=data["cutoff"],resolution=data["resolution"],split="time_forward_test",target_type="regression",
                     target_names={"explicit":"pce_component_mom_first_print_pct","transformed":"next_price_component_drift_pct"},
                     family_names={"explicit":"pce_component_nowcast","transformed":"component_price_drift"},unit="percent",
                     prompt="Forecast July 2023 first-print month-over-month price-index change in percent.",
                     license_text=LICENSE,source_name="BEA via ALFRED",rows=rows)


def build_gdp(root: Path, units: Path) -> None:
    path=root/"proxy-13-gdp-2023.json"; data=json.loads(path.read_text()); rows=[]
    for series,name in GDP:
        old,new=paired(data)[series]; om={x["date"]:x["value"] for x in old["rows"]}; nm={x["date"]:x["value"] for x in new["rows"]}
        current=om["2023-04-01"]; truth=nm["2023-04-01"]-current; hist=old["rows"][-8:]
        text="\n".join([f"{name} ({series}); annualized growth rates in the 2023-08-29 vintage.","quarter | annualized_percent",*(f"{x['date']} | {x['value']:.6f}" for x in hist)])
        rows.append({"entity_id":f"GDP_{series}_2023Q2","name":name,
                     "explicit":{"series_id":series,"current_estimate_pct":current,"estimate_stage":"advance"},
                     "transformed":{"account_code":f"NIPA-{len(rows)+51}","stage_ordinal":1,"published_rate_fraction":current/100},
                     "corpus_explicit":text,"corpus_transformed":text.replace("annualized_percent","annualized_fraction"),
                     "truth":truth,"naive_point":0.0,"naive_half":max(.2,abs(truth)*2)})
    materialize_pair(root=units,snapshot_path=path,question_id="proxy-13-gdp-revision-magnitude",origin="20230829",
                     cutoff=data["cutoff"],resolution=data["resolution"],split="time_forward_test",target_type="regression",
                     target_names={"explicit":"next_gdp_revision_pp","transformed":"subsequent_estimate_delta_pp"},
                     family_names={"explicit":"gdp_estimate_revision","transformed":"national_accounts_update"},unit="percentage_points",
                     prompt="Forecast the second-estimate minus advance-estimate annualized growth revision in percentage points.",
                     license_text=LICENSE,source_name="BEA via ALFRED",rows=rows)


def build_yields(root: Path, units: Path) -> None:
    path=root/"proxy-14-yields-2023.json"; data=json.loads(path.read_text()); sources={x["series_id"]:x for x in data["sources"]}
    common=set.intersection(*({x["date"] for x in source["rows"]} for source in sources.values())); visible=sorted(x for x in common if x<=data["cutoff"]); future=sorted(x for x in common if x>data["cutoff"])
    resolution=future[19]; rows=[]
    for series,name,months in YIELDS:
        m={x["date"]:x["value"] for x in sources[series]["rows"]}; start=m[visible[-1]]; truth=100*(m[resolution]-start)
        changes=[100*(m[visible[i]]-m[visible[i-20]]) for i in range(20,len(visible))]; half=max(5.0,statistics.pstdev(changes[-60:]))
        hist=visible[-81:]; text="\n".join([f"Treasury {name} constant-maturity yield ({series}); percent.","date | yield_percent",*(f"{d} | {m[d]:.4f}" for d in hist)])
        rows.append({"entity_id":f"UST_{series}_20230929","name":name,
                     "explicit":{"series_id":series,"maturity_months":months,"cutoff_yield_pct":start,"recent_20d_change_bp":changes[-1]},
                     "transformed":{"curve_node":f"T-{months}","tenor_months":months,"terminal_rate_fraction":start/100,"recent_move_fraction":changes[-1]/10000},
                     "corpus_explicit":text,"corpus_transformed":text.replace("yield_percent","rate_fraction"),
                     "truth":truth,"naive_point":0.0,"naive_half":half})
    materialize_pair(root=units,snapshot_path=path,question_id="proxy-14-yield-curve-steepening-rank",origin="20230929",
                     cutoff=data["cutoff"],resolution=resolution,split="time_forward_test",target_type="ranking",
                     target_names={"explicit":"maturity_yield_change_rank","transformed":"curve_node_move_order"},
                     family_names={"explicit":"yield_curve_move","transformed":"relative_rate_node_shift"},unit="basis_points",
                     prompt="Rank Treasury maturities by yield change through the twentieth common post-cutoff observation; rank 1 is the largest increase.",
                     license_text=LICENSE,source_name="Federal Reserve Board H.15 via FRED",rows=rows)


def build_cross_asset(root: Path, units: Path) -> None:
    path=root/"proxy-20-cross-asset-2023.json"; data=json.loads(path.read_text()); sources={x["series_id"]:x for x in data["sources"]}
    common=set.intersection(*({x["date"] for x in source["rows"]} for source in sources.values())); visible=sorted(x for x in common if x<=data["cutoff"]); future=sorted(x for x in common if x>data["cutoff"])
    if len(visible)<81 or len(future)<20: raise ValueError("cross-asset common calendar is incomplete")
    resolution=future[19]; rows=[]
    for series,name,asset_class in CROSS:
        m={x["date"]:x["value"] for x in sources[series]["rows"]}; start=m[visible[-1]]; truth=100*(m[resolution]/start-1)
        returns=[100*(m[visible[i]]/m[visible[i-20]]-1) for i in range(20,len(visible))]; naive=returns[-1]; half=max(.25,1.65*statistics.pstdev(returns[-60:]))
        hist=visible[-81:]; text="\n".join([f"{name} ({series}); public daily level; asset class {asset_class}.","date | published_level",*(f"{d} | {m[d]:.8f}" for d in hist)])
        rows.append({"entity_id":f"XASSET_{series}_20230929","name":name,
                     "explicit":{"series_id":series,"asset_class":asset_class,"cutoff_level":start,"trailing_20d_return_pct":naive},
                     "transformed":{"instrument_key":f"XA-{len(rows)+101}","group_code":asset_class,"terminal_level_scaled":start*1000,"lagged_window_return_fraction":naive/100},
                     "corpus_explicit":text,"corpus_transformed":text.replace("published_level","level_x1000"),
                     "truth":truth,"naive_point":naive,"naive_half":half})
    materialize_pair(root=units,snapshot_path=path,question_id="proxy-20-cross-asset-return-quintile",origin="20230929",
                     cutoff=data["cutoff"],resolution=resolution,split="confirmation",target_type="ranking",
                     target_names={"explicit":"forward_return_quintile_rank","transformed":"next_window_relative_performance"},
                     family_names={"explicit":"cross_asset_forward_return","transformed":"relative_instrument_performance"},unit="percent_return",
                     prompt="Rank the 20 instruments by published-level percentage return through the twentieth common post-cutoff observation; rank 1 is highest.",
                     license_text=LICENSE,source_name="Federal Reserve Board and EIA via FRED",rows=rows)


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--fetch",action="store_true"); parser.add_argument("--sources",type=Path,default=Path("proxy-benchmark/sources")); parser.add_argument("--units",type=Path,default=Path("proxy-benchmark/units")); args=parser.parse_args()
    if args.fetch: fetch_all(args.sources)
    build_claims(args.sources,args.units); build_pce(args.sources,args.units); build_gdp(args.sources,args.units); build_yields(args.sources,args.units); build_cross_asset(args.sources,args.units)
    print(json.dumps({"questions":[11,12,13,14,20],"variants":10},indent=2))


if __name__ == "__main__": main()
