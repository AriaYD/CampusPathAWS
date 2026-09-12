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


#: 凭据的**值**形态。这些在任何自由文本里出现都是凭据，没有第二种解释：
#: Google OAuth 访问令牌、Authorization 头、AWS 访问密钥 ID、PEM 私钥块。
CREDENTIAL_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ya29\.[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

#: 契约里的凭据字段名。**只在键位上算数。**
#:
#: 以前这三个是裸词匹配（``\baccess_token\b``）。A4 读的是社团公告、
#: 工作坊介绍这类外部文本，"OAuth 2.0 工作坊：access_token vs refresh_token"
#: 是完全正常的一句话——裸词匹配会把整条 A4 链路拦死，而拦下来的东西里
#: 一个凭据都没有。守卫会误伤到正常业务，就会被人绕过去，然后就没有守卫了。
#:
#: 键位形态才是"有人把整个对象 dump 进来了"的证据：``"access_token":``、
#: ``'access_token':``、``access_token=``。JSON 转义后的 ``\"access_token\":``
#: 也要认——hook 扫的是 ``json.dumps`` 之后的字符串。
CREDENTIAL_FIELDS: tuple[str, ...] = ("access_token", "refresh_token", "calendar_token")

CREDENTIAL_KEY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"""(?:\\?["']{field}\\?["']\s*:|\b{field}\s*=)""")
    for field in CREDENTIAL_FIELDS
)

CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    CREDENTIAL_VALUE_PATTERNS + CREDENTIAL_KEY_PATTERNS
)


#: ``json.dumps`` 把换行写成两个字符 ``\`` + ``n``。于是上下文里的
#: ``"…指令>>>\nAKIA…"`` 在扫描字符串里长成 ``nAKIA`` —— ``\bAKIA`` 这类
#: 词边界锚点就落空了（实测 2026-09-12：AKIA 样例没被拦下）。扫描前把这几个
#: 转义序列还原成空白，锚点才落在它们该落的地方。
_ESCAPED_WS_RE = re.compile(r"\\[nrt]")


def find_credential_shapes(texts: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for text in texts:
        for candidate in (text, _ESCAPED_WS_RE.sub(" ", text)):
            for pattern in CREDENTIAL_PATTERNS:
                if pattern.search(candidate) and pattern.pattern not in hits:
                    hits.append(pattern.pattern)
    return hits


class PromptHygieneHook(HookProvider):
    """模型调用前扫描全部消息与 system prompt；命中即抛，不发请求。

    扫的是 ``agent.messages`` 的**全量** JSON dump——所以工具结果那一轮同样被扫：
    凭据从 ``read_source`` 的返回值进上下文，和从 ``data`` 块进上下文，
    在这里没有区别。
    """

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
