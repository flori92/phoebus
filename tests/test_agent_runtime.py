"""Tests du runtime agent PHOEBUS."""

import PHOEBUS.agent_runtime as agent_runtime


def test_agent_runtime_trace_ecrit_statuts(tmp_path, monkeypatch):
    trace_file = tmp_path / "agent_traces.jsonl"
    monkeypatch.setattr(agent_runtime, "TRACE_FILE", trace_file)
    agent_runtime._RECENT_RUNS.clear()

    run = agent_runtime.start_agent_run("prépare un rapport", max_turns=3)
    run.record_step(
        {"step": 1, "action": "recherche_web"},
        "ok",
        result="résultat",
        duration_ms=12.34,
    )
    data = run.finish("completed", "terminé")

    assert data["status"] == "completed"
    assert data["steps"][0]["status"] == "ok"
    assert trace_file.exists()
    assert agent_runtime.recent_agent_runs(limit=1)[0]["summary"] == "terminé"
