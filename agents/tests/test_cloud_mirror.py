"""R7-D：云端部署镜像与本地 roster 的一致性。

Agent Engine 上跑的 orchestrator 是独立打包的（不 import 本 monorepo），
路由表因此存在第二份。这里断言两份逐项一致——表改了镜像没跟上，
先红的是 CI，不是演示现场。
"""

import importlib.util
import pathlib
import sys


def _load_cloud_module(name: str, rel: str):
    path = pathlib.Path(__file__).resolve().parents[1] / "cloud" / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_cloud_orchestrator_routes_mirror_roster():
    from campuspath_agents.roster import OrchestratorAgent

    cloud = _load_cloud_module(
        "cloud_orchestrator_agent", "orchestrator_agent/agent.py")

    local = {
        intent.value: [a.value for a in agents]
        for intent, agents in OrchestratorAgent.ROUTES.items()
    }
    assert cloud.ROUTES == local, (
        "云端镜像路由表与 roster.OrchestratorAgent.ROUTES 不一致——"
        "改了其中一份必须同步另一份并重新部署"
    )


def test_cloud_orchestrator_route_tool_is_deterministic():
    cloud = _load_cloud_module(
        "cloud_orchestrator_agent2", "orchestrator_agent/agent.py")
    hit = cloud.route_intent("find_opportunities")
    assert hit["kind"] == "deterministic_route" and hit["model_used"] is False
    assert [c["agent"] for c in hit["calls"]] == ["A1", "A3", "A5"]
    miss = cloud.route_intent("write_my_thesis")
    assert miss["kind"] == "llm_composed" and miss["model_used"] is True


def test_cloud_scout_cannot_publish():
    """A4 镜像：工具签名里没有 status 可传，产出恒为 draft。"""
    cloud = _load_cloud_module(
        "cloud_scout_agent", "opportunity_scout_agent/agent.py")
    draft = cloud.emit_opportunity_draft(
        title="X", organizer="Y", category="published",  # 越界分类也进不了发布态
        summary="s", signup_hint="",
    )["draft"]
    assert draft["publication_status"] == "draft"
    assert draft["category"] == "event"
    assert draft["signup_hint"] == "未提供"


def test_cloud_mirrors_build_a_fresh_agent_each_call():
    """F3：两个镜像模块都必须给出工厂，而不是只有一个模块级实例。

    已知会失败的样例是**这条改之前的两个文件**：只有 ``root_agent``，
    ``invoke()`` 每次调的都是同一个对象，``messages`` 跨调用累积。
    """
    for name, rel in (("f3_orchestrator", "orchestrator_agent/agent.py"),
                      ("f3_scout", "opportunity_scout_agent/agent.py")):
        cloud = _load_cloud_module(name, rel)
        first, second = cloud.build_agent(), cloud.build_agent()
        assert first is not second, f"{rel} 的 build_agent 返回了同一个实例"
        assert first.messages == [] and second.messages == []
        assert cloud.root_agent is not None          # 兼容入口仍在


def test_the_runtime_extract_path_uses_the_same_names_as_roster():
    """镜像守卫：AgentCore 入口的 ``kind="extract"`` 跑的是 ``extract_draft``
    的前半段（后半段要契约对象，线上送不过来）。它靠这几个名字与 roster 对齐——
    roster 改了名，这条先红，而不是云上第一次抽取时才红。
    """
    from campuspath_agents.roster import (
        A4_SYSTEM_PROMPT, A4_TOOL_SPECS, OpportunityAgent,
    )

    from campuspath_agents.model import ScriptedModel
    from campuspath_agents.tools import belt_for
    from campuspath_contracts.common import AgentId

    assert set(A4_TOOL_SPECS) == {"read_source", "emit_opportunity_draft"}
    assert A4_SYSTEM_PROMPT.strip()

    agent = OpportunityAgent(
        agent_id=AgentId.A4_OPPORTUNITY,
        belt=belt_for(AgentId.A4_OPPORTUNITY, {}),
        model=ScriptedModel({}),
    )
    for attribute in ("_source_id", "_raw_content", "last_emitted"):
        assert hasattr(agent, attribute), attribute
    agent._equip_defaults()
    assert agent.belt.available == {"read_source", "emit_opportunity_draft"}

    app = _load_cloud_module("mirror_agentcore_app", "agentcore_app.py")
    assert app.KIND_EXTRACT in app.KNOWN_KINDS
