"""历史活动质量反馈与去标识指标元组。

两条数据都是**通往校方的出域数据**，因此这里生成的是契约里的边界类型本身：
:class:`EventQualityFeedback` 与 :class:`MetricTuple`。
它们连字段都不含 student_id——不是"生成时记得别写"，是类型上写不进去。

刻意造出三种情形，供 B9 与 §17.4 的指标验证：

1. **样本充足且质量稳定好**——正常基线；
2. **宣传好但反馈持续差**——Spec §11.3 的失败样本，跨两届都低分；
3. **样本不足**（verified_n < MIN_CELL_N）——聚合时必须显示 `Insufficient evidence`。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.aggregation import MIN_CELL_N, MetricTuple
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.opportunity import Opportunity
from campuspath_contracts.reflection import (
    CohortDims,
    DimensionRating,
    EventQualityFeedback,
    FitTag,
    QualityDimension,
)

from .config import CURRENT_TERM, SEED_TODAY
from .personas import PersonaBundle
from .rng import pick, sample, stream

_TZ = timezone.utc


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 18, tzinfo=_TZ)


@dataclasses.dataclass
class FeedbackBundle:
    feedback: list[EventQualityFeedback]
    metric_tuples: list[MetricTuple]
    #: 被刻意设成"宣传好、反馈差"的系列 id，供失败样本与评测引用
    persistently_low_series: list[str]
    #: 样本不足的 occurrence id
    under_threshold_occurrences: list[str]


_SCHOOLS = ("ENGG", "BUS", "SCI")
_MODES = ("employment", "exploration", "academia", "entrepreneurship")


def build_feedback(
    opportunities: list[Opportunity], personas: list[PersonaBundle], count: int
) -> FeedbackBundle:
    rng = stream("feedback")
    events = [o for o in opportunities if o.occurrence_id and o.series_id]
    if not events:
        return FeedbackBundle([], [], [], [])

    # 2026-08-10（配合用户需求 D「编辑推荐」）：反馈要优先落在**还在架**的活动上。
    #
    # 旧写法按列表顺序取前 `count` 条，而前面几乎全是早已办完的场次——
    # 实测后果：全库唯一均分 ≥4 且已验证 ≥5 的活动 `OPP-EVT-006` **本身是过期的**，
    # 于是「编辑推荐」徽章在学生广场上永远看不到，功能等于没有。
    # 稳定排序（`sort` 保序），只把在架的整体提到前面，不引入新的随机性。
    def _still_live(o: Opportunity) -> bool:
        end = o.ends_at or o.starts_at or o.deadline
        return end is None or end.date() >= SEED_TODAY

    events.sort(key=lambda o: not _still_live(o))

    low_series = sorted({e.series_id for e in events})[:2]
    thin_occurrences = [e.occurrence_id for e in events[-2:]]

    feedback: list[EventQualityFeedback] = []
    index = 0
    for event in events:
        is_low = event.series_id in low_series
        is_thin = event.occurrence_id in thin_occurrences
        responses = 1 if is_thin else rng.randrange(MIN_CELL_N, MIN_CELL_N + 6)
        for _ in range(responses):
            if index >= count:
                break
            index += 1
            base = 2 if is_low else 4
            feedback.append(
                EventQualityFeedback(
                    feedback_id=f"EQF-{index:04d}",
                    occurrence_id=event.occurrence_id,
                    series_id=event.series_id,
                    verified_attendance=True,
                    # 不透明凭据：不能是 evidence_id，否则聚合域又连回个人
                    verification_ref=f"ver_{index:016x}",
                    dimensions=tuple(
                        DimensionRating(
                            dimension=dim,
                            rating=max(1, min(5, base + rng.randrange(-1, 2))),
                        )
                        for dim in QualityDimension
                    ),
                    fit_tags=(pick(rng, list(FitTag)),),
                    cohort_dims=CohortDims(
                        school=pick(rng, list(_SCHOOLS)),
                        year_level=rng.randrange(1, 5),
                        development_mode=pick(rng, list(_MODES)),
                    ),
                    submitted_at=_dt(SEED_TODAY - timedelta(days=rng.randrange(10, 200))),
                )
            )
        if index >= count:
            break

    # 2026-08-10（P4）：**去标识指标元组不再在这里造**。
    # 旧写法按 persona 各造一条 `prng.randrange` 随机数，period 全是当前学期
    # （趋势画不出来），而且造的就是运行时要真实派生的同一批学生——留着即重复
    # 计数，且与派生数据无法区分。合成扩样整体搬去 `metrics.py`：由手写 cell
    # plan 驱动、跨三期、全部标 provenance=synthetic。
    from .metrics import build_metric_tuples

    tuples = build_metric_tuples()

    return FeedbackBundle(
        feedback=feedback,
        metric_tuples=tuples,
        persistently_low_series=low_series,
        under_threshold_occurrences=thin_occurrences,
    )
