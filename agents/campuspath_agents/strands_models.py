"""Strands Agents 的模型后端：一个工厂，三种后端。

2026-09-12 起（Agents for Humans Hackathon，硬性要求 Strands Agents SDK）
CampusPath 的**每一次模型调用都是一次 Strands ``Agent`` 调用**——
Agent 事件循环、hooks、工具调度、追踪都由 Strands 负责，本包只决定：

* **用哪个模型**（这里）：``bedrock``（Amazon Bedrock，主）/ ``vertex``
  （Gemini on Vertex AI，保留）/ 剧本桩（测试，零成本）；
* **谁能调什么工具**（``hooks.py`` + ``tools.py``）；
* **什么内容不准进模型**（``hooks.PromptHygieneHook``）。

三种后端实现同一个 Strands ``Model`` 接口，Agent 代码不知道自己在跟谁说话。

钱的规则不变：Vertex 后端构造前经 :func:`campuspath_agents.vertex.assert_vertex_only`
把关；**禁止** ``GeminiModel(client_args={"api_key": ...})``——那是 AI Studio，直扣个人卡。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import AsyncGenerator, AsyncIterable, Coroutine
from typing import Any, TypeVar

from strands.models.model import Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

T = TypeVar("T")

#: 选后端的环境变量。默认 Bedrock——比赛形态"整个走 AWS"。
BACKEND_ENV = "CAMPUSPATH_MODEL_BACKEND"
BACKEND_BEDROCK = "bedrock"
BACKEND_VERTEX = "vertex"
BACKEND_SCRIPTED = "scripted"
BACKENDS = frozenset({BACKEND_BEDROCK, BACKEND_VERTEX})

#: Bedrock 模型 ID（跨区域推理配置）。可用 ``BEDROCK_MODEL_ID`` 覆盖。
BEDROCK_MODEL_ENV = "BEDROCK_MODEL_ID"
DEFAULT_BEDROCK_MODEL = "us.amazon.nova-pro-v1:0"
BEDROCK_REGION_ENV = "AWS_REGION"
DEFAULT_BEDROCK_REGION = "us-east-1"


class UnknownBackend(ValueError):
    """``CAMPUSPATH_MODEL_BACKEND`` 不是 bedrock / vertex。"""


def resolve_backend(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    chosen = (env.get(BACKEND_ENV) or BACKEND_BEDROCK).strip().lower()
    if chosen not in BACKENDS:
        raise UnknownBackend(
            f"{BACKEND_ENV}={chosen!r}；可选 {sorted(BACKENDS)}"
        )
    return chosen


# --------------------------------------------------------------------------
# 事件循环：一条常驻线程，所有 Strands 调用都在它上面跑
# --------------------------------------------------------------------------
#
# 为什么不是每次 ``asyncio.run``：google-genai 的 aio 客户端把 httpx 连接池
# 绑在**第一次**用它的循环上，第二次同步调用换了循环就报
# ``RuntimeError: Event loop is closed``（2026-09-12 实测）。一条常驻循环
# 让客户端可以复用（省掉每次 ~18s 的 ADC 冷启动），Bedrock/桩也同样受益。


class _LoopThread:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=loop.run_forever, name="campuspath-strands-loop", daemon=True
                )
                thread.start()
                self._loop = loop
            return self._loop

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        loop = self._ensure()
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            raise RuntimeError("不能在 Strands 循环线程内再同步等待自己")
        return asyncio.run_coroutine_threadsafe(coro, loop).result()


_LOOP = _LoopThread()


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """在常驻循环上同步执行一个协程。API 层的同步端点从这里进 Strands。"""
    return _LOOP.run(coro)


# --------------------------------------------------------------------------
# 剧本桩：Strands ``Model`` 的确定性实现
# --------------------------------------------------------------------------


class ScriptedStrandsModel(Model):
    """按 ``purpose`` 回放预设答案的 Strands 模型。

    ``purpose`` 由调用方经 ``invocation_state`` 传入（``StrandsModelClient`` 负责）。
    剧本值有两种形态：

    * ``str`` —— 作为一段文本回复；
    * ``{"tool": 名字, "input": {...}}`` —— 发起一次工具调用；工具结果回来后
      的下一轮回 ``"done"``（或剧本里 ``f"{purpose}#after_tool"`` 的值）。

    未预设的 purpose **抛异常**，不返回空串——空串会让 Agent 走进
    "模型没说话"的分支，而测试作者以为自己测的是正常路径。
    """

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script: dict[str, Any] = dict(script or {})
        self.seen: list[str] = []
        #: ``structured_output`` 拿不到 invocation_state，调用方先把 purpose 放这里。
        self.pending_purpose: str | None = None

    # Strands Model 接口 ---------------------------------------------------
    def update_config(self, **model_config: Any) -> None:  # noqa: D102
        return None

    def get_config(self) -> dict[str, Any]:  # noqa: D102
        return {"model_id": "scripted"}

    def _answer_for(self, purpose: str | None) -> Any:
        if purpose is None or purpose not in self.script:
            raise KeyError(
                f"ScriptedModel 没有为 purpose={purpose!r} 预设答案。"
                "补上预设，或确认这条调用路径是否本该发生"
            )
        return self.script[purpose]

    async def stream(  # noqa: D102
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        purpose = (invocation_state or {}).get("purpose") or self.pending_purpose
        self.seen.append(purpose)
        answer = self._answer_for(purpose)
        last = messages[-1] if messages else {"content": []}
        if any("toolResult" in block for block in last.get("content", [])):
            answer = self.script.get(f"{purpose}#after_tool", "done")

        yield {"messageStart": {"role": "assistant"}}
        if isinstance(answer, dict) and "tool" in answer:
            yield {"contentBlockStart": {"start": {"toolUse": {
                "toolUseId": f"scripted-{len(self.seen)}", "name": answer["tool"]}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {
                "input": json.dumps(answer.get("input", {}), ensure_ascii=False)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": str(answer)}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {
            "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            "metrics": {"latencyMs": 0},
        }}

    async def structured_output(  # noqa: D102
        self, output_model: type[T], prompt: Messages, system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        purpose = (kwargs.get("invocation_state") or {}).get("purpose") or self.pending_purpose
        self.seen.append(purpose)
        answer = self._answer_for(purpose)
        payload = json.loads(answer) if isinstance(answer, str) else answer
        yield {"output": output_model(**payload)}


# --------------------------------------------------------------------------
# 真实后端
# --------------------------------------------------------------------------


def build_bedrock_model(model_id: str | None = None, region: str | None = None,
                        env: dict[str, str] | None = None, **params: Any) -> Any:
    """Amazon Bedrock（Strands 默认后端）。凭据走 AWS SDK 默认链（env / profile / 角色）。"""
    from strands.models import BedrockModel  # noqa: PLC0415

    env = os.environ if env is None else env
    chosen = model_id or env.get(BEDROCK_MODEL_ENV) or DEFAULT_BEDROCK_MODEL
    region_name = region or env.get(BEDROCK_REGION_ENV) or DEFAULT_BEDROCK_REGION
    params.setdefault("temperature", 0.2)
    return BedrockModel(model_id=chosen, region_name=region_name, **params)


def build_gemini_model(model: str | None = None, *, thinking_level: str | None = "MINIMAL",
                       env: dict[str, str] | None = None) -> Any:
    """Gemini on Vertex AI。构造前断言走 Vertex（B12），并检查代际门槛。

    Strands 文档的示例只写 ``api_key``；这里把现成的 ``genai.Client(vertexai=True)``
    作为 ``client=`` 传入（源码 ``_get_client`` 直接返回注入的客户端）。
    """
    from google import genai  # noqa: PLC0415  # ai-studio-denylist
    from strands.models.gemini import GeminiModel  # noqa: PLC0415

    from .model import resolve_model  # noqa: PLC0415
    from .vertex import assert_vertex_only, vertex_config  # noqa: PLC0415

    assert_vertex_only(env)
    config = vertex_config(env)
    chosen = resolve_model(model, env)
    client = genai.Client(vertexai=True, project=config.project, location=config.location)
    params: dict[str, Any] = {"temperature": 0.2}
    if thinking_level is not None:
        params["thinking_config"] = {"thinking_level": thinking_level}
    return GeminiModel(client=client, model_id=chosen, params=params)
