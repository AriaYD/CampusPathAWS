#!/usr/bin/env bash
# CampusPath Strands（AWS "Agents for Humans" 投稿）—— 独立部署脚本。
#
# 只碰两个**全新、独立**的 Cloud Run 服务：
#   campuspath-api-strands / campuspath-web-strands
# 现役的 campuspath-api / campuspath-web 仍在被 Google 赛评审，本脚本
# 每个子命令都会在入口处用字面量核对目标服务名，拒绝碰现役服务名。
#
#   bash infra/deploy_strands.sh --help
#   DRY_RUN=1 bash infra/deploy_strands.sh all     # 只打印将执行的 gcloud 命令
#   bash infra/deploy_strands.sh all               # 真的执行
#
# bash 3.2 兼容（macOS 自带 /bin/bash 就是 3.2.57）：不用关联数组、
# 不用 ${var,,}、不用 readarray；只用 case/函数。
#
# 任何管道里带 gcloud 的命令都跑在 `set -euo pipefail` 下——
# `gcloud run deploy … | tail -4` 会让 tail 的退出码盖掉 gcloud 真实的失败
# （Plan V2 §10.2 踩过的坑），pipefail 保证管道整体失败才算失败。

set -euo pipefail
cd "$(dirname "$0")/.."

# DRY_RUN 由本脚本的调用者以环境变量方式决定（DRY_RUN=1 表示只打印不执行），
# 不复用 config.sh 的 --apply/--dry-run 命令行约定——那是给 bootstrap/verify
# 用的另一套开关。config.sh 底部会无条件把 DRY_RUN 设成 1，所以先把调用者的
# 值存起来，source 完再原样放回去。
_REQUESTED_DRY_RUN="${DRY_RUN:-0}"
source infra/config.sh
DRY_RUN="$_REQUESTED_DRY_RUN"

API_SERVICE="campuspath-api-strands"
WEB_SERVICE="campuspath-web-strands"

# ── 护栏：字面量核对，拒绝碰现役服务名 ──────────────────────────────
assert_not_forbidden() {
  local name="$1"
  case "$name" in
    campuspath-api|campuspath-web)
      bad "拒绝操作 $name —— 这是现役服务，Google 赛评审仍在进行（评审至 10-01），不可改动"
      exit 1
      ;;
  esac
}

# ── 打印后执行 / 只打印不执行 ────────────────────────────────────────
# 真正执行时用 `set -x` 把展开后的确切命令打到 stderr 再跑；
# DRY_RUN=1 时只打印一行等价预览，不落地任何一次 gcloud 调用。
xrun() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s' "$DIM" "$NC"
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  ( set -x; "$@" )
}

# 携带密钥值的调用绝不能走 xrun（set -x 会把展开后的参数原样打出来，
# 等于把密钥写进终端/日志）。这里手动打印一行打了码的预览，值本身
# 只经过一次管道，从不出现在任何 printf/echo 里。
xrun_secret_version_add() {
  local secret="$1" value="$2"
  local preview="printf **** | gcloud secrets versions add ${secret} --data-file=- --project=${PROJECT_ID}"
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s %s\n' "$DIM" "$NC" "$preview"
    return 0
  fi
  printf '%s$%s %s\n' "$DIM" "$NC" "$preview"
  printf '%s' "$value" | gcloud secrets versions add "$secret" --data-file=- --project="$PROJECT_ID"
}

# web 的 AUTH_SECRET / CAMPUSPATH_DEMO_PASSCODE 不经 Secret Manager
# （现役 web 服务也是这么配的——纯 env var，见 infra/README.md 的踩坑记录），
# 但既然是脚本刚生成的随机值，也不必让它原样出现在 set -x 的 trace 里。
xrun_web_env_update() {
  local app_origin="$1" auth_secret="$2" passcode="$3"
  local masked="APP_ORIGIN=${app_origin},AUTH_SECRET=****,CAMPUSPATH_DEMO_PASSCODE=****"
  local real="APP_ORIGIN=${app_origin},AUTH_SECRET=${auth_secret},CAMPUSPATH_DEMO_PASSCODE=${passcode}"
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s gcloud run services update %s --project=%s --region=%s --update-env-vars=%s\n' \
      "$DIM" "$NC" "$WEB_SERVICE" "$PROJECT_ID" "$APP_REGION" "$masked"
    return 0
  fi
  printf '%s$%s gcloud run services update %s --project=%s --region=%s --update-env-vars=%s\n' \
    "$DIM" "$NC" "$WEB_SERVICE" "$PROJECT_ID" "$APP_REGION" "$masked"
  gcloud run services update "$WEB_SERVICE" --project="$PROJECT_ID" --region="$APP_REGION" \
    --update-env-vars="$real"
}

# ── 服务账户探测 ─────────────────────────────────────────────────────
# "同一个服务账户"：从现役 campuspath-api 实测读出来，而不是把项目号
# 写死在这份脚本里。可用 API_SERVICE_ACCOUNT 环境变量覆盖。
# 这是一次只读 `describe`，不改动任何资源。
resolve_api_service_account() {
  if [ -n "${API_SERVICE_ACCOUNT:-}" ]; then
    printf '%s\n' "$API_SERVICE_ACCOUNT"
    return 0
  fi
  local sa
  sa=$(gcloud run services describe campuspath-api --region="$APP_REGION" --project="$PROJECT_ID" \
        --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)
  if [ -z "$sa" ]; then
    bad "无法从现役 campuspath-api 读出服务账户；请显式设置 API_SERVICE_ACCOUNT=<sa-email> 后重试"
    exit 1
  fi
  printf '%s\n' "$sa"
}

# ── secrets：AWS 凭据 → Secret Manager ───────────────────────────────
cmd_secrets() {
  # 守门：AWS_PROFILE 指向的身份若挂着 AdministratorAccess，拒绝把它的长期密钥推进公网服务。
  if command -v aws >/dev/null 2>&1; then
    if aws iam list-attached-user-policies --user-name "$(aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null | sed 's#.*/##')" --output text 2>/dev/null | grep -q AdministratorAccess; then
      bad "AWS_PROFILE=${AWS_PROFILE:-default} 是管理员身份——不把管理员长期密钥推进 Cloud Run。用最小权限用户 campuspath-runtime-invoker 的 profile。"; exit 1
    fi
  fi
  step "secrets：AWS 凭据 → Secret Manager"
  local profile="${AWS_PROFILE:-campuspath}"
  local access_key="" secret_key=""

  if command -v aws >/dev/null 2>&1; then
    access_key=$(aws configure get aws_access_key_id --profile "$profile" 2>/dev/null || true)
    secret_key=$(aws configure get aws_secret_access_key --profile "$profile" 2>/dev/null || true)
  fi

  if { [ -z "$access_key" ] || [ -z "$secret_key" ]; } && [ -f "$HOME/.aws/credentials" ]; then
    access_key=$(awk -F'=' -v p="[$profile]" '
      /^\[/ { infile = ($0 == p) }
      infile && $1 ~ /aws_access_key_id/ { gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2 }
    ' "$HOME/.aws/credentials")
    secret_key=$(awk -F'=' -v p="[$profile]" '
      /^\[/ { infile = ($0 == p) }
      infile && $1 ~ /aws_secret_access_key/ { gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2 }
    ' "$HOME/.aws/credentials")
  fi

  if [ -z "$access_key" ] || [ -z "$secret_key" ]; then
    bad "读不到 AWS profile '$profile' 的凭据——aws CLI 与 ~/.aws/credentials 都没有可用值"
    exit 1
  fi
  ok "已从本地 profile '$profile' 读取凭据（值不会被打印）"

  local api_sa; api_sa=$(resolve_api_service_account)
  ok "API 服务账户：$api_sa"

  local secret
  for secret in campuspath-aws-access-key-id campuspath-aws-secret-access-key; do
    if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
      ok "$secret 已存在（只更新版本）"
    else
      xrun gcloud secrets create "$secret" \
        --replication-policy=user-managed --locations="$APP_REGION" \
        --project="$PROJECT_ID"
    fi
  done

  xrun_secret_version_add campuspath-aws-access-key-id "$access_key"
  xrun_secret_version_add campuspath-aws-secret-access-key "$secret_key"

  xrun gcloud secrets add-iam-policy-binding campuspath-aws-access-key-id \
    --member="serviceAccount:${api_sa}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID"
  xrun gcloud secrets add-iam-policy-binding campuspath-aws-secret-access-key \
    --member="serviceAccount:${api_sa}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID"
}

# ── api：构建 + 部署 campuspath-api-strands ──────────────────────────
cmd_api() {
  assert_not_forbidden "$API_SERVICE"
  step "api：构建并部署 $API_SERVICE"

  local git_sha; git_sha=$(git rev-parse --short HEAD)
  local image="${APP_REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${API_SERVICE}:${git_sha}"

  xrun gcloud builds submit --tag "$image" --project="$PROJECT_ID" .

  local agent_runtime="${CAMPUSPATH_AGENT_RUNTIME:-agentcore}"
  local runtime_arn=""
  if [ "$agent_runtime" != "local" ]; then
    : "${AGENTCORE_RUNTIME_ARN:?AGENTCORE_RUNTIME_ARN is required when CAMPUSPATH_AGENT_RUNTIME=$agent_runtime (set CAMPUSPATH_AGENT_RUNTIME=local to skip AgentCore)}"
    runtime_arn="$AGENTCORE_RUNTIME_ARN"
  fi

  local api_sa; api_sa=$(resolve_api_service_account)

  local env_vars
  env_vars="CAMPUSPATH_MODEL_BACKEND=bedrock"
  env_vars="${env_vars},CAMPUSPATH_AGENT_RUNTIME=${agent_runtime}"
  env_vars="${env_vars},AWS_REGION=us-east-1"
  env_vars="${env_vars},AWS_EC2_METADATA_DISABLED=true"
  env_vars="${env_vars},BEDROCK_MODEL_ID=amazon.nova-pro-v1:0"
  env_vars="${env_vars},CAMPUSPATH_CHECKPOINT=firestore:strands"
  env_vars="${env_vars},CAMPUSPATH_TRACE=gcp"
  env_vars="${env_vars},GOOGLE_GENAI_USE_VERTEXAI=TRUE"
  env_vars="${env_vars},GOOGLE_CLOUD_LOCATION=global"
  env_vars="${env_vars},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  if [ -n "$runtime_arn" ]; then
    env_vars="${env_vars},AGENTCORE_RUNTIME_ARN=${runtime_arn}"
  fi

  # --set-secrets 一次性声明这个服务全部的密钥挂载：CHECKIN_SECRET 是
  # 复制现役 campuspath-api 已有的挂法（infra/bootstrap.sh 建的密钥容器，
  # 值人工注入），另外两个是新 Bedrock 凭据。
  xrun gcloud run deploy "$API_SERVICE" --allow-unauthenticated \
    --image="$image" \
    --project="$PROJECT_ID" \
    --region="$APP_REGION" \
    --service-account="$api_sa" \
    --max-instances=1 \
    --update-env-vars="$env_vars" \
    --set-secrets="CHECKIN_SECRET=campuspath-checkin-secret:latest,AWS_ACCESS_KEY_ID=campuspath-aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=campuspath-aws-secret-access-key:latest"
}

# ── web：构建 + 部署 campuspath-web-strands ──────────────────────────
cmd_web() {
  assert_not_forbidden "$WEB_SERVICE"
  step "web：构建并部署 $WEB_SERVICE"

  local api_url
  api_url=$(gcloud run services describe "$API_SERVICE" --region="$APP_REGION" --project="$PROJECT_ID" \
             --format='value(status.url)' 2>/dev/null || true)
  if [ -z "$api_url" ]; then
    if [ "$DRY_RUN" = "1" ]; then
      api_url="https://${API_SERVICE}-<hash>-<region>.a.run.app"
      warn "$API_SERVICE 还没有 URL（尚未部署）——dry-run 用占位 URL 预览命令"
    else
      bad "$API_SERVICE 还没有 URL——先跑 'api' 子命令"
      exit 1
    fi
  else
    ok "API origin: $api_url"
  fi

  local git_sha; git_sha=$(git rev-parse --short HEAD)
  local image="${APP_REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${WEB_SERVICE}:${git_sha}"

  # rewrites 在 build 时烧进 routes-manifest，契约类型必须在构建期就位
  # （README §6 踩过的坑：目录已存在时 cp -r 会拷成嵌套子目录）。
  local contracts_cmd="(cd apps/web && rm -rf .contracts-generated && cp -r ../../contracts/generated .contracts-generated)"
  if [ "$DRY_RUN" = "1" ]; then
    printf '%s[dry-run]%s %s\n' "$DIM" "$NC" "$contracts_cmd"
  else
    printf '%s$%s %s\n' "$DIM" "$NC" "$contracts_cmd"
    ( cd apps/web && rm -rf .contracts-generated && cp -r ../../contracts/generated .contracts-generated )
  fi

  xrun gcloud builds submit --tag "$image" --project="$PROJECT_ID" apps/web

  xrun gcloud run deploy "$WEB_SERVICE" --allow-unauthenticated \
    --image="$image" \
    --project="$PROJECT_ID" \
    --region="$APP_REGION" \
    --update-env-vars="CAMPUSPATH_API_ORIGIN=${api_url}"

  local web_url
  web_url=$(gcloud run services describe "$WEB_SERVICE" --region="$APP_REGION" --project="$PROJECT_ID" \
             --format='value(status.url)' 2>/dev/null || true)
  if [ -z "$web_url" ] && [ "$DRY_RUN" = "1" ]; then
    web_url="https://${WEB_SERVICE}-<hash>-<region>.a.run.app"   # dry-run 占位，真实 URL 部署后才有
  fi

  # APP_ORIGIN 只有服务自己第一次部署完才知道 URL（Cloud Run 的 hash 后缀
  # 部署前猜不到），所以是"先建服务，再用它自己的 URL 更新自己"的两步模式，
  # 与现役 campuspath-web 的配置方式一致。
  local auth_secret="${WEB_AUTH_SECRET:-}"
  if [ -z "$auth_secret" ]; then
    if [ "$DRY_RUN" = "1" ]; then
      auth_secret="<generated-by-openssl-rand-hex-32>"
    else
      auth_secret=$(openssl rand -hex 32)
    fi
  fi
  local passcode="${CAMPUSPATH_DEMO_PASSCODE:-CampusPathStrandsDemo!}"

  xrun_web_env_update "$web_url" "$auth_secret" "$passcode"
}

# ── status：只读，打印 URL / revision / 健康检查 ─────────────────────
cmd_status() {
  step "status：$API_SERVICE / $WEB_SERVICE"

  local api_url web_url api_rev web_rev
  api_url=$(gcloud run services describe "$API_SERVICE" --region="$APP_REGION" --project="$PROJECT_ID" \
             --format='value(status.url)' 2>/dev/null || true)
  web_url=$(gcloud run services describe "$WEB_SERVICE" --region="$APP_REGION" --project="$PROJECT_ID" \
             --format='value(status.url)' 2>/dev/null || true)

  if [ -n "$api_url" ]; then
    api_rev=$(gcloud run services describe "$API_SERVICE" --region="$APP_REGION" --project="$PROJECT_ID" \
               --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)
    ok "$API_SERVICE: $api_url (revision: ${api_rev:-<none>})"
  else
    warn "$API_SERVICE 尚未部署"
  fi

  if [ -n "$web_url" ]; then
    web_rev=$(gcloud run services describe "$WEB_SERVICE" --region="$APP_REGION" --project="$PROJECT_ID" \
               --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)
    ok "$WEB_SERVICE: $web_url (revision: ${web_rev:-<none>})"
  else
    warn "$WEB_SERVICE 尚未部署"
  fi

  if [ -n "$api_url" ]; then
    step "健康检查"
    curl -sS -o /dev/null -w '  healthz: HTTP %{http_code}\n' "${api_url}/healthz" \
      || warn "healthz 请求失败（服务可能刚冷启动，稍后重试）"
    printf '  /v1/ops/agents 响应头：\n'
    curl -sS -D - -o /dev/null "${api_url}/v1/ops/agents" \
      || warn "/v1/ops/agents 请求失败"
  fi
}

# ── 帮助 ──────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
CampusPath Strands 独立部署脚本

用法：
  bash infra/deploy_strands.sh <子命令>
  DRY_RUN=1 bash infra/deploy_strands.sh <子命令>   # 只打印将执行的 gcloud 命令

子命令：
  secrets   AWS 凭据（本地 profile）→ Secret Manager，并授权 API 服务账户读取
  api       构建根 Dockerfile 并部署 $API_SERVICE
  web       构建 apps/web/Dockerfile 并部署 ${WEB_SERVICE}（指向新 API 的 URL）
  status    打印两个新服务的 URL / revision，并做一次健康检查（只读）
  all       secrets → api → web → status
  --help    显示本帮助

环境变量：
  AWS_PROFILE              本地 AWS profile 名（默认 campuspath）
  CAMPUSPATH_AGENT_RUNTIME  agentcore（默认）| local
  AGENTCORE_RUNTIME_ARN     CAMPUSPATH_AGENT_RUNTIME != local 时必填
  API_SERVICE_ACCOUNT       覆盖自动探测的 API 服务账户（默认读现役 campuspath-api 用的那个）
  WEB_AUTH_SECRET           覆盖自动生成（openssl rand -hex 32）的 web AUTH_SECRET
  CAMPUSPATH_DEMO_PASSCODE  web 登录口令（默认占位值，建议自定义）
  DRY_RUN=1                 只打印命令，不执行任何 gcloud 调用

安全护栏：
  - 每个子命令都会字面量核对目标服务名不是 campuspath-api / campuspath-web
    （现役服务，Google 赛评审至 10-01，禁止改动）。
  - secrets 子命令绝不打印 AWS 凭据的值；web 子命令生成的 AUTH_SECRET /
    CAMPUSPATH_DEMO_PASSCODE 在打印预览时同样打码。
EOF
}

main() {
  local sub="${1:---help}"
  assert_not_forbidden "$API_SERVICE"
  assert_not_forbidden "$WEB_SERVICE"
  case "$sub" in
    --help|-h|help)
      usage
      ;;
    secrets)
      cmd_secrets
      ;;
    api)
      cmd_api
      ;;
    web)
      cmd_web
      ;;
    status)
      cmd_status
      ;;
    all)
      # 2026-09-12 起 Secret Manager 里存的是最小权限用户 campuspath-runtime-invoker
      # 的密钥（v2），不是管理员 profile 的。默认不再覆盖；确需轮换时 WITH_SECRETS=1。
      if [ "${WITH_SECRETS:-0}" = "1" ]; then cmd_secrets; else
        echo "[skip] secrets：沿用 Secret Manager 现有版本（最小权限 invoker）；轮换用 WITH_SECRETS=1"; fi
      cmd_api
      cmd_web
      cmd_status
      ;;
    *)
      bad "未知子命令：$sub"
      usage
      exit 1
      ;;
  esac
}

main "$@"
