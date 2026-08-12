"""P3-G（2026-08-10 用户裁定）：规划先出草案，学生批准才落盘。

用户原话：「第一次规划直接落盘 很不对劲…… 应该是根据我的目标和我的档案，
还有记忆中心的用户偏好去规划之后，弹窗询问我是否批准这个规划」。

最要紧的一条是**读端点不许写**：`GET /pathway` 此前在目标指纹或强度变化时
当场生成并写进 `deps.pathways`，学生一进页面就看到一份已经落盘的计划——
从来没人问过他。这里用"调用前后 `deps.pathways` 长度不变"钉死它，
因为这是唯一能把"看一眼"和"定下来"分开的断言。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

A5_SCRIPT = "\n".join([
    "OPP-EVT-001\t贴合主目标的沟通训练\tCommunication training for the goal",
    "overall\t优先近期可完成的差距闭环\tClose near-term gaps first",
])


@pytest.fixture()
def deps() -> Deps:
    d = Deps("full")
    d.model = ScriptedModel({"a5-pathway:STU-A": A5_SCRIPT,
                             "match_rationale:STU-A": "为目标补差距\tCloses a gap"})
    return d


@pytest.fixture()
def deps_no_model() -> Deps:
    """没配 ADC 的机器：回落夹具那条路**同样**不许静默落盘。"""
    d = Deps("full")
    d.model = None
    return d


def call(client, method, path, **kw):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


# ── 读端点不许写 ────────────────────────────────────────────────────


def test_get_pathway_writes_nothing_when_nothing_adopted(deps):
    """核心断言。GET 之后 `deps.pathways` 必须一条不多。"""
    client = TestClient(create_app(deps))
    before = len(deps.pathways)
    r = call(client, "GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "no_pathway_version"
    assert len(deps.pathways) == before, "读端点写了盘——这正是用户说的「很不对劲」"


def test_get_pathway_writes_nothing_without_a_model_either(deps_no_model):
    """演示夹具回落是另一条路径，闸门必须一并盖住。"""
    client = TestClient(create_app(deps_no_model))
    before = len(deps_no_model.pathways)
    r = call(client, "GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 404
    assert len(deps_no_model.pathways) == before


def test_switching_intensity_on_a_read_does_not_replan(deps):
    """换强度档是"我想看看"，不是"就这么办"。"""
    client = TestClient(create_app(deps))
    draft = call(client, "POST",
                 "/v1/students/STU-A/pathway/draft?intensity=balanced").json()
    call(client, "POST",
         f"/v1/students/STU-A/pathway/draft/{draft['draft_id']}/decision"
         "?decision=adopt&acknowledge_conflicts=true")
    adopted = call(client, "GET", "/v1/students/STU-A/pathway").json()

    again = call(client, "GET", "/v1/students/STU-A/pathway?intensity=ambitious")
    assert again.status_code == 200
    assert again.json()["pathway_id"] == adopted["pathway_id"], (
        "换档不该静默重排——要换先出草案")


# ── 草案 → 批准 ─────────────────────────────────────────────────────


def test_draft_does_not_land_until_adopted(deps):
    client = TestClient(create_app(deps))
    before = len(deps.pathways)
    r = call(client, "POST", "/v1/students/STU-A/pathway/draft?intensity=balanced")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft_id"]
    assert body["pathway"]["plan_items"], "草案要有内容，否则没什么可批准的"
    assert len(deps.pathways) == before, "草案不进已采纳版本"

    assert call(client, "GET", "/v1/students/STU-A/pathway").status_code == 404


def test_adopting_a_draft_lands_it(deps):
    client = TestClient(create_app(deps))
    draft = call(client, "POST",
                 "/v1/students/STU-A/pathway/draft?intensity=balanced").json()
    decided = call(client, "POST",
                   f"/v1/students/STU-A/pathway/draft/{draft['draft_id']}"
                   "/decision?decision=adopt&acknowledge_conflicts=true")
    assert decided.status_code == 200, decided.text
    assert decided.json()["adopted_at"] is not None

    got = call(client, "GET", "/v1/students/STU-A/pathway")
    assert got.status_code == 200
    assert got.json()["pathway_id"] == draft["pathway"]["pathway_id"]


def test_discarding_a_draft_leaves_the_profile_planless(deps):
    client = TestClient(create_app(deps))
    draft = call(client, "POST",
                 "/v1/students/STU-A/pathway/draft?intensity=balanced").json()
    decided = call(client, "POST",
                   f"/v1/students/STU-A/pathway/draft/{draft['draft_id']}"
                   "/decision?decision=discard")
    assert decided.status_code == 200
    assert decided.json()["discarded_at"] is not None
    assert call(client, "GET", "/v1/students/STU-A/pathway").status_code == 404


def test_a_decided_draft_cannot_be_decided_again(deps):
    """已知会失败的样例：批过的草案再批一次——必须 409，不能重复落盘。"""
    client = TestClient(create_app(deps))
    draft = call(client, "POST",
                 "/v1/students/STU-A/pathway/draft?intensity=balanced").json()
    path = (f"/v1/students/STU-A/pathway/draft/{draft['draft_id']}"
            "/decision?decision=adopt&acknowledge_conflicts=true")
    assert call(client, "POST", path).status_code == 200
    assert call(client, "POST", path).status_code == 409


def test_unknown_draft_is_404(deps):
    client = TestClient(create_app(deps))
    r = call(client, "POST",
             "/v1/students/STU-A/pathway/draft/DRAFT-NOPE/decision?decision=adopt")
    assert r.status_code == 404


def test_draft_of_another_student_cannot_be_adopted(deps):
    client = TestClient(create_app(deps))
    draft = call(client, "POST",
                 "/v1/students/STU-A/pathway/draft?intensity=balanced").json()
    r = call(client, "POST",
             f"/v1/students/STU-B/pathway/draft/{draft['draft_id']}"
             "/decision?decision=adopt&acknowledge_conflicts=true")
    assert r.status_code == 404


# ── 弹窗要能说出"依据是什么" ────────────────────────────────────────


def test_draft_carries_the_grounds_it_was_built_on(deps):
    """用户要的是"根据目标 + 档案 + 记忆偏好规划完再批准"——依据要上屏。"""
    client = TestClient(create_app(deps))
    body = call(client, "POST",
                "/v1/students/STU-A/pathway/draft?intensity=balanced").json()
    assert body["rationale_goals"], "至少要说清是按哪个目标规划的"
    assert body["diff"]["is_first_plan"] is True
    assert body["diff"]["removed_count"] == 0


def test_second_draft_diffs_against_the_adopted_version(deps):
    client = TestClient(create_app(deps))
    first = call(client, "POST",
                 "/v1/students/STU-A/pathway/draft?intensity=low_load").json()
    call(client, "POST",
         f"/v1/students/STU-A/pathway/draft/{first['draft_id']}/decision"
         "?decision=adopt&acknowledge_conflicts=true")
    second = call(client, "POST",
                  "/v1/students/STU-A/pathway/draft?intensity=ambitious").json()
    assert second["diff"]["is_first_plan"] is False
    assert (second["diff"]["added_count"] or second["diff"]["removed_count"]), (
        "换档重排却报零差异，说明 diff 是摆设")
