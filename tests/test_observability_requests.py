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
    assert snap["last"]["status"] == "ok"
    assert metrics_file.exists()


def test_trace_event_snapshot(tmp_path, monkeypatch):
    trace_file = tmp_path / "command_traces.jsonl"
    monkeypatch.setattr(observability, "TRACE_EVENTS_FILE", trace_file)
    observability.reset()

    observability.record_trace_event("cmd_test", "command.start", source="test")
    snap = observability.trace_snapshot()

    assert snap["count"] == 1
    assert snap["trace_ids"] == ["cmd_test"]
    assert snap["recent"][0]["event"] == "command.start"
    assert trace_file.exists()
