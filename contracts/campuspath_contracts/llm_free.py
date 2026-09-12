"""B11 的可复用检查器：确定性服务不得以**任何方式**接触模型。

九个服务此前各有一份 sed 复制出来的 ``test_llm_free.py``。复制品会各自漂移，
而且第二层当时对真实的发行名（``google-cloud-aiplatform``）根本不匹配——
九份一起无效。判定逻辑集中到这里，测试只负责调用。

四层，各挡一种躲法：

1. **运行时** —— 导入整个包后 ``sys.modules`` 里不能出现模型 SDK；
2. **依赖树** —— 声明的依赖（含传递）不能出现模型 SDK 的**发行名**；
3. **源码 import** —— 静态的 ``import x`` / ``from x import y``；
4. **动态与网络** —— ``importlib.import_module("vertexai")`` 这类惰性导入，
   以及直接对 ``aiplatform.googleapis.com`` 发裸 HTTP。

第 4 层是审查实测出来的：前三层挡不住把 import 挪进函数体再用字符串拼，
也挡不住绕开 SDK 直接 POST。
"""

from __future__ import annotations

import ast
import importlib.metadata
import pathlib
import re

from .guards import MODEL_SDK_MODULES, imported_model_sdks

__all__ = [
    "MODEL_SDK_DISTRIBUTIONS",
    "MODEL_ENDPOINT_HOSTS",
    "MODEL_AWS_SERVICE_PREFIXES",
    "boto_model_service",
    "declared_dependency_violations",
    "source_import_violations",
    "dynamic_access_violations",
]

#: PyPI 上的**发行名**，与 import 名不同。
#: 曾经的实现用 ``module.split(".")[0].replace("_", "-")`` 推导，得到的是
#: ``google``——真实依赖 ``google-cloud-aiplatform`` 一个都匹配不上，
#: 而那恰恰是 CLAUDE.md 指定的那个 SDK。
MODEL_SDK_DISTRIBUTIONS = frozenset(
    {
        "google-cloud-aiplatform",
        "google-generativeai",   # ai-studio-denylist
        "google-genai",
        "google-adk",
        "langchain-google-genai",
        "vertexai",
        "openai",
        "anthropic",
        "litellm",
        "transformers",
        "strands-agents",         # AWS Strands Agents SDK——编排层（agents/）专用
        "strands-agents-tools",
        "bedrock-agentcore",      # Amazon Bedrock AgentCore 运行时
    }
)

#: 绕开 SDK 直接发请求同样是"接触模型"。
#:
#: 两个 Bedrock 条目**不带尾点**（2026-09-12 修）：带尾点时只有完整主机名
#: （``bedrock-runtime.us-east-1.amazonaws.com``）会被命中，而
#: ``boto3.client("bedrock-runtime")`` 里那个**服务名**没有点——
#: 审查实测：整条 boto3 路径因此从四层里一层不落地穿过去。
MODEL_ENDPOINT_HOSTS = frozenset(
    {
        "aiplatform.googleapis.com",
        "generativelanguage.googleapis.com",   # ai-studio-denylist
        "api.openai.com",
        "api.anthropic.com",
        "bedrock-runtime",      # 含 bedrock-runtime.us-east-1.amazonaws.com
        "bedrock-agentcore",    # 含 bedrock-agentcore.us-east-1.amazonaws.com
    }
)

_DYNAMIC_IMPORTERS = {"import_module", "__import__"}

#: 用 boto3 直连模型服务：``boto3.client("bedrock-runtime")`` /
#: ``boto3.Session(...).client("bedrock-agentcore")``。前三层全部放行——
#: ``boto3`` 不是模型 SDK（S3、DynamoDB 都用它），源码里也没有任何禁用 import。
#: **第一个字符串实参**才是判定依据：它是 AWS 服务名。
BOTO_CLIENT_FACTORIES = ("client",)

#: 以此开头的 AWS 服务名 = 模型服务。``bedrock``（控制面）、
#: ``bedrock-runtime``（推理）、``bedrock-agentcore``（Runtime/Gateway）全在内。
MODEL_AWS_SERVICE_PREFIXES = ("bedrock",)


def declared_dependency_violations(distribution: str) -> list[str]:
    """遍历声明的依赖（含传递），按**发行名**匹配。"""
    seen: set[str] = set()
    frontier = [distribution]
    while frontier:
        name = frontier.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            requires = importlib.metadata.requires(name) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for requirement in requires:
            if "extra ==" in requirement:
                continue
            dependency = re.split(r"[<>=!~\[; ]", requirement.strip(), 1)[0]
            if dependency:
                frontier.append(dependency)
    return sorted(d for d in seen if d in MODEL_SDK_DISTRIBUTIONS)


def source_import_violations(root: pathlib.Path) -> list[str]:
    """静态 import 语句。用 AST 而非正则，免得被续行或缩进骗过。"""
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                      # pragma: no cover
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for hit in imported_model_sdks(names):
                offenders.append(f"{path.name}:{node.lineno} import {hit}")
    return offenders


def boto_model_service(node: ast.Call) -> str | None:
    """这次 ``Call`` 是不是在建一个**模型服务**的 boto 客户端？是就返回服务名。

    命中两种写法（两者的 ``func`` 都是 ``Attribute(attr="client")``）::

        boto3.client("bedrock-runtime", region_name=...)
        boto3.Session(...).client("bedrock-agentcore")

    只看**第一个字符串字面量实参**（位置或 ``service_name=``）。不是字面量就
    不判——这里宁可漏判也不误判：``session.client(name)`` 里的 ``name``
    十有八九是 S3。真正的兜底在第 1/2 层（依赖树与运行时 import）。
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in BOTO_CLIENT_FACTORIES:
        return None
    candidates = list(node.args[:1])
    candidates += [kw.value for kw in node.keywords if kw.arg == "service_name"]
    for arg in candidates:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value.startswith(MODEL_AWS_SERVICE_PREFIXES):
                return arg.value
    return None


def dynamic_access_violations(root: pathlib.Path) -> list[str]:
    """惰性导入与裸 HTTP。

    审查实测：把 ``import vertexai`` 换成函数体里的
    ``importlib.import_module("vertexai.generative_models")``，
    或者直接 ``urllib.request`` POST 到 aiplatform 端点，
    前三层**全部**放行。

    2026-09-12 再补一条（F5）：``boto3.client("bedrock-runtime")`` 连这一层
    原来也穿得过去——主机模式带尾点，而服务名里没有点。见
    :func:`boto_model_service`。
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")

        for host in sorted(MODEL_ENDPOINT_HOSTS):
            for match in re.finditer(re.escape(host), source):
                line_no = source.count("\n", 0, match.start()) + 1
                line = source.splitlines()[line_no - 1]
                if "ai-studio-denylist" in line or "MODEL_ENDPOINT_HOSTS" in line:
                    continue
                offenders.append(f"{path.name}:{line_no} 直接访问 {host}")

        try:
            tree = ast.parse(source)
        except SyntaxError:                      # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            service = boto_model_service(node)
            if service is not None:
                offenders.append(
                    f"{path.name}:{node.lineno} boto 客户端直连模型服务 {service}"
                )
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else ""
            )
            if name not in _DYNAMIC_IMPORTERS:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if imported_model_sdks([arg.value]):
                        offenders.append(
                            f"{path.name}:{node.lineno} 动态导入 {arg.value}"
                        )
                else:
                    offenders.append(
                        f"{path.name}:{node.lineno} 动态导入的模块名不是字面量，无法静态判定"
                    )
    return offenders
