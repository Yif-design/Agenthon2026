#!/usr/bin/env python3
"""Build proxy-01 through proxy-08 from cutoff-safe SEC company facts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from proxy_factory import dump, materialize_pair


CUTOFF = "2023-03-31"
RESOLUTION = "2023-06-07"
RETRIEVED = "2026-10-03"
LICENSE = "Public SEC EDGAR XBRL company facts; accession and filing dates retained"
REV = ("RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues")
TAGS = {
    "revenue": REV, "gross": ("GrossProfit",),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "dividend": ("CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"),
    "shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "buyback": ("PaymentsForRepurchaseOfCommonStock",),
    "assets_current": ("AssetsCurrent",), "liabilities_current": ("LiabilitiesCurrent",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
}


def days(row: dict[str, Any]) -> int:
    try: return (dt.date.fromisoformat(row["end"]) - dt.date.fromisoformat(row["start"])).days
    except (KeyError, TypeError, ValueError): return 9999


def build_snapshot(raw_dir: Path, destination: Path) -> None:
    companies=[]; raw_sources=[]
    wanted={tag for aliases in TAGS.values() for tag in aliases}
    for path in sorted(raw_dir.glob("*.json")):
        raw=json.loads(path.read_text()); facts=raw["facts"].get("us-gaap",{}); selected={}
        for tag in wanted:
            if tag not in facts: continue
            units={}
            for unit, values in facts[tag]["units"].items():
                kept=[row for row in values if row.get("form") in ("10-Q","10-K") and "2019-01-01" <= row.get("filed","") <= "2024-12-31"]
                if kept: units[unit]=kept
            if units: selected[tag]={"label":facts[tag]["label"],"units":units}
        sha=hashlib.sha256(path.read_bytes()).hexdigest(); cik=str(raw["cik"]).zfill(10)
        companies.append({"ticker":path.stem,"cik":cik,"name":raw["entityName"],"facts":selected})
        raw_sources.append({"ticker":path.stem,"url":f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json","sha256":sha})
    dump(destination,{"snapshot_version":"1.0.0","retrieved_at":RETRIEVED,"generator":"proxy-benchmark/build_sec_proxies.py","license":LICENSE,"cutoff":CUTOFF,"resolution":RESOLUTION,"raw_sources":raw_sources,"companies":companies})


def values(company: dict[str, Any], aliases: tuple[str,...], *, instant: bool=False) -> list[dict[str,Any]]:
    for tag in aliases:
        fact=company["facts"].get(tag)
        if not fact: continue
        result=[]
        for unit, rows in fact["units"].items():
            for row in rows:
                if row.get("form") != "10-Q": continue
                if instant:
                    if row.get("start") is not None: continue
                elif row.get("fp") != "Q1" or not 70 <= days(row) <= 120: continue
                result.append({**row,"unit":unit,"tag":tag})
        if result: return result
    return []


def pair(company: dict[str,Any], aliases: tuple[str,...]) -> tuple[dict[str,Any],dict[str,Any]] | None:
    rows=values(company,aliases)
    targets=[row for row in rows if CUTOFF < row["filed"] <= RESOLUTION and row["end"] >= "2023-03-01"]
    if not targets: return None
    target=min(targets,key=lambda row:(row["filed"],row["end"]))
    target_end=dt.date.fromisoformat(target["end"])
    prior=[row for row in rows if row["filed"] <= CUTOFF and 300 < (target_end-dt.date.fromisoformat(row["end"])).days < 430]
    if not prior: return None
    return target,max(prior,key=lambda row:row["end"])


def exact(company: dict[str,Any], aliases: tuple[str,...], basis: dict[str,Any], *, instant: bool=False) -> dict[str,Any] | None:
    candidates=[]
    for row in values(company,aliases,instant=instant):
        same = row["end"] == basis["end"] if instant else row.get("start") == basis.get("start") and row["end"] == basis["end"]
        if same and row["filed"] <= basis["filed"]: candidates.append(row)
    return min(candidates,key=lambda row:row["filed"]) if candidates else None


def companies(snapshot_path: Path) -> list[dict[str,Any]]:
    return json.loads(snapshot_path.read_text())["companies"]


def base(company: dict[str,Any]) -> tuple[dict[str,Any],dict[str,Any]] | None:
    return pair(company,REV)


def corpus(company: dict[str,Any], lines: list[str]) -> str:
    return "\n".join([f"SEC XBRL facts for {company['name']} ({company['ticker']}); facts include original accession and filed date.",*lines])


def common_row(company: dict[str,Any], target: dict[str,Any], prior: dict[str,Any], truth: Any, naive: float, half: float, explicit: dict[str,Any], transformed: dict[str,Any], lines: list[str], naive_label: str | None=None) -> dict[str,Any]:
    result={"entity_id":f"SEC_{company['ticker']}_2023Q1","name":company["name"],"explicit":{"ticker":company["ticker"],"cik":company["cik"],**explicit},"transformed":{"issuer_key":f"CIK-{company['cik']}",**transformed},"corpus_explicit":corpus(company,lines),"corpus_transformed":corpus(company,[line.replace("USD","scaled currency units") for line in lines]),"truth":truth,"naive_point":naive,"naive_half":half}
    if naive_label is not None: result["naive_label"]=naive_label
    return result


def q1_revenue(snapshot_path: Path) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=base(company)
        if not p: continue
        target,prior=p; reference=float(prior["val"]); surprise=100*(float(target["val"])/reference-1); label="above_band" if surprise>2 else "below_band" if surprise<-2 else "within_band"
        rows.append(common_row(company,target,prior,label,0,.5,{"reference_revenue_usd":reference,"prior_period_end":prior["end"],"band_pct":2.0},{"benchmark_turnover_millions":reference/1e6,"tolerance_fraction":.02,"period_key":target["end"]},[f"Prior comparable revenue: USD {reference:.0f}, filed {prior['filed']}, accession {prior['accn']}.",f"Frozen reference equals the prior comparable quarter; classification band is plus or minus 2 percent."],"within_band"))
    return rows


def q2_gross(snapshot_path: Path) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=base(company)
        if not p: continue
        tr,pr=p; tg=exact(company,TAGS["gross"],tr); pg=exact(company,TAGS["gross"],pr)
        if not tg or not pg: continue
        prior_margin=100*pg["val"]/pr["val"]; target_margin=100*tg["val"]/tr["val"]; truth=100*(target_margin-prior_margin)
        rows.append(common_row(company,tr,pr,truth,0,max(50,abs(truth)*2),{"prior_revenue_usd":pr["val"],"prior_gross_profit_usd":pg["val"],"prior_gross_margin_pct":prior_margin},{"base_sales_millions":pr["val"]/1e6,"base_gross_fraction":prior_margin/100,"target_unit":"basis_points"},[f"Prior Q1 revenue USD {pr['val']:.0f} and gross profit USD {pg['val']:.0f}; gross margin {prior_margin:.6f} percent."]))
    return rows


def cash_metric(snapshot_path: Path, mode: str) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=base(company)
        if not p: continue
        tr,pr=p; tc=exact(company,TAGS["cfo"],tr); pc=exact(company,TAGS["cfo"],pr); tx=exact(company,TAGS["capex"],tr); px=exact(company,TAGS["capex"],pr)
        if not all((tc,pc,tx,px)): continue
        if mode=="fcf": target=100*(tc["val"]-tx["val"])/tr["val"]; prior=100*(pc["val"]-px["val"])/pr["val"]
        else: target=100*tx["val"]/tr["val"]; prior=100*px["val"]/pr["val"]
        rows.append(common_row(company,tr,pr,target,prior,max(.5,abs(prior)*.75),{"prior_revenue_usd":pr["val"],"prior_operating_cash_flow_usd":pc["val"],"prior_capex_usd":px["val"],"prior_metric_pct":prior},{"sales_millions":pr["val"]/1e6,"operating_flow_millions":pc["val"]/1e6,"investment_outflow_millions":px["val"]/1e6,"baseline_ratio_fraction":prior/100},[f"Prior Q1 revenue USD {pr['val']:.0f}; operating cash flow USD {pc['val']:.0f}; capital expenditure USD {px['val']:.0f}."]))
    return rows


def dividend_rows(snapshot_path: Path) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=pair(company,TAGS["dividend"])
        if not p: continue
        tr,pr=p; change=100*(tr["val"]/pr["val"]-1) if pr["val"] else 0; label="increase" if change>.5 else "decrease_or_suspend" if change<-.5 else "unchanged"
        rows.append(common_row(company,tr,pr,label,0,.5,{"prior_dividend_per_share":pr["val"],"prior_period_end":pr["end"]},{"base_distribution_microunits":pr["val"]*1e6,"action_code_hint":"regular_distribution"},[f"Prior Q1 regular dividend per share {pr['val']:.6f}; filed {pr['filed']}."],"unchanged"))
    return rows


def share_rows(snapshot_path: Path) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=pair(company,TAGS["shares"])
        if not p: continue
        tr,pr=p; change=100*(tr["val"]/pr["val"]-1); label="increase" if change>1 else "decrease" if change<-1 else "flat"
        rows.append(common_row(company,tr,pr,label,0,.5,{"prior_diluted_weighted_average_shares":pr["val"],"flat_band_pct":1.0},{"baseline_share_count_thousands":pr["val"]/1000,"neutral_tolerance_fraction":.01},[f"Prior comparable diluted weighted-average shares {pr['val']:.0f}; flat band plus or minus 1 percent."],"flat"))
    return rows


def buyback_rows(snapshot_path: Path) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=base(company)
        if not p: continue
        tr,pr=p; tb=exact(company,TAGS["buyback"],tr); pb=exact(company,TAGS["buyback"],pr)
        if not tb or not pb: continue
        target=100*tb["val"]/tr["val"]; prior=100*pb["val"]/pr["val"]
        rows.append(common_row(company,tr,pr,target,prior,max(.2,abs(prior)),{"prior_buyback_usd":pb["val"],"prior_revenue_usd":pr["val"],"prior_intensity_pct":prior},{"executed_capital_millions":pb["val"]/1e6,"frozen_scale_millions":pr["val"]/1e6,"baseline_fraction":prior/100},[f"Prior Q1 executed common-stock repurchases USD {pb['val']:.0f}; revenue USD {pr['val']:.0f}."]))
    return rows


def liquidity_rows(snapshot_path: Path) -> list[dict[str,Any]]:
    rows=[]
    for company in companies(snapshot_path):
        p=base(company)
        if not p: continue
        tr,pr=p; ta=exact(company,TAGS["assets_current"],tr,instant=True); tl=exact(company,TAGS["liabilities_current"],tr,instant=True); tc=exact(company,TAGS["cash"],tr,instant=True); pa=exact(company,TAGS["assets_current"],pr,instant=True); pl=exact(company,TAGS["liabilities_current"],pr,instant=True); pc=exact(company,TAGS["cash"],pr,instant=True)
        if not all((ta,tl,tc,pa,pl,pc)) or not tl["val"] or not pl["val"]: continue
        current=ta["val"]/tl["val"]; cash=tc["val"]/tl["val"]; prior_current=pa["val"]/pl["val"]; prior_cash=pc["val"]/pl["val"]
        label="stress_screen" if current<1 and cash<.1 else "no_stress_screen"
        rows.append(common_row(company,tr,pr,label,.1,.2,{"prior_current_ratio":prior_current,"prior_cash_to_current_liabilities":prior_cash,"screen_current_ratio_max":1.0,"screen_cash_ratio_max":.1},{"base_current_assets_millions":pa["val"]/1e6,"base_current_liabilities_millions":pl["val"]/1e6,"base_cash_millions":pc["val"]/1e6,"rule_code":"CR_LT_1_AND_CASH_LT_0_1"},[f"Prior current assets USD {pa['val']:.0f}; current liabilities USD {pl['val']:.0f}; cash USD {pc['val']:.0f}."],"no_stress_screen"))
    return rows


def build_all(snapshot_path: Path, units: Path) -> None:
    configs=[
      ("proxy-01-revenue-surprise-band","classification",q1_revenue(snapshot_path),["above_band","within_band","below_band"],"revenue_surprise_band","turnover_deviation_class","revenue_surprise","relative_turnover_band","label","Classify Q1 revenue relative to the frozen prior-year reference and plus/minus 2 percent band."),
      ("proxy-02-gross-margin-delta","regression",q2_gross(snapshot_path),None,"gross_margin_change_bps","next_gross_spread_delta_bp","gross_margin_delta","gross_spread_change","basis_points","Forecast Q1 year-over-year gross-margin change in basis points."),
      ("proxy-03-free-cash-flow-margin","regression",cash_metric(snapshot_path,"fcf"),None,"free_cash_flow_margin_pct","next_cash_surplus_ratio_pct","free_cash_flow_margin","cash_surplus_ratio","percent","Forecast Q1 operating cash flow less capex divided by revenue, in percent."),
      ("proxy-04-capex-intensity","regression",cash_metric(snapshot_path,"capex"),None,"capex_to_revenue_pct","next_investment_outflow_ratio_pct","capex_intensity","investment_outflow_ratio","percent","Forecast Q1 capital expenditure divided by revenue, in percent."),
      ("proxy-05-dividend-action","classification",dividend_rows(snapshot_path),["increase","unchanged","decrease_or_suspend"],"dividend_action","next_distribution_action","dividend_action","distribution_action","label","Classify the next Q1 regular per-share distribution action relative to prior-year Q1."),
      ("proxy-06-share-dilution-direction","classification",share_rows(snapshot_path),["increase","flat","decrease"],"diluted_share_change","next_average_share_direction","diluted_share_direction","average_share_direction","label","Classify Q1 diluted weighted-average share change year over year using a plus/minus 1 percent flat band."),
      ("proxy-07-buyback-intensity-rank","ranking",buyback_rows(snapshot_path),None,"next_quarter_buyback_intensity_rank","next_executed_capital_ratio_order","buyback_intensity","executed_capital_ratio","percent_of_revenue","Rank issuers by Q1 executed common-stock repurchases divided by Q1 revenue; rank 1 is highest."),
      ("proxy-08-liquidity-stress-event","classification",liquidity_rows(snapshot_path),["stress_screen","no_stress_screen"],"liquidity_stress_screen","next_balance_sheet_stress_class","liquidity_stress_screen","balance_sheet_screen","label","Classify the next Q1 balance sheet as stress_screen only when current ratio is below 1 and cash/current liabilities is below 0.1."),
    ]
    for index,(qid,tt,rows,labels,tn1,tn2,f1,f2,unit,prompt) in enumerate(configs,1):
        if len(rows)<6: raise ValueError(f"{qid} has only {len(rows)} eligible issuers")
        materialize_pair(root=units,snapshot_path=snapshot_path,question_id=qid,origin="20230331",cutoff=CUTOFF,resolution=RESOLUTION,split="time_forward_test",target_type=tt,target_names={"explicit":tn1,"transformed":tn2},family_names={"explicit":f1,"transformed":f2},unit=unit,prompt=prompt,license_text=LICENSE,source_name="SEC EDGAR company facts",rows=rows,labels=labels)
        print(qid,len(rows))


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--raw-dir",type=Path);parser.add_argument("--snapshot",type=Path,default=Path("proxy-benchmark/sources/proxy-sec-2023q1.json"));parser.add_argument("--units",type=Path,default=Path("proxy-benchmark/units"));args=parser.parse_args()
    if args.raw_dir: build_snapshot(args.raw_dir,args.snapshot)
    build_all(args.snapshot,args.units)


if __name__=="__main__": main()
