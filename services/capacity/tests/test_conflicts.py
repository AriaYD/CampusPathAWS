"""时段冲突检测（Capacity & Calendar Service，零 LLM）。

**先红后绿**：`detect_conflicts` 此时还不存在。

为什么检测放在 Capacity 而不是 Rules 或 A5（Fable 5 裁定）：
重叠是纯区间数学，可单测可审计；而**全量时段真相只在 Capacity 手里**
（日历凭据止步于此是架构第 3 条），让别处去算等于在那条红线上打洞。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from campuspath_capacity.conflicts import Occupancy, detect_conflicts
from campuspath_contracts.common import LocalizedText
from campuspath_contracts.pathway import PlanItemConflictKind


def at(h: int, m: int = 0, day: int = 24) -> datetime:
    return datetime(2026, 9, day, h, m, tzinfo=timezone.utc)


def occ(start, end, *, oid="AB-x", kind=PlanItemConflictKind.COURSE, name="HUMA 1030"):
    return Occupancy(subject_id=oid, kind=kind,
                     label=LocalizedText(zh_Hans=name, en=name),
                     starts_at=start, ends_at=end)


def test_the_reported_case_is_detected() -> None:
    """用户实测那一条：活动 14:59–17:59 撞上 16:30–17:50 的课，重叠 80 分钟。"""
    found = detect_conflicts(at(14, 59), at(17, 59), [
        occ(at(16, 30), at(17, 50), oid="AB-huma1030", name="HUMA 1030"),
    ])
    assert len(found) == 1
    assert found[0].overlap_minutes == 80
    assert found[0].with_id == "AB-huma1030"


def test_touching_edges_is_not_a_conflict() -> None:
    """一个 14:00 结束、另一个 14:00 开始——**这不是冲突**。

    把邻接算成冲突，每个学生的每一天都会报一堆假冲突，
    真冲突随即淹没在噪声里。
    """
    assert detect_conflicts(at(12), at(14), [occ(at(14), at(16))]) == ()


def test_disjoint_is_not_a_conflict() -> None:
    assert detect_conflicts(at(9), at(10), [occ(at(16, 30), at(17, 50))]) == ()


def test_full_overlap_reports_the_whole_span() -> None:
    """缺陷 B 那一对：两个活动时间完全相同。"""
    found = detect_conflicts(at(14, 59), at(17, 59), [
        occ(at(14, 59), at(17, 59), oid="PI-2",
            kind=PlanItemConflictKind.PLANNED_ACTIVITY, name="作品集诊断会"),
    ])
    assert found[0].overlap_minutes == 180
    assert found[0].kind is PlanItemConflictKind.PLANNED_ACTIVITY


def test_contained_occupancy_reports_its_own_length() -> None:
    """被完全包住的那一方，重叠 = 它自己的长度（不能报成外层的长度）。"""
    found = detect_conflicts(at(9), at(18), [occ(at(12), at(12, 45))])
    assert found[0].overlap_minutes == 45


def test_sorted_by_overlap_desc() -> None:
    found = detect_conflicts(at(14), at(18), [
        occ(at(17, 30), at(18), oid="AB-short", name="短"),
        occ(at(14), at(16), oid="AB-long", name="长"),
    ])
    assert [c.with_id for c in found] == ["AB-long", "AB-short"]


def test_zero_length_candidate_conflicts_with_nothing() -> None:
    """长度为 0 的候选（数据异常）不该与任何东西冲突，而不是与所有东西冲突。"""
    assert detect_conflicts(at(14), at(14), [occ(at(9), at(20))]) == ()


def test_detector_imports_no_model_sdk() -> None:
    """零 LLM 是这一层的硬约束——用 AST 真解析 import，不扫文本。

    禁用清单**复用 `guards.imported_model_sdks`**，不在这里另抄一份：
    抄一份就有两处要维护，新增一个 SDK 时必漏其一。
    （顺带避开 pre-commit 的文本扫描——本文件不需要出现任何被禁的名字。）
    """
    import ast
    import pathlib

    import campuspath_capacity.conflicts as mod
    from campuspath_contracts.guards import imported_model_sdks

    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    assert imported_model_sdks(names) == set(), names
    # 检查器自身要能响：喂一个已知会中的名字进去（从清单里现取，不写死）
    from campuspath_contracts.guards import MODEL_SDK_MODULES
    canary = sorted(MODEL_SDK_MODULES)[0]
    assert imported_model_sdks([canary]) == {canary}, "禁用清单形同虚设"
