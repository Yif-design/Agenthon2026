from __future__ import annotations

from t4agent.evidence import EvidenceFact
from t4agent.formatting import build_answer
from t4agent.llm import Usage
from t4agent.predict import RowResult
from t4agent.reasons import build_submitted_reasons
from t4agent.retrieve import IndexedCorpus
from t4agent.taskio import Task


TEXT = "The exact target observation on 2024-03-01 was 2.61 ratio."


def row(entity_id: str = "ALPHA") -> RowResult:
    fact = EvidenceFact(
        fact_id=f"{entity_id}.value.DOC.0",
        entity_id=entity_id,
        name="value",
        kind="direct_observation",
        value=2.61,
        doc_id="DOC",
        span_start=0,
        span_end=len(TEXT),
        quote=TEXT,
        claim="The exact target observation was 2.61 ratio.",
        extractor="test",
    )
    prediction = {
        "entity_id": entity_id,
        "point_forecast": 2.61,
        "interval": {"level": 0.9, "lo": 2.0, "hi": 3.2},
        "claims": [fact.as_claim()],
    }
    return RowResult(
        prediction=prediction,
        raw_model=None,
        retrieved=[],
        method="generic_dated_table_baseline",
        facts=(fact,),
    )


def corpus() -> IndexedCorpus:
    return IndexedCorpus([], {"DOC": TEXT}, {"DOC": "2024-03-01"})


def test_submitted_reason_uses_exact_fact_and_final_answer(monkeypatch) -> None:
    monkeypatch.delenv("T4_ENABLE_SUBMITTED_REASONS", raising=False)
    reasons = build_submitted_reasons([row()], corpus())
    assert len(reasons) == 1
    reason = reasons[0]
    assert reason["premise"] == TEXT
    assert reason["citations"] == [{"doc_id": "DOC", "span_start": 0, "span_end": len(TEXT)}]
    assert reason["answer_implication"] == "For ALPHA, this supports the submitted point forecast 2.61."


def test_build_answer_adds_reasons_and_rollback_disables_them(monkeypatch) -> None:
    task = Task(
        raw={},
        task_id="reason-test",
        schema_version="3",
        target={"name": "metric", "type": "regression"},
        target_type="regression",
        labels=[],
        entities=[{"entity_id": "ALPHA"}],
        cutoff_date="2024-03-01",
        interval_level=0.9,
        prompt="Forecast metric.",
        family="generic",
    )
    monkeypatch.delenv("T4_ENABLE_SUBMITTED_REASONS", raising=False)
    enabled = build_answer(task, [row()], corpus(), Usage())
    assert len(enabled["submitted_reasons"]) == 1
    assert "validation_errors" not in enabled["notes"]
    monkeypatch.setenv("T4_ENABLE_SUBMITTED_REASONS", "0")
    disabled = build_answer(task, [row()], corpus(), Usage())
    assert "submitted_reasons" not in disabled


def test_reasons_are_omitted_when_projected_answer_exceeds_cap(monkeypatch) -> None:
    monkeypatch.delenv("T4_ENABLE_SUBMITTED_REASONS", raising=False)
    rows = [row("ENTITY_" + str(index) + "_" + "X" * 80) for index in range(30)]
    assert build_submitted_reasons(rows, corpus()) == []
