"""曝光日志（Spec §17.6 的唯一真实来源）。**零 LLM。**

放在 `state` 是因为这里本来就是「append-only 学生事件（L1 Episodic Timeline）」
的家，而曝光正是这样一条事件流。

**它永远不出域。** 出域的是 `metrics.py` 算出来的计数——那里已经没有
student_id 了。这个模块里的每个对象都带 student_id，所以任何把它直接塞进
`/v1/insights/*` 响应的写法都是 B10 违规，由契约测试钉死。

去重口径：`(subject_id, surface, depth, 当天)`。同一个学生今天在广场上把同一条
机会滚过八遍，那是**一次**曝光——按次数计会让「有多少人看见过」变成
「有多少次滚动」，两者的含义完全不同。
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import date, datetime

from campuspath_contracts.pathway import (
    ExposureDepth, ExposureEvent, ExposureSurface)

#: 去重键：同一天同一入口同一深度的同一条机会算一次。
DedupKey = tuple[str, str, str, date]


def _key(event: ExposureEvent) -> DedupKey:
    return (event.subject_id, event.surface.value, event.depth.value,
            event.occurred_at.date())


@dataclasses.dataclass
class ExposureLog:
    """一个学生的曝光流。进程内形态；生产实现换 Firestore，不变式不变。"""

    student_id: str
    _events: list[ExposureEvent] = dataclasses.field(default_factory=list)
    _seen: set[DedupKey] = dataclasses.field(default_factory=set)

    def record(self, events: tuple[ExposureEvent, ...]) -> tuple[int, int]:
        """收下一批，返回 ``(接受数, 去重数)``。

        **如实回报去重数**：静默丢弃会让前端以为都记上了，而曝光是所有
        转化率的分母——分母悄悄少了，比率就悄悄高了。
        """
        accepted = deduplicated = 0
        for event in events:
            if event.student_id != self.student_id:
                raise ValueError(
                    f"曝光事件属于 {event.student_id}，不是 {self.student_id}")
            k = _key(event)
            if k in self._seen:
                deduplicated += 1
                continue
            self._seen.add(k)
            self._events.append(event)
            accepted += 1
        return accepted, deduplicated

    @property
    def events(self) -> tuple[ExposureEvent, ...]:
        """append-only。返回元组，调用方拿不到可变引用。"""
        return tuple(self._events)

    def for_period(self, period: str) -> tuple[ExposureEvent, ...]:
        return tuple(e for e in self._events if e.period == period)

    def count_for_period(self, period: str) -> int:
        return sum(1 for e in self._events if e.period == period)

    def subjects_seen(self, period: str,
                      surface: ExposureSurface | None = None) -> set[str]:
        """该期被曝光过的 subject 集合。``surface=None`` 表示不限入口。"""
        return {
            e.subject_id for e in self._events
            if e.period == period and (surface is None or e.surface is surface)
        }

    def last_touch_surface(self, subject_id: str,
                           before: datetime) -> ExposureSurface | None:
        """last-touch 归因：这个 subject 在此刻之前**最近一次**曝光来自哪个入口。

        行动的归因走这里，而不是给 `ActionEvent` 加一个 `origin_surface` 字段——
        单一出处，且 B8/VGA 路径上的模型零改动。归不上就是归不上，返回 None
        （调用方记为 `unattributed`），不猜一个默认入口。
        """
        candidates = [e for e in self._events
                      if e.subject_id == subject_id and e.occurred_at <= before]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.occurred_at).surface


class ExposureStore:
    """按学生分片的曝光日志集合。"""

    def __init__(self) -> None:
        self._logs: dict[str, ExposureLog] = {}

    def log_for(self, student_id: str) -> ExposureLog:
        if student_id not in self._logs:
            self._logs[student_id] = ExposureLog(student_id=student_id)
        return self._logs[student_id]

    def student_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._logs))

    def opportunity_seen_counts(self, period: str) -> dict[str, int]:
        """逐机会「有多少个学生看见过」。

        注意是**学生数**不是事件数：同一个人看十遍仍是一个人看见了。
        这个计数是曝光断层榜的分子，口径错了整张榜就没有意义。
        """
        counts: dict[str, int] = defaultdict(int)
        for log in self._logs.values():
            for subject_id in log.subjects_seen(period):
                counts[subject_id] += 1
        return dict(counts)


__all__ = ["ExposureLog", "ExposureStore", "ExposureDepth", "ExposureSurface"]
