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


def _use_scripted(module, monkeypatch, script=None):
    """把两个工厂换成"用剧本桩模型建同一个 Agent"的工厂。

    换的是**模型**，不是工厂本身——被测的仍是 ``agent.py`` 里那两个
    ``build_agent``（hook 挂没挂、每次是不是新实例都照常成立）。
    """
    scripted = ScriptedStrandsModel(script or {"probe": "草稿已产出，等待人工审核。"})
    scripted.pending_purpose = "probe"
    for key, factory in list(module.AGENT_FACTORIES.items()):
        monkeypatch.setitem(
            module.AGENT_FACTORIES, key,
            lambda model=None, f=factory: f(model=model or scripted))
    return scripted


@pytest.fixture
def agentcore(monkeypatch):
    module = _load_cloud_module("campuspath_agentcore_app", "agentcore_app.py")
    _use_scripted(module, monkeypatch)
    return module


def test_entrypoint_imports_without_the_agentcore_package_installed(agentcore):
    assert callable(agentcore.invoke)
    assert agentcore.app is not None
    assert sorted(agentcore.AGENT_FACTORIES) == ["A0", "A4"]


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
    _use_scripted(module, monkeypatch, {"probe": "ok"})
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


# --------------------------------------------------------------------------
# F3：每次调用一个全新的 Agent —— 上一个学生的消息不许带给下一个
# --------------------------------------------------------------------------


def _built_agents(module, monkeypatch, script):
    """记下工厂每次造出来的 Agent，顺便把模型换成剧本桩。"""
    built: list[object] = []
    scripted = ScriptedStrandsModel(script)
    scripted.pending_purpose = "probe"

    def _spy(factory):
        def _make():
            agent = factory(model=scripted)
            built.append(agent)
            return agent
        return _make

    for key, factory in list(module.AGENT_FACTORIES.items()):
        monkeypatch.setitem(module.AGENT_FACTORIES, key, _spy(factory))
    return built


def test_two_invokes_do_not_share_conversation_state(agentcore, monkeypatch):
    """已知会失败的样例就是**这条改之前的实现**：模块级 ``root_agent`` 被
    ``invoke()`` 反复调用，``messages`` 一路累积——第二个学生的调用里带着
    第一个学生的原话，既串味又按别人的 token 计费。
    """
    built = _built_agents(agentcore, monkeypatch, {"probe": "好的。"})

    agentcore.invoke({"agent": "A4", "prompt": "第一位学生的公告原文 ALPHA"})
    agentcore.invoke({"agent": "A4", "prompt": "第二位学生的公告原文 BETA"})

    assert len(built) == 2 and built[0] is not built[1]
    first, second = built[0], built[1]
    assert "ALPHA" in str(first.messages)
    assert "ALPHA" not in str(second.messages), "第二次调用带着第一次的对话历史"
    assert "BETA" in str(second.messages)


def test_a_reused_agent_would_have_carried_the_history(agentcore, monkeypatch):
    """对照组（证明上一条不是空断言）：**同一个** Agent 连调两次，
    第二次的上下文里一定看得见第一次的原文。"""
    built = _built_agents(agentcore, monkeypatch, {"probe": "好的。"})
    agentcore.invoke({"agent": "A4", "prompt": "第一位学生的公告原文 ALPHA"})
    reused = built[0]
    reused("第二位学生的公告原文 BETA")
    assert "ALPHA" in str(reused.messages) and "BETA" in str(reused.messages)


def _hook_providers(agent) -> set[str]:
    return {
        type(entry.callback.__self__).__name__
        for entries in agent.hooks._registered_callbacks.values()
        for entry in entries
        if hasattr(entry.callback, "__self__")
    }


@pytest.mark.parametrize(
    ("key", "expected_agent"),
    [("A0", AgentId.A0_ORCHESTRATOR), ("A4", AgentId.A4_OPPORTUNITY)],
)
def test_each_mirror_agent_carries_both_hooks(agentcore, key, expected_agent):
    """已知会失败的样例：迁移到 Strands 时两个镜像 Agent 一个 hook 都没挂——
    白名单与提示词卫生在云端这一侧**完全不存在**，而本地测试全绿。"""
    from campuspath_agents.hooks import PromptHygieneHook, ToolWhitelistHook

    agent = agentcore.AGENT_FACTORIES[key]()
    assert {"PromptHygieneHook", "ToolWhitelistHook"} <= _hook_providers(agent)
    whitelist = [
        entry.callback.__self__
        for entries in agent.hooks._registered_callbacks.values()
        for entry in entries
        if isinstance(getattr(entry.callback, "__self__", None), ToolWhitelistHook)
    ]
    assert whitelist and all(h.agent is expected_agent for h in whitelist)
    assert any(
        isinstance(getattr(entry.callback, "__self__", None), PromptHygieneHook)
        for entries in agent.hooks._registered_callbacks.values()
        for entry in entries
    )


# --------------------------------------------------------------------------
# F6：payload 是不可信输入 —— 校验，且永不抛
# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload", ["不是对象", 42, None, ["a"]])
def test_a_payload_that_is_not_an_object_is_refused_not_raised(agentcore, payload):
    """已知会失败的样例：``payload.get`` 在字符串上是 AttributeError——
    入口抛异常时 AgentCore 回的是个没有形状的 500。"""
    out = agentcore.invoke(payload)
    assert out["error"] == "invalid_payload"
    assert "result" not in out


def test_missing_prompt_is_named_not_a_key_error(agentcore):
    """已知会失败的样例：``payload["prompt"]`` 缺席时直接 KeyError。"""
    out = agentcore.invoke({"agent": "A0"})
    assert out == {"error": "missing_prompt", "agent": "A0"}


@pytest.mark.parametrize("payload_builder", [
    lambda big: {"agent": "A0", "prompt": big},
    lambda big: {"kind": "generate", "request": {"system": big, "purpose": "probe"}},
    lambda big: {"kind": "generate", "request": {"system": "s", "data": ["ok", big]}},
    lambda big: {"kind": "extract", "raw_content": big, "source_id": "SRC-1"},
])
def test_oversized_fields_are_refused_before_the_model_is_called(
        agentcore, scripted_runtime, payload_builder):
    """32 KiB 以上的单块一律拒绝。Bedrock 按 token 收费——进来多少字就是
    花多少钱，所以这道闸必须在**调用模型之前**。"""
    model = scripted_runtime({"probe": "ok"})
    big = "啊" * (agentcore.MAX_FIELD_BYTES // 3 + 1)   # 中文 3 字节/字
    out = agentcore.invoke(payload_builder(big))
    assert out["error"] == "payload_too_large"
    assert out["limit_bytes"] == agentcore.MAX_FIELD_BYTES
    assert model.calls == [], "超限的 payload 仍然调了一次模型"


def test_a_field_just_under_the_cap_still_goes_through(agentcore, scripted_runtime):
    """对照组：卡在上限以内的 payload 必须照常跑，否则上面那条只是"全拒"。"""
    scripted_runtime({"probe": "ok"})
    ok_block = "a" * (agentcore.MAX_FIELD_BYTES - 1)
    out = agentcore.invoke({"kind": "generate",
                            "request": {"system": "s", "data": [ok_block],
                                        "purpose": "probe"}})
    assert out["result"].strip() == "ok"


@pytest.mark.parametrize("spec", ["不是对象", 7, ["a"]])
def test_a_request_block_that_is_not_an_object_is_refused(agentcore, spec):
    out = agentcore.invoke({"kind": "generate", "request": spec})
    assert out["error"] == "invalid_request"


def test_generate_with_an_unknown_agent_id_is_refused_not_raised(agentcore,
                                                                 scripted_runtime):
    """已知会失败的样例：``AgentId("A9")`` 抛 ValueError，入口整个炸掉。"""
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "generate", "request": {
        "system": "s", "purpose": "probe", "agent": "A9"}})
    assert out["error"] == "unknown_agent" and out["requested"] == "A9"
    assert model.calls == []


def test_data_must_be_an_array_not_a_bare_string(agentcore, scripted_runtime):
    """已知会失败的样例：``data="一段话"`` 会被 ``tuple()`` 拆成**单个字符**的
    数据块列表——模型收到的是一串 `<<<DATA-1 啊>>>`，没人会发现。"""
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "generate", "request": {
        "system": "s", "purpose": "probe", "data": "一段话"}})
    assert out["error"] == "invalid_request" and out["field"] == "request.data"
    assert model.calls == []


def test_an_exception_inside_the_agent_comes_back_as_an_error_not_a_result(
        agentcore, monkeypatch):
    """执行期炸了也必须是 JSON 里的 ``error``：调用方的 ``_absorb`` 看不到
    ``result`` 就会抛 AgentCoreProtocolError——失败是响的，不是一句空回答。"""
    def _boom(*_a, **_k):
        raise RuntimeError("模型那边挂了")

    monkeypatch.setitem(agentcore.AGENT_FACTORIES, "A0", lambda: _boom)
    out = agentcore.invoke({"agent": "A0", "prompt": "x"})
    assert out["error"] == "invocation_failed"
    assert "RuntimeError" in out["detail"] and "result" not in out


# --------------------------------------------------------------------------
# F6：``kind="extract"`` —— A4 的带工具循环搬进 Runtime
# --------------------------------------------------------------------------


EXTRACT_PAYLOAD = {
    "kind": "extract",
    "request": {"system": "你是 A4", "purpose": "extract:SRC-7", "agent": "A4"},
    "source_id": "SRC-7",
    "raw_content": "【AI 工作坊】主办：CSE 学会。10/20 晚 7 点，报名请发邮件。",
}


def test_extract_runs_the_tool_loop_and_returns_what_the_model_emitted(
        agentcore, scripted_runtime):
    """A4 在 Runtime 里调 ``emit_opportunity_draft``，提议的字段随回包出境。

    回包里的是 ``emitted``（模型的提议），**不是草稿**：契约对象仍由 API 侧构造。
    """
    model = scripted_runtime({
        "extract:SRC-7": {"tool": "emit_opportunity_draft", "input": {
            "title": "AI 工作坊", "organizer": "CSE 学会", "category": "workshop",
            "summary": "面向本科生的 AI 入门工作坊。", "signup_hint": "发邮件报名"}},
        "extract:SRC-7#after_tool": "已产出草稿，等待人工审核。",
    })
    out = agentcore.invoke(EXTRACT_PAYLOAD)

    assert out["result"].strip() == "已产出草稿，等待人工审核。"
    assert out["emitted"]["title"] == "AI 工作坊"
    assert out["emitted"]["category"] == "workshop"
    assert out["model"] == "scripted" and out["rejected_tools"] == []
    # 原文只进 data，system 里一个字都不来自来源（§8.9.1 第 1 条）
    assert model.system_prompts() == ["你是 A4"]
    assert model.calls[0].data == (EXTRACT_PAYLOAD["raw_content"],)
    assert model.calls[0].agent is AgentId.A4_OPPORTUNITY


def test_extract_refuses_the_publish_tool_and_says_so(agentcore, scripted_runtime):
    """已知会失败的样例：原文里写着"立即发布"，模型照做。

    白名单 hook 取消这次工具调用，被拒记录跟着回包出来，``emitted`` 是 None——
    没有任何东西被产出，更没有发布。
    """
    scripted_runtime({
        # ``unlisted``：模型幻觉出一个**没装备**的工具名——A4 被原文劫持后
        # 试图发布就是这个形状（剧本桩要求显式声明，见 ScriptedStrandsModel）。
        "extract:SRC-7": {"tool": "publish_opportunity", "unlisted": True,
                          "input": {"id": "OPP-9"}},
        "extract:SRC-7#after_tool": "我没有发布权。",
    })
    out = agentcore.invoke(EXTRACT_PAYLOAD)
    assert out["rejected_tools"][0][0] == "publish_opportunity"
    assert out["emitted"] is None
    assert "result" in out


def test_extract_without_raw_content_is_refused(agentcore, scripted_runtime):
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "extract", "source_id": "SRC-7"})
    assert out == {"error": "missing_raw_content"}
    assert model.calls == []


def test_extract_refuses_to_run_as_another_agent(agentcore, scripted_runtime):
    """已知会失败的样例：``agent="A1"`` 借 A4 的带工具循环跑一段外部原文——
    那会绕开"A4 是唯一处理不可信外部内容的 Agent"（§8.9.1）。"""
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({**EXTRACT_PAYLOAD,
                            "request": {**EXTRACT_PAYLOAD["request"], "agent": "A1"}})
    assert out["error"] == "unsupported_agent" and out["supported"] == ["A4"]
    assert model.calls == []


def test_extract_falls_back_to_the_vendored_a4_system_prompt(agentcore,
                                                             scripted_runtime):
    """没给 system 时用本仓那份 A4 指令，而不是空字符串。"""
    from campuspath_agents.roster import A4_SYSTEM_PROMPT

    model = scripted_runtime({"extract:SRC-7": "好的。"})
    out = agentcore.invoke({"kind": "extract", "source_id": "SRC-7",
                            "raw_content": "公告原文"})
    assert "error" not in out
    assert model.system_prompts() == [A4_SYSTEM_PROMPT]


def test_generate_without_a_system_prompt_is_refused(agentcore, scripted_runtime):
    """已知会失败的样例：``request`` 里没有 system。

    空 system 一样烧 token，而模型收到的是"没有任务"。让它在入口响，
    比在账单上响好。
    """
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "generate", "request": {"purpose": "probe"}})
    assert out == {"error": "missing_system"}
    assert model.calls == []


def test_generate_without_a_request_block_is_refused(agentcore, scripted_runtime):
    model = scripted_runtime({"probe": "ok"})
    out = agentcore.invoke({"kind": "generate"})
    assert out["error"] == "invalid_request"
    assert model.calls == []
