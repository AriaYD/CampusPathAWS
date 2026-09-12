"""Amazon Bedrock AgentCore 的入口模块（Agents for Humans Hackathon 部署形态）。

AgentCore Runtime 要的是一个 HTTP 服务：``BedrockAgentCoreApp`` 起服务，
``@app.entrypoint`` 装饰的函数收 payload、回 JSON。本模块就是那一层，
**它不做任何判断**——判断在 Agent 那边，这里只负责**校验**与路由。

三条口子：

* ``kind="generate"`` —— **整个语义平面（A0–A5）的模型调用**。API 进程
  （Cloud Run）把 ``ModelRequest`` 的四个字段送进来，这边用进程级
  :class:`~campuspath_agents.model.BedrockModelClient` 跑完整的 Strands 事件
  循环（白名单 hook、提示词卫生 hook 都在**这一侧**生效），回文本 + 用量 +
  被拒工具 + 模型 ID。凭据、学生档案、日历过不来——payload 里没有字段装它们；
* ``kind="extract"`` —— **A4 的带工具抽取**（2026-09-12 P5 起）。原文进来，
  ``OpportunityAgent`` 在这一侧跑 ``read_source`` / ``emit_opportunity_draft``
  的事件循环，回模型提议的字段。契约对象（``Opportunity`` / ``Provenance`` /
  ``OpportunityDraft``）仍在 API 侧构造——**草稿的形状不由这边决定**；
* ``{"agent","prompt"}``（``kind="agent"``）—— 两个镜像 Agent 的直调（保留）。

**payload 一律当作不可信输入校验**（F6）：类型不对、字段缺失、单块超过
:data:`MAX_FIELD_BYTES` 都回 ``{"error": ...}``，**不抛异常**。入口抛异常时
AgentCore 回的是一个没有形状的 500，调用方分不清"我发错了"与"那边挂了"。

``bedrock_agentcore`` 在部署镜像里一定有，本地/CI 未必。缺席时下面会退回一个
同形替身，目的很具体：``invoke()`` 的路由逻辑要能在 CI 里被调用、被断言，
而不是等部署之后在云上第一次发现 payload 的 key 拼错了。
替身的 ``run()`` 故意抛异常——**本地起不了真服务这件事必须响**，
不能让人以为自己在跑 AgentCore。
"""

from __future__ import annotations

import pathlib
import sys
import threading
from typing import Any

#: AgentCore 打包的是本目录，两个 Agent 包就在旁边。显式把自己所在目录
#: 放进 sys.path，本地按文件路径加载时也能找到它们。
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from opportunity_scout_agent.agent import build_agent as build_scout  # noqa: E402
from orchestrator_agent.agent import build_agent as build_orchestrator  # noqa: E402

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
except ImportError:  # 本地/CI：包没装，用同形替身，让模块仍然可导入可测
    class BedrockAgentCoreApp:  # type: ignore[no-redef]
        """``BedrockAgentCoreApp`` 的最小同形替身。只留被本模块用到的两个成员。"""

        installed = False

        def __init__(self) -> None:
            self.handler = None

        def entrypoint(self, fn):
            self.handler = fn
            return fn

        def run(self, *args: Any, **kwargs: Any):
            raise RuntimeError(
                "bedrock_agentcore 未安装：这是本地替身，起不了 AgentCore 服务。"
                "部署镜像里装上 bedrock-agentcore 再跑。"
            )

#: 能被这个入口调起的 Agent → **构造它的工厂**。白名单式：不在表里的一律拒绝，
#: 不落到某个默认 Agent 上——"A9 被当成 A0 跑了"是不该发生的静默错误。
#:
#: 值是工厂而不是实例（F3）：Strands 的 ``Agent`` 把对话历史留在自己的
#: ``messages`` 上，一个进程级实例被反复调用 = 把上一个学生的消息带给下一个。
AGENT_FACTORIES = {"A0": build_orchestrator, "A4": build_scout}

app = BedrockAgentCoreApp()

#: 进程级模型客户端（``kind="generate"`` / ``kind="extract"`` 用）。**惰性构造**：
#: ``BedrockModelClient()`` 一建就去问 AWS 凭据，而本模块必须能在
#: 没有凭据的机器上被导入并测试。测试直接替换这个名字。
#: 模型客户端本身是无状态的（每次调用自己建 ``Agent``、证据随
#: ``InvocationOutcome`` 返回），所以它可以跨调用共用，而 ``Agent`` 不可以。
_MODEL: Any = None
_MODEL_LOCK = threading.Lock()

#: 本入口认识的 payload 形态。``kind`` 缺省等于 ``agent``（老形态，向后兼容）。
KIND_GENERATE = "generate"
KIND_EXTRACT = "extract"
KIND_AGENT = "agent"
KNOWN_KINDS = (KIND_GENERATE, KIND_EXTRACT, KIND_AGENT)

#: 单个文本字段的上限（UTF-8 字节）。32 KiB 远大于任何一条真实的公告原文或
#: system 指令，又小到**一个 payload 撑不爆 Runtime 的内存、也烧不出一张
#: 意外的账单**：Bedrock 按 token 计费，进来多少字就是花多少钱。
MAX_FIELD_BYTES = 32 * 1024


def model_client() -> Any:
    """整个 Runtime 共用的一个 :class:`BedrockModelClient`（连接与凭据只建一次）。"""
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                from campuspath_agents.model import BedrockModelClient  # noqa: PLC0415

                _MODEL = BedrockModelClient()
    return _MODEL


# --------------------------------------------------------------------------
# 校验（F6）：payload 来自网线，一个字段都不假定
# --------------------------------------------------------------------------


def _oversized(value: str) -> bool:
    return len(value.encode("utf-8")) > MAX_FIELD_BYTES


def _too_large(field: str) -> dict:
    return {"error": "payload_too_large", "field": field,
            "limit_bytes": MAX_FIELD_BYTES}


def _text(spec: dict, key: str) -> str | None:
    """取一个字符串字段；不是字符串就当没有（调用方按"缺失"处理）。"""
    value = spec.get(key)
    return value if isinstance(value, str) else None


def _checked_request(spec: Any) -> tuple[Any, dict | None]:
    """``request`` 块 → ``(ModelRequest, None)`` 或 ``(None, 错误回包)``。

    ``system`` 来自调用方（Cloud Run 的 API 进程）。**TODO（已知限制，本次不修）**：
    这一侧信任它，依据只有"``invoke_agent_runtime`` 是 IAM 门禁的，能调到这里的
    只有我们自己的服务账号"。一旦哪天有第二个调用方（或那把凭据泄了），
    "system prompt 只来自本仓写死的指令"这条就不再由**形状**保证。
    真正的修法是把六个 system prompt 搬到 Runtime 这一侧、payload 只送
    ``purpose`` + 数据块，让"拼进 system"在协议上做不到。见
    ``infra/README.md`` 的同名条目。
    """
    from campuspath_agents.model import ModelRequest  # noqa: PLC0415
    from campuspath_contracts.common import AgentId  # noqa: PLC0415

    if not isinstance(spec, dict):
        return None, {"error": "invalid_request", "expected": "object",
                      "got": type(spec).__name__}

    system = _text(spec, "system") or ""
    if not system:
        # system 是这次调用的**全部指令**（数据块只是数据）。空 system 的调用
        # 会照样烧掉一次 token，而模型收到的是"没有任务"——那是调用方的 bug，
        # 让它在这里响，比在账单上响好。
        return None, {"error": "missing_system"}
    if _oversized(system):
        return None, _too_large("request.system")

    raw_blocks = spec.get("data") or ()
    if isinstance(raw_blocks, (str, bytes)) or not isinstance(raw_blocks, (list, tuple)):
        return None, {"error": "invalid_request", "field": "request.data",
                      "expected": "array of strings"}
    blocks: list[str] = []
    for index, block in enumerate(raw_blocks):
        text = block if isinstance(block, str) else str(block)
        if _oversized(text):
            return None, _too_large(f"request.data[{index}]")
        blocks.append(text)

    purpose = _text(spec, "purpose") or ""
    if _oversized(purpose):
        return None, _too_large("request.purpose")

    agent_value = spec.get("agent")
    agent: Any = None
    if agent_value:
        try:
            agent = AgentId(str(agent_value))
        except ValueError:
            return None, {"error": "unknown_agent", "requested": str(agent_value),
                          "known_agents": [a.value for a in AgentId]}

    return ModelRequest(system=system, data=tuple(blocks), purpose=purpose,
                        agent=agent), None


def _evidence(outcome: Any, model: Any) -> dict:
    """一次调用的证据 → 回包字段。

    优先读 :class:`~campuspath_agents.model.InvocationOutcome`（证据跟着**这次**
    调用走）；拿不到才退回客户端上的 ``last_*``（"最近一次完成的调用"，
    并发下会被别人覆盖）。两条都留着是因为 ``ModelClient`` 协议只要求 ``generate``。
    """
    usage = getattr(outcome, "usage", None)
    if usage is None:
        usage = getattr(model, "last_usage", None)
    rejected = getattr(outcome, "rejected_tools", None)
    if rejected is None:
        rejected = getattr(model, "last_rejected_tools", ())
    return {
        "usage": dict(usage or {}),
        "rejected_tools": [list(pair) for pair in rejected],
        "model": getattr(outcome, "model_id", None) or getattr(model, "model", None),
    }


# --------------------------------------------------------------------------
# 三条口子
# --------------------------------------------------------------------------


def _generate(payload: dict) -> dict:
    """``ModelRequest`` 的四个字段 → 一次 Strands 调用 → 文本 + 证据。

    白名单 hook 与提示词卫生 hook 在**这一侧**的事件循环里生效，被它们拦下的
    工具随回包一起送回去——调用方的注册表靠它说"拦截真的在生效"。
    """
    request, error = _checked_request(payload.get("request"))
    if error is not None:
        return error
    model = model_client()
    run = getattr(model, "run_agent", None)
    if run is None:                       # 非 Strands 的替身：只有纯文本路径
        outcome, text = None, str(model.generate(request)).strip()
    else:
        outcome = run(request)
        text = outcome.text() if hasattr(outcome, "text") else str(outcome).strip()
    return {"result": text, **_evidence(outcome, model)}


def _extract(payload: dict) -> dict:
    """A4 的带工具抽取：原文进来，模型提议的草稿字段出去。

    与本地 ``OpportunityAgent.extract_draft`` 跑的是**同一段事件循环**——
    同一个 system prompt、同一份 ToolSpec、同一条工具带（``belt_for`` 按白名单
    装备，``_equip_defaults`` 补上两个默认实现）。这边**不构造契约对象**：
    ``Opportunity`` / ``Provenance`` / ``OpportunityDraft`` 由 API 侧构造，
    所以"草稿恒为 draft"这条仍然由类型保证，而不是由这边的自觉保证。

    回包里的 ``emitted`` 是**模型的提议**，不是草稿：它进审核队列前还要过
    API 侧的契约构造。名字用 ``emitted`` 而不是 ``draft`` 就是为了这个区别。
    """
    from campuspath_agents.roster import (  # noqa: PLC0415
        A4_SYSTEM_PROMPT,
        A4_TOOL_SPECS,
        OpportunityAgent,
    )
    from campuspath_agents.tools import belt_for  # noqa: PLC0415
    from campuspath_contracts.common import AgentId  # noqa: PLC0415

    spec = payload.get("request")
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        return {"error": "invalid_request", "expected": "object",
                "got": type(spec).__name__}

    raw_content = _text(payload, "raw_content")
    if raw_content is None:
        return {"error": "missing_raw_content"}
    if _oversized(raw_content):
        return _too_large("raw_content")
    source_id = _text(payload, "source_id") or ""
    if _oversized(source_id):
        return _too_large("source_id")

    requested = spec.get("agent")
    if requested and str(requested) != AgentId.A4_OPPORTUNITY.value:
        # 带工具的抽取循环是 A4 的。让别的 Agent 借这条路跑，等于绕开
        # "A4 是唯一处理不可信外部内容的 Agent"（§8.9.1）。
        return {"error": "unsupported_agent", "requested": str(requested),
                "supported": [AgentId.A4_OPPORTUNITY.value]}

    system = _text(spec, "system") or A4_SYSTEM_PROMPT
    if _oversized(system):
        return _too_large("request.system")
    purpose = _text(spec, "purpose") or f"extract:{source_id}"
    if _oversized(purpose):
        return _too_large("request.purpose")

    model = model_client()
    agent = OpportunityAgent(
        agent_id=AgentId.A4_OPPORTUNITY,
        belt=belt_for(AgentId.A4_OPPORTUNITY, {}),   # 空工具带 → 下面补默认实现
        model=model,
    )
    # roster 那边同名的三个动作。它们是 ``extract_draft`` 的前半段——
    # 后半段（构造 OpportunityDraft）需要契约对象，而线上只送得过来原文。
    # ``test_cloud_mirror`` 盯着这三个名字：roster 改了名这边会先红。
    agent._source_id, agent._raw_content = source_id, raw_content
    agent.last_emitted = None
    agent._equip_defaults()

    from campuspath_agents.model import ModelRequest  # noqa: PLC0415

    request = ModelRequest(system=system, data=(raw_content,), purpose=purpose,
                           agent=AgentId.A4_OPPORTUNITY)
    run = getattr(model, "run_agent", None)
    if run is None:                       # 非 Strands 的替身：退回纯文本路径
        outcome, text = None, str(model.generate(request)).strip()
    else:
        outcome = run(request, tools=agent.belt.as_strands_tools(A4_TOOL_SPECS),
                      belt=agent.belt)
        text = outcome.text() if hasattr(outcome, "text") else str(outcome).strip()
    emitted = getattr(agent, "last_emitted", None)
    return {"result": text, "emitted": dict(emitted) if emitted else None,
            **_evidence(outcome, model)}


def _run_agent(payload: dict) -> dict:
    """两个镜像 Agent 的直调。**每次都新建一个 Agent**（F3）。"""
    name = str(payload.get("agent") or "").strip().upper()
    factory = AGENT_FACTORIES.get(name)
    if factory is None:
        return {"error": "unknown_agent", "requested": name,
                "known_agents": sorted(AGENT_FACTORIES)}
    prompt = _text(payload, "prompt")
    if not prompt:
        return {"error": "missing_prompt", "agent": name}
    if _oversized(prompt):
        return _too_large("prompt")
    return {"result": str(factory()(prompt))}


@app.entrypoint
def invoke(payload: dict) -> dict:
    """AgentCore 的调用入口。四种回包：结果、``error``、以及什么都不是的异常——
    最后一种**不允许发生**，所以下面既校验输入，也兜住执行期异常。

    * ``{"kind": "generate", "request": {system, data, purpose, agent}}``
      → ``{"result", "usage", "rejected_tools", "model"}``；
    * ``{"kind": "extract", "request": {...}, "source_id", "raw_content"}``
      → 上面四项 + ``emitted``（模型经 ``emit_opportunity_draft`` 提议的字段）；
    * ``{"agent": "A0"|"A4", "prompt": "…"}`` → ``{"result": …}``：镜像 Agent
      的直调（保留，Console 里手点一次就能看见活着）。

    ``prompt`` / ``data`` / ``raw_content`` 里的内容一律作为 user-role 消息进模型
    （A4 的原文尤其如此，§8.9.1 第 1 条）；system prompt 不来自来源内容。

    ``kind`` 不认识就**拒绝**，不落到某个默认分支上——"kind 拼错了但照样
    跑掉一次真钱调用"是不该发生的静默错误（与 ``unknown_agent`` 同一立场）。
    """
    if not isinstance(payload, dict):
        return {"error": "invalid_payload", "expected": "object",
                "got": type(payload).__name__}
    kind = payload.get("kind")
    kind = KIND_AGENT if kind is None else str(kind).strip().lower()
    if kind not in KNOWN_KINDS:
        return {"error": "unknown_kind", "requested": kind,
                "known_kinds": list(KNOWN_KINDS)}
    try:
        if kind == KIND_GENERATE:
            return _generate(payload)
        if kind == KIND_EXTRACT:
            return _extract(payload)
        return _run_agent(payload)
    except Exception as exc:  # noqa: BLE001
        # **不返回 result**：调用方的 ``_absorb`` 看不到 result 就会抛
        # ``AgentCoreProtocolError``，于是失败是响的。异常文本只带类型 +
        # 前 200 字，不把整个 payload 回显出去。
        return {"error": "invocation_failed", "kind": kind,
                "detail": f"{type(exc).__name__}: {exc}"[:200]}


if __name__ == "__main__":
    app.run()
