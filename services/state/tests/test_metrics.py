"""P4 第三波：学生私有域内的派生计算（Spec §17.1.2）。

这一层的职责只有一句话：**带 student_id 的东西进去，不带的出来**。
所以这里的断言集中在两处——口径对不对（分子分母各是什么），
以及不变量是**由构造成立**还是碰巧成立。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.aggregation import MetricProvenance
from campuspath_contracts.goals import (
    GapChangeOrigin, GapLevel, RequirementCategory)
from campuspath_contracts.pathway import (
    ActionEvent, ActionType, ExposureDepth, ExposureEvent, ExposureSurface)
from campuspath_contracts.reflection import CohortDims
from campuspath_state.exposure import ExposureLog, ExposureStore
from campuspath_state.metrics import (
    StudentMetricInputs, derive_metric_tuple, diff_gap_levels,
    gaps_closed_by_term, opportunity_exposure_counts)

TERM = "2026-27_FALL"
NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
COHORT = CohortDims(school="ENGG", year_level=2, development_mode="employment")


def _exposure(subject: str, *, student="STU-A", surface=ExposureSurface.PLAZA,
              depth=ExposureDepth.IMPRESSION, at=NOW, eid=None) -> ExposureEvent:
    return ExposureEvent(
        event_id=eid or f"EX-{subject}-{surface.value}-{at.isoformat()}",
        student_id=student, subject_id=subject, surface=surface, depth=depth,
        occurred_at=at, period=TERM)


def _action(subject: str, kind=ActionType.APPLY, at=NOW, student="STU-A") -> ActionEvent:
    return ActionEvent(
        event_id=f"AE-{subject}-{kind.value}", student_id=student,
        action_type=kind, subject_id=subject, timestamp=at)


def _log(*events: ExposureEvent, student="STU-A") -> ExposureLog:
    log = ExposureLog(student_id=student)
    log.record(events)
    return log


def _inputs(**kw) -> StudentMetricInputs:
    base = dict(
        period=TERM, cohort_dims=COHORT,
        eligible_ids=frozenset({"OPP-1", "OPP-2", "OPP-3"}),
        actions=(),
        gap_categories=(RequirementCategory.TECHNICAL_SKILL,
                        RequirementCategory.NETWORK),
        covered_categories=frozenset({RequirementCategory.TECHNICAL_SKILL}),
    )
    base.update(kw)
    return StudentMetricInputs(**base)


# ── 曝光日志 ────────────────────────────────────────────────────────


def test_same_card_scrolled_twice_in_a_day_is_one_exposure():
    """按次数计会把「有多少人看见过」变成「有多少次滚动」。"""
    log = ExposureLog(student_id="STU-A")
    accepted, deduped = log.record((
        _exposure("OPP-1", at=NOW),
        _exposure("OPP-1", at=NOW.replace(hour=15), eid="EX-again"),
    ))
    assert (accepted, deduped) == (1, 1)


def test_dedup_is_per_day_not_forever():
    """明天再看见是新的一次曝光——否则「本学期有多少人看过」永远只算首日。"""
    log = ExposureLog(student_id="STU-A")
    log.record((_exposure("OPP-1", at=NOW),))
    accepted, _ = log.record((
        _exposure("OPP-1", at=NOW.replace(day=16), eid="EX-tomorrow"),))
    assert accepted == 1


def test_detail_and_impression_are_different_exposures():
    """看见和点开是两件事，转化意义不同。"""
    log = ExposureLog(student_id="STU-A")
    accepted, deduped = log.record((
        _exposure("OPP-1"),
        _exposure("OPP-1", depth=ExposureDepth.DETAIL, eid="EX-detail"),
    ))
    assert (accepted, deduped) == (2, 0)


def test_log_refuses_another_students_event():
    log = ExposureLog(student_id="STU-A")
    with pytest.raises(ValueError):
        log.record((_exposure("OPP-1", student="STU-B"),))


def test_last_touch_ignores_exposures_after_the_action():
    """归因看的是行动**之前**最近一次曝光。之后的曝光不能倒过来解释它。"""
    log = _log(
        _exposure("OPP-1", surface=ExposureSurface.PLAZA,
                  at=NOW.replace(hour=8), eid="EX-a"),
        _exposure("OPP-1", surface=ExposureSurface.FOR_YOU,
                  at=NOW.replace(hour=18), eid="EX-b"),
    )
    assert log.last_touch_surface("OPP-1", NOW.replace(hour=12)) is ExposureSurface.PLAZA


def test_last_touch_returns_none_when_never_exposed():
    """归不上就是归不上——不猜一个默认入口。"""
    assert _log().last_touch_surface("OPP-9", NOW) is None


def test_store_counts_students_not_events():
    """曝光断层榜的分子是「多少人看见」，不是「滚动了多少次」。"""
    store = ExposureStore()
    store.log_for("STU-A").record((
        _exposure("OPP-1"), _exposure("OPP-1", depth=ExposureDepth.DETAIL, eid="d")))
    store.log_for("STU-B").record((_exposure("OPP-1", student="STU-B"),))
    assert store.opportunity_seen_counts(TERM)["OPP-1"] == 2


# ── 派生元组：口径与不变量 ──────────────────────────────────────────


def test_derived_tuple_is_marked_derived_and_carries_no_student():
    row = derive_metric_tuple(_inputs(), _log(_exposure("OPP-1")))
    assert row.provenance is MetricProvenance.DERIVED
    assert "student_id" not in row.model_fields


def test_acting_on_something_never_logged_as_seen_still_counts_as_seen():
    """「行动蕴含看见」——不做这一步，acted > seen 会让契约当场抛错，
    而那并不是数据错，是口径错。"""
    row = derive_metric_tuple(
        _inputs(actions=(_action("OPP-2"),)), _log())      # 零曝光记录
    assert row.seen_count == 1 and row.acted_count == 1


def test_ineligible_opportunities_stay_out_of_the_denominator():
    """学生看到的包含他不合格的机会；主计数只数合格的那些。"""
    row = derive_metric_tuple(
        _inputs(), _log(_exposure("OPP-1"), _exposure("OPP-99")))
    assert row.eligible_count == 3
    assert row.seen_count == 1          # OPP-99 不在 eligible 里


def test_declining_is_not_a_conversion():
    """取消收藏与拒绝是反向信号，混进转化率里等于奖励反悔。"""
    row = derive_metric_tuple(
        _inputs(actions=(_action("OPP-1", ActionType.DECLINE),
                         _action("OPP-2", ActionType.UNSAVE))),
        _log(_exposure("OPP-1"), _exposure("OPP-2")))
    assert row.acted_count == 0


def test_reflecting_is_not_a_conversion_either():
    """写反思走的是 VGA 那条闭环，不是「广场看到 → 去做」这条。"""
    row = derive_metric_tuple(
        _inputs(actions=(_action("OPP-1", ActionType.REFLECT),)),
        _log(_exposure("OPP-1")))
    assert row.acted_count == 0


def test_plaza_denominator_is_not_intersected_with_eligibility():
    """广场浏览就是浏览。把它与 E 求交会抹掉「对不合格的机会点了报名」
    这个信号——而那正是校方最想知道的。"""
    row = derive_metric_tuple(
        _inputs(eligible_ids=frozenset({"OPP-1"})),
        _log(_exposure("OPP-1"), _exposure("OPP-88"), _exposure("OPP-99")))
    plaza = next(s for s in row.surface_conversions if s.surface == "plaza")
    assert plaza.exposed_count == 3 > row.eligible_count


def test_gap_coverage_counts_categories_not_requirements():
    row = derive_metric_tuple(_inputs(), _log())
    assert (row.gap_total, row.gap_covered) == (2, 1)
    assert row.uncovered_requirement_categories == (RequirementCategory.NETWORK,)


def test_cohort_dims_reject_a_fingerprint_shaped_school():
    """已知会失败的样例：把可反推到个人的串塞进分组维度。

    这条守的是**这层守卫还活着**——CohortDims 的约束一旦被放宽，
    整个聚合域的匿名性就没了地基。
    """
    with pytest.raises(ValidationError):
        CohortDims(school="ENGG/COMP/AI-track/2024-intake",
                   year_level=2, development_mode="employment")


# ── 逐机会计数 ──────────────────────────────────────────────────────


def test_opportunity_counts_are_nested_by_construction():
    counts = opportunity_exposure_counts(
        TERM,
        eligible_by_student={"STU-A": frozenset({"OPP-1"}),
                             "STU-B": frozenset({"OPP-1"})},
        seen_by_student={"STU-A": {"OPP-1"}},
        acted_by_student={"STU-A": {"OPP-1"}},
    )
    row = next(c for c in counts if c.opportunity_id == "OPP-1")
    assert (row.eligible_n, row.seen_n, row.acted_n) == (2, 1, 1)


def test_acting_without_being_eligible_does_not_inflate_the_row():
    """不合格的人的行动不进这张榜——榜的口径是「合格却没看到」。"""
    counts = opportunity_exposure_counts(
        TERM,
        eligible_by_student={"STU-A": frozenset({"OPP-1"})},
        seen_by_student={"STU-B": {"OPP-1"}},
        acted_by_student={"STU-B": {"OPP-1"}},
    )
    row = next(c for c in counts if c.opportunity_id == "OPP-1")
    assert (row.eligible_n, row.seen_n, row.acted_n) == (1, 0, 0)


# ── Gap 差分：关闭 = 从列表里消失 ───────────────────────────────────


def _snapshot(**kw) -> dict[str, tuple[RequirementCategory, GapLevel]]:
    return {k: v for k, v in kw.items()}


def test_a_requirement_vanishing_means_it_was_satisfied():
    """gap_map 对已满足的要求是**跳过**的，所以「关闭」表现为从列表里消失。

    差分不把消失判为 satisfied，`gaps_closed` 就会永远是 0——只是把
    硬编码 0 那个错换了个位置重犯。
    """
    events = diff_gap_levels(
        "STU-A", TERM,
        before=_snapshot(**{"REQ-1": (RequirementCategory.TECHNICAL_SKILL,
                                      GapLevel.MISSING)}),
        after={},
        evidence_by_requirement={"REQ-1": ("EV-1",)},
        detected_at=NOW)
    assert len(events) == 1
    assert events[0].to_level is GapLevel.SATISFIED
    assert events[0].evidence_ids == ("EV-1",)


def test_a_closure_without_evidence_produces_no_event():
    """已知会失败的样例：说关闭了，却说不出是什么关闭的——不计数。"""
    events = diff_gap_levels(
        "STU-A", TERM,
        before=_snapshot(**{"REQ-1": (RequirementCategory.NETWORK,
                                      GapLevel.MISSING)}),
        after={}, evidence_by_requirement={}, detected_at=NOW)
    assert events == ()


def test_a_student_who_closed_nothing_produces_zero_events():
    """已知会失败的样例的反面：防「重放把所有要求都标成关闭」。"""
    snap = _snapshot(**{"REQ-1": (RequirementCategory.NETWORK, GapLevel.MISSING),
                        "REQ-2": (RequirementCategory.CREDENTIAL, GapLevel.PARTIAL)})
    assert diff_gap_levels("STU-A", TERM, before=snap, after=snap,
                           evidence_by_requirement={"REQ-1": ("EV-1",)},
                           detected_at=NOW) == ()


def test_a_downgrade_is_recorded_and_needs_no_evidence():
    events = diff_gap_levels(
        "STU-A", TERM,
        before=_snapshot(**{"REQ-1": (RequirementCategory.NETWORK,
                                      GapLevel.PARTIAL)}),
        after=_snapshot(**{"REQ-1": (RequirementCategory.NETWORK,
                                     GapLevel.MISSING)}),
        evidence_by_requirement={}, detected_at=NOW)
    assert len(events) == 1 and events[0].to_level is GapLevel.MISSING


def test_the_same_requirement_is_not_counted_twice_in_one_term():
    """先关后开再关会被算成两次——那是把反复计成了成果。"""
    close = diff_gap_levels(
        "STU-A", TERM,
        before=_snapshot(**{"REQ-1": (RequirementCategory.NETWORK,
                                      GapLevel.MISSING)}),
        after={}, evidence_by_requirement={"REQ-1": ("EV-1",)},
        detected_at=NOW)
    again = diff_gap_levels(
        "STU-A", TERM,
        before=_snapshot(**{"REQ-1": (RequirementCategory.NETWORK,
                                      GapLevel.PARTIAL)}),
        after={}, evidence_by_requirement={"REQ-1": ("EV-2",)},
        detected_at=NOW, id_prefix="GC2")
    assert gaps_closed_by_term(close + again) == {TERM: 1}


def test_replay_and_observed_stay_distinguishable():
    events = diff_gap_levels(
        "STU-A", TERM,
        before=_snapshot(**{"REQ-1": (RequirementCategory.NETWORK,
                                      GapLevel.MISSING)}),
        after={}, evidence_by_requirement={"REQ-1": ("EV-1",)},
        detected_at=NOW, origin=GapChangeOrigin.REPLAY)
    assert events[0].origin is GapChangeOrigin.REPLAY


# ── 分层：state 不许碰 Agent 与 Rules ───────────────────────────────


def test_state_layer_imports_neither_agents_nor_rules():
    """资格判定与缺口图必须由编排层算好递进来。

    这条断言比看上去重要：一旦 state 能 import rules，`make llm-free` 的
    四层扫描边界就被打穿了，模型 SDK 会顺着依赖爬进零 LLM 平面。
    """
    import ast
    import pathlib

    # 用 AST 解析真实 import，**不做文本扫描**：第一版扫文本，结果被这个
    # 模块自己 docstring 里的「不得 import campuspath_agents」那句话判红了。
    # 检查器把注释当成依赖，就等于它根本没在检查依赖。
    banned = {"campuspath_agents", "campuspath_rules"}
    root = pathlib.Path(__file__).resolve().parents[1] / "campuspath_state"
    offenders: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in banned:
                    offenders.append(f"{path.name}: {name}")
    assert not offenders, f"state 层引用了上层：{offenders}"
