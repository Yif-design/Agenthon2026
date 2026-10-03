from argparse import Namespace
from pathlib import Path

import pytest

from evaluation.experiments.combine_nli_members import _combine_case
from evaluation.experiments.run_nli_member import RecordingJudge, _case_paths


def test_manifest_mode_allows_multiple_answers_for_one_unit(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.json"
    manifest.write_text(
        '{"cases": ['
        '{"case_id": "baseline", "unit_id": "same-unit", "answer": "baseline.json"},'
        '{"case_id": "candidate", "unit_id": "same-unit", "answer": "candidate.json"}'
        ']}'
    )
    args = Namespace(
        track4_repo=tmp_path / "official",
        unit=None,
        unit_ids=None,
        case_manifest=manifest,
        answer=None,
        answers_root=None,
    )

    cases = _case_paths(args)

    assert [row[0] for row in cases] == ["baseline", "candidate"]
    assert cases[0][1] == tmp_path / "official" / "units" / "same-unit"
    assert cases[1][2] == tmp_path / "candidate.json"


def test_manifest_mode_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.json"
    manifest.write_text(
        '[{"case_id":"same","unit_id":"u","answer":"a.json"},'
        '{"case_id":"same","unit_id":"u","answer":"b.json"}]'
    )
    args = Namespace(
        track4_repo=tmp_path,
        unit=None,
        unit_ids=None,
        case_manifest=manifest,
        answer=None,
        answers_root=None,
    )

    with pytest.raises(ValueError, match="case_id values must be unique"):
        _case_paths(args)


def test_combiner_uses_case_id_to_align_duplicate_unit_variants() -> None:
    common = {
        "unit_id": "same-unit",
        "answer_sha256": "abc",
        "tau_citation": 0.5,
        "faithfulness_threshold": 0.8,
        "predictions": [
            {"entity_id": "e", "hypothesis": "h", "score": 0.8, "supported": True}
        ],
    }
    first = {"case_id": "candidate", **common}
    second = {
        "case_id": "candidate",
        **common,
        "predictions": [
            {"entity_id": "e", "hypothesis": "h", "score": 0.4, "supported": False}
        ],
    }

    combined = _combine_case([first, second], first)

    assert combined["case_id"] == "candidate"
    assert combined["predictions"][0]["ensemble_score"] == pytest.approx(0.6)
    assert combined["gate_pass"] is True


def test_combiner_rejects_misaligned_case_ids() -> None:
    common = {
        "unit_id": "same-unit",
        "answer_sha256": "abc",
        "tau_citation": 0.5,
        "faithfulness_threshold": 0.8,
        "predictions": [],
    }

    with pytest.raises(ValueError, match="same scoring input"):
        _combine_case(
            [{"case_id": "a", **common}, {"case_id": "b", **common}],
            {"case_id": "a", **common},
        )


def test_combiner_averages_each_citation_before_selecting_best() -> None:
    common = {
        "case_id": "multi",
        "unit_id": "u",
        "answer_sha256": "abc",
        "tau_citation": 0.5,
        "faithfulness_threshold": 0.8,
    }
    first = {
        **common,
        "predictions": [{
            "entity_id": "e",
            "hypothesis": "h",
            "score": 0.9,
            "supported": True,
            "citation_scores": [
                {"premise_sha256": "a", "premise_chars": 10, "score": 0.9},
                {"premise_sha256": "b", "premise_chars": 20, "score": 0.1},
            ],
        }],
    }
    second = {
        **common,
        "predictions": [{
            "entity_id": "e",
            "hypothesis": "h",
            "score": 0.9,
            "supported": True,
            "citation_scores": [
                {"premise_sha256": "a", "premise_chars": 10, "score": 0.1},
                {"premise_sha256": "b", "premise_chars": 20, "score": 0.9},
            ],
        }],
    }

    combined = _combine_case([first, second], first)

    assert combined["predictions"][0]["ensemble_score"] == pytest.approx(0.5)
    assert combined["predictions"][0]["supported"] is False
    assert combined["faithfulness"] == 0.0
    assert combined["gate_pass"] is False


def test_recording_judge_captures_exact_pairs() -> None:
    class FakeJudge:
        def entail(self, premise: str, hypothesis: str) -> float:
            return len(premise) / 10

    judge = RecordingJudge(FakeJudge())

    assert judge.entail("abcd", "h") == 0.4
    assert judge.calls == {("abcd", "h"): 0.4}
