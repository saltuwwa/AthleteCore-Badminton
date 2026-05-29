"""Latency trace serialization."""

from app.graph.latency_trace import LatencyTrace, init_latency_trace, stage_span


def test_latency_trace_to_dict_shape():
    trace = init_latency_trace("test-req-1")
    with stage_span("semantic_router"):
        pass
    trace.record_llm_call(
        name="semantic_router",
        model="gpt-4o-mini",
        duration_ms=12.5,
        prompt_chars=100,
        completion_chars=50,
    )
    trace.record_db_call(name="find_training_by_date", duration_ms=3.2, rows=1)
    trace.finish()
    d = trace.to_dict()
    assert d["request_id"] == "test-req-1"
    assert "total_ms" in d
    assert d["stages"]["semantic_router_ms"] >= 0
    assert len(d["llm_calls"]) == 1
    assert d["llm_calls"][0]["name"] == "semantic_router"
    assert len(d["db_calls"]) == 1
    assert d["db_calls"][0]["rows"] == 1
