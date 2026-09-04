"""MLflow 3 tracing — one trace per supervisor turn, and the join key back to an action.

Why tracing rather than inference tables: an inference table records the request and the response. For
an agent, everything interesting is in between — which domains the router chose and why, the SQL each
Genie Agent wrote, how many rows came back, which guardrail refused an action. A trace captures that
tree; a request/response log cannot.

The provenance chain this creates is the point:

    action.trace_id -> the MLflow trace -> the router span (why these domains)
                                        -> each Genie span (the exact SQL, the row count)
                                        -> the fuser span (the answer the officer read)

So from a field visit recorded against a customer, an auditor can reach the question that prompted it
and the numbers it was based on. Without that link, "the AI decided" is the end of the enquiry rather
than the start of it.

Tracing must never break the app. Every helper here degrades to a no-op if MLflow is unavailable or
the experiment cannot be resolved, because an observability failure is not a reason to stop answering
questions.
"""
from __future__ import annotations

import contextlib
import functools
import logging
import os
import threading
from typing import Any, Callable, Iterator

import config

log = logging.getLogger(__name__)

_ready: bool | None = None
_lock = threading.Lock()

# Whether the question and answer TEXT may be written into the trace.
#
# This is a real governance decision, not a tuning knob. Rows are already excluded from traces, but the
# question and the fused answer are derived from what THAT user was entitled to see, and the experiment
# is a single shared object — anyone who can read it can read answers built on rows their own filters
# would have excluded. Keeping it on makes traces genuinely useful for debugging a wrong answer;
# turning it off leaves timings, row counts and SQL, which is still enough to see WHERE a turn went
# wrong. Either way the experiment must be ACL'd to the team allowed to see everything.
TRACE_CONTENT: bool = os.environ.get("TRACE_CONTENT", "true").lower() not in ("0", "false", "no")

# Keys whose values are free text derived from governed data.
_CONTENT_KEYS = {"question", "answer", "recommended_action", "reasons", "genie_narrative",
                 "description", "subquestions"}


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop governed free text when TRACE_CONTENT is off, keeping the structural fields."""
    if TRACE_CONTENT:
        return payload
    return {k: ("<omitted: TRACE_CONTENT=false>" if k in _CONTENT_KEYS else v)
            for k, v in payload.items()}


def _init() -> bool:
    """Resolve the experiment once. Returns False if tracing is off or unavailable."""
    global _ready
    if _ready is not None:
        return _ready
    with _lock:
        if _ready is not None:
            return _ready
        if not config.TRACING_ENABLED:
            _ready = False
            return _ready
        try:
            import mlflow
            # Pin the tracking and registry URIs to Databricks BEFORE touching the experiment. Inside
            # the Apps container MLflow otherwise defaults to a local SQLite file and fails with
            # "unsupported URI 'sqlite:////app/python/source_code/mlflow.db' for model registry", so
            # tracing silently disabled itself on the first deploy.
            mlflow.set_tracking_uri("databricks")
            mlflow.set_registry_uri("databricks-uc")
            mlflow.set_experiment(config.MLFLOW_EXPERIMENT)
            # Autolog the Databricks SDK's LLM calls where supported; harmless if it is not.
            with contextlib.suppress(Exception):
                mlflow.openai.autolog()
            _ready = True
        except Exception as e:
            log.warning("MLflow tracing unavailable, continuing without it: %s", e)
            _ready = False
    return _ready


@contextlib.contextmanager
def span(name: str, span_type: str = "CHAIN", **attributes: Any) -> Iterator[Any]:
    """Open a trace span, or a no-op context if tracing is unavailable.

    Yields the span object (or None) so callers can attach outputs, but callers must tolerate None.

    IMPORTANT — why the try block wraps only the SETUP and not the yield. The obvious version of this
    function wraps `yield s` in `try/except Exception` so that a tracing failure cannot break the app.
    That version swallows every exception raised by the CALLER'S body, then yields a second time,
    which makes Python raise `RuntimeError: generator didn't stop after throw()`. The original
    exception is destroyed. In this app that turned a deliberate `PermissionError` — the OBO refusal —
    into an opaque 500, and would have hidden every other error inside a traced block.

    So: only span CREATION is guarded. Once the span exists, exceptions from the body propagate
    normally (and MLflow records them on the span, which is what you want).
    """
    if not _init():
        yield None
        return
    try:
        import mlflow
        cm = mlflow.start_span(name=name, span_type=span_type)
    except Exception as e:
        log.debug("span %s could not be created, continuing untraced: %s", name, e)
        yield None
        return
    with cm as s:
        if attributes:
            with contextlib.suppress(Exception):
                s.set_inputs(_redact(attributes))
        yield s


def set_outputs(s: Any, value: Any) -> None:
    """Attach outputs to a span, tolerating a no-op span."""
    if s is None:
        return
    with contextlib.suppress(Exception):
        s.set_outputs(_redact(value) if isinstance(value, dict) else value)


def set_attributes(s: Any, **kwargs: Any) -> None:
    if s is None:
        return
    with contextlib.suppress(Exception):
        for k, v in kwargs.items():
            s.set_attribute(k, v)


def current_trace_id() -> str | None:
    """The active trace id, for stamping onto the session and any action it produces."""
    if not _init():
        return None
    try:
        import mlflow
        return mlflow.get_current_active_span().trace_id  # type: ignore[union-attr]
    except Exception:
        try:
            import mlflow
            return mlflow.get_last_active_trace_id()
        except Exception:
            return None


def traced(name: str | None = None, span_type: str = "CHAIN") -> Callable:
    """Decorator form, for the top-level turn."""
    def decorate(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(name or fn.__name__, span_type=span_type) as s:
                result = fn(*args, **kwargs)
                if isinstance(result, dict):
                    # ROWS are never recorded — they are masked per user and a trace is shared. The
                    # answer TEXT is recorded, subject to TRACE_CONTENT, because a trace without the
                    # answer cannot explain a wrong answer. See the TRACE_CONTENT note above.
                    set_outputs(s, {k: result.get(k) for k in
                                    ("answer", "recommended_action", "latency_ms",
                                     "proposed_action_type") if k in result})
                return result
        return wrapper
    return decorate
