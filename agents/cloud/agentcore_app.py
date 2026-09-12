"""Amazon Bedrock AgentCore 的入口模块（Agents for Humans Hackathon 部署形态）。

AgentCore Runtime 要的是一个 HTTP 服务：``BedrockAgentCoreApp`` 起服务，
``@app.entrypoint`` 装饰的函数收 payload、回 JSON。本模块就是那一层，
**它不做任何判断**——判断在两个 root_agent 里，这里只负责路由到谁。

``bedrock_agentcore`` 在部署镜像里一定有，本地/CI 未必。缺席时下面会退回一个
同形替身，目的很具体：``invoke()`` 的路由逻辑要能在 CI 里被调用、被断言，
而不是等部署之后在云上第一次发现 payload 的 key 拼错了。
替身的 ``run()`` 故意抛异常——**本地起不了真服务这件事必须响**，
不能让人以为自己在跑 AgentCore。
"""

from __future__ import annotations

import pathlib
import sys
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


@app.entrypoint
def invoke(payload: dict) -> dict:
    """AgentCore 的调用入口。``{"agent": "A0"|"A4", "prompt": "…"}`` → ``{"result": …}``。

    ``prompt`` 里的内容一律作为 user-role 消息进模型（A4 的原文尤其如此，
    §8.9.1 第 1 条）；system prompt 是两个 Agent 各自写死的指令。
    """
    name = str(payload.get("agent") or "").strip().upper()
    agent = AGENTS.get(name)
    if agent is None:
        return {"error": "unknown_agent", "requested": name,
                "known_agents": sorted(AGENTS)}
    result = agent(payload["prompt"])
    return {"result": str(result)}


if __name__ == "__main__":
    app.run()
