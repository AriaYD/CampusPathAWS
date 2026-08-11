"""测试助手：把「排一版 + 采纳」压成一步。

2026-08-10 用户裁定 G 之后，`GET /pathway` **只读已采纳版本**，不再顺手生成。
既有测试里大量的 `GET /pathway` 本意是"拿到 A5 排出来的那一版"，
迁移到新流程就是 draft → adopt → GET 三步。抽在这里，是为了让那些测试
继续断言它们本来要断言的东西（A5 产物的形状），而不是被流程改动淹没。

**注意**：需要断言"没批准就不该落盘"的测试**不要**用这里的 `adopt_pathway`——
那正是 `test_pathway_approval.py` 的职责，它刻意手写每一步。
"""

from __future__ import annotations

from campuspath_contracts.common import ActorRole
from campuspath_api.rbac import ROLE_HEADER


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {ROLE_HEADER: ActorRole.STUDENT.value, **(extra or {})}


def draft_pathway(client, student: str = "STU-A", intensity: str | None = None,
                  headers: dict[str, str] | None = None):
    """只起草，不采纳。返回原始 Response。"""
    query = f"?intensity={intensity}" if intensity else ""
    return client.post(f"/v1/students/{student}/pathway/draft{query}",
                       headers=_headers(headers))


def adopt_pathway(client, student: str = "STU-A", intensity: str | None = None,
                  headers: dict[str, str] | None = None):
    """起草 → 采纳 → 读回。返回 `GET /pathway` 的 Response。

    起草或采纳失败时**原样返回那一步的 Response**，让调用方看到真实错误码
    （比如 422 unknown_intensity），而不是被后续步骤的 404 掩盖。
    """
    drafted = draft_pathway(client, student, intensity, headers)
    if drafted.status_code != 200:
        return drafted
    draft_id = drafted.json()["draft_id"]
    decided = client.post(
        f"/v1/students/{student}/pathway/draft/{draft_id}/decision?decision=adopt",
        headers=_headers(headers))
    if decided.status_code != 200:
        return decided
    return client.get(f"/v1/students/{student}/pathway",
                      headers=_headers(headers))
