"""可观测性（Hackathon P4，2026-08-24）：每次模型调用、每次工具调用、每轮修复、每次路由
都是一条 OpenTelemetry span。

只依赖 ``opentelemetry-api``——没装 SDK 或没配导出器时全是 no-op（零成本、零网络）。
导出到哪里由 api 层的 ``campuspath_api.telemetry`` 决定（Cloud Trace / console / 关）；
本模块**不**碰导出器，不然 agents 包会因为"要打点"而长出云依赖。

属性命名按 OTel GenAI 语义约定（``gen_ai.*``），评审在 Cloud Trace 里看到的是
业界通行的字段名，不是自造的。
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

try:  # opentelemetry-api 随 google-adk 装上；没有它就退化成 no-op
    from opentelemetry import trace as _otel_trace
except ImportError:  # pragma: no cover
    _otel_trace = None

TRACER_NAME = "campuspath.agents"

_ALLOWED = (str, bool, int, float)


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    """OTel 属性只收标量；其他一律 str() 并截断，绝不把整段 prompt 塞进 trace。"""
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, str):
            out[key] = value[:200]
        elif isinstance(value, _ALLOWED):
            out[key] = value
        else:
            out[key] = str(value)[:200]
    return out


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        pass

    def set_attributes(self, attrs: dict[str, Any]) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """``with span("gen_ai.generate", purpose=...) as s: ... s.set_attribute(...)``。

    异常照常抛出，但会记在 span 上（status=ERROR）——修复循环里"哪一轮为什么失败"
    才看得见。
    """
    if _otel_trace is None:
        yield _NoopSpan()
        return
    tracer = _otel_trace.get_tracer(TRACER_NAME)
    started = time.perf_counter()
    with tracer.start_as_current_span(name) as current:
        current.set_attributes(_clean(attrs))
        try:
            yield current
        finally:
            current.set_attribute("campuspath.duration_ms",
                                  round((time.perf_counter() - started) * 1000, 1))


def usage_attributes(response: Any) -> dict[str, Any]:
    """从 google-genai 响应里取 token 用量与 model_version（缺哪个就不记哪个）。"""
    usage = getattr(response, "usage_metadata", None)
    attrs: dict[str, Any] = {}
    version = getattr(response, "model_version", None)
    if version:
        attrs["gen_ai.response.model"] = version
    if usage is not None:
        for otel_key, genai_key in (
            ("gen_ai.usage.input_tokens", "prompt_token_count"),
            ("gen_ai.usage.output_tokens", "candidates_token_count"),
            ("campuspath.thoughts_tokens", "thoughts_token_count"),
        ):
            value = getattr(usage, genai_key, None)
            if isinstance(value, int):
                attrs[otel_key] = value
    return attrs
