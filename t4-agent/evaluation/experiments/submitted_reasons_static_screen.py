#!/usr/bin/env python3
"""Build bounded deterministic reasoning candidates from final public answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PUBLIC_UNITS = (
    "t4-EXAMPLE-eps-beat",
    "t4-auction-btc-202411-us7",
    "t4-cotpos-202411-us10",
    "t4-cpicomp-202410-us11",
    "t4-credit-event-2023",
    "t4-eps-growth-2024Q3-banks",
    "t4-eps-yoy-2023Q2-mixed",
    "t4-fomc-curve-20220728",
    "t4-fomc-curve-20240918",
    "t4-macrorev-20240930-us6",
    "t4-postearn-20240201-megacap",
)

MECHANISMS = {
    "consensus_strong_signal": "The cited earnings evidence is combined with the available consensus signal; a positive or negative signal moves the submitted earnings class away from the neutral threshold.",
    "same_tenor_recent_history": "Recent same-tenor bid-to-cover observations are averaged to estimate the next auction result, while their dispersion sets forecast uncertainty.",
    "net_position_mean_reversion": "Current net positioning is treated as a crowding signal: more extreme positioning implies a larger subsequent move in the opposite direction.",
    "component_history": "The component's pre-cutoff monthly history anchors its next monthly change; recent observations determine the point and historical variation sets uncertainty.",
    "component_history_mean12": "The complete pre-cutoff twelve-month component history is averaged to reduce sensitivity to one volatile monthly observation.",
    "explicit_credit_flags": "Explicit distress indicators in the cited filing raise estimated event risk; absent validated distress evidence leaves the forecast near the low-risk prior.",
    "seasonal_eps_delta_persistence": "The latest same-quarter EPS change is carried forward as a simple seasonal persistence estimate for next-quarter year-over-year EPS growth.",
    "prior_eps_direction_only": "The prior comparable EPS level anchors the forecast, and the validated directional signal applies only a bounded step rather than inventing a missing magnitude.",
    "policy_direction_maturity_decay": "The policy direction sets the sign of the curve response, with smaller sensitivity at longer maturities and a fixed uncertainty band.",
    "median_historical_revision": "The median of the series' pre-cutoff revision history is applied to the current vintage to estimate the next revised level.",
    "flat_unless_strong_outlook": "Without validated forward-looking evidence strong enough to choose a direction, the submitted reaction stays flat with an uncertainty band reflecting historical event volatility.",
    "generic_dated_table_baseline": "The latest cutoff-safe observation from the exact target-matched dated column is used as the persistence forecast.",
}


def corpus_texts(unit: Path) -> dict[str, str]:
    result = {}
    for path in (unit / "corpus").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        doc_id = str(document.get("doc_id") or path.stem)
        result[doc_id] = str(document.get("text") or "")
    return result


def implication(row: dict) -> str:
    entity_id = str(row["entity_id"])
    if "label" in row:
        return f"For {entity_id}, this supports the submitted label {row['label']}."
    value = float(row["point_forecast"])
    if "rank" in row:
        return f"For {entity_id}, this supports the submitted point forecast {value:g} and rank {row['rank']}."
    return f"For {entity_id}, this supports the submitted point forecast {value:g}."


def reasons(answer: dict, texts: dict[str, str]) -> list[dict]:
    methods = answer.get("notes", {}).get("methods", {})
    built = []
    for row in answer["entity_predictions"]:
        entity_id = str(row["entity_id"])
        method = str(methods.get(entity_id) or "")
        mechanism = MECHANISMS.get(method)
        if mechanism is None:
            continue
        chosen = None
        for claim in row.get("claims", []):
            doc_id = str(claim.get("doc_id") or "")
            start, end = claim.get("span_start"), claim.get("span_end")
            text = texts.get(doc_id, "")
            if (
                doc_id != "task"
                and isinstance(start, int)
                and isinstance(end, int)
                and 0 <= start < end <= len(text)
                and end - start <= 2_000
                and len(text[start:end].split()) >= 3
            ):
                chosen = (doc_id, start, end, text[start:end])
                break
        if chosen is None:
            continue
        doc_id, start, end, premise = chosen
        built.append({
            "reason_id": f"r{len(built) + 1}",
            "premise": premise,
            "mechanism": mechanism,
            "answer_implication": implication(row),
            "scope": {"entities": [entity_id]},
            "citations": [{"doc_id": doc_id, "span_start": start, "span_end": end}],
        })
        if len(built) == 3:
            break
    return built


def compact_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()
    details = []
    for name in PUBLIC_UNITS:
        answer = json.loads((args.answers / name / "answer.json").read_text(encoding="utf-8"))
        built = reasons(answer, corpus_texts(args.units / name))
        if built:
            answer["submitted_reasons"] = built
        candidate = args.candidate_dir / name
        candidate.mkdir(parents=True, exist_ok=True)
        (candidate / "answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        projected = [
            {key: row[key] for key in ("entity_id", "label", "point_forecast", "interval", "label_probs") if key in row}
            for row in answer["entity_predictions"]
        ]
        reason_projection = [
            {key: reason[key] for key in ("reason_id", "premise", "mechanism", "answer_implication")}
            for reason in built
        ]
        details.append({
            "task_id": name,
            "rows": len(projected),
            "reasons": len(built),
            "answer_bytes": compact_size(projected),
            "reason_bytes": compact_size(reason_projection),
            "maximum_citation_characters": max((c["span_end"] - c["span_start"] for r in built for c in r["citations"]), default=0),
            "all_premises_exact_cited_slices": all(
                reason["premise"] == corpus_texts(args.units / name)[citation["doc_id"]][citation["span_start"]:citation["span_end"]]
                for reason in built for citation in reason["citations"]
            ),
        })
    passed = all(
        item["reasons"] >= 1
        and item["answer_bytes"] <= 3_000
        and item["reason_bytes"] <= 6_500
        and item["maximum_citation_characters"] <= 8_000
        and item["all_premises_exact_cited_slices"]
        for item in details
    )
    report = {
        "schema_version": 1,
        "experiment": "submitted_reasons_static_screen_v1",
        "baseline_git_commit": args.baseline_commit,
        "hypothesis": "Existing exact evidence and deterministic methods can produce at least one bounded, answer-consistent reasoning candidate for every public unit without changing analysis fields.",
        "decision_rule": "Proceed only if 11/11 units have at least one reason, exact cited premises, answer bytes <=3000, reason bytes <=6500, citation length <=8000, and later pass the official 5.2.2 schema and submitted-reasons rail.",
        "units": len(details),
        "units_passing_static_limits": sum(
            item["reasons"] >= 1 and item["answer_bytes"] <= 3_000 and item["reason_bytes"] <= 6_500 and item["maximum_citation_characters"] <= 8_000 and item["all_premises_exact_cited_slices"]
            for item in details
        ),
        "details": details,
        "decision": "proceed_to_official_rail" if passed else "reject",
        "production_change": "none",
        "model_api": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "local_llm_run": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"units": report["units"], "passing": report["units_passing_static_limits"], "decision": report["decision"]}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
