"""逐条批准 + 拒绝即记住（用户 2026-08-11 报障 A/B）。

**先红后绿**。两条用户原话：
* A「每一条条目都要可以点击批准或者拒绝，而不是只给我一个批量写入批准的按钮」；
* B「对于用户拒绝的活动，下次用户再次规划的时候，就不要再推荐同一个活动了」。

查代码时发现 B **今天就是坏的**：`deps.declined` 有人写、没人读——
`decline_plan_item` 往里塞 subject，注释写着「A5 重新生成与演示夹具都要跳过」，
但全仓库没有任何一处消费这个集合。注释与代码不一致时，**代码才是事实**。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER
from campuspath_contracts.common import ActorRole

STUDENT = "STU-A"
A5_SCRIPT = "\n".join([
    "OPP-EVT-025\t同时段之一\tone",
    "OPP-EVT-012\t同时段之二\ttwo",
    "OPP-EVT-046\t撞课的工作坊\tclash",
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


def _draft(client) -> dict:
    r = call(client, "POST", f"/v1/students/{STUDENT}/pathway/draft")
    assert r.status_code == 200, r.text
    return r.json()


def _adopted_subjects(client) -> set[str]:
    r = call(client, "GET", f"/v1/students/{STUDENT}/pathway")
    assert r.status_code == 200, r.text
    return {i["subject_id"] for i in r.json()["plan_items"]}


def test_adopting_a_subset_lands_only_that_subset(client) -> None:
    """A：只勾几条就只落那几条——不是全有或全无。"""
    draft = _draft(client)
    opps = [i for i in draft["pathway"]["plan_items"] if i["kind"] == "opportunity"]
    assert len(opps) >= 3, "夹具至少要有三条活动，才谈得上挑几条"
    keep = [opps[0]["plan_item_id"], opps[1]["plan_item_id"]]
    dropped = {o["subject_id"] for o in opps[2:]}

    r = call(client, "POST",
             f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
             "?decision=adopt&acknowledge_conflicts=true",
             json={"keep_plan_item_ids": keep})
    assert r.status_code == 200, r.text

    landed = _adopted_subjects(client)
    assert not (landed & dropped), f"没勾的条目却落了盘：{landed & dropped}"


def test_unpicked_items_are_remembered_as_declined(deps, client) -> None:
    """B：没勾 = 拒绝，进拒绝名单。"""
    draft = _draft(client)
    opps = [i for i in draft["pathway"]["plan_items"] if i["kind"] == "opportunity"]
    keep = [opps[0]["plan_item_id"]]
    dropped = {o["subject_id"] for o in opps[1:]}
    call(client, "POST",
         f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
         "?decision=adopt&acknowledge_conflicts=true",
         json={"keep_plan_item_ids": keep})
    assert dropped <= deps.declined.get(STUDENT, set())


def test_declined_subjects_never_come_back_in_a_new_draft(deps, client) -> None:
    """B 的正题：下一版规划**不许**再推荐被拒过的活动。

    这一条今天就是红的——`deps.declined` 有人写没人读。
    """
    draft = _draft(client)
    opps = [i for i in draft["pathway"]["plan_items"] if i["kind"] == "opportunity"]
    keep = [opps[0]["plan_item_id"]]
    dropped = {o["subject_id"] for o in opps[1:]}
    call(client, "POST",
         f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
         "?decision=adopt&acknowledge_conflicts=true",
         json={"keep_plan_item_ids": keep})

    again = _draft(client)
    back = {i["subject_id"] for i in again["pathway"]["plan_items"]} & dropped
    assert not back, f"被拒过的活动又被推荐了：{back}"


def test_explicit_decline_endpoint_also_blocks_future_drafts(deps, client) -> None:
    """既有的「不参加」按钮同样要生效——它写的是同一个名单。"""
    draft = _draft(client)
    call(client, "POST",
         f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
         "?decision=adopt&acknowledge_conflicts=true")
    subjects = _adopted_subjects(client)
    victim = next(iter(s for s in subjects if s.startswith("OPP-")))
    items = call(client, "GET", f"/v1/students/{STUDENT}/pathway").json()["plan_items"]
    pid = next(i["plan_item_id"] for i in items if i["subject_id"] == victim)
    call(client, "DELETE", f"/v1/students/{STUDENT}/pathway/items/{pid}")

    again = _draft(client)
    assert victim not in {i["subject_id"] for i in again["pathway"]["plan_items"]}


def test_keeping_nothing_is_rejected(client) -> None:
    """一条都不勾却按"采纳"——那是"再想想"，不是采纳。

    静默写入一份空计划会让学生以为自己批准了什么。
    """
    draft = _draft(client)
    r = call(client, "POST",
             f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
             "?decision=adopt&acknowledge_conflicts=true",
             json={"keep_plan_item_ids": []})
    assert r.status_code == 422, r.text


def test_omitting_the_field_keeps_everything(client) -> None:
    """不传就是全留——既有调用方（与"全部批准"那个按钮）行为不变。"""
    draft = _draft(client)
    n = len(draft["pathway"]["plan_items"])
    r = call(client, "POST",
             f"/v1/students/{STUDENT}/pathway/draft/{draft['draft_id']}/decision"
             "?decision=adopt&acknowledge_conflicts=true")
    assert r.status_code == 200, r.text
    assert len(call(client, "GET", f"/v1/students/{STUDENT}/pathway")
               .json()["plan_items"]) == n
