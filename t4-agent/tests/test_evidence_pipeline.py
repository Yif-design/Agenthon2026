from __future__ import annotations

from t4agent.evidence import validate_model_output
from t4agent.family_specs import SPECS
from t4agent.predict import predict_rows
from t4agent.retrieve import BM25, Chunk, IndexedCorpus, allowed_document_ids
from t4agent.taskio import Task
from t4agent.validate import validate_answer


def make_task(family: str, target_name: str, entities: list[dict]) -> Task:
    return Task(
        raw={},
        task_id="test",
        schema_version="3",
        target={"name": target_name, "type": "classification", "labels": ["credit_event", "no_event"]},
        target_type="classification",
        labels=["credit_event", "no_event"],
        entities=entities,
        cutoff_date="2024-01-01",
        interval_level=0.9,
        prompt="",
        family=family,
    )


def test_company_document_scope_uses_cik() -> None:
    corpus = IndexedCorpus(
        [],
        {"EDGAR_0000000001_10K": "A", "EDGAR_0000000002_10K": "B"},
        {"EDGAR_0000000001_10K": "2023-01-01", "EDGAR_0000000002_10K": "2023-01-01"},
    )
    task = make_task("credit_event", "credit_event_12m", [{"entity_id": "A", "cik": "1"}])
    assert allowed_document_ids(task, task.entities[0], corpus) == {"EDGAR_0000000001_10K"}


def test_bm25_never_returns_foreign_document() -> None:
    chunks = [
        Chunk("A", "2023-01-01", 0, 17, "liquidity default"),
        Chunk("B", "2023-01-01", 0, 17, "liquidity default"),
    ]
    results = BM25(chunks).search("liquidity default", allowed_doc_ids={"B"})
    assert results and {result.chunk.doc_id for result in results} == {"B"}


def test_nonzero_signal_with_foreign_doc_is_neutralized() -> None:
    corpus = IndexedCorpus([], {"A": "substantial doubt about continuing"}, {"A": "2023-01-01"})
    parsed = {
        "signals": {
            "going_concern_present": {
                "level": 2,
                "doc_id": "A",
                "quote": "substantial doubt about continuing",
                "claim": "There is going-concern language.",
            }
        }
    }
    signals, _, facts, rejected = validate_model_output(parsed, SPECS["credit"], "B", corpus, set())
    assert signals["going_concern_present"] == 0
    assert not facts
    assert rejected[0].reason == "doc_not_in_entity_scope"


def test_nonexact_quote_is_rejected_and_neutralized() -> None:
    corpus = IndexedCorpus([], {"A": "exact source text"}, {"A": "2023-01-01"})
    parsed = {
        "signals": {
            "explicit_forward_outlook_signal": {
                "level": 2,
                "doc_id": "A",
                "quote": "invented source text",
                "claim": "Outlook improved.",
            }
        }
    }
    signals, _, facts, rejected = validate_model_output(parsed, SPECS["reaction"], "AAPL", corpus, {"A"})
    assert signals["explicit_forward_outlook_signal"] == 0
    assert not facts
    assert rejected[0].reason == "quote_not_exact_substring"


def test_exact_quote_produces_a_span_bound_fact() -> None:
    text = "prefix explicit guidance improved suffix"
    corpus = IndexedCorpus([], {"A": text}, {"A": "2023-01-01"})
    quote = "explicit guidance improved"
    parsed = {
        "signals": {
            "explicit_forward_outlook_signal": {
                "level": 2,
                "doc_id": "A",
                "quote": quote,
                "claim": "Explicit guidance improved.",
            }
        }
    }
    signals, _, facts, rejected = validate_model_output(parsed, SPECS["reaction"], "AAPL", corpus, {"A"})
    assert signals["explicit_forward_outlook_signal"] == 2
    assert not rejected
    assert len(facts) == 1
    assert text[facts[0].span_start : facts[0].span_end] == quote


def test_whitespace_normalized_quote_maps_back_to_original_span() -> None:
    text = "Diluted EPS  $  5.28\n\t$ 2.68"
    corpus = IndexedCorpus([], {"A": text}, {"A": "2023-01-01"})
    parsed = {
        "signals": {
            "yoy_earnings_signal": {
                "level": 2,
                "doc_id": "A",
                "quote": "Diluted EPS $ 5.28 $ 2.68",
                "claim": "Diluted EPS increased.",
            }
        }
    }
    signals, _, facts, rejected = validate_model_output(parsed, SPECS["eps_yoy"], "A", corpus, {"A"})
    assert signals["yoy_earnings_signal"] == 2
    assert not rejected
    assert "5.28" in text[facts[0].span_start : facts[0].span_end]


def test_validator_rejects_cross_entity_citation() -> None:
    text = "company A evidence"
    corpus = IndexedCorpus(
        [],
        {"EDGAR_0000000001_10K": text, "EDGAR_0000000002_10K": "company B evidence"},
        {"EDGAR_0000000001_10K": "2023-01-01", "EDGAR_0000000002_10K": "2023-01-01"},
    )
    entity = {"entity_id": "B", "cik": "2"}
    task = make_task("credit_event", "credit_event_12m", [entity])
    answer = {
        "task_id": "test",
        "target_type": "classification",
        "entity_predictions": [{
            "entity_id": "B",
            "point_forecast": 0.05,
            "interval": {"level": 0.9, "lo": 0.0, "hi": 0.2},
            "label": "no_event",
            "claims": [{"doc_id": "EDGAR_0000000001_10K", "span_start": 0, "span_end": len(text), "claim": "x"}],
        }],
    }
    errors = validate_answer(answer, task, corpus)
    assert any("outside entity scope" in error for error in errors)


def test_rates_extract_shared_policy_signal_once() -> None:
    text = "The Committee anticipates that ongoing increases in the target range will be appropriate."
    doc_id = "FOMC_STATEMENT_20220727"
    chunk = Chunk(doc_id, "2022-07-27", 0, len(text), text)
    corpus = IndexedCorpus([chunk], {doc_id: text}, {doc_id: "2022-07-27"})
    task = Task(
        raw={},
        task_id="rates",
        schema_version="3",
        target={"name": "yield_change_bps_intermeeting", "type": "regression"},
        target_type="regression",
        labels=[],
        entities=[
            {"entity_id": "UST2Y", "name": "2-Year", "maturity_years": 2, "start_yield_pct": 2.0},
            {"entity_id": "UST30Y", "name": "30-Year", "maturity_years": 30, "start_yield_pct": 3.0},
        ],
        cutoff_date="2022-07-28",
        interval_level=0.9,
        prompt="",
        family="rate_curve_cross_section",
    )

    class FakeLLM:
        calls = 0

        def chat_json(self, system: str, user: str, max_tokens: int) -> dict:
            self.calls += 1
            item = {"doc_id": doc_id, "quote": text, "claim": "The Committee expects ongoing increases."}
            return {"context": item, "signals": {"policy_direction": {**item, "level": 1}}}

    llm = FakeLLM()
    results = predict_rows(task, BM25(corpus.chunks), corpus, llm, top_k=2)
    assert llm.calls == 1
    assert [row.prediction["point_forecast"] for row in results] == [15.0, 6.0]
    assert all(row.derivation and row.derivation["replay_verified"] for row in results)
