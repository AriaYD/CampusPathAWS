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
    assert model.system_prompts() == ["你是 A5"]
    assert [c.purpose for c in model.calls] == ["pathway:S1"]


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


def test_session_id_is_long_enough_and_stable_per_purpose_prefix():
    assert len(session_id_for("pathway:S1")) >= 33
    assert session_id_for("pathway:S1") == session_id_for("pathway:S2")
    assert session_id_for("pathway:S1") != session_id_for("extract:SRC-1")


def test_session_id_without_a_purpose_is_random_but_still_long_enough():
    first, second = session_id_for(""), session_id_for("")
    assert len(first) >= 33 and len(second) >= 33
    assert first != second


def test_generate_uses_the_purpose_scoped_session_id():
    model = _client()
    model.generate(ModelRequest(system="s", purpose="pathway:S1"))
    model.generate(ModelRequest(system="s", purpose="pathway:S2"))
    ids = [c["runtimeSessionId"] for c in model.client.calls]
    assert ids[0] == ids[1] == session_id_for("pathway:S1")
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
