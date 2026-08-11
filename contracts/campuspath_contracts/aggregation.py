"""Spec §17.1.2 / §14.4：匿名聚合与校方洞察。

Aggregation Service 是确定性零 LLM 服务，只接受两类输入：

* :class:`~campuspath_contracts.reflection.EventQualityFeedback` —— 活动质量；
* :class:`MetricTuple` —— 资源利用率（去标识元组）。

契约层强制两条 BLOCKER：

* **B10 MetricTuple Field Leakage**：元组的字段列表就是全部允许出域的内容。
  ``uncovered_requirement_categories`` 只收枚举的**要求类别**，
  不收缺口原文——原文能反推到具体学生。
* **B9 Metric Re-identification**：样本量低于阈值的单元格**必须**把数值置为 None
  并显示 `Insufficient evidence`。这里用 validator 强制，
  而不是指望前端记得判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import Field, model_validator

from .common import CampusPathModel, Identifier, StrEnum, TermCode
from .goals import RequirementCategory
from .reflection import CohortDims, QualityDimension

#: 低于该样本量的任何聚合单元格一律抑制（Spec §17.1.2 硬性边界第 1 条）。
#: 数值是产品规则而非统计定理，改动须同步评测项 B9 的用例。
MIN_CELL_N = 5

#: 分组维度可组合的最大层数，防止多重筛选把单元格缩到可识别规模（硬性边界第 3 条）。
MAX_COHORT_DIMENSIONS = 2


class InsufficientEvidence(StrEnum):
    """UI 必须显示的占位值。刻意做成枚举，避免被渲染成 0 或 '-'。"""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MetricProvenance(StrEnum):
    """这条元组是**真的算出来的**，还是**造出来演示的**。

    两者绝不静默合并（2026-08-10 用户裁定 B）。冷启动的进程里派生侧本来就没有
    数据，如果把合成数据混进去充数，校方看到的每个百分比都失去意义。
    """

    #: 从真实曝光 × 资格 × 行动 × gap map 推导
    DERIVED = "derived"
    #: seed 造的演示样本。``seed/`` **永远不得**产出 ``derived``
    SYNTHETIC = "synthetic"


class SurfaceConversion(CampusPathModel):
    """某一个入口（广场 / 为你推荐）上的「看见 → 行动」转化（Spec §17.6）。

    嵌在 :class:`MetricTuple` 里而不是另开一条流：广场转化的分母是**全部**
    广场曝光，不满足 ``seen ≤ eligible`` 那条嵌套约束（学生在广场上看到的
    包括他并不合格的机会——而那恰恰是校方最想知道的信号）。放进带自己
    局部不变量的子模型，既保住「每人每期一条元组」，也不动现有 validator。
    """

    surface: Literal["plaza", "for_you"]
    exposed_count: int = Field(ge=0)
    acted_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _acted_within_exposed(self) -> "SurfaceConversion":
        if self.acted_count > self.exposed_count:
            raise ValueError("acted_count 不能超过 exposed_count（行动必先经过曝光）")
        return self


class OpportunityExposureCount(CampusPathModel):
    """逐机会的曝光计数，用于曝光断层榜。

    刻意是**计数**而不是「每个学生看过哪些机会的 id 集合」——后者本身就是指纹，
    足以把聚合反推回个人。累加在学生域内完成，只让计数出域。
    """

    period: TermCode
    opportunity_id: Identifier
    eligible_n: int = Field(ge=0)
    seen_n: int = Field(ge=0)
    acted_n: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_are_nested(self) -> "OpportunityExposureCount":
        if self.seen_n > self.eligible_n:
            raise ValueError("seen_n 不能超过 eligible_n")
        if self.acted_n > self.seen_n:
            raise ValueError("acted_n 不能超过 seen_n")
        return self


class MetricTuple(CampusPathModel):
    """离开学生数据域时携带的全部内容（Spec §17.1.2）。

    计算发生在学生私有域内；这个对象是**计算结果**，出域时已无 student_id。
    原始曝光与行动记录永不离开。
    """

    period: TermCode
    cohort_dims: CohortDims
    #: **必填无默认**（2026-08-10）：给它一个默认值，就等于允许未来的生产者
    #: 忘了声明来源。必填会当场弄红 seed 与既有测试——那正是目的。
    provenance: MetricProvenance
    eligible_count: int = Field(ge=0)
    seen_count: int = Field(ge=0)
    acted_count: int = Field(ge=0)
    gap_total: int = Field(ge=0)
    gap_covered: int = Field(ge=0)
    uncovered_requirement_categories: tuple[RequirementCategory, ...] = ()
    surface_conversions: tuple[SurfaceConversion, ...] = ()

    @model_validator(mode="after")
    def _counts_are_nested(self) -> "MetricTuple":
        if self.seen_count > self.eligible_count:
            raise ValueError("seen_count 不能超过 eligible_count")
        if self.acted_count > self.seen_count:
            raise ValueError("acted_count 不能超过 seen_count（行动必先经过曝光）")
        if self.gap_covered > self.gap_total:
            raise ValueError("gap_covered 不能超过 gap_total")
        return self

    @model_validator(mode="after")
    def _one_row_per_surface(self) -> "MetricTuple":
        surfaces = [s.surface for s in self.surface_conversions]
        if len(surfaces) != len(set(surfaces)):
            raise ValueError("同一个入口出现了两行转化——聚合时会被重复计数")
        return self


class SuppressedCell(CampusPathModel):
    """被抑制的单元格。**记录被抑制这件事本身，但不记录被抑制的数值。**"""

    cell_key: str
    n: int = Field(ge=0)
    reason: Literal["below_min_cell_n", "too_many_dimensions"] = "below_min_cell_n"


class ExposureGapEntry(CampusPathModel):
    """曝光断层榜的一行：合格的人多，实际看到的人少。"""

    opportunity_id: Identifier
    eligible_n: int = Field(ge=MIN_CELL_N)
    seen_n: int = Field(ge=0)
    exposure_rate: float = Field(ge=0, le=1)


class UnmetRequirementEntry(CampusPathModel):
    """供给缺口榜的一行：这个要求类别，资源池里没有东西能覆盖。"""

    category: RequirementCategory
    occurrences: int = Field(ge=MIN_CELL_N)
    covered_by_any_resource: bool = False


class ResourceCoverageAggregate(CampusPathModel):
    """校方看到的最终形态。三项比率在样本不足时**必须**为 None。"""

    aggregate_id: Identifier
    period: TermCode
    scope: Literal["institution", "school", "year_level", "development_mode"]
    cohort_dims_used: tuple[str, ...] = ()
    cell_n: int = Field(ge=0)
    #: 拆开报，别让校方把「造的」当「测的」（2026-08-10 用户裁定 B）
    derived_cell_n: int = Field(default=0, ge=0)
    synthetic_cell_n: int = Field(default=0, ge=0)
    discovery_rate: float | None = Field(default=None, ge=0, le=1)
    action_rate: float | None = Field(default=None, ge=0, le=1)
    gap_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    exposure_gap_ranking: tuple[ExposureGapEntry, ...] = ()
    unmet_requirement_ranking: tuple[UnmetRequirementEntry, ...] = ()
    suppressed_cells: tuple[SuppressedCell, ...] = ()
    computed_at: datetime

    #: 抑制清单的**单一出处**。以前是写死在 validator 里的字面量列表，
    #: 于是每加一个比率字段就要有人记得回来改它——记不住的那一次就是 B9 泄漏。
    SUPPRESSED_FIELDS: ClassVar[tuple[str, ...]] = (
        "discovery_rate", "action_rate", "gap_coverage_rate")

    @model_validator(mode="after")
    def _suppress_small_cells(self) -> "ResourceCoverageAggregate":
        if len(self.cohort_dims_used) > MAX_COHORT_DIMENSIONS:
            raise ValueError(
                f"分组维度层数 {len(self.cohort_dims_used)} 超过上限 {MAX_COHORT_DIMENSIONS}（B9）"
            )
        if self.cell_n < MIN_CELL_N:
            leaked = [
                name
                for name in type(self).SUPPRESSED_FIELDS
                if getattr(self, name) is not None
            ]
            if leaked or self.exposure_gap_ranking or self.unmet_requirement_ranking:
                raise ValueError(
                    f"样本量 {self.cell_n} < {MIN_CELL_N}，必须抑制数值并显示 "
                    f"Insufficient evidence（B9）；仍携带：{leaked or '排行榜'}"
                )
        return self

    @model_validator(mode="after")
    def _provenance_split_adds_up(self) -> "ResourceCoverageAggregate":
        total = self.derived_cell_n + self.synthetic_cell_n
        if total and total != self.cell_n:
            raise ValueError(
                f"来源拆分 {self.derived_cell_n}+{self.synthetic_cell_n}={total} "
                f"与 cell_n={self.cell_n} 对不上——有一侧被漏计了"
            )
        return self


class PlazaConversionAggregate(CampusPathModel):
    """Plaza-to-Action Conversion（Spec §17.6）：广场上看到的，有多少变成了行动。

    与 :class:`ResourceCoverageAggregate` 共用同一条抑制规则——样本不足就没有比率。
    分开成一个模型是因为它的分母不同（全部曝光，而不是「合格的机会」）。
    """

    aggregate_id: Identifier
    period: TermCode
    surface: Literal["plaza", "for_you"]
    cell_n: int = Field(ge=0)
    derived_cell_n: int = Field(default=0, ge=0)
    synthetic_cell_n: int = Field(default=0, ge=0)
    exposed_total: int = Field(ge=0)
    acted_total: int = Field(ge=0)
    conversion_rate: float | None = Field(default=None, ge=0, le=1)
    computed_at: datetime

    SUPPRESSED_FIELDS: ClassVar[tuple[str, ...]] = ("conversion_rate",)

    @model_validator(mode="after")
    def _suppress_small_cells(self) -> "PlazaConversionAggregate":
        if self.acted_total > self.exposed_total:
            raise ValueError("acted_total 不能超过 exposed_total")
        if self.cell_n < MIN_CELL_N:
            leaked = [
                name for name in type(self).SUPPRESSED_FIELDS
                if getattr(self, name) is not None
            ]
            if leaked:
                raise ValueError(
                    f"样本量 {self.cell_n} < {MIN_CELL_N}，必须抑制比率并显示 "
                    f"Insufficient evidence（B9）；仍携带：{leaked}"
                )
        return self


class DimensionAggregate(CampusPathModel):
    dimension: QualityDimension
    weighted_score: float = Field(ge=1, le=5)
    ci_low: float = Field(ge=1, le=5)
    ci_high: float = Field(ge=1, le=5)

    @model_validator(mode="after")
    def _interval_contains_estimate(self) -> "DimensionAggregate":
        if not (self.ci_low <= self.weighted_score <= self.ci_high):
            raise ValueError("weighted_score 必须落在置信区间内")
        return self


class EventQualityAggregate(CampusPathModel):
    """活动质量聚合（Spec §14.4）。时间衰减 + 届次/系列分层 + 样本阈值。"""

    aggregate_id: Identifier
    occurrence_id: Identifier | None = None
    series_id: Identifier | None = None
    cohort: CohortDims | None = None
    verified_n: int = Field(ge=0)
    dimensions: tuple[DimensionAggregate, ...] = ()
    time_decay_half_life_days: int = Field(default=365, ge=30)
    last_updated: datetime

    @model_validator(mode="after")
    def _threshold_and_target(self) -> "EventQualityAggregate":
        if self.occurrence_id is None and self.series_id is None:
            raise ValueError("质量聚合必须指向某一届或某个系列")
        if self.verified_n < MIN_CELL_N and self.dimensions:
            raise ValueError(
                f"verified_n={self.verified_n} 低于阈值 {MIN_CELL_N}，"
                "不得输出维度分数（B9）"
            )
        return self
