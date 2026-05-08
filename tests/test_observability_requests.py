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


def test_request_snapshot_filters_by_age(tmp_path, monkeypatch):
    metrics_file = tmp_path / "request_metrics.jsonl"
    monkeypatch.setattr(observability, "REQUEST_METRICS_FILE", metrics_file)
    observability.reset()

    monkeypatch.setattr(observability.time, "time", lambda: 1_000.0)
    observability.record_request(source="old", duration_ms=10_000, ok=True, text_len=3)
    monkeypatch.setattr(observability.time, "time", lambda: 10_000.0)
    observability.record_request(source="recent", duration_ms=12.5, ok=True, text_len=6)

    observability.reset()
    snap = observability.request_snapshot(limit=10, max_age_seconds=3600)

    assert snap["count"] == 1
    assert snap["p95_ms"] == 12.5
    assert snap["last"]["source"] == "recent"
    assert snap["window_seconds"] == 3600


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
