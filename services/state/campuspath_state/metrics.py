"""在学生私有域内把行为算成去标识元组（Spec §17.1.2）。**零 LLM。**

`derive_metric_tuple` 这个函数**就是那条边界**：进去的是带 student_id 的曝光、
行动与缺口，出来的是一条 `MetricTuple`——里面连放 student_id 的字段都没有。

**分层硬约束**：本模块不得 import `campuspath_agents` 或 `campuspath_rules`。
资格判定、缺口图这些要由 API 编排层算好，作为纯数据传进来
（:class:`StudentMetricInputs`）。`make llm-free` 的四层扫描守住这条。

派生口径（最容易被质疑的几条，写在这里而不是散在调用方）：

* ``E`` = 该期 Rules 判「现在合格」的已发布机会；
* ``X`` = 该期**有曝光** ∪ **有行动**的 subject。「行动蕴含看见」——靠这一条，
  ``seen ≤ eligible`` 与 ``acted ≤ seen`` 是**由构造成立**的，而不是碰巧成立；
* ``A`` = 行动类型属 :data:`CONVERTING_ACTIONS`（不含 unsave / decline / reflect）；
* ``eligible_count=|E|``、``seen_count=|X∩E|``、``acted_count=|A∩X∩E|``。

广场转化的分母**不与 E 求交**：学生在广场上看到的包含他并不合格的机会，
而「对不合格的机会点了报名」恰恰是校方最想知道的信号之一。
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import datetime

from campuspath_contracts.aggregation import (
    MetricProvenance, MetricTuple, OpportunityExposureCount, SurfaceConversion)
from campuspath_contracts.goals import (
    GapChangeEvent, GapChangeOrigin, GapLevel, RequirementCategory)
from campuspath_contracts.pathway import ActionEvent, ActionType, ExposureSurface
from campuspath_contracts.reflection import CohortDims

from .exposure import ExposureLog

#: 算作「转化」的行动。刻意**不含** ``unsave`` / ``decline`` / ``reflect``：
#: 取消收藏和拒绝是反向信号，写反思是另一条闭环（VGA 那条）。
CONVERTING_ACTIONS: frozenset[ActionType] = frozenset({
    ActionType.APPLY,
    ActionType.REGISTER,
    ActionType.SAVE,
    ActionType.ADD_TO_PATHWAY,
    ActionType.CALENDAR_WRITE,
    ActionType.COMPLETE,
})


@dataclasses.dataclass(frozen=True)
class StudentMetricInputs:
    """派生一条元组需要的全部输入。**纯数据**——没有服务、没有 Agent。

    这个 dataclass 的存在本身就是分层约束：state 层拿不到 Rules 与 A3，
    所以资格与缺口必须由 API 编排层算好再递进来。
    """

    period: str
    cohort_dims: CohortDims
    #: 该期 Rules 判「现在合格」的机会 id
    eligible_ids: frozenset[str]
    #: 该学生的行动事件（全量，函数内按期与类型过滤）
    actions: tuple[ActionEvent, ...]
    #: 每个缺口类别是否已被资源池里的某条机会覆盖
    gap_categories: tuple[RequirementCategory, ...]
    covered_categories: frozenset[RequirementCategory]


def derive_metric_tuple(
    inputs: StudentMetricInputs,
    exposure: ExposureLog,
) -> MetricTuple:
    """算出这个学生这一期的去标识元组。

    出去的对象里没有 student_id——不是「我们记得不写」，是类型里没有那个字段。
    """
    period = inputs.period
    eligible = inputs.eligible_ids

    exposed = exposure.subjects_seen(period)
    acted_subjects = {
        a.subject_id for a in inputs.actions
        if a.action_type in CONVERTING_ACTIONS and a.result == "succeeded"
    }
    # 行动蕴含看见：不做这一步，一个「从未被记录曝光却报了名」的学生会让
    # acted > seen，契约 validator 当场抛错——而那并不是数据错，是口径错。
    seen_subjects = exposed | acted_subjects

    seen = seen_subjects & eligible
    acted = acted_subjects & seen

    gap_total = len(inputs.gap_categories)
    covered = [c for c in inputs.gap_categories if c in inputs.covered_categories]
    uncovered = tuple(sorted(
        {c for c in inputs.gap_categories if c not in inputs.covered_categories},
        key=lambda c: c.value))

    conversions: list[SurfaceConversion] = []
    for surface in (ExposureSurface.PLAZA, ExposureSurface.FOR_YOU):
        on_surface = exposure.subjects_seen(period, surface)
        if not on_surface:
            continue
        # last-touch 归因：这次行动之前，该 subject 最近一次曝光来自哪个入口
        attributed = sum(
            1 for a in inputs.actions
            if a.action_type in CONVERTING_ACTIONS
            and a.result == "succeeded"
            and exposure.last_touch_surface(a.subject_id, a.timestamp) is surface
        )
        conversions.append(SurfaceConversion(
            surface=surface.value,  # type: ignore[arg-type]
            exposed_count=len(on_surface),
            # 归因数可能超过该入口的曝光 subject 数（同一 subject 多次行动），
            # 但契约要求 acted ≤ exposed——按 subject 去重才是同一口径
            acted_count=min(len(on_surface), attributed),
        ))

    return MetricTuple(
        period=period,
        cohort_dims=inputs.cohort_dims,
        provenance=MetricProvenance.DERIVED,
        eligible_count=len(eligible),
        seen_count=len(seen),
        acted_count=len(acted),
        gap_total=gap_total,
        gap_covered=len(covered),
        uncovered_requirement_categories=uncovered,
        surface_conversions=tuple(conversions),
    )


def opportunity_exposure_counts(
    period: str,
    eligible_by_student: dict[str, frozenset[str]],
    seen_by_student: dict[str, set[str]],
    acted_by_student: dict[str, set[str]],
) -> tuple[OpportunityExposureCount, ...]:
    """逐机会计数，供曝光断层榜使用。

    出去的是**计数**而不是「每个学生看过哪些机会」——后者本身就是指纹。
    累加在这里（学生域内）完成。
    """
    eligible_n: dict[str, int] = defaultdict(int)
    seen_n: dict[str, int] = defaultdict(int)
    acted_n: dict[str, int] = defaultdict(int)
    for student_id, ids in eligible_by_student.items():
        seen = seen_by_student.get(student_id, set())
        acted = acted_by_student.get(student_id, set())
        for oid in ids:
            eligible_n[oid] += 1
            if oid in seen:
                seen_n[oid] += 1
                if oid in acted:
                    acted_n[oid] += 1
    return tuple(
        OpportunityExposureCount(
            period=period, opportunity_id=oid,
            eligible_n=eligible_n[oid],
            seen_n=seen_n.get(oid, 0),
            acted_n=acted_n.get(oid, 0),
        )
        for oid in sorted(eligible_n)
    )


def diff_gap_levels(
    student_id: str,
    term: str,
    before: dict[str, tuple[RequirementCategory, GapLevel]],
    after: dict[str, tuple[RequirementCategory, GapLevel]],
    *,
    evidence_by_requirement: dict[str, tuple[str, ...]],
    detected_at: datetime,
    origin: GapChangeOrigin = GapChangeOrigin.OBSERVED,
    id_prefix: str = "GC",
) -> tuple[GapChangeEvent, ...]:
    """两份缺口快照的差分 → 变更事件。

    **关键陷阱**：`gap_map()` 对已满足的要求是跳过的，缺口列表里永远不会出现
    `satisfied`。所以「关闭」在数据上表现为**该 requirement_id 从列表里消失**——
    差分必须把「before 有、after 没有」判为 satisfied，否则 `gaps_closed` 会
    永远是 0，只是把硬编码 0 那个错误换了个位置重犯一遍。

    没有证据的关闭**不产出事件**：`gaps_closed` 只数说得出理由的关闭
    （契约层也会拒收，这里提前滤掉而不是让它抛）。
    """
    events: list[GapChangeEvent] = []
    index = 0
    for requirement_id in sorted(before):
        category, from_level = before[requirement_id]
        to_entry = after.get(requirement_id)
        to_level = to_entry[1] if to_entry is not None else GapLevel.SATISFIED
        if to_level is from_level:
            continue
        evidence = evidence_by_requirement.get(requirement_id, ())
        if to_level is GapLevel.SATISFIED and not evidence:
            continue
        index += 1
        events.append(GapChangeEvent(
            change_id=f"{id_prefix}-{student_id}-{term}-{index:03d}",
            student_id=student_id,
            requirement_id=requirement_id,
            category=category,
            term=term,
            from_level=from_level,
            to_level=to_level,
            evidence_ids=evidence,
            origin=origin,
            detected_at=detected_at,
        ))
    return tuple(events)


def gaps_closed_by_term(events: tuple[GapChangeEvent, ...]) -> dict[str, int]:
    """按学期数「关闭了几个缺口」。

    只数 ``to_level=satisfied``，且同一个 requirement 在同一学期只数一次——
    先关后开再关会被算成两次，那是把反复计成了成果。
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for event in events:
        if event.to_level is GapLevel.SATISFIED:
            seen[event.term].add(event.requirement_id)
    return {term: len(ids) for term, ids in sorted(seen.items())}


__all__ = [
    "CONVERTING_ACTIONS",
    "StudentMetricInputs",
    "derive_metric_tuple",
    "opportunity_exposure_counts",
    "diff_gap_levels",
    "gaps_closed_by_term",
]
