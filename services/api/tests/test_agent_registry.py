"""P4（2026-08-24）：Agent 注册表端点 + trace 状态 + 检查点状态，一屏说清"系统里有哪些 Agent、
它们能碰什么、现在跑在什么模型上、状态存在哪、trace 往哪去"。

注册表**不是手写的**：从 `campuspath_contracts.agents` 的治理表派生，
所以它和 A4 白名单/禁止清单/写域表永远一致——测试逐项对拍。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.agents import (
    AGENT_RUNTIME,
    AGENT_TOOL_WHITELIST,
    AGENT_WRITE_DOMAINS,
    FORBIDDEN_TOOL_PATTERNS,
)
from campuspath_contracts.common import AgentId
from campuspath_api.app import Deps, create_app

ADMIN = {"X-CampusPath-Role": "career_center_admin"}


@pytest.fixture
def client():
    return TestClient(create_app(Deps("full", model=None)))


def test_registry_mirrors_governance_tables(client):
    got = client.get("/v1/ops/agents", headers=ADMIN)
    assert got.status_code == 200, got.text
    body = got.json()
    entries = {e["agent_id"]: e for e in body["agents"]}
    assert set(entries) == {a.value for a in AgentId}
    for agent in AgentId:
        e = entries[agent.value]
        assert e["runtime"] == AGENT_RUNTIME[agent].value
        assert set(e["tool_whitelist"]) == AGENT_TOOL_WHITELIST[agent]
        assert set(e["forbidden_tool_patterns"]) == FORBIDDEN_TOOL_PATTERNS[agent]
        assert set(e["write_domains"]) == {d.value for d in AGENT_WRITE_DOMAINS[agent]}
    a4 = entries["A4"]
    assert set(a4["tool_whitelist"]) == {"read_source", "emit_opportunity_draft"}


def test_registry_reports_model_backend_and_floor(client, monkeypatch):
    # 代际门槛与 vertex_only 只在 Vertex 后端下有意义，所以显式选它。
    monkeypatch.setenv("CAMPUSPATH_MODEL_BACKEND", "vertex")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    body = client.get("/v1/ops/agents", headers=ADMIN).json()
    model = body["model_backend"]
    assert model["available"] is False                # 测试环境无模型
    assert model["default_model"].startswith("gemini-3.5")
    assert model["generation_floor"] == "3.5"
    assert model["vertex_only"] is True


def test_registry_reports_strands_runtime_with_a_scripted_model():
    """Strands 迁移后注册表要说清"跑在什么运行时/后端上"——桩也不例外。

    桩模型同样走完整 Strands 事件循环，所以 runtime/sdk_version 必须是真的，
    不是"因为是测试所以填 unknown"。
    """
    from campuspath_agents.model import ScriptedModel, strands_version

    client = TestClient(create_app(Deps("full", model=ScriptedModel({}))))
    model = client.get("/v1/ops/agents", headers=ADMIN).json()["model_backend"]
    assert model["available"] is True
    assert model["runtime"] == "strands"
    assert model["backend"] == "scripted"
    assert model["sdk_version"] == strands_version() and model["sdk_version"]
    assert model["sdk_version"] != "unknown"
    assert model["tool_rejections_last_call"] == 0
    assert model["last_usage"] is None            # 还没调用过


def test_registry_reports_env_default_backend_when_no_model(client, monkeypatch):
    """没有可用后端时，backend 报的是**环境会选的那个**，不是 None——
    否则运维看到 available=false 却无从判断"该配 AWS 还是 Google"。"""
    from campuspath_agents.strands_models import BACKEND_ENV

    monkeypatch.delenv(BACKEND_ENV, raising=False)
    body = client.get("/v1/ops/agents", headers=ADMIN).json()["model_backend"]
    assert body["available"] is False
    assert body["backend"] == "bedrock"          # 默认后端
    assert body["runtime"] == "strands"
    assert body["tool_rejections_last_call"] == 0

    monkeypatch.setenv(BACKEND_ENV, "vertex")
    body = client.get("/v1/ops/agents", headers=ADMIN).json()["model_backend"]
    assert body["backend"] == "vertex"


def test_registry_survives_a_bedrock_backend_without_google_env(monkeypatch):
    """Bedrock 形态下机器上可能一个 Google 环境变量都没有——注册表不许炸，
    且 location 报 Bedrock 区域、vertex_only 为假。"""
    for name in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT",
                 "GOOGLE_CLOUD_LOCATION", "GOOGLE_API_KEY", "GEMINI_API_KEY"):  # ai-studio-denylist
        monkeypatch.delenv(name, raising=False)

    class _FakeBedrock:
        backend = "bedrock"
        runtime = "strands"
        model = "amazon.nova-pro-v1:0"
        region = "us-east-1"
        last_model_version = None
        last_usage = {"inputTokens": 12, "outputTokens": 3}
        last_rejected_tools = (("read_student_state", "not in whitelist"),)

    client = TestClient(create_app(Deps("full", model=_FakeBedrock())))
    got = client.get("/v1/ops/agents", headers=ADMIN)
    assert got.status_code == 200, got.text
    model = got.json()["model_backend"]
    assert model["backend"] == "bedrock"
    assert model["default_model"] == "amazon.nova-pro-v1:0"
    assert model["location"] == "us-east-1"
    assert model["vertex_only"] is False
    assert model["last_usage"] == {"inputTokens": 12, "outputTokens": 3}
    assert model["tool_rejections_last_call"] == 1


def test_registry_reports_checkpoint_and_trace_status(client):
    body = client.get("/v1/ops/agents", headers=ADMIN).json()
    assert body["checkpoint"]["enabled"] is False and body["checkpoint"]["backend"] is None
    assert body["trace"]["enabled"] is False


def test_registry_requires_institution_role(client):
    assert client.get("/v1/ops/agents", headers={"X-CampusPath-Role": "student"}).status_code == 403


def test_registry_includes_recent_spans_when_tracing(monkeypatch):
    monkeypatch.setenv("CAMPUSPATH_TRACE", "memory")
    from campuspath_api import telemetry
    deps = Deps("full", model=None)
    client = TestClient(create_app(deps))
    client.get("/v1/students/STU-A/profile", headers={"X-CampusPath-Role": "student"})
    body = client.get("/v1/ops/agents", headers=ADMIN).json()
    assert body["trace"]["enabled"] is True and body["trace"]["exporter"] == "memory"
    names = {s["name"] for s in body["trace"]["recent_spans"]}
    assert "http.request" in names


def test_registry_reports_the_agentcore_runtime_when_the_semantic_plane_is_remote(monkeypatch):
    """P3：语义平面搬进 Bedrock AgentCore Runtime 之后，注册表必须说出来。

    ``runtime`` 是运维分诊的第一格：``strands`` = 模型调用在这个进程里跑，
    ``agentcore`` = 在 AgentCore Runtime 里跑，出了事要去 CloudWatch 看。
    两者的日志、配额、故障面完全不同，写死 ``strands`` 会把人指错方向。
    """
    for name in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT",
                 "GOOGLE_CLOUD_LOCATION"):
        monkeypatch.delenv(name, raising=False)

    class _FakeAgentCore:
        backend = "bedrock"
        runtime = "agentcore"
        model = "amazon.nova-pro-v1:0"
        region = "us-east-1"
        last_model_version = None
        last_usage = {"inputTokens": 120, "outputTokens": 18}
        last_rejected_tools = (("publish_opportunity", "不在 A4 白名单"),)

    client = TestClient(create_app(Deps("full", model=_FakeAgentCore())))
    model = client.get("/v1/ops/agents", headers=ADMIN).json()["model_backend"]
    assert model["available"] is True
    assert model["runtime"] == "agentcore"
    assert model["backend"] == "bedrock"
    assert model["location"] == "us-east-1"
    assert model["tool_rejections_last_call"] == 1


def test_model_unavailable_503_names_all_three_ways_to_get_a_backend(client):
    """已知会失败的样例：AgentCore 形态下 503 只说 Bedrock 与 Vertex，
    运维会以为"配 AWS 凭据"就够了，而缺的其实是 ``AGENTCORE_RUNTIME_ARN``。

    这条同时守着另一件事：``_require_model()`` 不再是死代码——它此前只被
    定义、从没被调用过，于是"503 的措辞"从来没被任何请求走到过。
    """
    got = client.post("/v1/students/STU-A/goals/GOAL-A-P/decomposition/research",
                      headers={"X-CampusPath-Role": "student"})
    assert got.status_code == 503, got.text
    body = got.json()["detail"]
    assert body["error"] == "model_backend_unavailable"
    detail = body["detail"]
    assert "AgentCore" in detail and "AGENTCORE_RUNTIME_ARN" in detail
    assert "Bedrock" in detail and "Vertex" in detail
