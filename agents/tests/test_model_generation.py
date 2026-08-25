"""模型代际门槛（2026-08-24，All Things Agentic Hackathon 硬性要求）。

比赛规则："Gemini 3.5 or newer accessed through Gemini API or Vertex AI"。
与 B12（只走 Vertex）同一思路：**写在文档里的要求会被下一次改默认值悄悄推翻**，
所以把门槛放进构造函数——构造一个 3.5 以下的模型客户端直接抛异常。

已知会失败的样例：``gemini-2.5-flash`` 是迁移前的默认值，它必须被拒绝；
这条测试红过（迁移前），才说明门槛真的在起作用。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from campuspath_agents.model import (
    DEFAULT_MODEL,
    MIN_GEMINI_GENERATION,
    ModelGenerationTooOld,
    VertexModel,
    assert_model_generation,
    gemini_generation,
)

VERTEX_ENV = {
    "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
    "GOOGLE_CLOUD_PROJECT": "test-project",
    "GOOGLE_CLOUD_LOCATION": "global",
}


@pytest.fixture
def vertex_env(monkeypatch):
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL_PRIMARY"):  # ai-studio-denylist
        monkeypatch.delenv(name, raising=False)
    for name, value in VERTEX_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gemini-3.5-flash", (3, 5)),
        ("gemini-3.5-pro", (3, 5)),
        ("gemini-3-flash-preview", (3, 0)),
        ("gemini-2.5-flash", (2, 5)),
        ("gemini-2.0-flash-001", (2, 0)),
        ("projects/p/locations/global/publishers/google/models/gemini-3.5-flash", (3, 5)),
    ],
)
def test_gemini_generation_parses_version(model, expected):
    assert gemini_generation(model) == expected


def test_gemini_generation_rejects_unparseable():
    with pytest.raises(ValueError):
        gemini_generation("gemma-3-27b-it")


def test_floor_is_three_point_five():
    assert MIN_GEMINI_GENERATION == (3, 5)
    assert gemini_generation(DEFAULT_MODEL) >= MIN_GEMINI_GENERATION


@pytest.mark.parametrize("model", ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview"])
def test_known_bad_models_are_rejected(model):
    """迁移前的默认值必须被拒——这是门槛的"已知会失败的样例"。"""
    with pytest.raises(ModelGenerationTooOld):
        assert_model_generation(model)


def test_default_vertex_model_meets_floor(vertex_env):
    client = VertexModel()
    assert client.model == DEFAULT_MODEL
    assert gemini_generation(client.model) >= MIN_GEMINI_GENERATION


def test_vertex_model_constructor_refuses_old_generation(vertex_env):
    with pytest.raises(ModelGenerationTooOld):
        VertexModel(model="gemini-2.5-flash")


def test_env_override_is_honoured_but_still_gated(vertex_env, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_PRIMARY", "gemini-3.5-pro")
    assert VertexModel().model == "gemini-3.5-pro"
    monkeypatch.setenv("GEMINI_MODEL_PRIMARY", "gemini-2.5-pro")
    with pytest.raises(ModelGenerationTooOld):
        VertexModel()


def test_thinking_is_configured_by_level_not_budget(vertex_env):
    """Gemini 3.x 用 thinking_level；实测 3.5-flash 上 thinking_budget=0 要 20.9s，
    thinking_level=MINIMAL 0.7s——沿用旧参数会直接顶掉 T9。"""
    pytest.importorskip("google.genai")
    config = VertexModel()._config()
    assert config.thinking_config.thinking_level == "MINIMAL"
    assert config.thinking_config.thinking_budget is None


def _load_cloud_module(name: str, rel: str):
    path = pathlib.Path(__file__).resolve().parents[1] / "cloud" / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "rel", ["orchestrator_agent/agent.py", "opportunity_scout_agent/agent.py"]
)
def test_cloud_mirrors_meet_floor(rel):
    """Agent Engine 镜像是独立打包的，本地门槛管不到它——所以这里单独断言。"""
    pytest.importorskip("google.adk")
    cloud = _load_cloud_module(f"gen_{rel.split('/')[0]}", rel)
    assert gemini_generation(cloud.MODEL_ID) >= MIN_GEMINI_GENERATION
    assert cloud.root_agent.model.model == cloud.MODEL_ID
    # 3.5-flash 只在 global 端点可用；镜像必须自己钉住 location，不能靠运行时区域
    assert cloud.root_agent.model.client_kwargs["location"] == "global"
    assert cloud.root_agent.model.client_kwargs["vertexai"] is True
