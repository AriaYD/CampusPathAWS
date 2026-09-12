"""现场市场研究：没有接地检索工具时**如实失败**，不静默降级成凭印象编造。

Bedrock 后端没有 Google Search grounding（``StrandsModelClient.generate_grounded``
直接抛 :class:`GroundingUnavailable`）。这条异常如果就这么冒到 API 层，
学生看到的是 500；它该变成与"搜不到 JD"同一类的 :class:`LiveResearchEmpty`——
前端已经会把那种情况说成"这次没采到，可换离线编制库"。

已知会失败的样例就是下面这个 fake：它的 ``generate_grounded`` 永远抛。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from campuspath_agents.live_market_research import (
    LiveResearchEmpty,
    run_live_market_research,
)
from campuspath_agents.model import GroundingUnavailable, ModelRequest
from campuspath_contracts.common import DevelopmentModeType
from campuspath_contracts.goals import Goal, GoalRole


def _goal() -> Goal:
    return Goal(
        goal_id="GOAL-1", student_id="STU-1", role=GoalRole.PRIMARY,
        development_mode=DevelopmentModeType.EMPLOYMENT, target_type="role",
        target_name="产品经理", created_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )


class _NoGroundingModel:
    """Bedrock 形态：普通生成可用，接地检索不可用。"""

    def __init__(self) -> None:
        self.grounded_calls: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> str:   # pragma: no cover - 不该被走到
        raise AssertionError("检索步都没过，不该走到逐行拆解")

    def generate_grounded(self, request: ModelRequest) -> str:
        self.grounded_calls.append(request)
        raise GroundingUnavailable("bedrock 后端没有接地检索工具")


def test_missing_grounding_becomes_an_honest_empty_result():
    model = _NoGroundingModel()
    steps: list[int] = []
    with pytest.raises(LiveResearchEmpty) as excinfo:
        run_live_market_research(
            model, _goal(),
            fetch_text=lambda url: None,
            progress=lambda pct, zh, en: steps.append(pct),
            today=date(2026, 9, 12),
        )
    assert "grounded" in str(excinfo.value) or "接地" in str(excinfo.value)
    assert len(model.grounded_calls) == 1          # 只试了检索步，没继续往下跑
    assert steps == [8]
