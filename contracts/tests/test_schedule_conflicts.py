"""时段冲突事实的契约（用户 2026-08-11 报障 A/B，Fable 5 裁定）。

**先红后绿**：这些类型此时还不存在，整个文件应当 import 失败。

裁定的三条落在类型上：
1. 冲突是**事实**，不是判决——它只陈述「与谁、重叠多少分钟」，
   不含"该不该去"的取舍。取舍归 A5，拍板归学生。
2. **重叠为零就不是冲突**。允许 `overlap_minutes=0` 等于允许生产者
   把「不重叠」也塞进冲突列表，界面就会开始报不存在的冲突。
3. 冲突挂在 `PlanItem` 上，与 `validation_id` 同行——B8 那道
   「每个计划项都得有凭据」的门因此顺带覆盖了冲突事实的来源。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.common import DateRange, LocalizedText
from campuspath_contracts.pathway import (
    PlanItem,
    PlanItemKind,
    PlanItemConflict,
    PlanItemConflictKind,
)


def _conflict(**over) -> dict:
    base = dict(
        with_id="AB-STU-A-course-huma1030",
        kind=PlanItemConflictKind.COURSE,
        label=LocalizedText(zh_Hans="HUMA 1030 · 汉语结构", en="HUMA 1030"),
        starts_at=datetime(2026, 9, 24, 16, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 24, 17, 50, tzinfo=timezone.utc),
        overlap_minutes=80,
    )
    base.update(over)
    return base


def test_conflict_records_who_and_how_long() -> None:
    c = PlanItemConflict(**_conflict())
    assert c.overlap_minutes == 80
    assert c.kind is PlanItemConflictKind.COURSE


def test_zero_overlap_is_not_a_conflict() -> None:
    """0 分钟重叠必须被拒——否则「冲突」这个词就不再有意义。"""
    with pytest.raises(ValidationError):
        PlanItemConflict(**_conflict(overlap_minutes=0))


def test_negative_overlap_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanItemConflict(**_conflict(overlap_minutes=-5))


def test_conflict_span_must_be_forward() -> None:
    with pytest.raises(ValidationError):
        PlanItemConflict(**_conflict(
            starts_at=datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)))


def test_overlap_cannot_exceed_the_conflicting_span() -> None:
    """80 分钟的课不可能与你重叠 200 分钟——算错了就该在类型层停住。"""
    with pytest.raises(ValidationError):
        PlanItemConflict(**_conflict(overlap_minutes=200))


def _plan_item(**over) -> dict:
    base = dict(
        plan_item_id="PI-0001",
        kind=PlanItemKind.OPPORTUNITY,
        subject_id="OPP-EVT-046",
        title=LocalizedText(zh_Hans="简历工作坊（第 4 期）", en="Résumé workshop 4"),
        date_range=DateRange(start=date(2026, 9, 24), end=date(2026, 9, 24)),
        validation_id="val_" + "a7ff4257" * 4,
    )
    base.update(over)
    return base


def test_plan_item_defaults_to_no_conflicts() -> None:
    """默认空元组——**不是** None：没冲突和没算过不该长得一样。"""
    assert PlanItem(**_plan_item()).conflicts == ()


def test_plan_item_carries_conflicts_alongside_validation_id() -> None:
    item = PlanItem(**_plan_item(conflicts=(PlanItemConflict(**_conflict()),)))
    assert item.validation_id.startswith("val_")
    assert item.conflicts[0].overlap_minutes == 80
