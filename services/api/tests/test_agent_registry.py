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
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    body = client.get("/v1/ops/agents", headers=ADMIN).json()
    model = body["model_backend"]
    assert model["available"] is False                # 测试环境无模型
    assert model["default_model"].startswith("gemini-3.5")
    assert model["generation_floor"] == "3.5"
    assert model["vertex_only"] is True


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
