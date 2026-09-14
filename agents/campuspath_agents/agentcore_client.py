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

**A4 的工具循环走另一条 kind。** ``OpportunityAgent.extract_draft`` 需要模型
真的能 ``read_source`` / ``emit_opportunity_draft``，而 ToolBelt 的工具是本地闭包，
过不了网线。所以本类不实现 ``run_agent``（那会把本地工具当成能远程执行的东西），
而是提供 :meth:`AgentCoreModelClient.extract_opportunity`：把 ``source_id`` 与
``raw_content`` 一起送过去，**由 runtime 那一侧装配 A4 的 ToolBelt 跑完整事件循环**，
再把 ``emitted``（模型提议的字段）与被拒工具带回来。退回纯 ``generate`` 会让 A4
在这条形态下彻底失去工具——审核队列里"模型提议了什么"的证据就没了。

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

#: 读超时（秒）。AgentCore 一次冷启动 + 多轮工具循环远超 botocore 默认的 60s。
READ_TIMEOUT_ENV = "AGENTCORE_READ_TIMEOUT"
DEFAULT_READ_TIMEOUT = 180
CONNECT_TIMEOUT = 5

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")

#: ``purpose`` 第二段"像不像一个 ID"。学号（``STU-A``）、课号（``COMP 2011``）、
#: 来源号（``SRC-1``）都带数字或大写；``balanced`` 这种变体名不带。
_ID_LIKE_RE = re.compile(r"^(?=.*[0-9A-Z])[0-9A-Za-z][0-9A-Za-z ._@+-]{0,63}$")


class AgentCoreProtocolError(RuntimeError):
    """AgentCore Runtime 的回包不是约定的形状。

    **不返回空串**：空串会让上层以为"模型没话说"，而真相是这次调用根本没成功。
    """


class AgentCoreInvocationFailed(RuntimeError):
    """这次 ``invoke_agent_runtime`` 根本没成功（HTTP 非 200、读超时……）。

    与 :class:`AgentCoreProtocolError` 分开：那条是"回来了但形状不对"，
    这条是"压根没回来"。运维要的是这两句话不同。
    """


def agentcore_selected(env: dict[str, str] | None = None) -> bool:
    """``CAMPUSPATH_AGENT_RUNTIME`` 是否选了 AgentCore。默认否。"""
    env = os.environ if env is None else env
    chosen = (env.get(AGENT_RUNTIME_ENV) or RUNTIME_LOCAL).strip().lower()
    return chosen == RUNTIME_AGENTCORE


def session_key_for(purpose: str) -> str:
    """``purpose`` → 会话分组键：**只取第一段（调用类别）**。空 purpose 返回空串。

    2026-09-14 实测：按"前缀 + 当事人 id"分片时，一个新学生的首次规划要为几十门课
    各冷启一个 microVM（``skill_tags:COMPxxxx`` 每门一个，每个 ~10 s），经 Web 代理
    直接 504。而"会话共享上下文"的顾虑在本设计里不成立：运行时**每次调用都新建**
    Strands ``Agent``，不挂 session manager，进程级客户端也不保留任何请求
    （审查 F1/F3 已改）——同一 ``runtimeSessionId`` 下两次调用彼此看不见。
    所以按类别分组即可：类别数固定（十个左右），冷启动只在每类首次或空闲 15 分钟后。
    """
    parts = purpose.split(":")
    return parts[0].strip()


def session_id_for(purpose: str) -> str:
    """按 :func:`session_key_for` 给出稳定的会话 ID。

    没有 purpose 时给一个随机 ID——宁可多几次冷启动，也不要把两件不相干的事
    塞进同一个会话。

    长度永远 ≥ :data:`MIN_SESSION_ID_LENGTH`：这是服务端的硬校验，
    不是我们的偏好。
    """
    key = session_key_for(purpose)
    if not key:
        return f"campuspath-adhoc-{uuid.uuid4().hex}"
    slug = _SLUG_RE.sub("-", key)[:48]
    #: 摘要取**完整的 key**，不是截断后的 slug——否则两个长学号会撞进同一会话。
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"campuspath-{slug}-{digest}"[:256]


class AgentCoreModelClient:
    """把 :class:`ModelRequest` 送进 AgentCore Runtime，拿回文本。

    表面与 :class:`~.model.StrandsModelClient` 对齐（``generate`` / ``backend`` /
    ``runtime`` / ``model`` / ``region`` / ``last_usage`` / ``last_rejected_tools``），
    API 层因此不需要知道模型在哪边跑。**请求本身一份都不留**——
    这条边界的全部价值就是本地不存学生原文。

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
        #: **最近一次完成的**调用的用量 / 被拒工具（注册表展示用）。
        #: 并发下是"最后写的赢"；判断某次调用发生了什么要看它的返回值。
        self.last_usage: dict[str, int] | None = None
        self.last_rejected_tools: tuple[tuple[str, str], ...] = ()
        self._read_timeout = _read_timeout_from(env)
        self._client = client

    def _note(self, request: ModelRequest) -> None:
        """**不记。** 请求里装的是学生原文；这条边界的价值就是本地不留副本。"""
        return None

    # -- boto 客户端 ---------------------------------------------------------
    @property
    def client(self) -> Any:
        """惰性构造的 boto 客户端。**超时与重试都写死在这里。**

        botocore 的默认配置在这条链路上有两个问题：

        * ``read_timeout=60`` —— AgentCore 一次冷启动加上多轮工具循环会超过它，
          于是"慢"被报成"失败"；
        * legacy 重试模式 —— 读超时后 botocore 会**自动重发**。
          ``invoke_agent_runtime`` 是按调用计费的：一次 A5 取舍可能被真跑两遍，
          钱付两遍，而调用方只看到一次失败。所以 ``max_attempts=1``：
          重试这件事该由知道"这次调用花不花钱"的那一层决定。
        """
        if self._client is None:
            import boto3  # noqa: PLC0415
            from botocore.config import Config  # noqa: PLC0415

            self._client = boto3.client(
                SERVICE_NAME, region_name=self.region,
                config=Config(connect_timeout=CONNECT_TIMEOUT,
                              read_timeout=self._read_timeout,
                              retries={"max_attempts": 1, "mode": "standard"}),
            )
        return self._client

    # -- 序列化 ---------------------------------------------------------------
    @staticmethod
    def request_fields(request: ModelRequest) -> dict[str, Any]:
        """``ModelRequest`` → 线上 JSON。**只有这四个字段能过去。**"""
        return {
            "system": request.system,
            "data": list(request.data),
            "purpose": request.purpose,
            "agent": request.agent.value if request.agent is not None else None,
        }

    @classmethod
    def payload_for(cls, request: ModelRequest) -> dict[str, Any]:
        return {"kind": "generate", "request": cls.request_fields(request)}

    @classmethod
    def extract_payload_for(cls, request: ModelRequest, *, source_id: str,
                            raw_content: str) -> dict[str, Any]:
        """A4 的抽取调用。``raw_content`` 是**外部不可信内容**，在 runtime 那侧
        只会经 ``read_source`` 工具与 ``data`` 块进模型，永不拼进 system prompt。
        """
        return {"kind": "extract", "request": cls.request_fields(request),
                "source_id": source_id, "raw_content": raw_content}

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

    def _absorb(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """回包 → 这次调用的证据（并顺手更新"最近一次完成"的那份）。

        返回值是**本次调用**的，调用方读它；``last_*`` 属性只给注册表看。
        """
        if "result" not in parsed:
            detail = parsed.get("error")
            raise AgentCoreProtocolError(
                "AgentCore Runtime 的回包里没有 'result' 字段"
                + (f"；它回的是 error={detail!r}（{parsed}）" if detail is not None
                   else f"：keys={sorted(parsed)}")
            )
        usage = parsed.get("usage") or None
        absorbed = {
            "result": str(parsed["result"]).strip(),
            "usage": ({k: int(v) for k, v in usage.items() if isinstance(v, (int, float))}
                      if isinstance(usage, dict) and usage else None),
            "rejected_tools": tuple(
                (str(pair[0]), str(pair[1]))
                for pair in (parsed.get("rejected_tools") or ())
                if isinstance(pair, (list, tuple)) and len(pair) >= 2
            ),
            "emitted": parsed.get("emitted") if isinstance(
                parsed.get("emitted"), dict) else None,
        }
        reported = parsed.get("model")
        if reported:
            self.model = str(reported)
        absorbed["model"] = self.model
        self.last_usage = absorbed["usage"]
        self.last_rejected_tools = absorbed["rejected_tools"]
        return absorbed

    # -- 调用 -----------------------------------------------------------------
    def _invoke(self, payload: dict[str, Any], request: ModelRequest,
                *, kind: str) -> dict[str, Any]:
        """一次出境调用：序列化 → invoke → 校验 HTTP → 解析 → 吸收证据。"""
        blob = json.dumps(payload, ensure_ascii=False).encode()
        session_id = session_id_for(request.purpose)
        attrs: dict[str, Any] = {
            "gen_ai.system": self.backend,
            "gen_ai.request.model": self.model,
            "campuspath.runtime": RUNTIME_AGENTCORE,
            "campuspath.purpose": request.purpose,
            "campuspath.data_blocks": len(request.data),
            "campuspath.agentcore.kind": kind,
            "campuspath.agentcore.session": session_id,
            "campuspath.agentcore.payload_bytes": len(blob),
        }
        if request.agent is not None:
            attrs["campuspath.agent"] = request.agent.value
        with span("gen_ai.generate", **attrs) as current:
            try:
                response = self.client.invoke_agent_runtime(
                    agentRuntimeArn=self.runtime_arn,
                    runtimeSessionId=session_id,
                    payload=blob,
                    qualifier=self.qualifier,
                    contentType="application/json",
                    accept="application/json",
                )
            except _timeout_errors() as exc:
                raise AgentCoreInvocationFailed(
                    f"AgentCore Runtime 在 {self._read_timeout}s 内没有回应"
                    f"（purpose={request.purpose!r}，kind={kind}）：{exc}"
                ) from exc
            _assert_ok(response, request, kind)
            absorbed = self._absorb(self._decode(response))
            usage = absorbed["usage"] or {}
            current.set_attributes({
                "gen_ai.usage.input_tokens": usage.get("inputTokens", 0),
                "gen_ai.usage.output_tokens": usage.get("outputTokens", 0),
                "campuspath.tool_rejections": len(absorbed["rejected_tools"]),
            })
        return absorbed

    def generate(self, request: ModelRequest) -> str:
        self._note(request)
        return self._invoke(self.payload_for(request), request,
                            kind="generate")["result"]

    def extract_opportunity(self, request: ModelRequest, *, source_id: str,
                            raw_content: str) -> dict[str, Any]:
        """A4 的抽取：**工具循环留在 runtime 那一侧**。

        纯 ``generate`` 会让 A4 在 AgentCore 形态下失去工具——
        ``emit_opportunity_draft`` 不会被调用，``last_emitted`` 永远是 None，
        审核队列里"模型提议了什么"这条证据就没了；被拒的
        ``publish_opportunity`` 也不会再有记录。所以这条 kind 把
        ``source_id`` / ``raw_content`` 一起送过去，由 runtime 装配
        A4 的 ToolBelt 跑完整的事件循环，再把 ``emitted`` 带回来。

        返回 ``{"result", "usage", "rejected_tools", "model", "emitted"}``。
        """
        self._note(request)
        return self._invoke(
            self.extract_payload_for(request, source_id=source_id,
                                     raw_content=raw_content),
            request, kind="extract")

    def generate_grounded(self, request: ModelRequest) -> str:
        raise GroundingUnavailable(
            "AgentCore Runtime 形态下没有接地检索工具（Google Search 是 Vertex "
            "原生工具）；现场市场研究需要 Vertex 后端"
        )


def _read_timeout_from(env: dict[str, str]) -> int:
    raw = (env.get(READ_TIMEOUT_ENV) or "").strip()
    try:
        return int(raw) if raw else DEFAULT_READ_TIMEOUT
    except ValueError:
        return DEFAULT_READ_TIMEOUT


def _timeout_errors() -> tuple[type[BaseException], ...]:
    """botocore 的超时异常类。botocore 缺席时返回空元组（``except ()`` 合法）。"""
    try:
        from botocore.exceptions import (  # noqa: PLC0415
            ConnectTimeoutError,
            ReadTimeoutError,
        )
    except ImportError:                       # pragma: no cover —— 装了 boto3 就有它
        return ()
    return (ReadTimeoutError, ConnectTimeoutError)


def _assert_ok(response: dict[str, Any], request: ModelRequest, kind: str) -> None:
    """HTTP 层先过一遍。**非 200 不解析回包**——500 的 body 不是答案。"""
    status = response.get("statusCode")
    if status is None or int(status) == 200:
        return
    raise AgentCoreInvocationFailed(
        f"AgentCore Runtime 回了 HTTP {status}（purpose={request.purpose!r}，"
        f"kind={kind}）；回包未被当作答案解析"
    )


def agent_id_from(value: str | None) -> AgentId | None:
    """``"A4"`` → ``AgentId.A4_OPPORTUNITY``；None/空 → None。runtime 侧也用它。"""
    if not value:
        return None
    return AgentId(value)
