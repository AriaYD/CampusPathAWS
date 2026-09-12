"""AgentCore 入口（2026-09-12，Agents for Humans Hackathon 的部署形态）。

比赛要求 "deployed on AgentCore"。部署本身没法在 CI 里证明，但**入口能被调用**
可以：这条测试在**没有任何 AWS 凭据**的机器上把 payload 喂进 ``invoke()``，
断言它路由到了对应的 root_agent 并回了 ``{"result": ...}``。

``bedrock_agentcore`` 本机装了（1.23.0），但**不能假定 CI 上也有**——
模块在它缺席时必须仍然可导入（内置同形替身）。两条分支都各有一条测试：
真包在场走真包，把它从 sys.modules 挖掉就走替身。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from campuspath_agents.strands_models import ScriptedStrandsModel
from campuspath_contracts.common import AgentId


def _load_cloud_module(name: str, rel: str):
    path = pathlib.Path(__file__).resolve().parents[1] / "cloud" / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def agentcore():
    module = _load_cloud_module("campuspath_agentcore_app", "agentcore_app.py")
    scripted = ScriptedStrandsModel({"probe": "草稿已产出，等待人工审核。"})
    scripted.pending_purpose = "probe"
    for agent in module.AGENTS.values():
        agent.model = scripted
    return module


def test_entrypoint_imports_without_the_agentcore_package_installed(agentcore):
    assert callable(agentcore.invoke)
    assert agentcore.app is not None
    assert sorted(agentcore.AGENTS) == ["A0", "A4"]


def test_invoke_routes_to_the_scout(agentcore):
    out = agentcore.invoke({"agent": "A4", "prompt": "工作坊详情……"})
    assert out["result"].strip() == "草稿已产出，等待人工审核。"


def test_invoke_routes_to_the_orchestrator(agentcore):
    out = agentcore.invoke({"agent": "A0", "prompt": "帮我排下学期的课"})
    assert out["result"].strip() == "草稿已产出，等待人工审核。"


def test_unknown_agent_is_refused_not_silently_routed(agentcore):
    """已知会失败的样例：A9 不存在——不能悄悄落到 A0 上跑。"""
    out = agentcore.invoke({"agent": "A9", "prompt": "x"})
    assert "result" not in out
    assert out["known_agents"] == ["A0", "A4"]


def test_module_still_imports_when_bedrock_agentcore_is_missing(monkeypatch):
    """已知会失败的样例：把 ``bedrock_agentcore`` 从 sys.modules 里挖掉。

    部署镜像里它在，本地/CI 里未必——替身分支如果从没被执行过，
    "本地也能导入"就只是一句注释。这条测试让那条分支真的跑一遍。
    """
    monkeypatch.setitem(sys.modules, "bedrock_agentcore", None)
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.runtime", None)
    module = _load_cloud_module("campuspath_agentcore_app_standin", "agentcore_app.py")

    assert getattr(type(module.app), "installed", None) is False   # 用的是替身
    scripted = ScriptedStrandsModel({"probe": "ok"})
    scripted.pending_purpose = "probe"
    for agent in module.AGENTS.values():
        agent.model = scripted
    assert module.invoke({"agent": "A0", "prompt": "x"})["result"].strip() == "ok"
    with pytest.raises(RuntimeError):
        module.app.run()


# --------------------------------------------------------------------------
# P3：``kind="generate"`` —— 整个语义平面（A0–A5）经这道口子在 Runtime 里跑
# --------------------------------------------------------------------------
#
# API 侧只送 ``ModelRequest`` 的四个字段，这里把它们装回去、跑完整的 Strands
# 事件循环、把文本与**证据**（用量、被拒工具、模型 ID）一起送回去。
# "被拒工具能回到调用方"这件事必须在 CI 里证明：不然 API 的注册表上那个
# ``tool_rejections_last_call`` 在 AgentCore 形态下会永远是 0，而看的人
# 会以为"没有越权"，真相却是"这条链路根本不报"。


@pytest.fixture
def scripted_runtime(agentcore, monkeypatch):
    """把进程级单例换成剧本桩。真单例惰性构造 ``BedrockModelClient``，
    在没有 AWS 凭据的机器上碰不得。"""
    from campuspath_agents.model import ScriptedModel

    def _install(script):
        model = ScriptedModel(script)
        monkeypatch.setattr(agentcore, "_MODEL", model)
        return model

    return _install


def test_model_client_singleton_is_lazy_so_import_stays_credential_free(agentcore):
    """已知会失败的样例：import 时就建 Bedrock 客户端的话，这里就不是 None。

    模块必须能在**没有任何 AWS 凭据**的机器上被导入（CI 就是这样一台）。
    """
    assert agentcore._MODEL is None


def test_generate_kind_round_trips_a_model_request(agentcore, scripted_runtime):
    model = scripted_runtime({"pathway:S1": "三套方案已生成。"})
    out = agentcore.invoke({"kind": "generate", "request": {
        "system": "你是 A5", "data": ["块一", "块二"],
        "purpose": "pathway:S1", "agent": "A5",
    }})

    assert out["result"].strip() == "三套方案已生成。"
    assert out["rejected_tools"] == []
    assert out["model"] == "scripted"
    assert out["usage"] == {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    # system 与 data 分开进——外部内容永远不拼进 system prompt（§8.9.1 第 1 条）
    assert model.system_prompts() == ["你是 A5"]
    assert model.calls[0].data == ("块一", "块二")
    assert model.calls[0].agent is AgentId.A5_PATHWAY


def test_generate_without_an_agent_still_runs(agentcore, scripted_runtime):
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "generate",
                            "request": {"system": "s", "purpose": "probe"}})
    assert out["result"].strip() == "ok"
    assert model.calls[0].agent is None


def test_generate_reports_tools_the_whitelist_hook_cancelled(agentcore, scripted_runtime):
    """已知会失败的样例：A4 在 Runtime 里请求 ``publish_opportunity``。

    白名单 hook 在 Runtime 那一侧的事件循环里取消调用，被拒记录必须
    **跟着回包出境**——API 侧的注册表就是靠它说"拦截真的在生效"。
    """
    scripted_runtime({
        "extract:SRC-1": {"tool": "publish_opportunity", "input": {"id": "OPP-1"}},
        "extract:SRC-1#after_tool": "我没有发布权。",
    })
    out = agentcore.invoke({"kind": "generate", "request": {
        "system": "你是 A4", "data": ["工作坊详情……"],
        "purpose": "extract:SRC-1", "agent": "A4",
    }})

    assert out["rejected_tools"] and out["rejected_tools"][0][0] == "publish_opportunity"
    assert "白名单" in out["rejected_tools"][0][1]
    assert out["result"].strip() == "我没有发布权。"


def test_unknown_kind_is_refused_not_routed_to_generate(agentcore, scripted_runtime):
    """已知会失败的样例：``kind`` 拼错了。落到 generate 上会静默跑掉真钱。"""
    scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "generat", "request": {"system": "s",
                                                          "purpose": "probe"}})
    assert out["error"] == "unknown_kind"
    assert "result" not in out


def test_the_legacy_agent_form_still_works_alongside_generate(agentcore):
    """回归：``{"agent","prompt"}`` 那条口子不能因为新增 kind 而消失。"""
    out = agentcore.invoke({"agent": "A0", "prompt": "帮我排下学期的课"})
    assert out["result"].strip() == "草稿已产出，等待人工审核。"
    out = agentcore.invoke({"kind": "agent", "agent": "A4", "prompt": "工作坊详情"})
    assert out["result"].strip() == "草稿已产出，等待人工审核。"
