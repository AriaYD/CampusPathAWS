"""工具白名单的**运行时**强制（Spec §8.9.1、D2 安全契约测试）。

契约层的 `AGENT_TOOL_WHITELIST` 是一张表；表本身不会阻止任何事。
这里让它变成闸门：Agent 拿到的是 :class:`ToolBelt`，
belt 里根本没有白名单之外的函数，而且每次调用都再查一次。

为什么两道都要：

* **没有那个函数** —— 模型即使被完全注入劫持，也调不到不存在的东西；
* **调用时再查** —— 防的是有人日后往 belt 里塞一个方法而忘了改白名单。

威胁模型（Spec §8.9.1 末）：即使 A4 被完全劫持，它能造成的最大影响是
"提交一条会被人工审核拒绝的草稿"。这条结论成立的前提就是 belt 里
只有 ``read_source`` 与 ``emit_opportunity_draft``。
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from .telemetry import span

from campuspath_contracts.agents import (
    AGENT_TOOL_WHITELIST,
    FORBIDDEN_TOOL_PATTERNS,
    ToolPermissionError,
    assert_tool_allowed,
)
from campuspath_contracts.common import AgentId


@dataclasses.dataclass(frozen=True)
class ToolCall:
    """一次工具调用的审计记录。D2 的治理证据从这里来。"""

    agent: AgentId
    tool_name: str
    accepted: bool
    detail: str = ""


class ToolBelt:
    """一个 Agent 能用的全部工具。**注册时就查白名单。**"""

    def __init__(self, agent: AgentId) -> None:
        self.agent = agent
        self._tools: dict[str, Callable[..., Any]] = {}
        self._log: list[ToolCall] = []

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        assert_tool_allowed(self.agent, name)
        for pattern in FORBIDDEN_TOOL_PATTERNS.get(self.agent, frozenset()):
            if name.startswith(pattern):
                raise ToolPermissionError(
                    f"{self.agent.value} 的禁止清单命中 {pattern!r}：{name}"
                )
        self._tools[name] = fn

    @property
    def available(self) -> frozenset[str]:
        return frozenset(self._tools)

    @property
    def call_log(self) -> tuple[ToolCall, ...]:
        return tuple(self._log)

    def reject(self, name: str, detail: str) -> None:
        """记一次被拒的调用（Strands hook 在执行前拦下的那种）。"""
        with span("agent.tool", **{"campuspath.agent": self.agent.value,
                                   "gen_ai.tool.name": name,
                                   "campuspath.tool.accepted": False}):
            self._log.append(ToolCall(self.agent, name, False, detail))

    def as_strands_tools(self, specs: dict[str, dict[str, Any]] | None = None) -> list[Any]:
        """把已装备的工具封装成 Strands ``AgentTool``。

        每个封装体执行时仍经 :meth:`call`——白名单在**三处**生效：
        注册时、Strands ``BeforeToolCallEvent`` hook、以及这里的每次调用。
        ``specs`` 给出工具的描述与输入 schema；没给的用最宽松的对象 schema。
        """
        import json as _json  # noqa: PLC0415

        from strands.tools.tools import PythonAgentTool  # noqa: PLC0415

        specs = specs or {}
        tools: list[Any] = []
        for name in sorted(self._tools):
            spec = specs.get(name) or {}
            tool_spec = {
                "name": name,
                "description": spec.get("description") or f"CampusPath 工具 {name}",
                "inputSchema": {"json": spec.get(
                    "schema", {"type": "object", "properties": {}, "additionalProperties": True}
                )},
            }

            def _run(tool_use, _name=name, **kwargs):
                try:
                    payload = self.call(_name, **(tool_use.get("input") or {}))
                    return {"toolUseId": tool_use["toolUseId"], "status": "success",
                            "content": [{"text": _json.dumps(payload, ensure_ascii=False,
                                                              default=str)}]}
                except ToolPermissionError as exc:
                    return {"toolUseId": tool_use["toolUseId"], "status": "error",
                            "content": [{"text": str(exc)}]}

            tools.append(PythonAgentTool(name, tool_spec, _run))
        return tools

    def call(self, name: str, /, **kwargs: Any) -> Any:
        """调用一个工具。**每次都重新查白名单**，不信任注册时的判断。

        每次调用一条 span（含被拒的）：Cloud Trace 里"A4 试图 publish 被白名单拦下"
        和"A5 调 validate_constraints 三次"同样看得见。
        """
        with span("agent.tool", **{"campuspath.agent": self.agent.value,
                                   "gen_ai.tool.name": name}) as current:
            try:
                assert_tool_allowed(self.agent, name)
            except ToolPermissionError as exc:
                self._log.append(ToolCall(self.agent, name, False, str(exc)))
                current.set_attribute("campuspath.tool.accepted", False)
                raise
            fn = self._tools.get(name)
            if fn is None:
                self._log.append(ToolCall(self.agent, name, False, "工具未注册"))
                current.set_attribute("campuspath.tool.accepted", False)
                raise ToolPermissionError(
                    f"{self.agent.value} 没有装备工具 {name!r}；"
                    f"已装备：{sorted(self._tools)}"
                )
            self._log.append(ToolCall(self.agent, name, True))
            current.set_attribute("campuspath.tool.accepted", True)
            return fn(**kwargs)


def belt_for(agent: AgentId, tools: dict[str, Callable[..., Any]]) -> ToolBelt:
    """按白名单装备一个 Agent。传入白名单之外的工具会当场报错。"""
    belt = ToolBelt(agent)
    for name, fn in sorted(tools.items()):
        belt.register(name, fn)
    return belt


def unequipped_whitelist_entries(belt: ToolBelt) -> frozenset[str]:
    """白名单里有、但没装备的工具。

    不是错误——分阶段实现时本来就会有缺口。但它应该**可见**，
    否则"A5 能调 validate_constraints"会在没人发现的情况下变成不能。
    """
    return AGENT_TOOL_WHITELIST[belt.agent] - belt.available
