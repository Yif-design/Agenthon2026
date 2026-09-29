from __future__ import annotations

import math

from t4agent.predict import predict_rows
from t4agent.retrieve import BM25, Chunk, IndexedCorpus
from t4agent.tables import extract_generic_table_baseline, parse_dated_tables
from t4agent.taskio import Task


def task(target_name: str = "metric_ratio", unit: str = "ratio", target_type: str = "regression") -> Task:
    target = {"name": target_name, "type": target_type, "unit": unit}
    return Task({}, "table-test", "3", target, target_type, [], [{"entity_id": "X"}], "2024-02-15", 0.9, "", "unseen")


def corpus(text: str) -> IndexedCorpus:
    chunk = Chunk("DOC", "2024-02-10", 0, len(text), text)
    return IndexedCorpus([chunk], {"DOC": text}, {"DOC": "2024-02-10"})


def test_exact_target_table_extracts_latest_cutoff_safe_value() -> None:
    text = "date | metric_ratio\n2024-01-01 | 2.5\n2024-02-01 | 2.7\n2024-03-01 | 99"
    value = extract_generic_table_baseline(task(), {"entity_id": "X"}, corpus(text))

    assert value is not None
    assert value.value == 2.7
    assert value.quote == "2024-02-01 | 2.7"
    assert value.observation_date == "2024-02-01"
    assert value.unit == "ratio"


def test_derived_change_abstains_but_direct_change_column_is_supported() -> None:
    text = "date | rate_pct\n2024-01-01 | 4.10\n2024-02-01 | 4.02"
    assert extract_generic_table_baseline(task("rate_change_bps", "basis points"), {"entity_id": "X"}, corpus(text)) is None

    direct = "date | rate_change_bps\n2024-01-01 | -7\n2024-02-01 | -8"
    value = extract_generic_table_baseline(task("rate_change_bps", "basis points"), {"entity_id": "X"}, corpus(direct))
    assert value is not None
    assert math.isclose(value.value, -8.0)
    assert value.quote == "2024-02-01 | -8"


def test_malformed_missing_duplicate_and_unknown_unit_tables_abstain() -> None:
    rejected = [
        "date | metric_ratio\n2024-01-01 | --\n2024-02-01 | 2.7",
        "date | metric_ratio\n2024-01-01 | 2.5\n2024-01-01 | 2.7",
        "date | metric_ratio | METRIC_RATIO\n2024-01-01 | 2.5 | 2.7",
    ]
    assert all(extract_generic_table_baseline(task(), {"entity_id": "X"}, corpus(text)) is None for text in rejected)
    assert extract_generic_table_baseline(task("metric", ""), {"entity_id": "X"}, corpus("date | metric\n2024-01-01 | 2.5")) is None


def test_parser_does_not_cross_blank_or_malformed_rows() -> None:
    for boundary in ("", "broken"):
        text = f"date | metric_ratio\n2024-01-01 | 2.5\n{boundary}\n2024-02-01 | 99"
        [table] = parse_dated_tables(text, "2024-02-15")
        assert [row.cells[1] for row in table.rows] == ["2.5"]


def test_multiple_documents_require_doc_id_entity_binding() -> None:
    alpha = "date | metric_ratio\n2024-01-01 | 2.5"
    beta = "date | metric_ratio\n2024-02-01 | 99"
    indexed = IndexedCorpus(
        [],
        {"ALPHA_HISTORY": alpha, "BETA_HISTORY": beta},
        {"ALPHA_HISTORY": "2024-01-01", "BETA_HISTORY": "2024-02-01"},
    )
    value = extract_generic_table_baseline(task(), {"entity_id": "ALPHA"}, indexed)

    assert value is not None
    assert value.doc_id == "ALPHA_HISTORY"
    assert value.value == 2.5


def test_generic_pipeline_uses_table_baseline_and_exact_claim_without_extra_model_calls(monkeypatch) -> None:
    monkeypatch.setenv("T4_ENABLE_DATED_TABLE_BASELINE", "1")
    text = "date | metric_ratio\n2024-01-01 | 2.5\n2024-02-01 | 2.7"
    indexed = corpus(text)

    class NeutralLLM:
        calls = 0
        last_failure_kind = None

        def chat_json(self, *_args, **_kwargs):
            self.calls += 1
            return {"signals": {"directional_signal": {"level": 0}}}

    llm = NeutralLLM()
    [result] = predict_rows(task(), BM25(indexed.chunks), indexed, llm, top_k=3)

    assert llm.calls == 1
    assert result.prediction["point_forecast"] == 2.7
    assert result.method == "generic_dated_table_baseline"
    assert result.derivation["baseline_reason"] == "cutoff_safe_target_matched_table"
    assert result.prediction["claims"][0]["doc_id"] == "DOC"
    assert text[result.prediction["claims"][0]["span_start"] : result.prediction["claims"][0]["span_end"]] == "2024-02-01 | 2.7"


def test_generic_pipeline_keeps_current_baseline_while_candidate_is_disabled(monkeypatch) -> None:
    monkeypatch.delenv("T4_ENABLE_DATED_TABLE_BASELINE", raising=False)
    text = "date | metric_ratio\n2024-01-01 | 2.5\n2024-02-01 | 2.7"
    indexed = corpus(text)

    class NeutralLLM:
        last_failure_kind = None

        def chat_json(self, *_args, **_kwargs):
            return {"signals": {"directional_signal": {"level": 0}}}

    [result] = predict_rows(task(), BM25(indexed.chunks), indexed, NeutralLLM(), top_k=3)
    assert result.prediction["point_forecast"] == 0.0
    assert result.method == "generic_baseline"


def test_known_family_does_not_use_generic_table_extractor(monkeypatch) -> None:
    monkeypatch.setenv("T4_ENABLE_DATED_TABLE_BASELINE", "1")
    known = task("cpi_component_mom", "percent")
    known = Task(known.raw, known.task_id, known.schema_version, known.target, known.target_type, known.labels, [{"entity_id": "X", "latest_published_mom_pct": 0.3}], known.cutoff_date, known.interval_level, known.prompt, "cpi_component")
    text = "date | cpi_component_mom\n2024-01-01 | 99"
    indexed = corpus(text)

    class NeverLLM:
        calls = 0

        def chat_json(self, *_args, **_kwargs):
            self.calls += 1
            return None

    [result] = predict_rows(known, BM25(indexed.chunks), indexed, NeverLLM(), top_k=3)
    assert result.prediction["point_forecast"] == 0.3
