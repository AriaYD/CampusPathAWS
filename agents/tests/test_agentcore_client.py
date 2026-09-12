"""P3（2026-09-12）：语义平面搬到 Bedrock AgentCore Runtime 之后，API 侧的客户端。

这条边界的价值在于**它把什么留在了本地**：API 进程只序列化 ``ModelRequest``
的四个字段（system / data / purpose / agent），拿回一段文本 + 用量 + 被拒工具。
凭据、日历、学生档案一个都不过去——因为根本没有字段装它们。

所以这里断言的是 **payload 的形状**与**失败时的响声**，不是"能不能连上 AWS"：
连上 AWS 要花钱，且在没有凭据的机器上根本跑不了。boto 客户端是注入的假货，
它把每次调用原样记下来，我们对着记录逐项对拍。

每条守卫配一个"已知会失败的样例"：
* runtime 回包里没有 ``result`` → 抛，不返回空串；
* ``AGENTCORE_RUNTIME_ARN`` 没配 → autodetect 返回 None，**不悄悄退回本地 Bedrock**
  （那会让"语义平面在 AgentCore 上"这句话变成看运气）。
"""

from __future__ import annotations

import io
import json

import pytest

from campuspath_agents.agentcore_client import (
    AGENT_RUNTIME_ENV,
    RUNTIME_AGENTCORE,
    RUNTIME_ARN_ENV,
    AgentCoreModelClient,
    AgentCoreProtocolError,
    session_id_for,
)
from campuspath_agents.model import GroundingUnavailable, ModelRequest, autodetect_model
from campuspath_contracts.common import AgentId

ARN = ("arn:aws:bedrock-agentcore:us-east-1:123456789012:"
       "runtime/campuspath_semantic-abc123")


class FakeAgentCoreClient:
    """``boto3.client("bedrock-agentcore")`` 的同形替身：记下调用，回预设包。"""

    def __init__(self, *bodies: object) -> None:
        self.calls: list[dict] = []
        self.bodies = list(bodies) or [{"result": "ok"}]

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        raw = body if isinstance(body, (bytes, str)) else json.dumps(body, ensure_ascii=False)
        if isinstance(raw, str):
            raw = raw.encode()
        return {"statusCode": 200, "contentType": "application/json",
                "runtimeSessionId": kwargs.get("runtimeSessionId"),
                "response": io.BytesIO(raw)}


def _client(*bodies: object, **kwargs) -> AgentCoreModelClient:
    return AgentCoreModelClient(ARN, region="us-east-1",
                                client=FakeAgentCoreClient(*bodies), **kwargs)


# --------------------------------------------------------------------------
# 1. 过去的是 ModelRequest 的四个字段，回来的是文本
# --------------------------------------------------------------------------


def test_generate_sends_the_model_request_shape_and_returns_the_text():
    model = _client({"result": "  三套方案已生成。  "})
    out = model.generate(ModelRequest(system="你是 A5", data=("块一", "块二"),
                                      purpose="pathway:S1", agent=AgentId.A5_PATHWAY))

    assert out == "三套方案已生成。"
    call = model.client.calls[0]
    assert call["agentRuntimeArn"] == ARN
    assert call["qualifier"] == "DEFAULT"
    payload = json.loads(call["payload"].decode())
    assert payload == {"kind": "generate", "request": {
        "system": "你是 A5", "data": ["块一", "块二"],
        "purpose": "pathway:S1", "agent": "A5",
    }}
    assert (model.backend, model.runtime) == ("bedrock", "agentcore")
    assert model.region == "us-east-1"


def test_payload_is_bytes_not_a_dict():
    """boto 的 ``payload`` 是 blob；传 dict 会在真调用时才炸。"""
    model = _client()
    model.generate(ModelRequest(system="s", purpose="p"))
    assert isinstance(model.client.calls[0]["payload"], bytes)


def test_no_agent_means_no_agent_key_value_not_a_fabricated_one():
    model = _client()
    model.generate(ModelRequest(system="s", purpose="p"))
    assert json.loads(model.client.calls[0]["payload"].decode())["request"]["agent"] is None


# --------------------------------------------------------------------------
# 2. 会话 ID：AgentCore 要求 ≥ 33 字符，且同一类调用要落在同一会话
# --------------------------------------------------------------------------


def test_session_id_is_long_enough_and_scoped_to_the_subject():
    """已知会失败的样例：只按第一段分会话 —— **全校学生共用一个 AgentCore 会话**。

    AgentCore 会话是有状态的：同一个 ``runtimeSessionId`` 下的调用会看到彼此的
    上下文。``reflect:STU-A`` 与 ``reflect:STU-B`` 落在同一会话上，等于把
    A 的反思暴露给 B 的那次调用。所以第二段**像 ID**（带数字或大写的代号）
    时必须进 key；第三段（变体名之类）不进——同一学生的三套强度共享冷启动。
    """
    table = {
        "reflect:STU-A": "reflect:STU-B",              # 不同学生 → 不同会话
        "a5-pathway:STU-A": "a5-pathway:STU-B",
        "skill_tags:COMP4211": "skill_tags:COMP2011",
        "extract:SRC-1": "extract:SRC-2",
    }
    for left, right in table.items():
        assert session_id_for(left) != session_id_for(right), left
        assert len(session_id_for(left)) >= 33

    # 同一学生的不同变体（第三段）仍共用会话
    assert session_id_for("a5-pathway:STU-A:balanced") == session_id_for(
        "a5-pathway:STU-A:intense")
    assert session_id_for("a5-pathway:STU-A:balanced") == session_id_for("a5-pathway:STU-A")

    # 第二段不像 ID（纯小写词）时只按第一段分 —— 不为措辞制造无谓的冷启动
    assert session_id_for("compose:balanced") == session_id_for("compose:relaxed")

    # 不同类别之间永远不串味
    assert session_id_for("reflect:STU-A") != session_id_for("a5-pathway:STU-A")

    # 稳定：同一个 purpose 反复问到同一个 ID
    assert session_id_for("reflect:STU-A") == session_id_for("reflect:STU-A")


def test_session_id_without_a_purpose_is_random_but_still_long_enough():
    first, second = session_id_for(""), session_id_for("")
    assert len(first) >= 33 and len(second) >= 33
    assert first != second


def test_generate_uses_the_purpose_scoped_session_id():
    model = _client()
    model.generate(ModelRequest(system="s", purpose="a5-pathway:STU-A:balanced"))
    model.generate(ModelRequest(system="s", purpose="a5-pathway:STU-A:intense"))
    model.generate(ModelRequest(system="s", purpose="a5-pathway:STU-B:balanced"))
    ids = [c["runtimeSessionId"] for c in model.client.calls]
    assert ids[0] == ids[1] == session_id_for("a5-pathway:STU-A")
    assert ids[2] != ids[0]
    assert all(len(i) >= 33 for i in ids)


# --------------------------------------------------------------------------
# 3. 用量、被拒工具、模型 ID 都从 runtime 回来
# --------------------------------------------------------------------------


def test_usage_and_rejected_tools_travel_back_from_the_runtime():
    model = _client({
        "result": "我没有发布权。",
        "usage": {"inputTokens": 120, "outputTokens": 18},
        "rejected_tools": [["publish_opportunity", "不在 A4 白名单"]],
        "model": "amazon.nova-pro-v1:0",
    })
    model.generate(ModelRequest(system="s", purpose="extract:SRC-1",
                                agent=AgentId.A4_OPPORTUNITY))

    assert model.last_usage == {"inputTokens": 120, "outputTokens": 18}
    assert model.last_rejected_tools == (("publish_opportunity", "不在 A4 白名单"),)
    assert model.model == "amazon.nova-pro-v1:0"


def test_configured_model_is_reported_before_the_first_call():
    model = _client(model_id="amazon.nova-lite-v1:0")
    assert model.model == "amazon.nova-lite-v1:0"


def test_a_call_without_usage_leaves_last_usage_none_not_zero():
    """零和"没量到"不是一回事——注册表上这两者的运维含义不同。"""
    model = _client({"result": "ok"})
    model.generate(ModelRequest(system="s", purpose="p"))
    assert model.last_usage is None
    assert model.last_rejected_tools == ()


# --------------------------------------------------------------------------
# 4. 接地检索：AgentCore 形态下没有（Google Search 是 Vertex 原生工具）
# --------------------------------------------------------------------------


def test_grounded_generation_is_refused_not_silently_downgraded():
    model = _client()
    with pytest.raises(GroundingUnavailable):
        model.generate_grounded(ModelRequest(system="s", purpose="p"))
    assert model.client.calls == []


# --------------------------------------------------------------------------
# 5. 已知会失败的样例：回包形状不对
# --------------------------------------------------------------------------


def test_a_response_without_result_raises_instead_of_returning_empty_text():
    model = _client({"usage": {"inputTokens": 1}})
    with pytest.raises(AgentCoreProtocolError) as exc:
        model.generate(ModelRequest(system="s", purpose="p"))
    assert "result" in str(exc.value)


def test_an_error_payload_from_the_runtime_is_raised_with_its_text():
    model = _client({"error": "unknown_kind", "requested": "generat"})
    with pytest.raises(AgentCoreProtocolError) as exc:
        model.generate(ModelRequest(system="s", purpose="p"))
    assert "unknown_kind" in str(exc.value)


def test_non_json_body_raises_with_the_body_quoted():
    model = _client(b"<html>502 Bad Gateway</html>")
    with pytest.raises(AgentCoreProtocolError) as exc:
        model.generate(ModelRequest(system="s", purpose="p"))
    assert "502" in str(exc.value)


# --------------------------------------------------------------------------
# 6. autodetect：没配 ARN 就没有后端，**不退回本地 Bedrock**
# --------------------------------------------------------------------------


@pytest.fixture
def aws_credentials(monkeypatch):
    """让凭据链看起来有货——否则下面的 None 是因为没凭据，证明不了 ARN 那条。"""
    import boto3

    class _Session:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def get_credentials(self):
            return object()

    monkeypatch.setattr(boto3, "Session", _Session)


def test_autodetect_picks_the_agentcore_client_when_the_arn_is_configured(aws_credentials):
    model = autodetect_model({
        AGENT_RUNTIME_ENV: RUNTIME_AGENTCORE,
        RUNTIME_ARN_ENV: ARN,
        "AWS_REGION": "us-east-1",
    })
    assert isinstance(model, AgentCoreModelClient)
    assert (model.runtime, model.backend) == ("agentcore", "bedrock")
    assert model.runtime_arn == ARN


def test_autodetect_returns_none_when_the_runtime_arn_is_missing(aws_credentials):
    """已知会失败的样例：选了 agentcore 却没给 ARN。

    退回本地 Bedrock 会让"语义平面跑在 AgentCore 上"变成运气问题——
    宁可整个端点 503。
    """
    assert autodetect_model({AGENT_RUNTIME_ENV: RUNTIME_AGENTCORE,
                             "AWS_REGION": "us-east-1"}) is None


def test_local_runtime_is_still_the_default(aws_credentials, monkeypatch):
    """对照组：不设 ``CAMPUSPATH_AGENT_RUNTIME`` 时照旧走**进程内** Bedrock。

    真 ``BedrockModelClient`` 会去建 boto 客户端（这台机器上不一定成），
    所以这里把它换成哨兵——本条测的是分支选择，不是 Bedrock 能不能连上。
    """
    from campuspath_agents import model as model_module

    class _Sentinel:
        runtime = "strands"

    monkeypatch.setattr(model_module, "BedrockModelClient", _Sentinel)
    assert isinstance(autodetect_model({"AWS_REGION": "us-east-1"}), _Sentinel)
    # 同一哨兵在场，选了 agentcore 就必须**不是**它
    picked = autodetect_model({AGENT_RUNTIME_ENV: RUNTIME_AGENTCORE,
                               RUNTIME_ARN_ENV: ARN, "AWS_REGION": "us-east-1"})
    assert isinstance(picked, AgentCoreModelClient)


# --------------------------------------------------------------------------
# 7. 客户端不留存请求（F1）
# --------------------------------------------------------------------------


def test_the_client_retains_no_request_text():
    """已知会失败的样例：``self.calls`` 把每段学生原文留在 API 进程里。

    这条边界的全部价值是"本地留下的东西尽可能少"。把请求存成列表等于
    在本地又建了一份副本——而且是永不回收的那种。
    """
    def _deep_text(obj, depth: int = 0) -> str:
        if depth > 5:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            return "".join(_deep_text(k, depth + 1) + _deep_text(v, depth + 1)
                           for k, v in obj.items())
        if isinstance(obj, (list, tuple, set, frozenset)):
            return "".join(_deep_text(x, depth + 1) for x in obj)
        if hasattr(obj, "__dict__"):
            return "".join(_deep_text(v, depth + 1) for v in vars(obj).values())
        return ""

    secret = "学生反思原文-ZZ-9137-不可留存"
    model = _client()
    for _ in range(3):
        model.generate(ModelRequest(system="s", data=(secret,), purpose="p"))

    # 假 boto 客户端会记下 payload（那是测试替身的事），只看客户端自己
    state = {k: v for k, v in vars(model).items() if k != "_client"}
    assert secret not in _deep_text(state)
    assert not hasattr(model, "calls")


# --------------------------------------------------------------------------
# 8. boto 配置：超时与重试（F4）
# --------------------------------------------------------------------------


def test_boto_client_is_built_with_bounded_timeouts_and_no_retries(monkeypatch):
    """已知会失败的样例：默认 botocore 配置（legacy 重试）。

    ``invoke_agent_runtime`` 是**按调用计费**的。botocore 默认 legacy 重试模式
    会在读超时后自动重发——一次 A5 取舍因此可能被真的跑两遍，钱付两次，
    而调用方只看到一次失败。read_timeout 60s 也短于 AgentCore 的冷启动 + 多轮工具循环。
    """
    import boto3

    captured: dict = {}

    def _fake_client(service, **kwargs):
        captured["service"] = service
        captured.update(kwargs)
        return FakeAgentCoreClient()

    monkeypatch.setattr(boto3, "client", _fake_client)
    model = AgentCoreModelClient(ARN, region="us-east-1")
    assert model.client is not None

    config = captured["config"]
    assert captured["service"] == "bedrock-agentcore"
    assert config.connect_timeout == 5
    assert config.read_timeout == 180
    assert config.retries == {"max_attempts": 1, "mode": "standard"}


def test_read_timeout_is_configurable_from_the_environment(monkeypatch):
    import boto3

    captured: dict = {}

    def _fake_client(service, **kwargs):
        captured.update(kwargs)
        return FakeAgentCoreClient()

    monkeypatch.setattr(boto3, "client", _fake_client)
    model = AgentCoreModelClient(ARN, region="us-east-1",
                                 env={"AGENTCORE_READ_TIMEOUT": "45"})
    assert model.client is not None
    assert captured["config"].read_timeout == 45


def test_a_non_200_status_code_raises_instead_of_parsing_the_body():
    """已知会失败的样例：runtime 回 500 但带一段 JSON 体。"""
    from campuspath_agents.agentcore_client import AgentCoreInvocationFailed

    class _Failing(FakeAgentCoreClient):
        def invoke_agent_runtime(self, **kwargs):
            self.calls.append(kwargs)
            return {"statusCode": 500, "response": io.BytesIO(
                json.dumps({"result": "不该被当成答案"}).encode())}

    model = AgentCoreModelClient(ARN, region="us-east-1", client=_Failing())
    with pytest.raises(AgentCoreInvocationFailed) as exc:
        model.generate(ModelRequest(system="s", purpose="p"))
    assert "500" in str(exc.value)


def test_a_read_timeout_raises_a_clear_failure_not_a_botocore_traceback():
    from botocore.exceptions import ReadTimeoutError

    from campuspath_agents.agentcore_client import AgentCoreInvocationFailed

    class _Timeout(FakeAgentCoreClient):
        def invoke_agent_runtime(self, **kwargs):
            self.calls.append(kwargs)
            raise ReadTimeoutError(endpoint_url="https://bedrock-agentcore.invalid")

    model = AgentCoreModelClient(ARN, region="us-east-1", client=_Timeout())
    with pytest.raises(AgentCoreInvocationFailed) as exc:
        model.generate(ModelRequest(system="s", purpose="p"))
    assert "AgentCore" in str(exc.value)


# --------------------------------------------------------------------------
# 9. A4 的工具循环也能过网线（F13）
# --------------------------------------------------------------------------


def test_extract_opportunity_sends_the_source_and_returns_the_emitted_fields():
    model = _client({
        "result": "草稿已产出，等待人工审核。",
        "usage": {"inputTokens": 300, "outputTokens": 40},
        "rejected_tools": [["publish_opportunity", "不在 A4 白名单"]],
        "model": "amazon.nova-pro-v1:0",
        "emitted": {"title": "产品实践工作坊", "category": "workshop"},
    })
    reply = model.extract_opportunity(
        ModelRequest(system="你是 A4", data=("工作坊详情……",),
                     purpose="extract:SRC-club", agent=AgentId.A4_OPPORTUNITY),
        source_id="SRC-club", raw_content="工作坊详情……")

    payload = json.loads(model.client.calls[0]["payload"].decode())
    assert payload["kind"] == "extract"
    assert payload["source_id"] == "SRC-club"
    assert payload["raw_content"] == "工作坊详情……"
    assert payload["request"] == {"system": "你是 A4", "data": ["工作坊详情……"],
                                  "purpose": "extract:SRC-club", "agent": "A4"}
    assert reply["emitted"] == {"title": "产品实践工作坊", "category": "workshop"}
    assert reply["result"] == "草稿已产出，等待人工审核。"
    assert reply["rejected_tools"] == (("publish_opportunity", "不在 A4 白名单"),)
    assert model.last_usage == {"inputTokens": 300, "outputTokens": 40}


def test_extract_opportunity_without_an_emitted_draft_reports_none():
    model = _client({"result": "读完了，没有可抽取的机会。"})
    reply = model.extract_opportunity(
        ModelRequest(system="s", data=("x",), purpose="extract:SRC-1",
                     agent=AgentId.A4_OPPORTUNITY),
        source_id="SRC-1", raw_content="x")
    assert reply["emitted"] is None


def test_a4_over_agentcore_keeps_its_tool_loop():
    """已知会失败的样例：A4 走 AgentCore 时退回纯 ``generate``。

    退回纯文本路径意味着模型**没有工具**：``emit_opportunity_draft`` 不会被调用，
    ``last_emitted`` 永远是 None，审核队列里那条"模型提议了什么"的证据就没了。
    """
    from campuspath_agents.roster import OpportunityAgent
    from campuspath_agents.tools import ToolBelt
    from campuspath_contracts.common import Provenance
    from campuspath_contracts.opportunity import (
        Opportunity,
        OpportunityType,
        PublicationStatus,
    )

    from datetime import datetime, timezone

    model = _client({
        "result": "草稿已产出。",
        "emitted": {"title": "产品实践工作坊", "category": "workshop"},
        "rejected_tools": [["publish_opportunity", "不在 A4 白名单"]],
    })
    provenance = Provenance(source="hkust_ugcourse", parser_version="t/1",
                            retrieved_at=datetime(2026, 9, 12, tzinfo=timezone.utc))
    extracted = Opportunity(
        opportunity_id="OPP-1", type=OpportunityType.WORKSHOP, title="产品实践工作坊",
        organizer="合成社团（Demo）", official_url="https://example.invalid/w",
        source_id="SRC-club", provenance=provenance,
        publication_status=PublicationStatus.DRAFT)

    a4 = OpportunityAgent(AgentId.A4_OPPORTUNITY,
                          ToolBelt(AgentId.A4_OPPORTUNITY), model)
    draft = a4.extract_draft("SRC-club", "工作坊详情……", extracted,
                             draft_id="D-1", provenance=provenance)

    assert json.loads(model.client.calls[0]["payload"].decode())["kind"] == "extract"
    assert a4.last_emitted == {"title": "产品实践工作坊", "category": "workshop"}
    assert [n for n, _ in a4.last_rejected_tools] == ["publish_opportunity"]
    assert draft.extracted.publication_status is PublicationStatus.DRAFT
