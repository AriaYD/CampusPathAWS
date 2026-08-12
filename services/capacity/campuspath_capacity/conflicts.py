"""时段冲突检测（用户 2026-08-11 报障 A/B，Fable 5 裁定）。

**为什么在这一层**：重叠是纯区间数学——两个 `[start, end)` 相交与否、
相交多少分钟——零语义、可单测、可审计，是确定性平面的教科书式工作。
而且全量时段真相（课表、保护块、已批准的活动）只在 Capacity 手里；
让别的模块去算冲突，就得把日历数据递出去，那是在架构第 3 条
「日历凭据止步于 Capacity & Calendar Service」上打洞。

**这一层只出事实，不出判决**。「与 HUMA 1030 重叠 80 分钟」是事实；
「所以别去这个工作坊」是取舍——取舍归 A5，拍板归学生。
课能不能翘，学生知道（点不点名、期中考不考），系统不知道。

零 LLM：本模块只 import 标准库与契约类型（有 AST 断言守着）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from campuspath_contracts.common import LocalizedText
from campuspath_contracts.pathway import PlanItemConflict, PlanItemConflictKind


@dataclass(frozen=True)
class Occupancy:
    """一段已被占用的时间。

    **刻意只有五个字段**：谁、什么性质、叫什么、起、止。
    地点、参与人、原始日历事件字段一律不进来——契约里就没有承载它们的地方，
    这是日历边界在类型上的样子。
    """

    subject_id: str
    kind: PlanItemConflictKind
    label: LocalizedText
    starts_at: datetime
    ends_at: datetime


def overlap_minutes(a_start: datetime, a_end: datetime,
                    b_start: datetime, b_end: datetime) -> int:
    """两个区间的重叠分钟数；不重叠或仅相邻则为 0。

    **半开区间 `[start, end)`**：一个 14:00 结束、另一个 14:00 开始
    不算冲突。把邻接算成冲突，每天都会冒出一堆假冲突，
    真冲突随即淹没在噪声里。
    """
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


def detect_conflicts(starts_at: datetime, ends_at: datetime,
                     others: Iterable[Occupancy]) -> tuple[PlanItemConflict, ...]:
    """候选时段与已占用时段的全部重叠，按重叠时长降序。

    候选自身长度为 0（数据异常）时返回空——**不是与所有东西冲突**。
    """
    if ends_at <= starts_at:
        return ()
    found: list[tuple[int, PlanItemConflict]] = []
    for o in others:
        minutes = overlap_minutes(starts_at, ends_at, o.starts_at, o.ends_at)
        if minutes <= 0:
            continue
        found.append((minutes, PlanItemConflict(
            with_id=o.subject_id,
            kind=o.kind,
            label=o.label,
            starts_at=o.starts_at,
            ends_at=o.ends_at,
            overlap_minutes=minutes,
        )))
    # 重叠多的排前面；同长按 id 稳定排序，免得同一份数据两次调用顺序不同
    found.sort(key=lambda pair: (-pair[0], pair[1].with_id))
    return tuple(c for _, c in found)
