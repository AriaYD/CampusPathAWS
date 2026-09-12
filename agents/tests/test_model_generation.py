"""模型代际门槛（2026-08-24，All Things Agentic Hackathon 硬性要求）。

比赛规则："Gemini 3.5 or newer accessed through Gemini API or Vertex AI"。
与 B12（只走 Vertex）同一思路：**写在文档里的要求会被下一次改默认值悄悄推翻**，
所以把门槛放进构造函数——构造一个 3.5 以下的模型客户端直接抛异常。

已知会失败的样例：``gemini-2.5-flash`` 是迁移前的默认值，它必须被拒绝；
这条测试红过（迁移前），才说明门槛真的在起作用。

2026-09-12（Agents for Humans Hackathon）起主后端换成 **Amazon Bedrock**，
代际门槛只管 Vertex 那条备用路径；云端镜像改由本文件末尾的
"不许 import google / MODEL_ID 必须是 Bedrock 默认值" 两条守着。
"""

from __future__ import annotations

import ast
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
from campuspath_agents.strands_models import DEFAULT_BEDROCK_MODEL

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


CLOUD_MIRRORS = ["orchestrator_agent/agent.py", "opportunity_scout_agent/agent.py"]


def _import_roots(rel: str) -> set[str]:
    """镜像源码里出现的所有顶层 import 名。

    比"跑一遍看 sys.modules"更硬：模块里任何一条 ``import google…``
    都会被看见，哪怕它藏在函数体里、哪怕运行时那条分支没被走到。
    """
    source = (pathlib.Path(__file__).resolve().parents[1] / "cloud" / rel).read_text()
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("rel", CLOUD_MIRRORS)
def test_cloud_mirrors_are_strands_on_bedrock_not_google(rel, monkeypatch):
    """云端镜像在 2026-09-12 迁到 Strands + Bedrock：整条链路走 AWS。

    已知会失败的样例是**迁移前那两个文件**——它们 ``from google.adk.agents
    import Agent``，这条断言会当场红。
    """
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    roots = _import_roots(rel)
    assert "google" not in roots, f"{rel} 仍在 import google.*；镜像必须整条走 AWS"
    assert {"strands"} <= roots
    # F3 起两个镜像都 import 本仓的 hooks/契约——**打包脚本必须把它们带上**，
    # 否则云上第一次调用时才会 ImportError。
    assert {"campuspath_agents", "campuspath_contracts"} <= roots

    cloud = _load_cloud_module(f"gen_{rel.split('/')[0]}", rel)
    assert cloud.MODEL_ID == DEFAULT_BEDROCK_MODEL
    assert cloud.root_agent.model.config["model_id"] == cloud.MODEL_ID
    # 模块对象里也不该留下任何 google 包的引用（import 之外的拿法同样算）
    leaked = sorted(
        name for name, value in vars(cloud).items()
        if (getattr(value, "__module__", "") or "").split(".")[0] == "google"
        or (getattr(value, "__name__", "") or "").split(".")[0] == "google"
    )
    assert leaked == [], f"{rel} 的模块命名空间里有 google 对象：{leaked}"


@pytest.mark.parametrize("rel", CLOUD_MIRRORS)
def test_cloud_mirror_model_id_follows_the_env(rel, monkeypatch):
    """对照组：``BEDROCK_MODEL_ID`` 是真的生效的覆盖，不是摆设。"""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
    cloud = _load_cloud_module(f"env_{rel.split('/')[0]}", rel)
    assert cloud.MODEL_ID == "us.amazon.nova-lite-v1:0"


def test_the_staging_script_vendors_what_the_mirrors_import():
    """镜像 import 了 ``campuspath_agents`` / ``campuspath_contracts``，
    而 AgentCore 的 CodeZip 只上传打包目录——打包脚本必须把这两个包复制进去。

    已知会失败的样例：把 ``agents/campuspath_agents`` 那一行从 PAIRS 里删掉，
    ``make agentcore-stage`` 的自检会在 import 时炸；这条测试让它更早红。
    """
    script = (pathlib.Path(__file__).resolve().parents[2]
              / "scripts" / "agentcore_stage.sh").read_text(encoding="utf-8")
    for pair in ("agents/campuspath_agents:campuspath_agents",
                 "contracts/campuspath_contracts:campuspath_contracts",
                 "agents/cloud:campuspath_cloud"):
        assert pair in script, f"打包脚本没有 vendoring {pair}"
