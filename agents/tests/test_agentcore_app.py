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
