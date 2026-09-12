"""AgentCore Runtime 的 entrypoint（CodeZip 构建打的就是本目录）。

**这里故意什么都不做。** 路由与判断全在
``campuspath_cloud/agentcore_app.py``——它同时是本仓 ``agents/cloud/agentcore_app.py``
的**同一份源码**（由 ``scripts/agentcore_stage.sh`` rsync 过来，
`.gitignore` 里排除），所以 ``agents/tests/test_agentcore_app.py`` 在 CI 里
测的就是这里会跑的那段逻辑。入口文件里如果长出第二份逻辑，那份逻辑就
永远没有测试——这是唯一的理由。

打包进来的四个包（外加 ``campuspath_packs``，``campuspath_rules`` 的本地依赖）：

    campuspath_contracts   契约（Pydantic，零模型 SDK）
    campuspath_agents      A0–A5 + Strands 通道 + 白名单/卫生 hook
    campuspath_rules       Rules & Constraint Engine（零 LLM）
    campuspath_capacity    Capacity & Calendar（零 LLM）
    campuspath_cloud       本入口的路由层（= agents/cloud）

``app.run()`` 只在本地手工起服务时用得上；AgentCore 自己会起。
"""

from __future__ import annotations

import pathlib
import sys

#: CodeZip 解包后的工作目录未必在 ``sys.path`` 的第一位——把自己所在目录
#: 显式放进去，vendored 的五个包才一定找得到。
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from campuspath_cloud.agentcore_app import app, invoke  # noqa: E402,F401

if __name__ == "__main__":
    app.run()
