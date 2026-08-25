"""api 层的 trace 导出（Hackathon P4）。agents 包只打点，这里决定点往哪儿去。

``CAMPUSPATH_TRACE``：
* ``gcp``      → Cloud Trace（Cloud Run 服务账号 ADC；批量导出，不阻塞请求）；
* ``console``  → 标准输出（本地看结构）；
* ``memory``   → 进程内环形缓冲（测试与 ``GET /v1/ops/agents`` 的"最近 trace"）；
* 未设         → 不装 SDK，agents 里的 span() 全是 no-op。

每个 HTTP 请求一条根 span（``http.request``），模型/工具/修复循环的 span 挂在它下面——
在 Cloud Trace 里一次「起草规划」就是一棵树：请求 → A5 修复循环 → 第 n 轮 → gemini 调用。
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from typing import Any

log = logging.getLogger("campuspath.telemetry")

TRACE_ENV = "CAMPUSPATH_TRACE"


class RecentSpans:
    """环形缓冲：最近 N 条已结束的 span 摘要（名字、属性、时长）。给注册表端点用。"""

    def __init__(self, capacity: int = 200) -> None:
        self._rows: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.exported = 0

    def on_end(self, span: Any) -> None:
        row = {
            "name": span.name,
            "trace_id": format(span.context.trace_id, "032x"),
            "attributes": dict(span.attributes or {}),
            "duration_ms": round((span.end_time - span.start_time) / 1e6, 1)
            if span.end_time and span.start_time else None,
            "status": str(getattr(span.status, "status_code", "")).rsplit(".", 1)[-1],
        }
        with self._lock:
            self._rows.appendleft(row)
            self.exported += 1

    def rows(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._rows)


class TraceStatus:
    def __init__(self, exporter: str, recent: RecentSpans | None) -> None:
        self.exporter = exporter
        self.recent = recent
        self.started_at = time.time()


def install(app: Any) -> TraceStatus | None:
    spec = (os.environ.get(TRACE_ENV) or "").strip().lower()
    if not spec:
        return None
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    provider = TracerProvider(resource=Resource.create({"service.name": "campuspath-api"}))
    recent = RecentSpans()

    class _RecentProcessor(SpanProcessor):
        def on_end(self, span):
            recent.on_end(span)

    provider.add_span_processor(_RecentProcessor())
    if spec == "gcp":
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        provider.add_span_processor(BatchSpanProcessor(
            CloudTraceSpanExporter(project_id=os.environ.get("GOOGLE_CLOUD_PROJECT"))))
    elif spec == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    elif spec != "memory":
        raise ValueError(f"{TRACE_ENV}={spec!r} 不认识；用 gcp / console / memory")
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("campuspath.api")

    @app.middleware("http")
    async def _request_span(request, call_next):
        with tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
            return response

    status = TraceStatus(spec, recent)
    app.state.trace = status
    log.info("trace exporter: %s", spec)
    return status
