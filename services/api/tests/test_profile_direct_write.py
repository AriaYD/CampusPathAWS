"""P3-F（2026-08-10 用户裁定）：学生本人上传官方模板 → **直写档案** + 逐条可撤销。

用户原话：「上传档案之后 直接更新到成长档案总览，然后弹窗提醒用户自行检查，
不用还要切换到「档案更新建议」再按确认，很多余」。

这里守两件事，缺一不可：
1. **正向**——上传后档案总览立刻有内容，且每条都能单独撤回去；
2. **反向**——B3 的豁免只给学生自述。A1 从反思里抽出来的候选变更，
   仍然只能落 pending 提案，写不进档案。反向用例比正向用例重要：
   直写这件事一旦做过头，B3 就是被自己人拆掉的。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from campuspath_api.app import create_app
from campuspath_contracts.profile import (
    AppliedChange, ProfileWriteOrigin, ResumeUploadResult)

from test_resume_template import TEMPLATE_RESUME


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _headers(student: str = "STU-A") -> dict[str, str]:
    return {"X-CampusPath-Role": "student", "X-CampusPath-Student": student}


def _upload(client: TestClient, student: str = "STU-A") -> dict:
    resp = client.post(
        f"/v1/students/{student}/resume", headers=_headers(student),
        json={"filename": "template.md", "content_text": TEMPLATE_RESUME},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 正向：上传即落盘 ────────────────────────────────────────────────


def test_upload_writes_into_the_profile_without_a_second_confirmation(
        client: TestClient):
    """核心断言：**没有任何裁决调用**，档案里已经有了这些条目。"""
    before = client.get("/v1/students/STU-A/experiences",
                        headers=_headers()).json()
    result = _upload(client)
    after = client.get("/v1/students/STU-A/experiences",
                       headers=_headers()).json()

    assert len(after) > len(before)
    applied_exp = [c for c in result["applied"] if c["entity_type"] == "experience"]
    assert len(after) - len(before) == len(applied_exp)


def test_upload_leaves_no_pending_proposal_to_click(client: TestClient):
    """用户说的"多余的一步"必须真的消失——提案分页里不能还挂着它。"""
    def _pending() -> int:
        return len([p for p in client.get(
            "/v1/students/STU-A/profile/proposals",
            headers=_headers()).json() if p["status"] == "pending"])

    pending_before = _pending()
    result = _upload(client)

    proposals = client.get("/v1/students/STU-A/profile/proposals",
                           headers=_headers()).json()
    mine = [p for p in proposals if p["proposal_id"] == result["proposal_id"]]
    assert mine, "审计留痕不能断：提案本身仍要在"
    assert mine[0]["status"] == "confirmed"

    assert _pending() == pending_before, "上传不该给学生留下待办"


def test_uploading_the_same_resume_twice_does_not_duplicate_experiences(
        client: TestClient):
    """直写之后重复上传的代价直接落在总览上——按机构+角色去重并如实报出。"""
    _upload(client)
    first = client.get("/v1/students/STU-A/experiences",
                       headers=_headers()).json()
    second = _upload(client)
    after = client.get("/v1/students/STU-A/experiences",
                       headers=_headers()).json()
    assert len(after) == len(first)
    assert not [c for c in second["applied"] if c["entity_type"] == "experience"]
    assert any("经历" in s for s in second["skipped"])


def test_upload_bumps_profile_version_through_the_store(client: TestClient):
    """直写不是绕过 store——版本号与事件流照常推进（B3 的审计链）。"""
    before = client.get("/v1/students/STU-A/profile",
                        headers=_headers()).json()["version"]
    result = _upload(client)
    assert result["profile_version"] > before


def test_already_known_entries_are_reported_as_skipped(client: TestClient):
    """第二次上传同一份：写不进去了，但要说清是"你已经有了"而不是"没读到"。"""
    _upload(client)
    second = _upload(client)
    assert second["skipped"], "重复上传必须如实交代跳过了什么"
    assert any("已在档案中" in s for s in second["skipped"])


# ── 撤销 ────────────────────────────────────────────────────────────


def test_undo_removes_the_entry_and_keeps_the_record(client: TestClient):
    result = _upload(client)
    target = next(c for c in result["applied"] if c["entity_type"] == "experience")

    exps = client.get("/v1/students/STU-A/experiences", headers=_headers()).json()
    assert any(e["experience_id"] for e in exps)

    undo = client.post(
        f"/v1/students/STU-A/profile/changes/{target['change_id']}/undo",
        headers=_headers())
    assert undo.status_code == 200, undo.text
    assert undo.json()["undone_at"] is not None

    after = client.get("/v1/students/STU-A/experiences", headers=_headers()).json()
    assert len(after) == len(exps) - 1

    ledger = client.get("/v1/students/STU-A/profile/changes",
                        headers=_headers()).json()
    kept = [c for c in ledger if c["change_id"] == target["change_id"]]
    assert kept and kept[0]["undone_at"] is not None, "撤销不是删除"


def test_undo_of_a_skill_takes_the_tag_back_out(client: TestClient):
    result = _upload(client)
    target = next(c for c in result["applied"] if c["entity_type"] == "skill")
    tag = target["summary"].split(" · ")[-1]

    profile = client.get("/v1/students/STU-A/profile", headers=_headers()).json()
    assert tag in profile["interests"]

    client.post(f"/v1/students/STU-A/profile/changes/{target['change_id']}/undo",
                headers=_headers())
    after = client.get("/v1/students/STU-A/profile", headers=_headers()).json()
    assert tag not in after["interests"]


def test_undo_is_idempotent(client: TestClient):
    result = _upload(client)
    target = result["applied"][0]
    path = f"/v1/students/STU-A/profile/changes/{target['change_id']}/undo"
    first = client.post(path, headers=_headers()).json()
    second = client.post(path, headers=_headers()).json()
    assert first["undone_at"] == second["undone_at"]


def test_undo_of_an_unknown_change_is_404(client: TestClient):
    resp = client.post("/v1/students/STU-A/profile/changes/AC-NOPE/undo",
                       headers=_headers())
    assert resp.status_code == 404


def test_one_student_cannot_undo_another_students_change(client: TestClient):
    result = _upload(client, "STU-A")
    target = result["applied"][0]
    resp = client.post(
        f"/v1/students/STU-B/profile/changes/{target['change_id']}/undo",
        headers=_headers("STU-B"))
    assert resp.status_code == 404


# ── 反向：豁免只给学生自述，AI 路径仍写不进去 ──────────────────────


def test_agent_inferred_change_cannot_use_the_direct_write_channel():
    """已知会失败的样例：把 A1 的推断塞进直写结果——契约层必须拒收。

    这条测试是 B3 豁免的边界证明。删掉它，"上传即直写"就会悄悄变成
    "任何东西都能直写"。
    """
    with pytest.raises(ValidationError) as excinfo:
        ResumeUploadResult(
            proposal_id="PROP-REFL-9", student_id="STU-A", profile_version=2,
            applied=(AppliedChange(
                change_id="AC-X", student_id="STU-A",
                origin=ProfileWriteOrigin.AGENT_PROPOSAL,
                entity_type="skill", summary="技能 · 用户访谈",
                applied_at="2026-08-10T00:00:00Z"),),
        )
    assert "B3" in str(excinfo.value)


def test_agent_proposal_still_lands_pending_and_writes_nothing(client: TestClient):
    """A1 提交的提案仍然是 pending，且在学生裁决前档案零变化。"""
    before = client.get("/v1/students/STU-A/profile",
                        headers=_headers()).json()
    payload = {
        "proposal_id": "PROP-AI-1",
        "student_id": "STU-A",
        "proposed_changes": [{
            "entity_type": "skill", "operation": "add",
            "field_path": "skills[]", "new_value": "因果推断",
        }],
        "reason": "从反思里读出来的",
        "impact": "medium",
        "created_at": "2026-08-10T00:00:00Z",
    }
    resp = client.post("/v1/students/STU-A/profile/proposals",
                       headers=_headers(), json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"

    after = client.get("/v1/students/STU-A/profile", headers=_headers()).json()
    assert after["version"] == before["version"]
    assert "因果推断" not in after["interests"]


def test_agent_proposal_that_claims_to_be_confirmed_is_rejected(client: TestClient):
    """已知会失败的样例：Agent 自己把状态置成 confirmed——store 必须拦下。"""
    payload = {
        "proposal_id": "PROP-AI-2",
        "student_id": "STU-A",
        "proposed_changes": [{
            "entity_type": "skill", "operation": "add",
            "field_path": "skills[]", "new_value": "自封技能",
        }],
        "reason": "我自己确认了",
        "impact": "high",
        "status": "confirmed",
        "decided_at": "2026-08-10T00:00:00Z",
        "created_at": "2026-08-10T00:00:00Z",
    }
    resp = client.post("/v1/students/STU-A/profile/proposals",
                       headers=_headers(), json=payload)
    assert resp.status_code == 422
    after = client.get("/v1/students/STU-A/profile", headers=_headers()).json()
    assert "自封技能" not in after["interests"]
