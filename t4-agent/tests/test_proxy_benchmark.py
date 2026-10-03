from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "proxy-benchmark"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_proxy", PROXY / "validate_proxy.py")
scorer = load_module("score_proxy", PROXY / "score_proxy.py")


class ProxyBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.explicit = PROXY / "units/proxy-18-cot-positioning-rank-20230926-explicit"
        self.transformed = PROXY / "units/proxy-18-cot-positioning-rank-20230926-transformed"
        self.auction_explicit = PROXY / "units/proxy-15-auction-indirect-bidder-share-20230802-explicit"
        self.auction_transformed = PROXY / "units/proxy-15-auction-indirect-bidder-share-20230802-transformed"

    def test_materialized_units_pass_integrity_and_variant_checks(self) -> None:
        errors = validator.validate_unit(self.explicit)
        errors += validator.validate_unit(self.transformed)
        errors += validator.compare_variants(self.explicit, self.transformed)
        self.assertEqual(errors, [])

    def test_auction_units_pass_integrity_and_variant_checks(self) -> None:
        errors = validator.validate_unit(self.auction_explicit)
        errors += validator.validate_unit(self.auction_transformed)
        errors += validator.compare_variants(self.auction_explicit, self.auction_transformed)
        self.assertEqual(errors, [])

    def test_source_snapshot_has_only_cutoff_history_plus_resolution_rows(self) -> None:
        source = json.loads((PROXY / "sources/proxy-18-cot-2023.json").read_text())
        dates = {row["report_date_as_yyyy_mm_dd"][:10] for row in source["rows"]}
        self.assertIn("2023-09-26", dates)
        self.assertIn("2023-10-03", dates)
        self.assertNotIn("2023-10-10", dates)

    def test_naive_answer_scores_exactly_half_on_both_legs(self) -> None:
        result = scorer.score(self.explicit, self.explicit / "reference/naive_answer.json")
        self.assertAlmostEqual(result["predictive_quality"], 0.5)
        self.assertAlmostEqual(result["interval_quality"], 0.5)
        self.assertAlmostEqual(result["composite_before_claim_penalty"], 0.5)

    def test_regression_naive_answer_scores_exactly_half_on_both_legs(self) -> None:
        result = scorer.score(
            self.auction_explicit,
            self.auction_explicit / "reference/naive_answer.json",
        )
        self.assertAlmostEqual(result["predictive_quality"], 0.5)
        self.assertAlmostEqual(result["interval_quality"], 0.5)
        self.assertAlmostEqual(result["composite_before_claim_penalty"], 0.5)

    def test_auction_snapshot_separates_cutoff_history_from_outcomes(self) -> None:
        source = json.loads((PROXY / "sources/proxy-15-auctions-2023.json").read_text())
        targets = [row for row in source["rows"] if row["announcemt_date"] == "2023-08-02"]
        self.assertEqual({row["original_security_term"] for row in targets}, {"3-Year", "10-Year", "30-Year"})
        for unit in (self.auction_explicit, self.auction_transformed):
            corpus = "\n".join(path.read_text() for path in (unit / "corpus").glob("*.json"))
            for row in targets:
                self.assertNotIn(row["indirect_bidder_accepted"], corpus)

    def test_average_rank_ties_are_neutral(self) -> None:
        self.assertEqual(scorer.spearman([0.0] * 10, list(range(10))), 0.0)

    def test_schema_variants_reverse_roster_without_changing_truth(self) -> None:
        left = json.loads((self.explicit / "task.json").read_text())
        right = json.loads((self.transformed / "task.json").read_text())
        self.assertEqual(
            [row["entity_id"] for row in left["entities"]],
            list(reversed([row["entity_id"] for row in right["entities"]])),
        )


if __name__ == "__main__":
    unittest.main()
