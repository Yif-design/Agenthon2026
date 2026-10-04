from evaluation.experiments.compact_table_numeric_identity_audit import (
    MAX_PASSAGE,
    candidate_chunks_for_text,
    compact_tables,
    numeric_identity_tokenize,
)
from t4agent.retrieve import _chunks_for_text


def test_compact_table_is_recognized_and_never_split() -> None:
    table = "Metric | 2-Year | 10-Year\n--- | --- | ---\nYield | 4.2 | 4.5\n"
    text = "x" * 1900 + ". " + table + "tail " * 200
    recognized = compact_tables(text)
    assert len(recognized) == 1
    chunks = candidate_chunks_for_text("d", "2026-01-01", text, 0)
    assert any(c.span_start <= recognized[0].start and c.span_end >= recognized[0].end for c in chunks)
    assert all(c.text == text[c.span_start:c.span_end] for c in chunks)


def test_non_table_and_rejected_tables_keep_production_spans() -> None:
    samples = [
        "plain sentence. " * 300,
        "A | B\\|C\n1 | 2\n" + "tail. " * 500,
        "A | B\n1 | 2 | 3\n" + "tail. " * 500,
        "A | B\n" + ("1 | " + "2" * MAX_PASSAGE + "\n"),
    ]
    for text in samples:
        assert compact_tables(text) == []
        expected = _chunks_for_text("d", "2026-01-01", text, 17)
        assert candidate_chunks_for_text("d", "2026-01-01", text, 17) == expected


def test_numeric_identity_adds_joined_unsigned_identity_only() -> None:
    assert "2year" in numeric_identity_tokenize("2-Year Treasury")
    assert "10year" in numeric_identity_tokenize("10–Year Treasury")
    assert "2year" not in numeric_identity_tokenize("- 2-Year move")
    assert "2year" not in numeric_identity_tokenize("1.2-Year range")
    assert "10year" not in numeric_identity_tokenize("2-10-Year range")


def test_caption_is_included_with_original_offsets() -> None:
    text = "Treasury yields, units percent:\nTenor | Rate\n--- | ---\n2-Year | 4.2\n"
    table = compact_tables(text)[0]
    assert table.start == 0
    assert text[table.row_spans[-1][0]:table.row_spans[-1][1]] == "2-Year | 4.2\n"
