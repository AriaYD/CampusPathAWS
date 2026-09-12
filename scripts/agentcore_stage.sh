#!/usr/bin/env bash
# 把语义平面的源码复制进 AgentCore 的构建目录（CodeZip 打的就是那一份）。
#
# 为什么是复制而不是 symlink 或 pip install：CodeZip 把 `codeLocation` 整个打包
# 上传给 CodeBuild，符号链接过不去，editable install 更过不去。所以 vendoring 是
# AgentCore 的构建形态决定的，不是偷懒。
#
# **复制进去的东西是构建产物，不是源码**（`.gitignore` 排除）：源头只有一处，
# 改代码永远改 contracts/ 、agents/ 、services/ 下的那一份，然后重跑本脚本。
# 两份源码分叉是这类 vendoring 最典型的塌方方式——用 `--delete` 让复制目标
# 永远等于源头，而不是"源头 + 上次残留"。
#
# 用法：  bash scripts/agentcore_stage.sh      （或 make agentcore-stage）

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/infra/agentcore/app/campuspath"

if ! command -v rsync >/dev/null 2>&1; then
  echo "需要 rsync（macOS/Linux 自带）" >&2
  exit 1
fi

# 源目录 → 目标包名。campuspath_rules 的本地依赖 campuspath_packs 一并带上：
# 少了它 `import campuspath_rules.context_pack` 会在**云上第一次调用时**才炸。
PAIRS=(
  "contracts/campuspath_contracts:campuspath_contracts"
  "agents/campuspath_agents:campuspath_agents"
  "agents/cloud:campuspath_cloud"
  "services/rules/campuspath_rules:campuspath_rules"
  "services/capacity/campuspath_capacity:campuspath_capacity"
  "services/packs/campuspath_packs:campuspath_packs"
)

mkdir -p "$DEST"

for pair in "${PAIRS[@]}"; do
  src="$ROOT/${pair%%:*}"
  name="${pair##*:}"
  if [ ! -d "$src" ]; then
    echo "源目录不存在：$src" >&2
    exit 1
  fi
  rsync -a --delete \
    --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude 'tests/' --exclude '.pytest_cache/' --exclude '.DS_Store' \
    "$src/" "$DEST/$name/"
  printf '  %-22s ← %s\n' "$name" "${pair%%:*}"
done

# agents/cloud 是按目录加载的，没有 __init__.py；作为 campuspath_cloud 包被
# `main.py` import 时必须有一个。生成的这一份也是产物，不回写源目录。
if [ ! -f "$DEST/campuspath_cloud/__init__.py" ]; then
  cat > "$DEST/campuspath_cloud/__init__.py" <<'PY'
"""AgentCore Runtime 的路由层（构建产物：源头是本仓 agents/cloud/）。

由 scripts/agentcore_stage.sh 生成，别手改——改 agents/cloud/ 再重跑。
"""
PY
fi

echo "已就位：$DEST"
