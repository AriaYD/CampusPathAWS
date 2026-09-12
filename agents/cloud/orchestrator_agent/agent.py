"""CampusPath A0 Orchestrator —— AgentCore 部署形态。

**这是 A0 的云端运行时镜像，不是第二个 A0。** 判定逻辑与本地
``campuspath_agents.roster.OrchestratorAgent`` 同一张路由表；
``agents/tests/test_cloud_mirror.py`` 断言两者逐项一致——表改了
镜像没跟上，CI 会先红。

部署为独立包（不 import campuspath_agents）：AgentCore 打包的是本目录，
把整个 monorepo 塞进 runtime 只为查一张字典不值得。

2026-09-12（Agents for Humans Hackathon）起改用 **Strands Agents + Amazon
Bedrock**：整条链路走 AWS，运行时凭据由 AgentCore 的执行角色提供，
本模块**不 import 任何 google 包**（``test_model_generation`` 有断言守着）。
"""

import os

from strands import Agent, tool
from strands.models import BedrockModel

#: 与本地 ``campuspath_agents.strands_models.DEFAULT_BEDROCK_MODEL`` 同值
#: （``test_model_generation`` 断言两边一致）。镜像独立打包，不能 import 本仓，
#: 所以这里是第二份。跨区域推理配置（``us.`` 前缀）而非裸模型 ID。
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

#: 区域跟随运行时（AgentCore 注入 ``AWS_REGION``），默认 us-east-1。
MODEL = BedrockModel(model_id=MODEL_ID, region_name=os.environ.get("AWS_REGION", "us-east-1"))

#: 与 roster.OrchestratorAgent.ROUTES 逐项一致（有 CI 断言守着）。
#: 已知意图 → 确定性路由，**不调模型**；只有未命中才由 LLM 编排。
ROUTES: dict[str, list[str]] = {
    "plan_courses": ["A1", "A2", "A3", "A5"],
    "find_opportunities": ["A1", "A3", "A5"],
    "build_pathway": ["A1", "A2", "A3", "A5"],
    "view_gap_map": ["A1", "A3"],
    "reflect": ["A1"],
    "replan": ["A5"],
    "browse_plaza": [],
    "update_profile": ["A1"],
    "set_goal": ["A3"],
    "onboard": ["A1"],
    "approve_actions": [],
    "explain_why_not_recommended": ["A5"],
}


def route_intent(intent: str) -> dict:
    """查确定性路由表：这个意图要派哪些 Agent、按什么顺序。

    Args:
        intent: 意图标识（如 plan_courses / find_opportunities / reflect）。

    Returns:
        kind=deterministic_route 与调用序列；未知意图返回 kind=llm_composed，
        表示需要模型兜底编排（并说明这不是路由表的一部分）。
    """
    key = intent.strip().lower()
    if key in ROUTES:
        return {
            "kind": "deterministic_route",
            "intent": key,
            "calls": [
                {"call_id": f"C-{i + 1}", "agent": a,
                 "parallel_group": "facts" if a in {"A1", "A2", "A3"} else None}
                for i, a in enumerate(ROUTES[key])
            ],
            "model_used": False,
        }
    return {
        "kind": "llm_composed",
        "intent": key,
        "known_intents": sorted(ROUTES),
        "model_used": True,
        "note": "未命中路由表——由 LLM 编排兜底，trace 里与确定性路由分得开",
    }


#: Strands 工具包装。**纯函数保持可直接调用**（``test_cloud_mirror`` 直接调它），
#: 工具形态只是同一个函数的另一层皮——不存在"测的是一份、跑的是另一份"。
route_intent_tool = tool(route_intent)

INSTRUCTION = (
    "你是 CampusPath 的 A0 Orchestrator。收到学生请求时：\n"
    "1. 先判断它属于哪个已知意图，调用 route_intent 查确定性路由表；\n"
    "2. 命中路由表就按工具返回的调用序列回答『派了哪些 Agent、谁并行谁串行』，"
    "不要自行增删 Agent；\n"
    "3. 未命中时如实说明这是 LLM 兜底编排，并给出最小必要的 Agent 序列建议。\n"
    "永远不要虚构路由表里没有的 Agent。回答用中文。"
)

root_agent = Agent(
    name="campuspath_orchestrator",
    model=MODEL,
    description="CampusPath A0：意图路由编排器（确定性路由表优先，模型只做兜底）",
    system_prompt=INSTRUCTION,
    tools=[route_intent_tool],
    callback_handler=None,
)
