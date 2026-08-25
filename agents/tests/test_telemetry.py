"""P4（2026-08-24）：Agent 平面的每次模型调用 / 工具调用 / 修复循环 / 路由都留 span。

用 SDK 的进程内导出器断言**真的有 span、属性对**；没装 SDK 时 span() 退化为 no-op，
Agent 代码一行不改也照跑（第二条测试）。
"""

from __future__ import annotations

import pytest

from campuspath_agents import telemetry
from campuspath_agents.model import ScriptedModel
from campuspath_agents.tools import ToolBelt, ToolPermissionError
from campuspath_agents.workflows import ConstraintRepairFailed, run_repair_loop
from campuspath_contracts.common import AgentId


@pytest.fixture
def spans():
    sdk = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = sdk.TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # 全局 provider 只能设一次；测试内用 tracer 直接绑定到这个 provider
    original = telemetry._otel_trace.get_tracer
    telemetry._otel_trace.get_tracer = lambda name, *a, **k: provider.get_tracer(name)
    yield exporter
    telemetry._otel_trace.get_tracer = original


def test_tool_calls_leave_spans_including_rejections(spans):
    belt = ToolBelt(AgentId.A4_OPPORTUNITY)
    belt.register("emit_opportunity_draft", lambda **kw: "draft")
    assert belt.call("emit_opportunity_draft", title="x") == "draft"
    with pytest.raises(ToolPermissionError):
        belt.call("publish")
    rows = {(s.name, s.attributes["gen_ai.tool.name"]): s.attributes for s in spans.get_finished_spans()}
    assert rows[("agent.tool", "emit_opportunity_draft")]["campuspath.tool.accepted"] is True
    assert rows[("agent.tool", "publish")]["campuspath.tool.accepted"] is False
    assert rows[("agent.tool", "publish")]["campuspath.agent"] == "A4"


def test_repair_loop_records_each_attempt_and_outcome(spans):
    calls = []

    def generate(reasons):
        calls.append(reasons)
        return len(calls)

    result, rounds = run_repair_loop(generate, lambda c: () if c >= 2 else ("too_early",))
    assert (result, rounds) == (2, 2)
    names = [s.name for s in spans.get_finished_spans()]
    assert names.count("agent.repair_attempt") == 2 and "agent.repair_loop" in names
    loop = next(s for s in spans.get_finished_spans() if s.name == "agent.repair_loop")
    assert loop.attributes["campuspath.outcome"] == "valid" and loop.attributes["campuspath.iterations"] == 2
    attempts = [s for s in spans.get_finished_spans() if s.name == "agent.repair_attempt"]
    assert [a.attributes["campuspath.violations"] for a in attempts] == [1, 0]


def test_exhausted_repair_loop_is_visible_as_such(spans):
    with pytest.raises(ConstraintRepairFailed):
        run_repair_loop(lambda reasons: 0, lambda c: ("never",), max_iterations=2)
    loop = next(s for s in spans.get_finished_spans() if s.name == "agent.repair_loop")
    assert loop.attributes["campuspath.outcome"] == "exhausted"


def test_span_attributes_never_carry_prompt_text(spans):
    with telemetry.span("probe", **{"gen_ai.request.model": "gemini-3.5-flash",
                                    "blob": "x" * 5000, "none": None, "n": 3}):
        pass
    attrs = spans.get_finished_spans()[-1].attributes
    assert len(attrs["blob"]) <= 200 and "none" not in attrs and attrs["n"] == 3
    assert "campuspath.duration_ms" in attrs


def test_usage_attributes_reads_genai_shape():
    class Usage:
        prompt_token_count = 18
        candidates_token_count = 12
        thoughts_token_count = 230

    class Response:
        model_version = "gemini-3.5-flash"
        usage_metadata = Usage()

    assert telemetry.usage_attributes(Response()) == {
        "gen_ai.response.model": "gemini-3.5-flash",
        "gen_ai.usage.input_tokens": 18, "gen_ai.usage.output_tokens": 12,
        "campuspath.thoughts_tokens": 230,
    }


def test_noop_when_no_tracer(monkeypatch):
    monkeypatch.setattr(telemetry, "_otel_trace", None)
    with telemetry.span("x", a=1) as current:
        current.set_attribute("k", "v")          # 不抛、不记
    assert isinstance(ScriptedModel({}), ScriptedModel)
