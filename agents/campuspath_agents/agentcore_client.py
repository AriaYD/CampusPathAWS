"""语义平面跑在 **Bedrock AgentCore Runtime** 上时，API 侧用的模型客户端（P3）。

`CAMPUSPATH_AGENT_RUNTIME=agentcore` 之后，A0–A5 的每一次模型调用都不再在
API 进程里发生：:class:`AgentCoreModelClient` 把 :class:`~.model.ModelRequest`
序列化成一段 JSON，经 ``invoke_agent_runtime`` 送进 AgentCore Runtime，
在那边由 :mod:`campuspath_cloud.agentcore_app` 用同一个
:class:`~.model.BedrockModelClient` 跑完整的 Strands 事件循环（同样的白名单 hook、
同样的提示词卫生 hook），再把**文本 + 用量 + 被拒工具 + 模型 ID** 回给这边。

**这条边界的价值在于它把什么留在了本地。** 过去的只有四个字段——
``system`` / ``data`` / ``purpose`` / ``agent``。日历凭据、学生档案、
Reflection 原文没有字段可装，所以"不会泄漏"是形状决定的，不是纪律决定的
（CLAUDE.md 架构第 3 条在这条链路上继续成立）。

**A4 不走这条路。** ``OpportunityAgent.extract_draft`` 需要 ``run_agent(...,
tools=belt.as_strands_tools(...), belt=belt)``，而 ToolBelt 的工具是**本地闭包**
（读数据库、写草稿），它们过不了网线。本类因此**故意不实现** ``run_agent``：
:mod:`campuspath_agents.roster` 看到没有 ``run_agent`` 就退回纯文本路径，
A4 的抽取仍由 API 侧自己的进程内模型跑。要让 A4 整体上云，得先把它的工具
搬成 AgentCore Gateway 目标，那是另一件事。

本地与 CI 里 ``CAMPUSPATH_AGENT_RUNTIME`` 不设（默认 ``local``），一切照旧在
进程内跑——这个模块的所有测试都用注入的假 boto 客户端，零 AWS 调用、零费用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any

from campuspath_contracts.common import AgentId

from .model import GroundingUnavailable, ModelRequest
from .strands_models import (
    BACKEND_BEDROCK,
    BEDROCK_MODEL_ENV,
    BEDROCK_REGION_ENV,
    DEFAULT_BEDROCK_MODEL,
    DEFAULT_BEDROCK_REGION,
)
from .telemetry import span

#: Agent 运行时在哪。``local``（默认，进程内 Strands）或 ``agentcore``。
AGENT_RUNTIME_ENV = "CAMPUSPATH_AGENT_RUNTIME"
RUNTIME_LOCAL = "local"
RUNTIME_AGENTCORE = "agentcore"

#: 目标 Runtime 的 ARN。选了 ``agentcore`` 却没给它 → 没有可用后端（见
#: :func:`campuspath_agents.model.autodetect_model`），**不退回本地 Bedrock**。
RUNTIME_ARN_ENV = "AGENTCORE_RUNTIME_ARN"

#: ``invoke_agent_runtime`` 的默认端点限定符。
DEFAULT_QUALIFIER = "DEFAULT"

#: AgentCore 对 ``runtimeSessionId`` 的硬约束（botocore 模型：min 33 / max 256）。
#: 写在这里是因为它是**服务端**的数字：短一个字符就是 ValidationException。
MIN_SESSION_ID_LENGTH = 33

#: boto 客户端的服务名。
SERVICE_NAME = "bedrock-agentcore"

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")


class AgentCoreProtocolError(RuntimeError):
    """AgentCore Runtime 的回包不是约定的形状。

    **不返回空串**：空串会让上层以为"模型没话说"，而真相是这次调用根本没成功。
    """


def agentcore_selected(env: dict[str, str] | None = None) -> bool:
    """``CAMPUSPATH_AGENT_RUNTIME`` 是否选了 AgentCore。默认否。"""
    env = os.environ if env is None else env
    chosen = (env.get(AGENT_RUNTIME_ENV) or RUNTIME_LOCAL).strip().lower()
    return chosen == RUNTIME_AGENTCORE


def session_id_for(purpose: str) -> str:
    """按 ``purpose`` 的前缀（``:`` 之前那段）给出稳定的会话 ID。

    同一类调用（``pathway:S1`` / ``pathway:S2``）落在同一个 AgentCore 会话上，
    冷启动只付一次；不同类之间互不串味。没有 purpose 时给一个随机 ID——
    宁可多几次冷启动，也不要把两件不相干的事塞进同一个会话。

    长度永远 ≥ :data:`MIN_SESSION_ID_LENGTH`：这是服务端的硬校验，
    不是我们的偏好。
    """
    prefix = _SLUG_RE.sub("-", purpose.split(":", 1)[0].strip())[:32]
    if not prefix:
        return f"campuspath-adhoc-{uuid.uuid4().hex}"
    digest = hashlib.sha256(prefix.encode()).hexdigest()
    return f"campuspath-{prefix}-{digest}"[:256]


class AgentCoreModelClient:
    """把 :class:`ModelRequest` 送进 AgentCore Runtime，拿回文本。

    表面与 :class:`~.model.StrandsModelClient` 对齐（``generate`` / ``backend`` /
    ``runtime`` / ``model`` / ``region`` / ``last_usage`` / ``last_rejected_tools`` /
    ``calls`` / ``system_prompts``），API 层因此不需要知道模型在哪边跑。

    ``client`` 参数是给测试注入假 boto 客户端用的；生产不传，第一次调用时
    才惰性构造——**构造即凭据查询**，而 API 进程在没有 AWS 凭据的机器上
    也必须能起来（依赖模型的端点照旧 503）。
    """

    def __init__(
        self,
        runtime_arn: str,
        region: str | None = None,
        *,
        client: Any = None,
        qualifier: str = DEFAULT_QUALIFIER,
        model_id: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        env = os.environ if env is None else env
        if not runtime_arn:
            raise ValueError(
                f"AgentCore Runtime ARN 为空；设 {RUNTIME_ARN_ENV} 或显式传入"
            )
        self.runtime_arn = runtime_arn
        self.region = region or env.get(BEDROCK_REGION_ENV) or DEFAULT_BEDROCK_REGION
        self.qualifier = qualifier
        self.backend = BACKEND_BEDROCK
        self.runtime = RUNTIME_AGENTCORE
        #: runtime 还没回报过模型 ID 之前，报**配置里会用的那个**——
        #: 运维看注册表时需要知道钱会花在哪个模型上，而不是 "unknown"。
        self.model = model_id or env.get(BEDROCK_MODEL_ENV) or DEFAULT_BEDROCK_MODEL
        self.last_model_version: str | None = None
        self.last_usage: dict[str, int] | None = None
        self.last_rejected_tools: tuple[tuple[str, str], ...] = ()
        self.calls: list[ModelRequest] = []
        self._client = client

    # -- boto 客户端 ---------------------------------------------------------
    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3  # noqa: PLC0415

            self._client = boto3.client(SERVICE_NAME, region_name=self.region)
        return self._client

    # -- 序列化 ---------------------------------------------------------------
    @staticmethod
    def payload_for(request: ModelRequest) -> dict[str, Any]:
        """``ModelRequest`` → 线上 JSON。**只有这四个字段能过去。**"""
        return {"kind": "generate", "request": {
            "system": request.system,
            "data": list(request.data),
            "purpose": request.purpose,
            "agent": request.agent.value if request.agent is not None else None,
        }}

    # -- 反序列化 -------------------------------------------------------------
    @staticmethod
    def _decode(response: dict[str, Any]) -> dict[str, Any]:
        body = response.get("response")
        if body is None:
            raise AgentCoreProtocolError(
                f"AgentCore 回包里没有 response 体：keys={sorted(response)}"
            )
        raw = body.read() if hasattr(body, "read") else body
        if isinstance(raw, (list, tuple)):          # 分块流：拼回来再解析
            raw = b"".join(
                chunk if isinstance(chunk, bytes) else str(chunk).encode()
                for chunk in raw
            )
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentCoreProtocolError(
                f"AgentCore 回包不是 JSON：{str(raw)[:200]!r}"
            ) from exc
        if not isinstance(parsed, dict):
            raise AgentCoreProtocolError(
                f"AgentCore 回包不是对象而是 {type(parsed).__name__}：{str(raw)[:200]!r}"
            )
        return parsed

    def _absorb(self, parsed: dict[str, Any]) -> str:
        if "result" not in parsed:
            detail = parsed.get("error")
            raise AgentCoreProtocolError(
                "AgentCore Runtime 的回包里没有 'result' 字段"
                + (f"；它回的是 error={detail!r}（{parsed}）" if detail is not None
                   else f"：keys={sorted(parsed)}")
            )
        usage = parsed.get("usage") or None
        self.last_usage = (
            {k: int(v) for k, v in usage.items() if isinstance(v, (int, float))}
            if isinstance(usage, dict) and usage else None
        )
        self.last_rejected_tools = tuple(
            (str(pair[0]), str(pair[1]))
            for pair in (parsed.get("rejected_tools") or ())
            if isinstance(pair, (list, tuple)) and len(pair) >= 2
        )
        reported = parsed.get("model")
        if reported:
            self.model = str(reported)
        return str(parsed["result"]).strip()

    # -- 调用 -----------------------------------------------------------------
    def generate(self, request: ModelRequest) -> str:
        self.calls.append(request)
        payload = json.dumps(self.payload_for(request), ensure_ascii=False).encode()
        session_id = session_id_for(request.purpose)
        attrs: dict[str, Any] = {
            "gen_ai.system": self.backend,
            "gen_ai.request.model": self.model,
            "campuspath.runtime": RUNTIME_AGENTCORE,
            "campuspath.purpose": request.purpose,
            "campuspath.data_blocks": len(request.data),
            "campuspath.agentcore.session": session_id,
            "campuspath.agentcore.payload_bytes": len(payload),
        }
        if request.agent is not None:
            attrs["campuspath.agent"] = request.agent.value
        with span("gen_ai.generate", **attrs) as current:
            response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.runtime_arn,
                runtimeSessionId=session_id,
                payload=payload,
                qualifier=self.qualifier,
                contentType="application/json",
                accept="application/json",
            )
            text = self._absorb(self._decode(response))
            usage = self.last_usage or {}
            current.set_attributes({
                "gen_ai.usage.input_tokens": usage.get("inputTokens", 0),
                "gen_ai.usage.output_tokens": usage.get("outputTokens", 0),
                "campuspath.tool_rejections": len(self.last_rejected_tools),
            })
        return text

    def generate_grounded(self, request: ModelRequest) -> str:
        raise GroundingUnavailable(
            "AgentCore Runtime 形态下没有接地检索工具（Google Search 是 Vertex "
            "原生工具）；现场市场研究需要 Vertex 后端"
        )

    def system_prompts(self) -> list[str]:
        return [c.system for c in self.calls]


def agent_id_from(value: str | None) -> AgentId | None:
    """``"A4"`` → ``AgentId.A4_OPPORTUNITY``；None/空 → None。runtime 侧也用它。"""
    if not value:
        return None
    return AgentId(value)
