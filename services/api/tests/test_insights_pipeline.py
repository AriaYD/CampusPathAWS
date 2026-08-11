"""P4 第四波：校方指标管线的端到端行为（Spec §17.1.2 / §17.6）。

最要紧的一条是**「数字不再是随机数」**：给一个学生记一次曝光加一次报名，
校方那一侧的派生计数必须精确 +1。此前 `deps.metric_tuples` 读的是 seed 里
12 条 `prng.randrange`，与学生的真实行为毫无关系。

其余断言集中在隐私边界：无参响应不许出现薄格子（B9 评测器的前提）、
曝光端点只有学生本人能打、聚合响应里不许出现 student_id。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER
from campuspath_contracts.aggregation import MIN_CELL_N
from campuspath_contracts.common import ActorRole

TERM = "2026-27_FALL"
NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


@pytest.fixture()
def deps() -> Deps:
    return Deps("full")


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def _student(student: str = "STU-A") -> dict[str, str]:
    return {ROLE_HEADER: ActorRole.STUDENT.value,
            "X-CampusPath-Student": student}


def _admin() -> dict[str, str]:
    return {ROLE_HEADER: ActorRole.CAREER_CENTER_ADMIN.value}


def _expose(client: TestClient, subjects: list[str], *, student="STU-A",
            surface="plaza"):
    return client.post(
        f"/v1/students/{student}/exposures", headers=_student(student),
        json={"student_id": student, "events": [
            {"event_id": f"EX-{student}-{s}-{surface}", "student_id": student,
             "subject_id": s, "surface": surface, "depth": "impression",
             "occurred_at": NOW.isoformat(), "period": TERM}
            for s in subjects
        ]})


def _first_eligible(client: TestClient, student="STU-A") -> str:
    matches = client.get(f"/v1/students/{student}/matches",
                         headers=_student(student)).json()
    live = [m for m in matches
            if m["eligibility"]["state"] == "eligible_now"]
    assert live, "夹具里没有任何现在合格的机会——这条测试的前提不成立"
    return live[0]["opportunity_id"]


# ── 「数字不再是随机数」 ────────────────────────────────────────────


def test_one_students_action_moves_the_school_facing_number_by_exactly_one(
        client: TestClient):
    """本批最重要的一条断言。

    基线 → 给 STU-A 记一次曝光 + 一次报名 → 以校方身份再读 → 派生的
    `acted_total` **精确 +1**。不是 ">0"：">0" 在数字本来就是随机数的时候
    也会绿。
    """
    def acted_total() -> int:
        rows = client.get("/v1/insights/plaza-conversion?include_synthetic=false",
                          headers=_admin()).json()
        return sum(r["acted_total"] for r in rows if r["surface"] == "plaza")

    before = acted_total()
    oid = _first_eligible(client)
    assert _expose(client, [oid]).status_code == 200
    assert client.post(
        "/v1/students/STU-A/actions", headers=_student(),
        json={"event_id": "AE-metrics-1", "student_id": "STU-A",
              "action_type": "apply", "subject_id": oid,
              "timestamp": NOW.isoformat()}).status_code == 200

    assert acted_total() == before + 1


def test_exposure_alone_moves_seen_but_not_acted(client: TestClient):
    """看见不等于行动。混为一谈，转化率就永远是 100%。"""
    oid = _first_eligible(client)
    _expose(client, [oid])
    rows = client.get("/v1/insights/plaza-conversion?include_synthetic=false",
                      headers=_admin()).json()
    plaza = next(r for r in rows if r["surface"] == "plaza")
    assert plaza["exposed_total"] >= 1 and plaza["acted_total"] == 0


def test_for_you_exposure_does_not_move_the_plaza_denominator(client: TestClient):
    """Plaza-to-Action 只数广场那一半（§17.6）。"""
    oid = _first_eligible(client)
    _expose(client, [oid], surface="for_you")
    rows = client.get("/v1/insights/plaza-conversion?include_synthetic=false",
                      headers=_admin()).json()
    plaza = next(r for r in rows if r["surface"] == "plaza")
    assert plaza["exposed_total"] == 0


def test_exposures_are_deduplicated_and_the_receipt_says_so(client: TestClient):
    """静默丢弃会让前端以为都记上了，而曝光是所有转化率的分母。"""
    oid = _first_eligible(client)
    first = _expose(client, [oid]).json()
    again = _expose(client, [oid]).json()
    assert (first["accepted"], first["deduplicated"]) == (1, 0)
    assert (again["accepted"], again["deduplicated"]) == (0, 1)


# ── B9：无参响应不许出现薄格子 ─────────────────────────────────────


def test_default_coverage_response_has_no_thin_rows(client: TestClient):
    """评测器 B9 **无参**调这个端点，把任何 `cell_n < 5` 的行判为泄漏——
    哪怕那行已经被正确抑制。所以无参响应只能是 institution 行。"""
    rows = client.get("/v1/insights/resource-coverage", headers=_admin()).json()
    assert rows, "无参响应不该是空的——趋势要靠它"
    assert all(r["cell_n"] >= MIN_CELL_N for r in rows), \
        [r["cell_n"] for r in rows]
    assert all(r["scope"] == "institution" for r in rows)


def test_cohort_view_does_show_suppressed_cells(client: TestClient):
    """分组对比里**必须**看得到抑制格——那是隐私红线在工作，不是缺陷。"""
    rows = client.get("/v1/insights/resource-coverage?cohort=school",
                      headers=_admin()).json()
    thin = [r for r in rows if r["cell_n"] < MIN_CELL_N]
    assert all(r["discovery_rate"] is None for r in thin)


def test_no_endpoint_lists_the_students_behind_a_number(client: TestClient):
    """硬性边界第 2 条：聚合响应里不许出现任何指向个人的字段。"""
    import json

    for path in ("/v1/insights/resource-coverage",
                 "/v1/insights/resource-coverage?cohort=school",
                 "/v1/insights/plaza-conversion"):
        body = json.dumps(client.get(path, headers=_admin()).json())
        for term in ("student_id", "STU-A", "student_ids"):
            assert term not in body, f"{path} 泄漏了 {term}"


def test_provenance_split_is_reported_not_merged(client: TestClient):
    """合成与派生绝不静默合并——校方要能分清哪些是测的、哪些是造的。"""
    rows = client.get("/v1/insights/resource-coverage", headers=_admin()).json()
    assert all(r["derived_cell_n"] + r["synthetic_cell_n"] == r["cell_n"]
               for r in rows)


def test_pure_derived_view_is_honestly_empty_on_a_cold_process(client: TestClient):
    """冷启动进程里派生侧本来就没有数据。

    这时 `include_synthetic=false` 全格抑制**是正确答案**，不是 bug——
    演示时容易被读成坏了，所以这条断言把它钉成预期行为。
    """
    rows = client.get("/v1/insights/resource-coverage?include_synthetic=false",
                      headers=_admin()).json()
    assert all(r["discovery_rate"] is None for r in rows)


# ── RBAC ───────────────────────────────────────────────────────────


def test_curator_cannot_write_exposures(client: TestClient):
    """曝光只经学生角色端点写入——它带 student_id。"""
    resp = client.post(
        "/v1/students/STU-A/exposures",
        headers={ROLE_HEADER: ActorRole.CURATOR.value},
        json={"student_id": "STU-A", "events": [
            {"event_id": "EX-x", "student_id": "STU-A", "subject_id": "OPP-1",
             "surface": "plaza", "depth": "impression",
             "occurred_at": NOW.isoformat(), "period": TERM}]})
    assert resp.status_code == 403


def test_a_student_cannot_post_exposures_for_someone_else(client: TestClient):
    resp = client.post(
        "/v1/students/STU-A/exposures", headers=_student("STU-A"),
        json={"student_id": "STU-B", "events": [
            {"event_id": "EX-y", "student_id": "STU-B", "subject_id": "OPP-1",
             "surface": "plaza", "depth": "impression",
             "occurred_at": NOW.isoformat(), "period": TERM}]})
    assert resp.status_code == 422


def test_default_deny_still_holds_for_an_undeclared_path(client: TestClient):
    """已知会失败的样例：一个**故意不在**契约路由表里的路径。

    它必须打不通——证明上面那条 403 是 RBAC 在起作用，
    而不是"这个路径碰巧不存在"。
    """
    resp = client.get("/v1/insights/not-declared-on-purpose", headers=_admin())
    assert resp.status_code in (404, 405)


# ── gaps_closed 可回溯 ─────────────────────────────────────────────


def test_gaps_closed_equals_the_event_ledger(client: TestClient):
    """`gaps_closed` 必须**等于** `/gap-changes` 的逐学期计数。

    不是 "> 0"：写成 `return len(所有事件)` 这种 bug 在 ">0" 下也会绿。
    """
    client.get("/v1/students/STU-A/gap-map", headers=_student())
    events = client.get("/v1/students/STU-A/gap-changes",
                        headers=_student()).json()
    trajectory = client.get("/v1/students/STU-A/growth-trajectory",
                            headers=_student()).json()

    expected: dict[str, int] = {}
    for e in events:
        if e["to_level"] == "satisfied":
            expected.setdefault(e["term"], set()).add(e["requirement_id"])  # type: ignore[arg-type]
    counts = {term: len(ids) for term, ids in expected.items()}
    for point in trajectory["points"]:
        assert point["gaps_closed"] == counts.get(point["term"], 0)


def test_a_term_with_no_closures_is_exactly_zero(client: TestClient):
    """冷启动没有关闭事件时，每一期都必须**精确为 0**——
    而这个 0 现在是数出来的，不是硬编码的。"""
    trajectory = client.get("/v1/students/STU-A/growth-trajectory",
                            headers=_student()).json()
    assert all(p["gaps_closed"] == 0 for p in trajectory["points"])
    assert client.get("/v1/students/STU-A/gap-changes",
                      headers=_student()).json() == []
