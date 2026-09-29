from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from t4agent.evidence import fact_from_quote, validate_model_output
from t4agent.family_specs import (
    GENERIC_MAX_SCALAR_FIELDS,
    GENERIC_STRING_FIELD_LIMIT,
    GENERIC_TOTAL_STRING_LIMIT,
    SPECS,
    project_entity,
)
from t4agent.predict import PreparedRow, _claims_with_context, _model_batch_size, _unpack_batch, predict_rows
from t4agent.retrieve import BM25, Chunk, IndexedCorpus, allowed_document_ids, build_index, query_for, tokenize
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


def test_nested_corpus_ref_indexes_and_isolates_entity_subtree(tmp_path) -> None:
    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "entity-a").mkdir(parents=True)
    (corpus_dir / "entity-a-old").mkdir()
    (corpus_dir / "entity-b").mkdir()
    documents = {
        "entity-a/a.json": {"doc_id": "A", "doc_date": "2023-01-01", "text": "entity A evidence"},
        "entity-a/future.json": {"doc_id": "A_FUTURE", "doc_date": "2025-01-01", "text": "future answer"},
        "entity-a-old/a-old.json": {"doc_id": "A_OLD", "doc_date": "2023-01-01", "text": "old A evidence"},
        "entity-b/b.json": {"doc_id": "B", "doc_date": "2023-01-01", "text": "entity B evidence"},
    }
    for relative_path, document in documents.items():
        (corpus_dir / relative_path).write_text(json.dumps(document), encoding="utf-8")

    corpus = build_index(corpus_dir, "2024-01-01")
    entity = {"entity_id": "A", "corpus_ref": "corpus/entity-a/"}
    task = make_task("unseen_family", "unknown_metric", [entity])

    assert set(corpus.doc_texts) == {"A", "A_OLD", "B"}
    assert corpus.doc_paths == {
        "A": "entity-a/a.json",
        "A_OLD": "entity-a-old/a-old.json",
        "B": "entity-b/b.json",
    }
    assert allowed_document_ids(task, entity, corpus) == {"A"}


def test_root_corpus_ref_preserves_shared_document_scope(tmp_path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    for doc_id in ("A", "B"):
        (corpus_dir / f"{doc_id}.json").write_text(
            json.dumps({"doc_id": doc_id, "doc_date": "2023-01-01", "text": doc_id}),
            encoding="utf-8",
        )
    corpus = build_index(corpus_dir, "2024-01-01")
    entity = {"entity_id": "shared", "corpus_ref": "corpus/"}
    task = make_task("unseen_family", "unknown_metric", [entity])

    assert allowed_document_ids(task, entity, corpus) == {"A", "B"}


@pytest.mark.parametrize("corpus_ref", ["../private/", "corpus/../../private", "/input/corpus/entity", "corpus\\entity"])
def test_unsafe_corpus_ref_is_rejected(corpus_ref) -> None:
    corpus = IndexedCorpus([], {"A": "text"}, {"A": "2023-01-01"}, {"A": "entity/a.json"})
    entity = {"entity_id": "A", "corpus_ref": corpus_ref}
    task = make_task("unseen_family", "unknown_metric", [entity])

    with pytest.raises(ValueError, match="unsafe corpus_ref"):
        allowed_document_ids(task, entity, corpus)


def test_nested_index_rejects_duplicate_document_ids(tmp_path) -> None:
    corpus_dir = tmp_path / "corpus"
    for subtree in ("one", "two"):
        (corpus_dir / subtree).mkdir(parents=True)
        (corpus_dir / subtree / "doc.json").write_text(
            json.dumps({"doc_id": "DUPLICATE", "doc_date": "2023-01-01", "text": subtree}),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="duplicate corpus doc_id"):
        build_index(corpus_dir, "2024-01-01")


def test_bm25_never_returns_foreign_document() -> None:
    chunks = [
        Chunk("A", "2023-01-01", 0, 17, "liquidity default"),
        Chunk("B", "2023-01-01", 0, 17, "liquidity default"),
    ]
    results = BM25(chunks).search("liquidity default", allowed_doc_ids={"B"})
    assert results and {result.chunk.doc_id for result in results} == {"B"}


@pytest.mark.parametrize(
    ("family", "target_name"),
    [
        ("inventory_forecast", "inventory_position_rank"),
        ("housing", "auction_price_change"),
        ("equity_research", "analyst_revision_probability"),
        ("agriculture", "cotton_yield_rank"),
        ("marketing", "credit_eventual_return"),
        ("sports", "rate_curveball_score"),
        ("supply_chain", "positioning_of_inventory"),
    ],
)
def test_unknown_family_scope_ignores_incidental_specialist_substrings(family, target_name) -> None:
    corpus = IndexedCorpus(
        [],
        {"ENTITY_A_LOCAL": "local evidence", "GLOBAL_SHARED": "shared evidence"},
        {"ENTITY_A_LOCAL": "2023-01-01", "GLOBAL_SHARED": "2023-01-01"},
        {"ENTITY_A_LOCAL": "local.json", "GLOBAL_SHARED": "shared.json"},
    )
    entity = {"entity_id": "ENTITY_A", "corpus_ref": "corpus/"}
    task = make_task(family, target_name, [entity])

    assert allowed_document_ids(task, entity, corpus) == {"ENTITY_A_LOCAL", "GLOBAL_SHARED"}


def test_generic_projection_preserves_bounded_scalar_unknown_fields() -> None:
    projected = project_entity(
        {
            "entity_id": "ISSUER_A",
            "rating_bucket": "deep_speculative",
            "watch_negative": True,
            "custom_score": 2.5,
            "analyst_excerpt": "x" * (GENERIC_STRING_FIELD_LIMIT + 50),
            "nested": {"unsafe": "large"},
            "items": ["not", "scalar"],
            "corpus_ref": "corpus/issuer-a/",
        },
        SPECS["generic"],
    )

    assert projected["rating_bucket"] == "deep_speculative"
    assert projected["watch_negative"] is True
    assert projected["custom_score"] == 2.5
    assert projected["analyst_excerpt"] == "x" * GENERIC_STRING_FIELD_LIMIT
    assert "nested" not in projected
    assert "items" not in projected
    assert "corpus_ref" not in projected


def test_known_family_projection_still_rejects_unlisted_scalar_fields() -> None:
    projected = project_entity(
        {"entity_id": "A", "name": "Issuer A", "consensus_eps": 1.0, "hidden_status": "critical"},
        SPECS["eps_consensus"],
    )

    assert "hidden_status" not in projected


def test_generic_projection_bounds_total_fields_and_text() -> None:
    entity = {"entity_id": "A"}
    entity.update({f"text_{index}": "x" * GENERIC_STRING_FIELD_LIMIT for index in range(80)})
    projected = project_entity(entity, SPECS["generic"])

    assert len(projected) <= GENERIC_MAX_SCALAR_FIELDS
    assert sum(len(value) for value in projected.values() if isinstance(value, str)) <= GENERIC_TOTAL_STRING_LIMIT


def test_generic_query_uses_unknown_categorical_field_to_retrieve_correct_document() -> None:
    chunks = [
        Chunk("SAFE", "2023-01-01", 0, 34, "Issuer status is investment grade."),
        Chunk("RISK", "2023-01-01", 0, 37, "Issuer status is deep speculative."),
    ]
    entity = {"entity_id": "ISSUER_A", "rating_bucket": "deep speculative"}
    task = make_task("unseen_family", "future_credit_state", [entity])

    legacy = BM25(chunks).search(query_for(task, entity), top_k=1)
    candidate = BM25(chunks).search(query_for(task, entity, include_all_scalar_fields=True), top_k=1)

    assert legacy[0].chunk.doc_id == "SAFE"
    assert candidate[0].chunk.doc_id == "RISK"


def test_generic_query_prioritizes_semantic_schema_terms_over_generic_rubric() -> None:
    chunks = [
        Chunk("DISTRACTOR", "2023-01-01", 0, 58, "results outlook growth risk change forecast target evidence"),
        Chunk("MATCH", "2023-01-01", 0, 51, "Operating margin trend improved during the quarter."),
    ]
    entity = {"entity_id": "ISSUER_A", "operatingMarginTrend": 1.0}
    task = make_task("unseen_family", "futureMetric", [entity])

    query = query_for(task, entity, include_all_scalar_fields=True)

    assert "operatingMarginTrend operating Margin Trend" in query
    assert "results outlook growth risk change forecast target evidence" not in query
    assert BM25(chunks).search(query, top_k=1)[0].chunk.doc_id == "MATCH"


def test_generic_query_retains_rubric_for_opaque_schema() -> None:
    entity = {"entity_id": "ISSUER_A", "x1": 7}
    task = make_task("unseen_family", "opaqueTarget", [entity])

    query = query_for(task, entity, include_all_scalar_fields=True)

    assert query == (
        "ISSUER_A x1 7 opaqueTarget unseen_family "
        "results outlook growth risk change forecast target evidence"
    )


def test_generic_opaque_query_uses_bounded_prompt_terms() -> None:
    chunks = [
        Chunk("DISTRACTOR", "2023-01-01", 0, 58, "results outlook growth risk change forecast target evidence"),
        Chunk("MATCH", "2023-01-01", 0, 43, "The issuer reported a covenant breach."),
    ]
    entity = {"entity_id": "ISSUER_A", "x1": 7}
    base = make_task("unseen_family", "opaqueTarget", [entity])
    task = Task(**{**base.__dict__, "prompt": "Predict whether the issuer faces a covenant breach within 12 months."})

    query = query_for(task, entity, include_all_scalar_fields=True)

    assert "issuer faces covenant breach within months" in query
    assert "results outlook growth risk change forecast target evidence" not in query
    assert BM25(chunks).search(query, top_k=1)[0].chunk.doc_id == "MATCH"


def test_generic_template_prompt_keeps_legacy_rubric() -> None:
    entity = {"entity_id": "ISSUER_A", "x1": 7}
    base = make_task("unseen_family", "opaqueTarget", [entity])
    task = Task(**{**base.__dict__, "prompt": "Predict target value for each entity."})

    assert query_for(task, entity, include_all_scalar_fields=True) == (
        "ISSUER_A x1 7 opaqueTarget unseen_family "
        "results outlook growth risk change forecast target evidence"
    )


def test_known_query_does_not_expand_or_suppress_rubric() -> None:
    entity = {"entity_id": "ISSUER_A", "operatingMarginTrend": 1.0}
    task = make_task("known_family", "futureMetric", [entity])

    query = query_for(task, entity, include_all_scalar_fields=False)

    assert "operatingMarginTrend" not in query
    assert "futureMetric" in query
    assert "future Metric" not in query
    assert "results outlook growth risk change forecast target evidence" in query


@pytest.mark.parametrize(
    ("family", "target_name", "wrong_terms"),
    [
        ("inventory_forecast", "inventory_position_rank", "commitments traders"),
        ("housing", "auction_price_change", "indirect direct dealer"),
        ("equity_research", "analyst_revision_probability", "durable goods shipments"),
        ("agriculture", "cotton_yield_rank", "fomc inflation labor"),
        ("marketing", "credit_eventual_return", "liquidity debt default"),
        ("sports", "rate_curveball_score", "fomc inflation labor"),
        ("supply_chain", "positioning_of_inventory", "commitments traders"),
    ],
)
def test_generic_query_does_not_inject_specialist_rubric_from_substrings(
    family: str, target_name: str, wrong_terms: str
) -> None:
    entity = {"entity_id": "A", "opaqueValue": 1}
    task = make_task(family, target_name, [entity])

    query = query_for(task, entity, include_all_scalar_fields=True)

    assert wrong_terms not in query


def test_tokenizer_ignores_trailing_punctuation_but_preserves_financial_tokens() -> None:
    assert tokenize("action_flat.") == tokenize("action_flat") == ["action_flat"]
    assert tokenize("$5.28, 10%; 2024-10-31 year-over-year.") == [
        "$5.28",
        "10%",
        "2024-10-31",
        "year-over-year",
    ]
    assert tokenize("... - %") == []


def test_bm25_entity_token_matches_sentence_final_identifier() -> None:
    chunks = []
    for entity_id in ("action_up", "action_flat", "action_down"):
        text = f"{entity_id}. evidence"
        chunks.append(Chunk(f"DOC_{entity_id.upper()}", "2023-01-01", 0, len(text), text))

    index = BM25(chunks)

    for entity_id in ("action_up", "action_flat", "action_down"):
        assert index.search(entity_id, top_k=1)[0].chunk.doc_id == f"DOC_{entity_id.upper()}"


def test_bm25_exact_score_tie_prefers_newer_cutoff_safe_document() -> None:
    text = "Acme earnings outlook evidence"
    chunks = [
        Chunk("A_OLD", "2023-01-01", 0, len(text), text),
        Chunk("Z_NEW", "2024-12-01", 0, len(text), text),
    ]

    results = BM25(chunks).search("Acme earnings", top_k=2)

    assert results[0].score == results[1].score
    assert [item.chunk.doc_id for item in results] == ["Z_NEW", "A_OLD"]


def test_bm25_zero_score_fallback_prefers_newer_document() -> None:
    chunks = [
        Chunk("A_OLD", "2023-01-01", 0, 8, "old text"),
        Chunk("Z_NEW", "2024-12-01", 0, 8, "new text"),
    ]

    results = BM25(chunks).search("unmatched", top_k=2)

    assert [item.chunk.doc_id for item in results] == ["Z_NEW", "A_OLD"]


def test_bm25_higher_score_still_beats_newer_document() -> None:
    chunks = [
        Chunk("A_OLD", "2023-01-01", 0, 30, "Acme earnings earnings evidence"),
        Chunk("Z_NEW", "2024-12-01", 0, 21, "Acme earnings evidence"),
    ]

    results = BM25(chunks).search("earnings", top_k=2)

    assert results[0].score > results[1].score
    assert results[0].chunk.doc_id == "A_OLD"


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


def test_context_citations_preserve_facts_and_add_three_exact_scoped_chunks() -> None:
    text = "fact sentence. first context. second context. third context. fourth context."
    foreign = "foreign context"
    corpus = IndexedCorpus([], {"A": text, "B": foreign}, {"A": "2023-01-01", "B": "2023-01-01"})
    fact = fact_from_quote(
        entity_id="E",
        name="fact",
        kind="context",
        value="fact",
        doc_id="A",
        quote="fact sentence.",
        claim="A verified fact.",
        extractor="test",
        corpus=corpus,
    )
    assert fact is not None
    chunks = []
    for phrase in ("first context.", "second context.", "third context.", "fourth context."):
        start = text.index(phrase)
        chunks.append(Chunk("A", "2023-01-01", start, start + len(phrase), phrase))
    chunks.insert(1, Chunk("B", "2023-01-01", 0, len(foreign), foreign))
    chunks.insert(2, Chunk("A", "2023-01-01", 0, 4, "not exact"))

    claims = _claims_with_context([fact], chunks, corpus, {"A"}, max_context=3)

    assert claims[0] == fact.as_claim()
    assert len(claims) == 4
    assert [text[c["span_start"] : c["span_end"]] for c in claims[1:]] == [
        "first context.",
        "second context.",
        "third context.",
    ]
    assert {claim["doc_id"] for claim in claims} == {"A"}


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


def test_generic_entities_are_batched_and_mapped_by_item_id(monkeypatch) -> None:
    entities = [{"entity_id": f"E{i}", "latest_value": float(i + 1)} for i in range(7)]
    task = Task(
        raw={},
        task_id="unknown",
        schema_version="3",
        target={"name": "unknown_metric", "type": "regression"},
        target_type="regression",
        labels=[],
        entities=entities,
        cutoff_date="2024-01-01",
        interval_level=0.9,
        prompt="forecast the unknown metric",
        family="unseen_family",
    )
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "3")

    class FakeLLM:
        calls = 0

        def chat_json(self, system: str, user: str, max_tokens: int) -> dict:
            self.calls += 1
            if "REQUEST_JSON:\n" not in user:
                return {"signals": {"directional_signal": {"level": 0}}}
            request = json.loads(user.split("REQUEST_JSON:\n", 1)[1].split("\nOUTPUT_SCHEMA_JSON:", 1)[0])
            return {
                "entities": [
                    {
                        "item_id": item["item_id"],
                        "entity_id": item["entity_id"],
                        "signals": {"directional_signal": {"level": 0}},
                    }
                    for item in reversed(request["items"])
                ]
            }

    llm = FakeLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)
    assert llm.calls == 3
    assert [row.prediction["entity_id"] for row in results] == [f"E{i}" for i in range(7)]
    assert [row.prediction["point_forecast"] for row in results] == [float(i + 1) for i in range(7)]


def test_context_limited_batch_retries_each_row_individually(monkeypatch) -> None:
    entities = [{"entity_id": f"E{i}", "latest_value": float(i + 1)} for i in range(3)]
    task = make_task("unseen_family", "unknown_metric", entities)
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "3")

    class FakeLLM:
        calls = 0
        last_failure_kind = None

        def chat_json(self, system: str, user: str, max_tokens: int) -> dict | None:
            self.calls += 1
            if "REQUEST_JSON:\n" in user:
                self.last_failure_kind = "context_length"
                return None
            self.last_failure_kind = None
            return {"signals": {"directional_signal": {"level": 0}}}

    llm = FakeLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)

    assert llm.calls == 4
    assert all(row.raw_model is not None for row in results)
    assert all(row.model_prompt and "REQUEST_JSON:\n" not in row.model_prompt for row in results)


def test_non_context_batch_failure_does_not_split(monkeypatch) -> None:
    entities = [{"entity_id": f"E{i}", "latest_value": float(i + 1)} for i in range(3)]
    task = make_task("unseen_family", "unknown_metric", entities)
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "3")

    class FakeLLM:
        calls = 0
        last_failure_kind = "other"

        def chat_json(self, system: str, user: str, max_tokens: int) -> None:
            self.calls += 1
            self.last_failure_kind = "other"
            return None

    llm = FakeLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)

    assert llm.calls == 1
    assert all(row.raw_model is None for row in results)


def test_single_context_failure_is_not_retried(monkeypatch) -> None:
    task = make_task("unseen_family", "unknown_metric", [{"entity_id": "E0", "latest_value": 1.0}])
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "3")

    class FakeLLM:
        calls = 0
        last_failure_kind = None

        def chat_json(self, system: str, user: str, max_tokens: int) -> None:
            self.calls += 1
            self.last_failure_kind = "context_length"
            return None

    llm = FakeLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)

    assert llm.calls == 1
    assert results[0].raw_model is None


def test_context_recovery_defers_single_rows_until_after_normal_batches(monkeypatch) -> None:
    entities = [{"entity_id": f"E{i}", "latest_value": float(i + 1)} for i in range(78)]
    task = make_task("unseen_family", "unknown_metric", entities)
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "3")

    class BudgetedLLM:
        network_calls = 0
        batch_calls = 0
        last_failure_kind = None

        def chat_json(self, system: str, user: str, max_tokens: int) -> dict | None:
            if self.network_calls >= 25:
                self.last_failure_kind = None
                return None
            self.network_calls += 1
            if "REQUEST_JSON:\n" not in user:
                self.last_failure_kind = None
                return {"signals": {"directional_signal": {"level": 0}}}
            request = json.loads(user.split("REQUEST_JSON:\n", 1)[1].split("\nOUTPUT_SCHEMA_JSON:", 1)[0])
            self.batch_calls += 1
            if self.batch_calls == 1:
                self.last_failure_kind = "context_length"
                return None
            self.last_failure_kind = None
            return {
                "entities": [
                    {
                        "item_id": item["item_id"],
                        "entity_id": item["entity_id"],
                        "signals": {"directional_signal": {"level": 0}},
                    }
                    for item in request["items"]
                ]
            }

    llm = BudgetedLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)

    assert llm.network_calls == 25
    assert sum(row.raw_model is not None for row in results) == 72


def test_adaptive_batch_width_uses_remaining_request_capacity(monkeypatch) -> None:
    monkeypatch.delenv("T4_MODEL_BATCH_SIZE", raising=False)
    monkeypatch.delenv("T4_ENABLE_ADAPTIVE_BATCH", raising=False)
    llm = SimpleNamespace(max_calls=25, usage=SimpleNamespace(calls=0))

    assert _model_batch_size(75, llm) == 3
    assert _model_batch_size(78, llm) == 4
    assert _model_batch_size(100, llm) == 4
    assert _model_batch_size(150, llm) == 6

    llm.usage.calls = 5
    assert _model_batch_size(78, llm) == 4
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "2")
    assert _model_batch_size(150, llm) == 2


def test_adaptive_batch_can_be_disabled(monkeypatch) -> None:
    monkeypatch.delenv("T4_MODEL_BATCH_SIZE", raising=False)
    monkeypatch.setenv("T4_ENABLE_ADAPTIVE_BATCH", "0")
    llm = SimpleNamespace(max_calls=25, usage=SimpleNamespace(calls=0))

    assert _model_batch_size(150, llm) == 3


@pytest.mark.parametrize(("context_first", "expected_calls"), [(False, 20), (True, 24)])
def test_adaptive_batch_covers_78_rows_with_clean_or_first_context_failure(
    monkeypatch, context_first: bool, expected_calls: int
) -> None:
    entities = [{"entity_id": f"E{i}", "latest_value": float(i + 1)} for i in range(78)]
    task = make_task("unseen_family", "unknown_metric", entities)
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.delenv("T4_MODEL_BATCH_SIZE", raising=False)
    monkeypatch.setenv("T4_ENABLE_ADAPTIVE_BATCH", "1")

    class BudgetedLLM:
        max_calls = 25
        usage = SimpleNamespace(calls=0)
        batch_calls = 0
        last_failure_kind = None

        def chat_json(self, system: str, user: str, max_tokens: int) -> dict | None:
            if self.usage.calls >= self.max_calls:
                self.last_failure_kind = None
                return None
            self.usage.calls += 1
            if "REQUEST_JSON:\n" not in user:
                self.last_failure_kind = None
                return {"signals": {"directional_signal": {"level": 0}}}
            request = json.loads(user.split("REQUEST_JSON:\n", 1)[1].split("\nOUTPUT_SCHEMA_JSON:", 1)[0])
            self.batch_calls += 1
            if context_first and self.batch_calls == 1:
                self.last_failure_kind = "context_length"
                return None
            self.last_failure_kind = None
            return {
                "entities": [
                    {
                        "item_id": item["item_id"],
                        "entity_id": item["entity_id"],
                        "signals": {"directional_signal": {"level": 0}},
                    }
                    for item in request["items"]
                ]
            }

    llm = BudgetedLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)

    assert llm.usage.calls == expected_calls
    assert sum(row.raw_model is not None for row in results) == 78


def test_deferred_recovery_preserves_small_all_context_case(monkeypatch) -> None:
    entities = [{"entity_id": f"E{i}", "latest_value": float(i + 1)} for i in range(9)]
    task = make_task("unseen_family", "unknown_metric", entities)
    corpus = IndexedCorpus([], {}, {})
    monkeypatch.setenv("T4_MODEL_BATCH_SIZE", "3")

    class ContextBatchLLM:
        calls = 0
        last_failure_kind = None

        def chat_json(self, system: str, user: str, max_tokens: int) -> dict | None:
            self.calls += 1
            if "REQUEST_JSON:\n" in user:
                self.last_failure_kind = "context_length"
                return None
            self.last_failure_kind = None
            return {"signals": {"directional_signal": {"level": 0}}}

    llm = ContextBatchLLM()
    results = predict_rows(task, BM25([]), corpus, llm, top_k=2)

    assert llm.calls == 12
    assert sum(row.raw_model is not None for row in results) == 9


def test_batch_unpack_rejects_disagreeing_item_and_entity_ids() -> None:
    corpus = IndexedCorpus([], {}, {})
    rows = [
        PreparedRow(index, {"entity_id": entity_id}, set(), corpus, [], {}, [], [], True)
        for index, entity_id in enumerate(("A", "B"))
    ]
    parsed = {
        "entities": [
            {"item_id": 0, "entity_id": "B", "signals": {}},
            {"item_id": 1, "entity_id": "A", "signals": {}},
        ]
    }

    assert _unpack_batch(parsed, rows) == {0: None, 1: None}


def test_batch_unpack_falls_back_only_the_missing_entity() -> None:
    corpus = IndexedCorpus([], {}, {})
    rows = [
        PreparedRow(index, {"entity_id": entity_id}, set(), corpus, [], {}, [], [], True)
        for index, entity_id in enumerate(("A", "B"))
    ]
    returned = {"item_id": 1, "entity_id": "B", "signals": {}}

    assert _unpack_batch({"entities": [returned]}, rows) == {0: None, 1: returned}


def test_batch_unpack_does_not_treat_boolean_item_ids_as_integers() -> None:
    corpus = IndexedCorpus([], {}, {})
    rows = [
        PreparedRow(index, {"entity_id": entity_id}, set(), corpus, [], {}, [], [], True)
        for index, entity_id in enumerate(("A", "B"))
    ]

    assert _unpack_batch(
        {
            "entities": [
                {"item_id": False, "signals": {}},
                {"item_id": True, "signals": {}},
            ]
        },
        rows,
    ) == {0: None, 1: None}


def test_batch_unpack_rejects_any_present_invalid_identity() -> None:
    corpus = IndexedCorpus([], {}, {})
    rows = [
        PreparedRow(index, {"entity_id": entity_id}, set(), corpus, [], {}, [], [], True)
        for index, entity_id in enumerate(("A", "B"))
    ]
    invalid_rows = [
        {"item_id": 0, "entity_id": "FOREIGN", "signals": {}},
        {"item_id": 1, "entity_id": 123, "signals": {}},
        {"item_id": "0", "entity_id": "A", "signals": {}},
        {"item_id": 9, "entity_id": "A", "signals": {}},
        {"signals": {}},
    ]

    assert _unpack_batch({"entities": invalid_rows}, rows) == {0: None, 1: None}


def test_batch_unpack_allows_one_valid_identity_when_the_other_is_absent() -> None:
    corpus = IndexedCorpus([], {}, {})
    rows = [
        PreparedRow(index, {"entity_id": entity_id}, set(), corpus, [], {}, [], [], True)
        for index, entity_id in enumerate(("A", "B"))
    ]
    item_only = {"item_id": 0, "signals": {}}
    entity_only = {"entity_id": "B", "signals": {}}

    assert _unpack_batch({"entities": [item_only, entity_only]}, rows) == {0: item_only, 1: entity_only}


def test_model_evidence_rejects_boolean_signal_and_nonfinite_parameter() -> None:
    text = "The filing reports diluted EPS of 1.25 and discusses financial performance."
    corpus = IndexedCorpus([], {"DOC": text}, {"DOC": "2023-01-01"})
    parsed = {
        "signals": {
            "target_period_earnings_signal": {
                "level": True,
                "doc_id": "DOC",
                "quote": text,
                "claim": "The signal is positive.",
            }
        },
        "parameters": {
            "latest_reported_eps": {
                "value": "NaN",
                "doc_id": "DOC",
                "quote": text,
                "claim": "The filing reports EPS.",
            },
            "latest_reported_prior_year_eps": {
                "value": "1.25",
                "doc_id": "DOC",
                "quote": text,
                "claim": "The filing reports EPS of 1.25.",
            },
        },
    }

    signals, _, signal_facts, signal_rejected = validate_model_output(
        parsed, SPECS["eps_consensus"], "A", corpus, {"DOC"}
    )
    _, parameters, parameter_facts, parameter_rejected = validate_model_output(
        parsed, SPECS["bank_eps"], "A", corpus, {"DOC"}
    )

    assert signals == {"target_period_earnings_signal": 0}
    assert signal_facts == []
    assert signal_rejected == []
    assert parameters == {"latest_reported_eps": None, "latest_reported_prior_year_eps": 1.25}
    assert [fact.name for fact in parameter_facts] == ["latest_reported_prior_year_eps"]
    assert parameter_rejected == []
