"""规划读出来时必须自带冲突事实（用户 2026-08-11 报障 A/B）。

**先红后绿**：现在 `GET /pathway` 的 plan_items 一律 `conflicts=()`。

这些用例钉的是四件事：
1. 活动撞课要被报出来，且重叠分钟数**精确**（不是"有冲突"这种含糊话）；
2. 同一份计划里两个时间完全相同的活动要**互相**报冲突——
   缺陷 B 的真相不是"日历少画了一个"，是规划本身给了两个撞死的活动；
3. 采纳带冲突的草案必须**显式确认**才放行——不确认就 409。
   这是「系统给排序，你来拍板」在服务端的落点，前端拦不住直连 API 的人；
4. 「再想想」永远不被拦——拦住"放弃"等于逼学生接受。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER
from campuspath_contracts.common import ActorRole
from campuspath_contracts.pathway import PlanItemConflictKind

STUDENT = "STU-A"
A5_SCRIPT = "\n".join([
    "OPP-EVT-025\t同时段活动之一\tOne of two at the same hour",
    "OPP-EVT-012\t同时段活动之二\tThe other one",
    "OPP-EVT-046\t与课程重叠的工作坊\tWorkshop clashing with a lecture",
    "overall\t优先近期可完成的差距闭环\tClose near-term gaps first",
])


@pytest.fixture()
def deps() -> Deps:
    d = Deps("full")
    d.model = ScriptedModel({f"a5-pathway:{STUDENT}": A5_SCRIPT,
                             f"match_rationale:{STUDENT}": "为目标补差距\tCloses a gap"})
    return d


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def call(client, method, path, **kw):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


def _adopt(client) -> dict:
    d = call(client, "POST", f"/v1/students/{STUDENT}/pathway/draft")
    assert d.status_code == 200, d.text
    draft = d.json()
    call(client, "POST",
         f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
         "?decision=adopt&acknowledge_conflicts=true")
    return draft


def _items(client) -> list[dict]:
    r = call(client, "GET", f"/v1/students/{STUDENT}/pathway")
    assert r.status_code == 200, r.text
    return r.json()["plan_items"]


def _minutes(iso_a: str, iso_b: str) -> float:
    a = datetime.fromisoformat(iso_a.replace("Z", "+00:00"))
    b = datetime.fromisoformat(iso_b.replace("Z", "+00:00"))
    return (b - a).total_seconds() // 60


def test_conflicts_field_is_always_present(client) -> None:
    """没冲突是 `[]`，不是缺字段——"没有"和"没算过"必须分得开。"""
    _adopt(client)
    assert all(isinstance(i.get("conflicts"), list) for i in _items(client))


def test_overlap_minutes_never_exceed_the_other_span(client) -> None:
    """报出来的分钟数必须物理上成立——契约层已拦，这里守到 API 出口。"""
    _adopt(client)
    for item in _items(client):
        for c in item["conflicts"]:
            assert 1 <= c["overlap_minutes"] <= _minutes(c["starts_at"], c["ends_at"])


def test_same_hour_activities_report_each_other(client) -> None:
    """缺陷 B：同时段的两个活动必须**互报**，单向就是漏报。"""
    _adopt(client)
    # 键用 plan_item_id：冲突指向的是**这一版计划里的那个条目**，
    # 不是 subject——同一个活动可能在不同版本里是不同条目。
    mutual = {
        i["plan_item_id"]: {c["with_id"] for c in i["conflicts"]
                            if c["kind"] == PlanItemConflictKind.PLANNED_ACTIVITY.value}
        for i in _items(client)
    }
    pairs = [(a, b) for a, others in mutual.items() for b in others]
    assert pairs, "计划里两个同时段活动没有互报冲突"
    for a, b in pairs:
        assert a in mutual.get(b, set()), f"{b} 没有回报与 {a} 的冲突（单向 = 漏报）"


def test_activity_clashing_with_a_course_is_reported(client) -> None:
    """缺陷 A：活动压着课，必须说出来压了哪门课、压了多久。"""
    _adopt(client)
    course_hits = [c for i in _items(client) for c in i["conflicts"]
                   if c["kind"] == PlanItemConflictKind.COURSE.value]
    assert course_hits, "撞课一条都没报出来"
    assert all(c["label"]["zh_Hans"] for c in course_hits), "冲突对象得有名字"


def test_adopting_with_conflicts_requires_acknowledgement(client) -> None:
    d = call(client, "POST", f"/v1/students/{STUDENT}/pathway/draft")
    draft = d.json()
    assert any(i["conflicts"] for i in draft["pathway"]["plan_items"]), \
        "夹具里应当存在冲突，否则这条用例证明不了什么"
    url = (f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}"
           "/decision?decision=adopt")
    blocked = call(client, "POST", url)
    assert blocked.status_code == 409, blocked.text
    assert "conflict" in blocked.text.lower()
    ok = call(client, "POST", url + "&acknowledge_conflicts=true")
    assert ok.status_code == 200, ok.text


def test_discard_is_never_blocked_by_conflicts(client) -> None:
    d = call(client, "POST", f"/v1/students/{STUDENT}/pathway/draft")
    draft = d.json()
    r = call(client, "POST",
             f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}"
             "/decision?decision=discard")
    assert r.status_code == 200, r.text
