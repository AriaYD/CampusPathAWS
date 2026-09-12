"""Strands hooks：把架构硬约束挂进 Agent 事件循环。

提示词里写"不要调用发布工具"是请求，hook 里拒绝才是强制。
两条约束在这里落地（Spec §8.9）：

* **第 4 条 工具白名单** —— :class:`ToolWhitelistHook` 在 ``BeforeToolCallEvent``
  查 ``contracts.agents.AGENT_TOOL_WHITELIST`` 与禁止前缀，不在名单上的调用
  **取消**（模型收到的是拒绝说明，不是执行结果），并写进 ToolBelt 的审计日志；
* **第 3 条 Calendar Token 不进任何 LLM 上下文** —— :class:`PromptHygieneHook`
  在 ``BeforeModelCallEvent`` 扫描即将发出的全部消息，命中凭据形态就**抛异常**，
  整次调用失败——宁可失败，也不让 token 出门。

两个 hook 都不看模型是谁。剧本桩、Bedrock、Vertex 一视同仁，
所以 CI 里就能证明它们真的会拦。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from strands.hooks import (
    AfterToolCallEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

from campuspath_contracts.agents import (
    FORBIDDEN_TOOL_PATTERNS,
    ToolPermissionError,
    assert_tool_allowed,
)
from campuspath_contracts.common import AgentId

from .telemetry import span


class ToolWhitelistHook(HookProvider):
    """每次工具调用前重查白名单；被拒的调用在 belt 日志与 trace 里都看得见。"""

    def __init__(self, agent: AgentId, belt=None) -> None:
        self.agent = agent
        self.belt = belt
        self.rejected: list[tuple[str, str]] = []
        self.accepted: list[str] = []

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:  # noqa: D102
        registry.add_callback(BeforeToolCallEvent, self._before)
        registry.add_callback(AfterToolCallEvent, self._after)

    def _before(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        try:
            assert_tool_allowed(self.agent, name)
            for pattern in FORBIDDEN_TOOL_PATTERNS.get(self.agent, frozenset()):
                if name.startswith(pattern):
                    raise ToolPermissionError(
                        f"{self.agent.value} 的禁止清单命中 {pattern!r}：{name}"
                    )
        except ToolPermissionError as exc:
            self.rejected.append((name, str(exc)))
            if self.belt is not None:
                self.belt.reject(name, str(exc))
            else:
                with span("agent.tool", **{"campuspath.agent": self.agent.value,
                                           "gen_ai.tool.name": name,
                                           "campuspath.tool.accepted": False}):
                    pass
            event.cancel_tool = f"工具 {name!r} 不在 {self.agent.value} 的白名单，已拒绝：{exc}"

    def _after(self, event: AfterToolCallEvent) -> None:
        if event.cancel_message is None and event.exception is None:
            self.accepted.append(event.tool_use["name"])


class CredentialLeakBlocked(RuntimeError):
    """即将发给模型的上下文里出现了凭据形态的内容。"""


#: 凭据形态。日历 token（Google OAuth ``ya29.``）、Bearer 头、刷新令牌、
#: 以及契约里的字段名本身——字段名出现就说明有人把整个对象 dump 了进来。
CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ya29\.[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]{20,}"),
    re.compile(r"\brefresh_token\b"),
    re.compile(r"\bcalendar_token\b"),
    re.compile(r"\baccess_token\b"),
)


def find_credential_shapes(texts: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for text in texts:
        for pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text):
                hits.append(pattern.pattern)
    return hits


class PromptHygieneHook(HookProvider):
    """模型调用前扫描全部消息与 system prompt；命中即抛，不发请求。"""

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:  # noqa: D102
        registry.add_callback(BeforeModelCallEvent, self._before)

    def _before(self, event: BeforeModelCallEvent) -> None:
        agent = event.agent
        texts = [json.dumps(agent.messages, ensure_ascii=False, default=str)]
        if isinstance(agent.system_prompt, str):
            texts.append(agent.system_prompt)
        hits = find_credential_shapes(texts)
        if hits:
            with span("agent.prompt_hygiene", **{"campuspath.blocked": True,
                                                 "campuspath.patterns": len(hits)}):
                pass
            raise CredentialLeakBlocked(
                "模型上下文里出现凭据形态内容，调用已取消（Spec §8.9 第 3 条）："
                + ", ".join(sorted(set(hits)))
            )
