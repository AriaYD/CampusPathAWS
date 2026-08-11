"""P4 第一波（2026-08-10 用户需求 B）：校方量化指标的契约层约束。

这一批新增的字段全都通向**校方能看到的数字**，所以每一条不变量都是 B9/B10
的一部分。这里逐条钉住，且每条都配一个"已知会失败的样例"——
先证明断言真的会响，再相信它守得住（Plan §10 H5）。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.aggregation import (
    MAX_COHORT_DIMENSIONS,
    MIN_CELL_N,
    MetricProvenance,
    MetricTuple,
    OpportunityExposureCount,
    PlazaConversionAggregate,
    ResourceCoverageAggregate,
    SurfaceConversion,
)
from campuspath_contracts.goals import (
    GapChangeEvent, GapChangeOrigin, GapLevel, RequirementCategory)
from campuspath_contracts.pathway import (
    ExposureBatch, ExposureDepth, ExposureEvent, ExposureSurface)
from campuspath_contracts.reflection import CohortDims

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)
TERM = "2026-27_FALL"
COHORT = CohortDims(school="ENGG", year_level=2, development_mode="employment")


def _tuple(**kw) -> MetricTuple:
    base = dict(
        period=TERM, cohort_dims=COHORT, provenance=MetricProvenance.DERIVED,
        eligible_count=30, seen_count=18, acted_count=6,
        gap_total=10, gap_covered=7,
    )
    base.update(kw)
    return MetricTuple(**base)


def _coverage(**kw) -> ResourceCoverageAggregate:
    base = dict(
        aggregate_id="AGG-1", period=TERM, scope="institution",
        cell_n=12, computed_at=NOW,
    )
    base.update(kw)
    return ResourceCoverageAggregate(**base)


# ── provenance：合成与派生绝不静默合并 ──────────────────────────────


def test_metric_tuple_must_declare_where_it_came_from():
    """已知会失败的样例：不声明来源。有默认值就等于允许生产者忘记声明。"""
    with pytest.raises(ValidationError):
        MetricTuple(
            period=TERM, cohort_dims=COHORT,
            eligible_count=1, seen_count=1, acted_count=1,
            gap_total=1, gap_covered=1,
        )


def test_provenance_has_exactly_two_values():
    """加第三种来源之前先想清楚聚合侧怎么拆分——拆分口径是二元的。"""
    assert {p.value for p in MetricProvenance} == {"derived", "synthetic"}


def test_coverage_split_must_add_up_to_cell_n():
    """已知会失败的样例：3 派生 + 4 合成却报 cell_n=12——有一侧被漏计了。"""
    with pytest.raises(ValidationError):
        _coverage(cell_n=12, derived_cell_n=3, synthetic_cell_n=4)


def test_coverage_split_that_adds_up_is_accepted():
    agg = _coverage(cell_n=7, derived_cell_n=3, synthetic_cell_n=4)
    assert agg.derived_cell_n + agg.synthetic_cell_n == agg.cell_n


def test_split_may_be_omitted_entirely():
    """0+0 表示"没拆"，不是"两边都是 0"——既有生产者不必一次全改完。"""
    assert _coverage(cell_n=9).derived_cell_n == 0


# ── 嵌套计数：让不变量由构造成立，而不是碰巧成立 ────────────────────


def test_surface_conversion_cannot_act_more_than_it_showed():
    with pytest.raises(ValidationError):
        SurfaceConversion(surface="plaza", exposed_count=3, acted_count=9)


def test_one_row_per_surface():
    """已知会失败的样例：同一个入口两行——聚合时会被重复计数。"""
    with pytest.raises(ValidationError):
        _tuple(surface_conversions=(
            SurfaceConversion(surface="plaza", exposed_count=5, acted_count=1),
            SurfaceConversion(surface="plaza", exposed_count=2, acted_count=0),
        ))


def test_plaza_conversion_denominator_is_not_the_eligible_set():
    """广场转化的分母是**全部**曝光——含学生并不合格的机会。

    这正是它必须独立于 `seen ≤ eligible` 那条嵌套约束的原因：
    「学生对自己不合格的机会点了报名」是校方最想知道的信号之一，
    塞进主计数里会被约束吃掉。
    """
    row = _tuple(
        eligible_count=10, seen_count=8, acted_count=2,
        surface_conversions=(
            SurfaceConversion(surface="plaza", exposed_count=40, acted_count=5),),
    )
    assert row.surface_conversions[0].exposed_count > row.eligible_count


def test_opportunity_exposure_counts_are_nested():
    with pytest.raises(ValidationError):
        OpportunityExposureCount(
            period=TERM, opportunity_id="OPP-1",
            eligible_n=4, seen_n=9, acted_n=0)


# ── B9：样本不足就没有数字 ─────────────────────────────────────────


def test_thin_plaza_cell_must_not_carry_a_rate():
    """已知会失败的样例：4 个人的格子却报出 31% 的转化率。"""
    with pytest.raises(ValidationError) as excinfo:
        PlazaConversionAggregate(
            aggregate_id="PCA-1", period=TERM, surface="plaza",
            cell_n=MIN_CELL_N - 1, exposed_total=40, acted_total=12,
            conversion_rate=0.31, computed_at=NOW)
    assert "B9" in str(excinfo.value)


def test_thin_plaza_cell_with_suppressed_rate_is_fine():
    agg = PlazaConversionAggregate(
        aggregate_id="PCA-2", period=TERM, surface="plaza",
        cell_n=MIN_CELL_N - 1, exposed_total=40, acted_total=12,
        computed_at=NOW)
    assert agg.conversion_rate is None


def test_plaza_conversion_cannot_act_more_than_exposed():
    with pytest.raises(ValidationError):
        PlazaConversionAggregate(
            aggregate_id="PCA-3", period=TERM, surface="plaza",
            cell_n=9, exposed_total=3, acted_total=8, computed_at=NOW)


def test_every_rate_field_is_in_the_suppression_list():
    """这条测试守的是**别人以后加字段时会不会忘**。

    抑制清单曾是 validator 里的字面量列表；加一个比率字段而忘了回来改它，
    样本不足时那个数字就会直接漏出去。现在清单是 SUPPRESSED_FIELDS，
    这里断言「所有 `*_rate` 字段都在清单里」，忘了就红。
    """
    for model in (ResourceCoverageAggregate, PlazaConversionAggregate):
        rates = {n for n in model.model_fields if n.endswith("_rate")}
        missing = rates - set(model.SUPPRESSED_FIELDS)
        assert not missing, f"{model.__name__} 新增的比率字段没进抑制清单：{missing}"


def test_cohort_dimensions_stay_within_the_cap():
    with pytest.raises(ValidationError):
        _coverage(scope="school",
                  cohort_dims_used=("school", "year_level", "development_mode"),
                  cell_n=40)
    assert MAX_COHORT_DIMENSIONS == 2


# ── Gap 变更：gaps_closed 只数说得出理由的关闭 ──────────────────────


def _change(**kw) -> GapChangeEvent:
    base = dict(
        change_id="GC-1", student_id="STU-A", requirement_id="REQ-1",
        category=RequirementCategory.TECHNICAL_SKILL, term=TERM,
        from_level=GapLevel.MISSING, to_level=GapLevel.SATISFIED,
        evidence_ids=("EV-1",), origin=GapChangeOrigin.OBSERVED,
        detected_at=NOW,
    )
    base.update(kw)
    return GapChangeEvent(**base)


def test_closing_a_gap_needs_evidence():
    """已知会失败的样例：说关闭了，却说不出是什么关闭的。"""
    with pytest.raises(ValidationError):
        _change(evidence_ids=())


def test_a_change_must_actually_change_something():
    with pytest.raises(ValidationError):
        _change(from_level=GapLevel.SATISFIED, to_level=GapLevel.SATISFIED)


def test_downgrade_needs_no_evidence():
    """从满足退回缺失不需要证据——证据要求约束的是"算作成果"那个方向。"""
    assert _change(from_level=GapLevel.SATISFIED, to_level=GapLevel.PARTIAL,
                   evidence_ids=()).to_level is GapLevel.PARTIAL


def test_gap_change_is_append_only():
    with pytest.raises(ValidationError):
        _change().to_level = GapLevel.MISSING


# ── 曝光：只活在学生私有域 ────────────────────────────────────────


def _exposure(**kw) -> ExposureEvent:
    base = dict(
        event_id="EX-1", student_id="STU-A", subject_id="OPP-1",
        surface=ExposureSurface.PLAZA, depth=ExposureDepth.IMPRESSION,
        occurred_at=NOW, period=TERM,
    )
    base.update(kw)
    return ExposureEvent(**base)


def test_exposure_batch_rejects_someone_elses_events():
    """已知会失败的样例：把别人的曝光塞进自己的批次里。"""
    with pytest.raises(ValidationError):
        ExposureBatch(student_id="STU-A",
                      events=(_exposure(), _exposure(student_id="STU-B")))


def test_exposure_batch_cannot_be_empty():
    with pytest.raises(ValidationError):
        ExposureBatch(student_id="STU-A", events=())


def test_exposure_is_not_an_action_type():
    """曝光**不进** ActionType：VGA 与 B8 都挂在 ActionEvent 上，
    混进去会让「不奖励忙碌」这条口径失效。"""
    from campuspath_contracts.pathway import ActionType

    assert not {a.value for a in ActionType} & {"impression", "exposure", "view"}


def test_exposure_event_is_append_only():
    with pytest.raises(ValidationError):
        _exposure().subject_id = "OPP-2"
