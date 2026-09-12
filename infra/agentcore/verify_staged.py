"""打包目录的自检：**在那份将被 zip 上传的代码里**跑一次真调用。

怎么跑（`make agentcore-stage` 会自动做）：

    cd infra/agentcore/app/campuspath \
      && PYTHONPATH=. ../../../../.venv/bin/python - < ../../verify_staged.py

经 stdin 喂进解释器是刻意的：``python -`` 的 ``sys.path[0]`` 是**当前目录**
（也就是打包目录），不是本文件所在目录。于是解释器看得见的只有打包目录
与 site-packages——本仓的 editable 安装不会替它把缺的包补上。
这正是我们要问的问题：**CodeZip 上去的那份，自己站得住吗？**

"能 import"还不够，所以这里跑的是一次带工具调用的 A4 请求：
模型（剧本桩，零成本）去调 ``publish_opportunity``，白名单 hook 必须留下
被拒记录，且该记录必须**跟着回包出境**。少任何一个包、hook 没挂进事件循环、
回包字段拼错——这条都会在**本地**红，而不是在云上第一次调用时红。

**它证明不了的事**（实测：把 ``event.cancel_tool`` 那行删掉，本脚本照样绿）：
"调用真的被取消了"。那条由 ``agents/tests/test_strands_runtime.py::
test_whitelist_hook_cancels_a_tool_the_model_can_actually_reach`` 守着——
那里把工具真的注册进 Strands，hook 不拦工具就会执行。本脚本守的是
**打包边界**：这份 zip 自己站不站得住。
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path.cwd().resolve()

import main  # noqa: E402  —— 打包目录里的 entrypoint

VENDORED = ("campuspath_agents", "campuspath_contracts", "campuspath_rules",
            "campuspath_capacity", "campuspath_packs", "campuspath_cloud")

for name in VENDORED:
    module = __import__(name)
    path = pathlib.Path(module.__file__).resolve()
    if not path.is_relative_to(HERE):
        raise SystemExit(
            f"FAIL {name} 来自 {path}——不是打包目录。"
            "CodeZip 只上传打包目录，这个包在云上会缺席。"
        )

from campuspath_agents.model import ScriptedModel  # noqa: E402
from campuspath_cloud import agentcore_app  # noqa: E402

#: 剧本桩替掉进程级单例：真 BedrockModelClient 要 AWS 凭据，还要花钱。
agentcore_app._MODEL = ScriptedModel({
    "extract:SRC-1": {"tool": "publish_opportunity", "input": {"id": "OPP-1"}},
    "extract:SRC-1#after_tool": "我没有发布权，已产出草稿。",
})

out = main.invoke({"kind": "generate", "request": {
    "system": "你是 A4", "data": ["工作坊详情……"],
    "purpose": "extract:SRC-1", "agent": "A4",
}})

if out.get("result", "").strip() != "我没有发布权，已产出草稿。":
    raise SystemExit(f"FAIL generate 回包不对：{out}")
if not out.get("rejected_tools") or out["rejected_tools"][0][0] != "publish_opportunity":
    raise SystemExit(
        f"FAIL 白名单 hook 没有拦下 publish_opportunity，或被拒记录没跟着回包出来：{out}"
    )
if main.invoke({"kind": "nope"}).get("error") != "unknown_kind":
    raise SystemExit("FAIL 不认识的 kind 必须被拒，不能落到默认分支")

print(f"OK  staged app  python={sys.version.split()[0]}  "
      f"{json.dumps(out, ensure_ascii=False)}")
