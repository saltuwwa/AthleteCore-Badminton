"""
Langfuse observability for AthleteCore (SDK v4 observation API).

Complements latency_trace (local dev JSON) with persistent cross-request tracing.
Safe no-op when disabled, keys missing, or SDK unavailable.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.config import Settings, settings

logger = logging.getLogger(__name__)

_langfuse_client: Any | None = None
_langfuse_init_attempted = False
_langfuse_warned_missing_keys = False

_current: ContextVar["LangfuseRequestContext | None"] = ContextVar(
    "langfuse_request_context",
    default=None,
)

_PREVIEW_MAX = 400
_MESSAGE_PREVIEW_MAX = 280


@dataclass
class LangfuseRequestContext:
    """Active api_chat (or background) observation tree."""

    request_id: str
    trace_id: str
    root: Any
    tags: list[str] = field(default_factory=list)
    span_stack: list[Any] = field(default_factory=list)

    def current_parent(self) -> Any:
        if self.span_stack:
            return self.span_stack[-1]
        return self.root


def _bool_setting(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def langfuse_configured(cfg: Settings | None = None) -> bool:
    cfg = cfg or settings
    if not _bool_setting(cfg.langfuse_enabled):
        return False
    if not (cfg.langfuse_public_key or "").strip():
        return False
    if not (cfg.langfuse_secret_key or "").strip():
        return False
    return True


def _get_client(cfg: Settings | None = None) -> Any | None:
    global _langfuse_client, _langfuse_init_attempted, _langfuse_warned_missing_keys
    cfg = cfg or settings

    if not _bool_setting(cfg.langfuse_enabled):
        return None

    if not (cfg.langfuse_public_key or "").strip() or not (cfg.langfuse_secret_key or "").strip():
        if not _langfuse_warned_missing_keys:
            logger.warning(
                "LANGFUSE_ENABLED=true but LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is empty; "
                "tracing disabled"
            )
            _langfuse_warned_missing_keys = True
        return None

    if _langfuse_init_attempted:
        return _langfuse_client

    _langfuse_init_attempted = True
    try:
        from langfuse import Langfuse

        host = cfg.langfuse_host_resolved
        _langfuse_client = Langfuse(
            public_key=(cfg.langfuse_public_key or "").strip(),
            secret_key=(cfg.langfuse_secret_key or "").strip(),
            host=host,
        )
        logger.info("Langfuse client initialized (host=%s, sdk=v4 observations)", host)
    except Exception as exc:
        logger.warning("Langfuse client init failed: %s", exc)
        _langfuse_client = None
    return _langfuse_client


def _should_sample(cfg: Settings) -> bool:
    rate = float(cfg.langfuse_sample_rate)
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def _resolve_langfuse_trace_id(request_id: str, client: Any) -> str:
    """Langfuse v4 requires 32-char lowercase hex trace ids."""
    try:
        return uuid.UUID(str(request_id)).hex
    except (ValueError, AttributeError):
        if hasattr(client, "create_trace_id"):
            return str(client.create_trace_id())
        return uuid.uuid4().hex


def truncate_text(text: str | None, *, limit: int = _PREVIEW_MAX) -> str:
    if not text:
        return ""
    t = str(text).strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def messages_preview(messages: list[dict[str, str]], *, verbose: bool) -> Any:
    if verbose:
        return messages
    parts: list[str] = []
    total = 0
    for m in messages:
        role = m.get("role", "?")
        content = truncate_text(m.get("content"), limit=120)
        line = f"{role}: {content}"
        total += len(m.get("content") or "")
        parts.append(line)
    return {
        "preview": parts,
        "message_count": len(messages),
        "total_chars": total,
    }


def _base_tags(*extra: str) -> list[str]:
    tags = ["athletecore", "backend", "semantic-router-v1"]
    tags.extend(t for t in extra if t)
    return tags


def _trace_url(trace_id: str, cfg: Settings, client: Any | None = None) -> str | None:
    c = client or _get_client(cfg)
    if c is not None and hasattr(c, "get_trace_url"):
        try:
            url = c.get_trace_url(trace_id=trace_id)
            if url:
                return str(url)
        except Exception:
            pass
    host = cfg.langfuse_host_resolved.rstrip("/")
    if not host:
        return None
    return f"{host}/trace/{trace_id}"


def start_api_chat_trace(
    *,
    request_id: str,
    user_id: str,
    session_id: str,
    thread_id: str | None,
    message: str,
    cfg: Settings | None = None,
) -> LangfuseRequestContext | None:
    cfg = cfg or settings
    client = _get_client(cfg)
    if client is None or not _should_sample(cfg):
        return None

    trace_id = _resolve_langfuse_trace_id(request_id, client)
    msg_preview = truncate_text(message, limit=_MESSAGE_PREVIEW_MAX)
    inp: Any = (
        msg_preview
        if cfg.langfuse_trace_verbose
        else {"message_preview": msg_preview}
    )

    try:
        root = client.start_observation(
            trace_context={"trace_id": trace_id},
            name="api_chat",
            as_type="span",
            input=inp,
            metadata={
                "request_id": request_id,
                "langfuse_trace_id": trace_id,
                "thread_id": thread_id,
                "session_id": session_id,
                "user_id": user_id,
                "debug_build_id": "semantic-router-v1",
                "environment": cfg.langfuse_env,
            },
        )
        ctx = LangfuseRequestContext(
            request_id=request_id,
            trace_id=trace_id,
            root=root,
        )
        _current.set(ctx)
        return ctx
    except Exception as exc:
        logger.warning("Langfuse start_api_chat_trace failed: %s", exc)
        return None


def current_langfuse_context() -> LangfuseRequestContext | None:
    return _current.get()


def clear_langfuse_context() -> None:
    ctx = _current.get()
    if ctx is not None:
        _end_observation_tree(ctx)
    _current.set(None)


def _end_observation_tree(ctx: LangfuseRequestContext) -> None:
    while ctx.span_stack:
        span = ctx.span_stack.pop()
        try:
            if hasattr(span, "end"):
                span.end()
        except Exception:
            pass
    try:
        if hasattr(ctx.root, "end"):
            ctx.root.end()
    except Exception:
        pass


@contextmanager
def langfuse_observation_span(
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    ctx = _current.get()
    if ctx is None:
        yield
        return

    parent = ctx.current_parent()
    span = None
    t0 = time.perf_counter()
    errored = False
    try:
        try:
            span = parent.start_observation(
                name=name,
                as_type="span",
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.debug("Langfuse span create failed (%s): %s", name, exc)
            yield
            return
        ctx.span_stack.append(span)
        yield
    except Exception as exc:
        errored = True
        record_langfuse_exception(exc, stage=name)
        raise
    finally:
        if span is not None:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            end_meta = {
                **(metadata or {}),
                "duration_ms": duration_ms,
                "status": "error" if errored else "success",
            }
            try:
                if hasattr(span, "update"):
                    span.update(metadata=end_meta)
                if hasattr(span, "end"):
                    span.end()
            except Exception as exc:
                logger.debug("Langfuse span end failed (%s): %s", name, exc)
            if span in ctx.span_stack:
                ctx.span_stack.remove(span)


def record_langfuse_generation(
    *,
    name: str,
    model: str,
    messages: list[dict[str, str]],
    output: str,
    duration_ms: float,
    temperature: float | None = None,
    usage: dict[str, Any] | None = None,
    error: str | None = None,
    cfg: Settings | None = None,
) -> None:
    ctx = _current.get()
    if ctx is None:
        return
    cfg = cfg or settings
    parent = ctx.current_parent()
    if parent is None:
        return

    meta: dict[str, Any] = {
        "duration_ms": round(duration_ms, 2),
        "provider": "litellm",
    }
    if temperature is not None:
        meta["temperature"] = temperature
    if error:
        meta["error"] = error

    inp = messages_preview(messages, verbose=cfg.langfuse_trace_verbose)
    out: Any = output if cfg.langfuse_trace_verbose else truncate_text(output)

    level = "ERROR" if error else "DEFAULT"
    gen = None
    try:
        gen = parent.start_observation(
            name=name,
            as_type="generation",
            model=model,
            input=inp,
            metadata=meta,
            level=level,
        )
        if gen is not None and hasattr(gen, "update"):
            gen.update(output=out, usage_details=_usage_to_details(usage))
        if gen is not None and hasattr(gen, "end"):
            gen.end()
    except Exception as exc:
        logger.debug("Langfuse generation record failed (%s): %s", name, exc)


def _usage_to_details(usage: dict[str, Any] | None) -> dict[str, int] | None:
    if not usage:
        return None
    out: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in usage and usage[key] is not None:
            out[key] = int(usage[key])
    return out or None


def record_langfuse_exception(exc: BaseException, *, stage: str | None = None) -> None:
    ctx = _current.get()
    if ctx is None:
        return
    meta = {"stage": stage, "error_type": type(exc).__name__}
    try:
        if hasattr(ctx.root, "update"):
            ctx.root.update(
                metadata={**meta, "error": type(exc).__name__},
                level="ERROR",
            )
        ctx.tags = list(ctx.tags) + ["error"]
        if stage:
            with langfuse_observation_span(stage, metadata={"error": type(exc).__name__}):
                pass
    except Exception as log_exc:
        logger.debug("Langfuse exception record failed: %s", log_exc)


def finish_api_chat_trace(
    *,
    result: dict[str, Any],
    latency_meta: dict[str, Any] | None = None,
    total_latency_ms: float | None = None,
    cfg: Settings | None = None,
) -> dict[str, str | None]:
    """Flush trace metadata/tags; return trace_id and public URL if available."""
    cfg = cfg or settings
    ctx = _current.get()
    if ctx is None:
        return {"langfuse_trace_id": None, "langfuse_trace_url": None}

    meta = dict(latency_meta or {})
    analyst = result.get("analyst_trace") or {}
    if isinstance(analyst, dict):
        meta.setdefault("llm_called", analyst.get("llm_called"))
        meta.setdefault("blocked_reason", analyst.get("blocked_reason"))
        meta.setdefault("structured_retrieval_used", analyst.get("structured_retrieval_used"))

    turn_intent = meta.get("turn_intent")
    if not turn_intent and isinstance(result.get("turn_decision"), dict):
        turn_intent = result["turn_decision"].get("turn_intent")

    agents = result.get("agents_used") or []
    agent_tag = f"agent:{agents[0]}" if agents else None

    tags = _base_tags()
    if agent_tag:
        tags.append(agent_tag)
    if turn_intent:
        tags.append(f"turn_intent:{turn_intent}")
    if meta.get("route_source") == "fast_path_general_chat":
        tags.append("fast_path")
    if result.get("comparison_status") == "not_found" or analyst.get("llm_called") is False:
        tags.append("blocked")
    if meta.get("memory_write_scheduled") or result.get("memory_write_scheduled"):
        tags.append("background_write")

    update_payload: dict[str, Any] = {
        "request_id": ctx.request_id,
        "thread_id": result.get("thread_id"),
        "debug_build_id": result.get("debug_build_id", "semantic-router-v1"),
        "environment": cfg.langfuse_env,
        "route_source": meta.get("route_source"),
        "turn_intent": turn_intent,
        "recommended_agent": agents[0] if agents else None,
        "event_type": meta.get("event_type"),
        "event_date": meta.get("event_date"),
        "memory_action": meta.get("memory_action"),
        "comparison_status": result.get("comparison_status"),
        "safety_invariant_applied": analyst.get("blocked_reason") is not None,
        "total_latency_ms": total_latency_ms,
        "memory_write_scheduled": bool(
            meta.get("memory_write_scheduled") or result.get("memory_write_scheduled")
        ),
        "methodology_rag_skipped_reason": meta.get("methodology_rag_skipped_reason"),
        "tags": tags,
    }
    update_payload = {k: v for k, v in update_payload.items() if v is not None}

    output_preview = truncate_text(result.get("message"), limit=_MESSAGE_PREVIEW_MAX)
    client = _get_client(cfg)
    try:
        out_val: Any = (
            output_preview
            if cfg.langfuse_trace_verbose
            else {"message_preview": output_preview}
        )
        if hasattr(ctx.root, "update"):
            ctx.root.update(metadata=update_payload, output=out_val)
        ctx.tags = tags
        _end_observation_tree(ctx)
        if client is not None and hasattr(client, "flush"):
            client.flush()
    except Exception as exc:
        logger.warning("Langfuse finish_api_chat_trace failed: %s", exc)
    finally:
        if _current.get() is ctx:
            _current.set(None)

    return {
        "langfuse_trace_id": ctx.trace_id,
        "langfuse_trace_url": _trace_url(ctx.trace_id, cfg, client),
    }


def start_linked_background_trace(
    *,
    parent_request_id: str,
    user_id: str,
    session_id: str,
    cfg: Settings | None = None,
) -> LangfuseRequestContext | None:
    """Separate trace for async memory write (linked via metadata)."""
    cfg = cfg or settings
    client = _get_client(cfg)
    if client is None:
        return None

    trace_id = _resolve_langfuse_trace_id(f"{parent_request_id}:memory_write", client)
    try:
        root = client.start_observation(
            trace_context={"trace_id": trace_id},
            name="memory_write_background",
            as_type="span",
            metadata={
                "parent_request_id": parent_request_id,
                "environment": cfg.langfuse_env,
            },
        )
        ctx = LangfuseRequestContext(
            request_id=parent_request_id,
            trace_id=trace_id,
            root=root,
            tags=_base_tags("background_write"),
        )
        _current.set(ctx)
        return ctx
    except Exception as exc:
        logger.warning("Langfuse background trace start failed: %s", exc)
        return None


def finish_background_trace(ctx: LangfuseRequestContext | None, *, status: str = "success") -> None:
    if ctx is None:
        return
    try:
        if hasattr(ctx.root, "update"):
            ctx.root.update(metadata={"status": status})
        _end_observation_tree(ctx)
        client = _get_client()
        if client is not None and hasattr(client, "flush"):
            client.flush()
    except Exception as exc:
        logger.debug("Langfuse background trace finish failed: %s", exc)
    finally:
        if _current.get() is ctx:
            _current.set(None)
