"""Langfuse tracing — safe no-op and privacy helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.observability import langfuse_tracing as lf


@pytest.fixture(autouse=True)
def reset_langfuse_globals():
    lf._langfuse_client = None
    lf._langfuse_init_attempted = False
    lf._langfuse_warned_missing_keys = False
    lf.clear_langfuse_context()
    yield
    lf.clear_langfuse_context()
    lf._langfuse_client = None
    lf._langfuse_init_attempted = False


def test_disabled_when_langfuse_enabled_false():
    cfg = Settings(langfuse_enabled=False, langfuse_public_key="pk", langfuse_secret_key="sk")
    assert lf.langfuse_configured(cfg) is False
    assert lf._get_client(cfg) is None
    ctx = lf.start_api_chat_trace(
        request_id="r1",
        user_id="u",
        session_id="s",
        thread_id=None,
        message="hi",
        cfg=cfg,
    )
    assert ctx is None


def test_enabled_but_missing_keys_warns_no_client(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    cfg = Settings(langfuse_enabled=True, langfuse_public_key="", langfuse_secret_key="")
    assert lf._get_client(cfg) is None
    assert any("LANGFUSE_ENABLED" in r.message for r in caplog.records)


def test_messages_preview_compact_not_full():
    msgs = [{"role": "user", "content": "x" * 5000}]
    preview = lf.messages_preview(msgs, verbose=False)
    assert "preview" in preview
    assert preview["total_chars"] == 5000
    assert len(str(preview)) < 5000


def test_messages_preview_verbose_returns_messages():
    msgs = [{"role": "user", "content": "short"}]
    assert lf.messages_preview(msgs, verbose=True) == msgs


def test_stage_span_works_without_langfuse():
    from app.graph.latency_trace import clear_latency_trace, init_latency_trace, stage_span

    trace = init_latency_trace("req-1")
    try:
        with stage_span("semantic_router"):
            pass
        assert trace.stages_ms.get("semantic_router_ms", 0) >= 0
    finally:
        clear_latency_trace()


@pytest.mark.asyncio
async def test_acompletion_works_when_langfuse_disabled():
    from app.graph.llm import acompletion

    cfg = Settings(
        openai_api_key="sk-test",
        langfuse_enabled=False,
    )
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
    mock_resp.usage = None

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        out = await acompletion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            app_settings=cfg,
            latency_name="semantic_router",
        )
    assert "ok" in out


def test_finish_api_chat_trace_no_context():
    refs = lf.finish_api_chat_trace(result={"message": "x", "thread_id": "t", "agents_used": []})
    assert refs["langfuse_trace_id"] is None


def test_start_trace_with_mock_client():
    mock_client = MagicMock()
    mock_root = MagicMock()
    mock_client.start_observation.return_value = mock_root

    cfg = Settings(
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_sample_rate=1.0,
    )

    request_id = "550e8400-e29b-41d4-a716-446655440000"
    with patch.object(lf, "_get_client", return_value=mock_client):
        ctx = lf.start_api_chat_trace(
            request_id=request_id,
            user_id="aigerim",
            session_id="main",
            thread_id="thread-1",
            message="как дела?",
            cfg=cfg,
        )
    assert ctx is not None
    assert ctx.trace_id == uuid.UUID(request_id).hex
    mock_client.start_observation.assert_called_once()
    call_kw = mock_client.start_observation.call_args.kwargs
    assert call_kw["name"] == "api_chat"
    assert call_kw["trace_context"]["trace_id"] == ctx.trace_id
