"""Tests des métriques persistantes par requête."""

import PHOEBUS.observability as observability


def test_record_request_snapshot(tmp_path, monkeypatch):
    metrics_file = tmp_path / "request_metrics.jsonl"
    monkeypatch.setattr(observability, "REQUEST_METRICS_FILE", metrics_file)
    observability.reset()

    observability.record_request(source="test", duration_ms=123.4, ok=True, text_len=12)
    snap = observability.request_snapshot()

    assert snap["count"] == 1
    assert snap["p50_ms"] == 123.4
    assert snap["last"]["source"] == "test"
    assert metrics_file.exists()
