"""P4 第二波：四个校方视图的聚合口径（Spec §17.1.2 / §17.6）。

这里守的不是"算得对"，而是**算错时会不会泄漏**：抑制、来源拆分、
以及两个排行榜的入榜门槛。
"""

from __future__ import annotations

from datetime import datetime, timezone

from campuspath_contracts.aggregation import (
    MIN_CELL_N, MetricProvenance, MetricTuple, OpportunityExposureCount,
    SurfaceConversion)
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.reflection import CohortDims
from campuspath_aggregation.aggregate import (
    aggregate_plaza_conversion, aggregate_resource_coverage,
    build_exposure_gap_ranking)

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)
TERM = "2026-27_FALL"
COHORT = CohortDims(school="ENGG", year_level=2, development_mode="employment")


def _tuple(provenance=MetricProvenance.DERIVED, plaza=(20, 4), **kw) -> MetricTuple:
    base = dict(
        period=TERM, cohort_dims=COHORT, provenance=provenance,
        eligible_count=10, seen_count=6, acted_count=2,
        gap_total=4, gap_covered=2,
        uncovered_requirement_categories=(RequirementCategory.NETWORK,),
        surface_conversions=(
            SurfaceConversion(surface="plaza",
                              exposed_count=plaza[0], acted_count=plaza[1]),),
    )
    base.update(kw)
    return MetricTuple(**base)


# ── 来源拆分：合成与派生不静默合并 ─────────────────────────────────


def test_coverage_reports_how_many_rows_were_really_derived():
    rows = ([_tuple() for _ in range(3)]
            + [_tuple(MetricProvenance.SYNTHETIC) for _ in range(4)])
    agg = aggregate_resource_coverage(
        rows, period=TERM, scope="institution", computed_at=NOW)
    assert agg.cell_n == 7
    assert (agg.derived_cell_n, agg.synthetic_cell_n) == (3, 4)


def test_a_suppressed_cell_still_reports_its_split():
    """被抑制的格子也要说清它是「没有真实数据」还是「真实数据太少」。"""
    agg = aggregate_resource_coverage(
        [_tuple(MetricProvenance.SYNTHETIC) for _ in range(2)],
        period=TERM, scope="institution", computed_at=NOW)
    assert agg.discovery_rate is None
    assert (agg.derived_cell_n, agg.synthetic_cell_n) == (0, 2)


# ── 供给缺口榜：不再谎报「没有资源能覆盖」 ─────────────────────────


def test_covered_categories_are_no_longer_hardcoded_false():
    """此前 `covered_by_any_resource` 恒 False——每一行都在说资源池覆盖不了，
    哪怕目录里明明有能覆盖它的活动。"""
    rows = [_tuple() for _ in range(MIN_CELL_N)]
    agg = aggregate_resource_coverage(
        rows, period=TERM, scope="institution",
        covered_categories=frozenset({RequirementCategory.NETWORK}),
        computed_at=NOW)
    entry = next(e for e in agg.unmet_requirement_ranking
                 if e.category is RequirementCategory.NETWORK)
    assert entry.covered_by_any_resource is True


def test_not_telling_us_is_not_the_same_as_not_covered():
    """不传 covered_categories 时退回 False，但那是「没人告诉我」。"""
    rows = [_tuple() for _ in range(MIN_CELL_N)]
    agg = aggregate_resource_coverage(
        rows, period=TERM, scope="institution", computed_at=NOW)
    assert all(not e.covered_by_any_resource
               for e in agg.unmet_requirement_ranking)


# ── 曝光断层榜：最惨的那条恰恰最不能上榜 ───────────────────────────


def test_the_most_tempting_row_is_the_one_that_must_be_suppressed():
    """已知会失败的样例用**最诱人的那条**：eligible_n=4、seen_n=0。

    它是"合格却零曝光"的极端，最像该上榜的一行——正因为它样本不足，
    上榜就等于告诉校方"这 4 个人一个都没看到"。榜单本身也是单元格。
    """
    ranking = build_exposure_gap_ranking({
        "OPP-THIN": (MIN_CELL_N - 1, 0),
        "OPP-OK": (20, 3),
    })
    assert [e.opportunity_id for e in ranking] == ["OPP-OK"]


def test_ranking_puts_the_worst_exposure_first():
    ranking = build_exposure_gap_ranking({
        "OPP-A": (20, 18), "OPP-B": (20, 2), "OPP-C": (20, 9)})
    assert [e.opportunity_id for e in ranking] == ["OPP-B", "OPP-C", "OPP-A"]


def test_coverage_carries_the_ranking_only_when_counts_are_supplied():
    rows = [_tuple() for _ in range(MIN_CELL_N)]
    counts = (OpportunityExposureCount(period=TERM, opportunity_id="OPP-1",
                                       eligible_n=30, seen_n=4, acted_n=1),)
    agg = aggregate_resource_coverage(
        rows, period=TERM, scope="institution",
        exposure_counts=counts, computed_at=NOW)
    assert [e.opportunity_id for e in agg.exposure_gap_ranking] == ["OPP-1"]


def test_exposure_counts_from_another_period_do_not_leak_in():
    rows = [_tuple() for _ in range(MIN_CELL_N)]
    counts = (OpportunityExposureCount(period="2025-26_FALL",
                                       opportunity_id="OPP-OLD",
                                       eligible_n=30, seen_n=1, acted_n=0),)
    agg = aggregate_resource_coverage(
        rows, period=TERM, scope="institution",
        exposure_counts=counts, computed_at=NOW)
    assert agg.exposure_gap_ranking == ()


# ── Plaza 转化 ─────────────────────────────────────────────────────


def test_plaza_conversion_uses_all_exposures_as_the_denominator():
    rows = [_tuple(plaza=(20, 4)) for _ in range(MIN_CELL_N)]
    agg = aggregate_plaza_conversion(
        rows, period=TERM, surface="plaza", computed_at=NOW)
    assert agg.exposed_total == 100 and agg.acted_total == 20
    assert agg.conversion_rate == 0.2


def test_a_thin_plaza_cell_reports_totals_but_no_rate():
    """计数可以出，比率不行——比率才是能反推到个人的那个数。"""
    rows = [_tuple(plaza=(20, 4)) for _ in range(MIN_CELL_N - 1)]
    agg = aggregate_plaza_conversion(
        rows, period=TERM, surface="plaza", computed_at=NOW)
    assert agg.conversion_rate is None and agg.exposed_total > 0


def test_for_you_exposures_do_not_move_the_plaza_denominator():
    """两个入口分开算。混在一起，「广场发现」这个指标就没有意义了。"""
    rows = [
        _tuple(surface_conversions=(
            SurfaceConversion(surface="plaza", exposed_count=10, acted_count=1),
            SurfaceConversion(surface="for_you", exposed_count=99, acted_count=40),
        )) for _ in range(MIN_CELL_N)
    ]
    plaza = aggregate_plaza_conversion(
        rows, period=TERM, surface="plaza", computed_at=NOW)
    assert plaza.exposed_total == 50


def test_conversion_splits_by_provenance_too():
    rows = ([_tuple() for _ in range(3)]
            + [_tuple(MetricProvenance.SYNTHETIC) for _ in range(3)])
    agg = aggregate_plaza_conversion(
        rows, period=TERM, surface="plaza", computed_at=NOW)
    assert (agg.derived_cell_n, agg.synthetic_cell_n) == (3, 3)


# ── 与 F26 评测口径分离 ────────────────────────────────────────────


def test_aggregation_does_not_import_the_evaluation_harness():
    """Gold Label 与引擎**故意分开实现**——用同一份代码生成标签又用它评测，
    等于自己给自己打分。这条断言钉住两边不许互相 import。
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "campuspath_aggregation"
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module] if isinstance(node, ast.ImportFrom) and node.module
                     else [])
            assert not any(n.split(".")[0] == "campuspath_eval" for n in names), (
                f"{path.name} 引用了评测器——两条管线必须互不干涉")
