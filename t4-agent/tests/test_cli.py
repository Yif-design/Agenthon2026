from __future__ import annotations

import json

from t4agent.cli import main


def _fixture(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.json").write_text(
        json.dumps(
            {
                "doc_id": "DOC",
                "doc_date": "2023-12-01",
                "text": "Issuer A expects the future metric to improve.",
            }
        ),
        encoding="utf-8",
    )
    task = {
        "task_id": "trace-contract",
        "schema_version": "3",
        "cutoff_date": "2024-01-01",
        "family": "unseen_family",
        "prompt": "Predict the future metric.",
        "interval_level": 0.9,
        "target": {"name": "future_metric", "type": "regression"},
        "entities": [{"entity_id": "A", "future_metric": 1.0, "corpus_ref": "corpus/"}],
    }
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    return task_path, corpus


def _run(tmp_path, monkeypatch, *extra):
    monkeypatch.delenv("MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("MODEL_TOKEN", raising=False)
    task, corpus = _fixture(tmp_path)
    out = tmp_path / "out" / "answer.json"
    result = main(
        [
            "analyze",
            "--task",
            str(task),
            "--corpus",
            str(corpus),
            "--out",
            str(out),
            *extra,
        ]
    )
    return result, out


def test_cli_writes_only_required_answer_by_default(tmp_path, monkeypatch) -> None:
    result, out = _run(tmp_path, monkeypatch)

    assert result == 0
    assert out.is_file()
    assert sorted(path.name for path in out.parent.iterdir()) == ["answer.json"]


def test_cli_writes_full_trace_when_explicitly_requested(tmp_path, monkeypatch) -> None:
    trace = tmp_path / "developer-trace"
    result, out = _run(tmp_path, monkeypatch, "--trace-dir", str(trace))

    assert result == 0
    assert out.is_file()
    assert {path.name for path in trace.iterdir()} == {"route.json", "rows.json", "usage.json"}
