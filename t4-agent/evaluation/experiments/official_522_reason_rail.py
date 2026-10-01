#!/usr/bin/env python3
"""Run the pinned scorer 5.2.2 schema, claim and submitted-reason rails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sys.path[:0] = [str(args.official_root / "track4"), str(args.official_root / "common" / "common")]
    import jsonschema
    from baselines.guardrails_example.citation_rail import (
        check_answer, check_claim_rules, check_submitted_reasons, load_corpus, reasons_judged,
    )

    schema = json.loads(
        (args.official_root / "common" / "common" / "qfbench2_common" / "schemas" / "analysis.schema.json")
        .read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(schema)
    details = []
    for answer_path in sorted(args.answers.glob("t4-*/answer.json")):
        name = answer_path.parent.name
        unit = args.units / name
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        task = json.loads((unit / "task.json").read_text(encoding="utf-8"))
        corpus = load_corpus(unit / "corpus")
        schema_errors = [error.message for error in validator.iter_errors(answer)]
        basic = check_answer(answer, corpus, task["cutoff_date"], task=task)
        claims = check_claim_rules(answer, unit, token_counter=None)
        warnings = [item for item in claims if item.code == "claim_tokens_unchecked"]
        deterministic = [item for item in claims if item.code != "claim_tokens_unchecked"]
        reasons = check_submitted_reasons(answer, corpus, task["cutoff_date"])
        plan = reasons_judged(answer, corpus, task["cutoff_date"])
        details.append({
            "task_id": name,
            "schema_errors": schema_errors,
            "basic_findings": [item.__dict__ for item in basic],
            "claim_warnings": [item.__dict__ for item in warnings],
            "deterministic_claim_findings": [item.__dict__ for item in deterministic],
            "reason_findings": [item.__dict__ for item in reasons],
            "reasons": len(answer.get("submitted_reasons", [])),
            "reasons_judged": sum(bool(item.get("judged")) for item in plan),
            "claims": sum(len(row.get("claims", [])) for row in answer.get("entity_predictions", [])),
        })
    passed = all(
        not item["schema_errors"] and not item["basic_findings"]
        and not item["deterministic_claim_findings"] and not item["reason_findings"]
        and item["reasons"] == item["reasons_judged"]
        for item in details
    )
    report = {
        "schema_version": 1,
        "date": "2026-10-01",
        "experiment": "reason_evidence_relevance_official_522_rail_v1",
        "official_track4_commit": "ede7381d8c1ba9d8c84068f9d142f5e093a33892",
        "official_shared_commit": "84221f1b553475b1283cb653145051e916377dd0",
        "official_scorer_version": "5.2.2",
        "units": len(details),
        "schema_valid_units": sum(not item["schema_errors"] for item in details),
        "claims": sum(item["claims"] for item in details),
        "reasons": sum(item["reasons"] for item in details),
        "reasons_judged": sum(item["reasons_judged"] for item in details),
        "basic_finding_count": sum(len(item["basic_findings"]) for item in details),
        "deterministic_claim_finding_count": sum(len(item["deterministic_claim_findings"]) for item in details),
        "reason_finding_count": sum(len(item["reason_findings"]) for item in details),
        "claim_token_cap_check": "unchecked because official tokenizers are not installed locally",
        "claim_nli_contradiction_check": "not repeated; claims and claim citations are byte-identical",
        "decision": "accept_rail" if passed else "reject",
        "local_llm_run": False,
        "local_nli_run": False,
        "details": details,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "units", "schema_valid_units", "claims", "reasons", "reasons_judged", "basic_finding_count",
        "deterministic_claim_finding_count", "reason_finding_count", "decision",
    )}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
