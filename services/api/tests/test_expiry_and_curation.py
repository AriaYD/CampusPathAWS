"""广场过期治理（E）与官方 / 编辑推荐标签（D）——2026-08-10 用户需求。

**E 的根因**（读源码定位，非猜测）：过期判定此前只在 `Deps.__init__` 里算**一次**，
且只看 `deadline`。于是两类条目会以「在架」身份继续流通：

1. 有 `ends_at`/`starts_at` 但**没有 deadline** 的活动——办完了也永远不过期；
2. 进程启动之后才越过截止线的条目——内存态不会重算。

而 `_compute_matches` 遍历的正是 `deps.opportunities`，所以这些死条目会被**推荐进
For You**。用户原话：「已经过了活动时间的那些活动……禁止把这些活动推送给用户」。

**D 的口径**（对齐 Spec §6.12「官方推荐应显示原因」与 §6.13「不公开羞辱」）：
编辑推荐是**徽章不是分数**——广场上只显示徽章，绝不显示分数，
这是用户「不搞活动比分」的落点；k-匿名阈值同时保证样本不足的活动不会被贴标签。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole
from campuspath_contracts.opportunity import PublicationStatus
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


def call(client, method, path, role=ActorRole.STUDENT, **kw):
    headers = {ROLE_HEADER: role.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


@pytest.fixture()
def deps() -> Deps:
    return Deps("full")


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def _seed_finished_event(deps: Deps):
    """造一条**已经办完但没有 deadline** 的活动，塞进在架池。

    这正是旧判定漏掉的那一类：`deadline is None` 所以启动期分区不认它，
    于是它以 published 身份留在 `deps.opportunities` 里。

    **日期必须挑在两条规则之间**（第一版栽在这里，断言碰巧全绿）：
    - 早于 `deps.today`（演示时钟 2026-09-15）→ 才算过期；
    - 晚于「真实 now − 60 天」→ 才不会被**归档**规则（`_stats_frozen_at`，
      用的是真实时钟）先一步捞走。归档与过期是两条独立的路，
      样例落进归档窗就等于把被测约束遮住了。
    """
    ended = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
    assert ended.date() < deps.today, "样例必须早于演示时钟，否则根本不算过期"

    live = deps.opportunities[0]
    finished = live.model_copy(update={
        "opportunity_id": "OPP-TEST-FINISHED",
        "deadline": None,
        "starts_at": ended,
        "ends_at": ended,
        "publication_status": PublicationStatus.PUBLISHED,
    })
    deps.opportunities.insert(0, finished)
    return finished


# ── E：过期治理 ──────────────────────────────────────────────────────


def test_finished_event_without_deadline_leaves_the_live_catalog(deps, client):
    """办完的活动必须移出在架列表，且能经 include_expired 取回并标 expired。

    先前行为：`deadline is None` ⇒ 判定根本不看它 ⇒ 永远在架。
    """
    _seed_finished_event(deps)

    live = call(client, "GET", "/v1/catalog/opportunities?limit=1000").json()
    assert "OPP-TEST-FINISHED" not in {o["opportunity_id"] for o in live}, (
        "已经办完（starts_at/ends_at 均在 deps.today 之前）的活动仍留在在架列表里"
    )

    everything = call(
        client, "GET", "/v1/catalog/opportunities?limit=1000&include_expired=true"
    ).json()
    row = next(o for o in everything if o["opportunity_id"] == "OPP-TEST-FINISHED")
    assert row["publication_status"] == PublicationStatus.EXPIRED.value, (
        "取回来的条目状态必须是 expired——Spec 允许它作未来参考，"
        "但不能看起来和还开着的一样"
    )


def test_expired_opportunity_is_never_recommended(deps, client):
    """**这是「禁止推送给用户」的落点**，用前后对照证明断言有约束力。

    第一版栽了：造一条新机会塞进池首位，然后断言它不在推荐里——绿了，
    但绿得毫无意义，因为**被复制的那条本来就进不了前 50**（排序是六维加权，
    不是池内顺序）。「加料没进分数前列，断言碰巧全绿」是 §10.2 记过的坑。

    现在改成拿**真正排第一**的那条动手：先证明它在推荐里（前），
    就地把它改成已办完并清掉当日缓存，再证明它不在了（后）。
    同一个对象、同一套评分，唯一变量就是过期与否。
    """
    before = call(client, "GET", "/v1/students/STU-A/matches?limit=50").json()
    assert before, "推荐为空，这条测试没有立足点"
    top = before[0]["opportunity_id"]

    index = next(i for i, o in enumerate(deps.opportunities)
                 if o.opportunity_id == top)
    ended = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
    assert ended.date() < deps.today
    deps.opportunities[index] = deps.opportunities[index].model_copy(update={
        "deadline": None, "starts_at": ended, "ends_at": ended,
    })
    deps.match_cache.clear()        # 推荐按日缓存，不清就读到改动前的结果

    after = call(client, "GET", "/v1/students/STU-A/matches?limit=50").json()
    assert top not in {m["opportunity_id"] for m in after}, (
        f"{top} 已经办完（{ended.date()} 早于演示时钟 {deps.today}），"
        "却仍被推进 For You"
    )


def test_expiry_is_evaluated_at_read_time_not_only_at_startup(deps, client):
    """进程启动之后才越线的条目也要被认出来——内存态不会自己重算。

    做法：把一条在架条目的截止日改到 `deps.today` 之前，**不重建 Deps**，
    再读一次目录。
    """
    victim = deps.opportunities[1]
    past = deps.today - timedelta(days=30)
    deps.opportunities[1] = victim.model_copy(update={
        "deadline": victim.deadline.replace(
            year=past.year, month=past.month, day=past.day
        ) if victim.deadline else None,
    })
    if deps.opportunities[1].deadline is None:      # 该条目本来就没有 deadline
        pytest.skip("样例条目无 deadline，换用 test_finished_event_* 覆盖")

    live = call(client, "GET", "/v1/catalog/opportunities?limit=1000").json()
    assert victim.opportunity_id not in {o["opportunity_id"] for o in live}, (
        "运行期越过截止线的条目仍以在架身份出现——过期判定只在启动时算了一次"
    )


# ── D：官方 / 编辑推荐徽章 ────────────────────────────────────────────


def _rate(deps, opportunity, *, n: int, score: int, tag: str):
    """给某条机会灌 n 份**已验证**四维反馈，每维都打 score 分。

    为什么测试要自己造这个状态、而不是挑一条 seed 里恰好高分的：
    第一版就是那么写的，结果全红——因为 seed 里唯一均分 ≥4 的
    `OPP-EVT-006` **本身已经过期**，根本不在在架目录里。
    「断言依赖偶然的种子数据」和「加料没进分数前列」是同一类错：
    被测约束不是唯一变量，绿或红都说明不了问题。
    """
    from campuspath_contracts.reflection import (
        CohortDims, DimensionRating, EventQualityFeedback, QualityDimension,
    )
    occ = opportunity.occurrence_id or opportunity.opportunity_id
    for i in range(n):
        deps.quality_feedback.append(EventQualityFeedback(
            feedback_id=f"FB-{tag}-{i}",
            occurrence_id=occ,
            verified_attendance=True,
            verification_ref=f"ver_{i:016x}",
            dimensions=tuple(
                DimensionRating(dimension=d, rating=score) for d in QualityDimension
            ),
            cohort_dims=CohortDims(school="ENGG", year_level=2,
                                   development_mode="employment"),
            submitted_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        ))


def _live(deps, index: int):
    """取一条**在架**（未过期）机会——过期的不会出现在广场，拿它测徽章没意义。"""
    live = [o for o in deps.opportunities
            if not (o.deadline and o.deadline.date() < deps.today)
            and not ((o.ends_at or o.starts_at or o.deadline)
                     and (o.ends_at or o.starts_at or o.deadline).date() < deps.today)]
    assert len(live) > index, "在架条目不够，测试前提不成立"
    return live[index]


def _badge_of(client, opportunity_id: str):
    rows = call(client, "GET", "/v1/catalog/opportunities?limit=1000").json()
    row = next((r for r in rows if r["opportunity_id"] == opportunity_id), None)
    assert row is not None, f"{opportunity_id} 不在在架目录里，测试前提不成立"
    return row.get("curation")


def test_editor_pick_needs_both_a_high_score_and_enough_verified_feedback(deps, client):
    """编辑推荐 = 四维均分 ≥4.0 **且** 已验证反馈 ≥ MIN_CELL_N(5)。

    三个样例把两个条件各自钉死：
    - 分够、样本够 → 有徽章；
    - 分够、样本差一份（4 < 5）→ **没有**徽章（只看分数会让「一个人打了五分」
      的活动被贴标，k-匿名阈值顺带挡住了这种噪声）；
    - 样本够、分不够（3.0）→ **没有**徽章；
    - 均分正好 4.0 → 有徽章（「4 分以上」含 4 分）。
    """
    from campuspath_contracts.aggregation import MIN_CELL_N

    good, thin, mediocre, edge = (_live(deps, i) for i in range(4))
    _rate(deps, good, n=MIN_CELL_N, score=5, tag="good")
    _rate(deps, thin, n=MIN_CELL_N - 1, score=5, tag="thin")
    _rate(deps, mediocre, n=MIN_CELL_N + 2, score=3, tag="mid")
    _rate(deps, edge, n=MIN_CELL_N, score=4, tag="edge")   # 正好 4.0，含边界

    badge = _badge_of(client, good.opportunity_id)
    assert badge is not None, "分够样本够，却没拿到编辑推荐徽章"
    assert badge["reason"] == "high_verified_student_value"
    assert badge["set_by"] == "auto"

    assert _badge_of(client, thin.opportunity_id) is None, (
        f"只有 {MIN_CELL_N - 1} 份已验证反馈（阈值 {MIN_CELL_N}）却拿到了徽章"
    )
    assert _badge_of(client, mediocre.opportunity_id) is None, (
        "均分 3.0 低于 4.0 却拿到了徽章"
    )
    assert _badge_of(client, edge.opportunity_id) is not None, (
        "均分正好 4.0 应当入选——用户口径是「4 分以上」含 4 分"
    )


def test_plaza_never_ships_a_score_alongside_the_badge(deps, client):
    """用户裁定「不搞活动比分」：徽章可以出域，**分数不可以**。

    广场的机会对象上不得出现任何分数字段——想看分数只能去校方端
    （那里有 k-匿名抑制与「非质量分」的分区说明）。
    """
    rows = call(client, "GET", "/v1/catalog/opportunities?limit=1000").json()
    forbidden = {"avg_overall", "favorable_rate", "score", "rating", "verified_n"}
    for row in rows:
        leaked = forbidden & set(row) | forbidden & set(row.get("curation") or {})
        assert not leaked, f"{row['opportunity_id']} 的广场对象带出了分数字段：{leaked}"


def test_curator_badge_wins_over_auto_and_can_be_revoked(deps, client):
    """人工置位优先于自动派生，且可显式撤销回落到自动。

    三段：① curator 给一条**没有任何反馈**的机会贴「校方已核验」→ 徽章在，
    `set_by=curator`；② 给同一条灌满高分反馈 → 徽章**仍是人工那个**
    （自动派生不许覆盖人的判断，§6.12）；③ curator 撤销 → 回落到自动派生，
    这时因为分够样本够，徽章以 `set_by=auto` 回来——撤的是「人工加权」，
    不是「学生给的高分」。
    """
    from campuspath_contracts.aggregation import MIN_CELL_N

    target = _live(deps, 5)
    oid = target.opportunity_id
    assert _badge_of(client, oid) is None, "样例前提：它本来没有徽章"

    r = call(client, "PUT", f"/v1/catalog/opportunities/{oid}",
             role=ActorRole.CAREER_CENTER_ADMIN,
             json={"curation_reason": "verified_by_school"})
    assert r.status_code == 200, r.text
    badge = _badge_of(client, oid)
    assert badge["reason"] == "verified_by_school" and badge["set_by"] == "curator"

    _rate(deps, target, n=MIN_CELL_N, score=5, tag="override")
    badge = _badge_of(client, oid)
    assert badge["set_by"] == "curator", "自动派生覆盖了 curator 的人工置位"

    r = call(client, "PUT", f"/v1/catalog/opportunities/{oid}",
             role=ActorRole.CAREER_CENTER_ADMIN,
             json={"curation_reason": "none"})
    assert r.status_code == 200, r.text
    badge = _badge_of(client, oid)
    assert badge is not None and badge["set_by"] == "auto", (
        "撤销人工置位后应回落到自动派生（此时分够样本够）"
    )


def test_curator_cannot_hand_sign_the_automatic_reason(deps, client):
    """`high_verified_student_value` 是数据说的话，curator 不能手签。

    契约层用 Literal 收窄取值——不是靠服务端记得判断。
    """
    oid = _live(deps, 6).opportunity_id
    r = call(client, "PUT", f"/v1/catalog/opportunities/{oid}",
             role=ActorRole.CAREER_CENTER_ADMIN,
             json={"curation_reason": "high_verified_student_value"})
    assert r.status_code == 422, f"契约应拒收自动理由，实际 {r.status_code}"
