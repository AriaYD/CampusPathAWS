"""Amazon Bedrock AgentCore 的入口模块（Agents for Humans Hackathon 部署形态）。

AgentCore Runtime 要的是一个 HTTP 服务：``BedrockAgentCoreApp`` 起服务，
``@app.entrypoint`` 装饰的函数收 payload、回 JSON。本模块就是那一层，
**它不做任何判断**——判断在 Agent 那边，这里只负责路由。

两条口子（2026-09-12 P3 起）：

* ``kind="generate"`` —— **整个语义平面（A0–A5）的模型调用**。API 进程
  （Cloud Run）把 ``ModelRequest`` 的四个字段送进来，这边用进程级
  :class:`~campuspath_agents.model.BedrockModelClient` 跑完整的 Strands 事件
  循环（白名单 hook、提示词卫生 hook 都在**这一侧**生效），回文本 + 用量 +
  被拒工具 + 模型 ID。凭据、学生档案、日历过不来——payload 里没有字段装它们；
* ``{"agent","prompt"}`` —— 两个 root_agent 的直调（保留）。

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

from opportunity_scout_agent.agent import root_agent as scout_agent  # noqa: E402
from orchestrator_agent.agent import root_agent as orchestrator_agent  # noqa: E402

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

#: 能被这个入口调起的 Agent。**白名单式**：不在表里的一律拒绝，
#: 不落到某个默认 Agent 上——"A9 被当成 A0 跑了"是不该发生的静默错误。
AGENTS = {"A0": orchestrator_agent, "A4": scout_agent}

app = BedrockAgentCoreApp()

#: 进程级模型客户端（``kind="generate"`` 用）。**惰性构造**：
#: ``BedrockModelClient()`` 一建就去问 AWS 凭据，而本模块必须能在
#: 没有凭据的机器上被导入并测试。测试直接替换这个名字。
_MODEL: Any = None
_MODEL_LOCK = threading.Lock()

#: 本入口认识的 payload 形态。``kind`` 缺省等于 ``agent``（老形态，向后兼容）。
KIND_GENERATE = "generate"
KIND_AGENT = "agent"
KNOWN_KINDS = (KIND_GENERATE, KIND_AGENT)


def model_client() -> Any:
    """整个 Runtime 共用的一个 :class:`BedrockModelClient`（连接与凭据只建一次）。"""
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                from campuspath_agents.model import BedrockModelClient  # noqa: PLC0415

                _MODEL = BedrockModelClient()
    return _MODEL


def _generate(spec: dict) -> dict:
    """``ModelRequest`` 的四个字段 → 一次 Strands 调用 → 文本 + 证据。

    API 侧（Cloud Run）只送 ``system`` / ``data`` / ``purpose`` / ``agent``；
    白名单 hook 与提示词卫生 hook 在**这一侧**的事件循环里生效，被它们拦下的
    工具随回包一起送回去——调用方的注册表靠它说"拦截真的在生效"。
    """
    from campuspath_agents.model import ModelRequest  # noqa: PLC0415
    from campuspath_contracts.common import AgentId  # noqa: PLC0415

    agent_value = spec.get("agent")
    request = ModelRequest(
        system=str(spec.get("system") or ""),
        data=tuple(str(block) for block in (spec.get("data") or ())),
        purpose=str(spec.get("purpose") or ""),
        agent=AgentId(agent_value) if agent_value else None,
    )
    model = model_client()
    result = model.generate(request)
    return {
        "result": result,
        "usage": dict(getattr(model, "last_usage", None) or {}),
        "rejected_tools": [list(pair) for pair in getattr(model, "last_rejected_tools", ())],
        "model": getattr(model, "model", None),
    }


def _run_agent(payload: dict) -> dict:
    name = str(payload.get("agent") or "").strip().upper()
    agent = AGENTS.get(name)
    if agent is None:
        return {"error": "unknown_agent", "requested": name,
                "known_agents": sorted(AGENTS)}
    result = agent(payload["prompt"])
    return {"result": str(result)}


@app.entrypoint
def invoke(payload: dict) -> dict:
    """AgentCore 的调用入口。两种 payload：

    * ``{"kind": "generate", "request": {system, data, purpose, agent}}``
      → ``{"result", "usage", "rejected_tools", "model"}``：整个语义平面
      （A0–A5）的模型调用都走这一条，API 进程那边只剩编排与契约；
    * ``{"agent": "A0"|"A4", "prompt": "…"}`` → ``{"result": …}``：两个
      root_agent 的直调（保留，Console 里手点一次就能看见活着）。

    ``prompt`` / ``data`` 里的内容一律作为 user-role 消息进模型（A4 的原文
    尤其如此，§8.9.1 第 1 条）；system prompt 只来自本仓写死的指令。

    ``kind`` 不认识就**拒绝**，不落到某个默认分支上——"kind 拼错了但照样
    跑掉一次真钱调用"是不该发生的静默错误（与 ``unknown_agent`` 同一立场）。
    """
    kind = payload.get("kind")
    if kind is None:
        return _run_agent(payload)
    kind = str(kind).strip().lower()
    if kind == KIND_GENERATE:
        return _generate(payload.get("request") or {})
    if kind == KIND_AGENT:
        return _run_agent(payload)
    return {"error": "unknown_kind", "requested": kind,
            "known_kinds": list(KNOWN_KINDS)}


if __name__ == "__main__":
    app.run()
