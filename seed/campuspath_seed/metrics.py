"""合成 MetricTuple 扩样（2026-08-10 用户裁定 B）。

**为什么要换掉旧写法**：旧的 12 条挂在 `feedback.py` 里，按 persona 用
`prng.randrange` 现造，`period` 全是当前学期——于是「趋势」根本画不出来，
而且它造的**就是运行时要真实派生的那同一批学生**，留着即重复计数。

这里改成由一张**手写的 cell plan 字面表**驱动，不做自由采样。理由是演示的形状
必须确定：每一期的 institution 格都要 ≥ MIN_CELL_N（否则 B9 评测器会把无参
`/insights/resource-coverage` 的行判成泄漏），同时**必须**留下几个 n ∈ 1..4 的
薄格子——`Insufficient evidence` 要在演示里真的出现一次，那是隐私红线在工作，
不是缺陷。

全部标 `provenance=synthetic`。**seed 永远不得产出 `derived`**：那两个字是留给
真实曝光 × 资格 × 行动推导出来的元组的，混了就再也分不开。
"""

from __future__ import annotations

from campuspath_contracts.aggregation import (
    MIN_CELL_N, MetricProvenance, MetricTuple, SurfaceConversion)
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.reflection import CohortDims

from .rng import stream

#: 覆盖三期，够画趋势。用**过去两期 + 当前期**，因为未来学期还没有行为可言。
PERIODS = ("2025-26_FALL", "2025-26_SPRING", "2026-27_FALL")

#: `(period, school, year_level, development_mode, n)`。
#:
#: 形状是刻意设计的，不是采样出来的：
#: * 每期加总 ≥ MIN_CELL_N —— institution 行才出得了数（B9 评测器的前提）；
#: * ENGG/BUS 的几格 ≥ 5 —— 分组对比里有真出数的格；
#: * 末尾两格 n ∈ 1..4 —— 分组对比里有 `Insufficient evidence` 的格；
#: * 三期的 seen/acted 基线逐期抬升 —— 趋势大致单调，看得出方向。
CELL_PLAN: tuple[tuple[str, str, int, str, int], ...] = (
    # ── 2025-26_FALL ──
    ("2025-26_FALL", "ENGG", 2, "employment", 9),
    ("2025-26_FALL", "ENGG", 3, "academia", 6),
    ("2025-26_FALL", "BUS", 2, "employment", 7),
    ("2025-26_FALL", "BUS", 3, "entrepreneurship", 5),
    ("2025-26_FALL", "SCI", 1, "exploration", 6),
    ("2025-26_FALL", "SCI", 4, "academia", 3),          # 薄格：抑制
    # ── 2025-26_SPRING ──
    ("2025-26_SPRING", "ENGG", 2, "employment", 11),
    ("2025-26_SPRING", "ENGG", 3, "academia", 7),
    ("2025-26_SPRING", "BUS", 2, "employment", 8),
    ("2025-26_SPRING", "BUS", 3, "entrepreneurship", 6),
    ("2025-26_SPRING", "SCI", 1, "exploration", 7),
    ("2025-26_SPRING", "SCI", 4, "academia", 2),        # 薄格：抑制
    # ── 2026-27_FALL（当前期）──
    ("2026-27_FALL", "ENGG", 2, "employment", 12),
    ("2026-27_FALL", "ENGG", 3, "academia", 8),
    ("2026-27_FALL", "BUS", 2, "employment", 9),
    ("2026-27_FALL", "BUS", 3, "entrepreneurship", 6),
    ("2026-27_FALL", "SCI", 1, "exploration", 8),
    ("2026-27_FALL", "SCI", 4, "academia", 4),          # 薄格：抑制
)

#: 每期的基线发现率与行动率。逐期小幅抬升，让趋势读得出方向。
_PERIOD_BASELINE = {
    "2025-26_FALL": (0.52, 0.18),
    "2025-26_SPRING": (0.58, 0.21),
    "2026-27_FALL": (0.64, 0.25),
}

_UNCOVERED_POOL = (
    RequirementCategory.RESEARCH_EXPERIENCE,
    RequirementCategory.INDUSTRY_EXPERIENCE,
    RequirementCategory.NETWORK,
    RequirementCategory.CREDENTIAL,
    RequirementCategory.LANGUAGE,
)


def build_metric_tuples() -> list[MetricTuple]:
    """按 cell plan 造合成元组。确定性：同样的 plan 出同样的字节。

    RNG 用**新命名空间** `metrics.synthetic.v2`——`stream` 的每个命名空间独立
    派生，所以新增它不会挪动任何既有表的取值，字节稳定性不受影响。
    绝不复用 `stream("feedback")`。
    """
    rng = stream("metrics.synthetic.v2")
    rows: list[MetricTuple] = []
    for period, school, year, mode, n in CELL_PLAN:
        discovery, action = _PERIOD_BASELINE[period]
        for i in range(n):
            eligible = 24 + rng.randrange(0, 22)
            # 由构造保证嵌套：seen ⊆ eligible，acted ⊆ seen。
            # 「碰巧满足」和「构造上满足」在这里差别很大——前者会在某次
            # 调参后无声地开始抛 ValidationError。
            seen = min(eligible, max(1, round(eligible * discovery)
                                     + rng.randrange(-3, 4)))
            acted = min(seen, max(0, round(seen * action) + rng.randrange(-1, 2)))
            gap_total = 8 + rng.randrange(0, 8)
            gap_covered = min(gap_total, max(0, round(gap_total * 0.62)
                                             + rng.randrange(-2, 3)))
            uncovered_n = gap_total - gap_covered
            uncovered = tuple(sorted(
                {_UNCOVERED_POOL[(i + k) % len(_UNCOVERED_POOL)]
                 for k in range(min(uncovered_n, 3))},
                key=lambda c: c.value))
            # 广场曝光的分母是**全部**浏览，与 eligible 无关——学生在广场上
            # 看到的包含他并不合格的机会，这正是校方想知道的信号。
            plaza_exposed = eligible + rng.randrange(8, 30)
            plaza_acted = min(plaza_exposed, acted + rng.randrange(0, 3))
            rows.append(MetricTuple(
                period=period,
                cohort_dims=CohortDims(school=school, year_level=year,
                                       development_mode=mode),
                provenance=MetricProvenance.SYNTHETIC,
                eligible_count=eligible,
                seen_count=seen,
                acted_count=acted,
                gap_total=gap_total,
                gap_covered=gap_covered,
                uncovered_requirement_categories=uncovered,
                surface_conversions=(
                    SurfaceConversion(surface="plaza",
                                      exposed_count=plaza_exposed,
                                      acted_count=plaza_acted),
                    SurfaceConversion(surface="for_you",
                                      exposed_count=seen,
                                      acted_count=acted),
                ),
            ))
    return rows


def thin_cells() -> tuple[tuple[str, str, int, str, int], ...]:
    """样本不足的格子。一致性检查用它断言"抑制真的会被演示到"。"""
    return tuple(c for c in CELL_PLAN if c[4] < MIN_CELL_N)
