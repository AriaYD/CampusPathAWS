"""评测共享的重对象：Seed 与 API 客户端。

两者都**只建一次**：Seed 构建要读 1500 门课，13 条 BLOCKER 各建一次
会把评测拖成分钟级；而 D6.7 要求两次跑数字一致，共享同一个实例
也顺带保证了它们看到的是同一份数据。
"""

from __future__ import annotations

import functools
from typing import Any


@functools.cache
def seed_bundle() -> dict[str, Any]:
    from campuspath_seed.build import build_seed

    return build_seed("full")


@functools.cache
def _deps():
    from campuspath_api.app import Deps

    # model=None：**评测不调模型**。13 条 BLOCKER 全是结构性的，
    # 依赖模型的端点会返回 503，而那正是它们此刻的真实状态。
    return Deps("full", model=None)


@functools.cache
def api_client():
    from fastapi.testclient import TestClient

    from campuspath_api.app import create_app

    return TestClient(create_app(_deps()))


def ensure_pathway(client, student_id: str) -> bool:
    """让这个学生有一版**已采纳**的路径，然后返回是否成功。

    2026-08-10（P3-G）之后 `GET /pathway` 只读已采纳版本：读一下就生成并写盘
    的旧行为被撤掉了，因为「第一次规划直接落盘」从来没问过学生。评测器原本
    正是靠那个副作用拿到路径的，于是 B8/T4/T5 一起变成「没有可检查的 PlanItem」。

    **修法是让评测走真实流程，不是放宽断言**：起草 → 采纳 → 再读。
    学生在界面上做的就是这两步，评测器没有理由走一条学生走不到的捷径。

    幂等：已有已采纳版本时直接返回 True，不重复起草。
    """
    headers = {"X-CampusPath-Role": "student"}
    if client.get(f"/v1/students/{student_id}/pathway",
                  headers=headers).status_code == 200:
        return True
    drafted = client.post(f"/v1/students/{student_id}/pathway/draft",
                          headers=headers)
    if drafted.status_code != 200:
        return False
    draft_id = drafted.json()["draft_id"]
    # 2026-08-11 起带时段冲突的草案必须**显式确认**才能采纳（服务端 409
    # `schedule_conflicts_unacknowledged`）。评测器替的是学生"看过冲突后仍采纳"
    # 那一下点击——不是放宽断言：冲突本身仍由 B1/B2 与 `test_schedule_conflicts_api`
    # 判定。2026-08-25 P8 复跑抓到：少了这个参数，13 项 BLOCKER 里 B8/T4/T5
    # 全部因为"没有已采纳规划"而空跑。
    decided = client.post(
        f"/v1/students/{student_id}/pathway/draft/{draft_id}/decision"
        "?decision=adopt&acknowledge_conflicts=true", headers=headers)
    return decided.status_code == 200
