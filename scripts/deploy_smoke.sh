#!/usr/bin/env bash
# 生产部署冒烟（G6/H3）：health → SPA 首页 → 登录（含滑块验证码）→ 鉴权接口，
# 全部经 nginx 走真实生产链路。
#
# 用法：
#   BASE_URL=http://localhost:8080 ADMIN_USER=admin ADMIN_PASS=xxx \
#   REDIS_CONTAINER=loom-prod-redis REDIS_PASSWORD=xxx \
#   bash scripts/deploy_smoke.sh
#
# 验证码说明：生产（DEBUG=false）强制滑块验证码且答案不回传（防脚本）。
# 冒烟是携带基础设施凭据的部署验证而非渗透测试，因此从 Redis 侧读取本次
# 验证码的 target_x 后构造合规轨迹（±tolerance、时长/轨迹点/回滑均达标）。
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
ADMIN_USER="${ADMIN_USER:?请设置 ADMIN_USER}"
ADMIN_PASS="${ADMIN_PASS:?请设置 ADMIN_PASS}"
REDIS_CONTAINER="${REDIS_CONTAINER:-loom-prod-redis}"
REDIS_PASSWORD="${REDIS_PASSWORD:?请设置 REDIS_PASSWORD}"

fail() { echo "FAIL: $*"; exit 1; }

# 1. 健康检查（nginx /api/ 剥前缀 → 后端 /health，验证响应包装结构）
health=$(curl -fsS "$BASE_URL/api/health") || fail "/api/health 不可达（nginx 反代或后端未起）"
echo "$health" | python -c "import sys,json; d=json.load(sys.stdin); assert (d.get('data') or d).get('status')=='healthy', d" \
  || fail "health 状态异常: $health"
echo "OK   /api/health → healthy"

# 2. SPA 首页（前端静态资源 + history 路由兜底）
curl -fsS "$BASE_URL/" | head -c 400 | grep -qi "<!doctype html\|<html" || fail "首页返回非 HTML"
echo "OK   / → SPA index"

# 3. 获取滑块验证码并从 Redis 侧读取本次答案
captcha_resp=$(curl -fsS "$BASE_URL/api/admin/base/open/captcha?width=280&height=160")
captcha_id=$(echo "$captcha_resp" | python -c "import sys,json; print(json.load(sys.stdin)['data']['captchaId'])")
[ -n "$captcha_id" ] || fail "验证码获取失败: $captcha_resp"
target_x=$(docker exec "$REDIS_CONTAINER" redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
  GET "verify:slider:$captcha_id" \
  | python -c "import sys,json; print(json.load(sys.stdin)['target_x'])") \
  || fail "无法从 Redis 读取验证码答案（检查 REDIS_CONTAINER/REDIS_PASSWORD）"
echo "OK   captcha → id 已取，target_x=$target_x（基础设施侧读取）"

# 4. 登录（构造合规滑块轨迹：单调递增、时长 800ms、8 个轨迹点）
login_payload=$(python - "$ADMIN_USER" "$ADMIN_PASS" "$captcha_id" "$target_x" <<'EOF'
import json, sys

user, pwd, cid, tx = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
# 单调递增轨迹（每步允许 ≤ max_backtrack 的微回滑，这里保持干净递增），终点即答案
track = [{"x": round(tx * i / 7, 2)} for i in range(8)]
track[-1]["x"] = tx
print(json.dumps({
    "username": user,
    "password": pwd,
    "captchaId": cid,
    "verifyCode": json.dumps({"x": tx, "duration": 800, "track": track}),
}))
EOF
)
login_resp=$(curl -fsS -X POST "$BASE_URL/api/admin/base/open/login" \
  -H "Content-Type: application/json" -H "Origin: $BASE_URL" \
  -d "$login_payload") || fail "登录请求失败（检查 Origin/CORS_ORIGINS/口令/锁定状态）"
token=$(echo "$login_resp" | python -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data') or {}
print(data.get('token') or data.get('access_token') or '')
")
[ -n "$token" ] || fail "登录未返回 token: $login_resp"
echo "OK   login → token 已签发"

# 5. 鉴权接口（经 permission/role 校验的完整链路）
curl -fsS "$BASE_URL/api/admin/base/comm/person" \
  -H "Authorization: Bearer $token" -H "Origin: $BASE_URL" \
  | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('code')==1000, d" \
  || fail "person 接口异常"
echo "OK   /admin/base/comm/person → 鉴权链路通"

# 6. 容器健康矩阵（异步审查第二轮）：prod compose 固定 container_name；
#    backend/worker/beat 有 healthcheck 断言 healthy，web 无 healthcheck 断言 running
if command -v docker >/dev/null 2>&1; then
  for c in loom-prod-backend loom-prod-celery-worker loom-prod-celery-beat; do
    state=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$c" 2>/dev/null) \
      || fail "容器 $c 不存在（docker inspect；本步骤面向 prod compose 部署）"
    [ "$state" = "healthy" ] || fail "容器 $c 健康状态异常: $state"
  done
  web_state=$(docker inspect -f '{{.State.Status}}' loom-prod-web 2>/dev/null) || fail "容器 loom-prod-web 不存在"
  [ "$web_state" = "running" ] || fail "容器 loom-prod-web 状态异常: $web_state"
  echo "OK   容器健康矩阵 → backend/worker/beat healthy，web running"
fi

# 7. metrics 采样（可选：传入 --with-metrics；需服务端 METRICS_ENABLED=true，
#    异步审查·可观测性的七组指标键必须齐备，防止「开关开了但指标没接上」的假绿）
WITH_METRICS=0
for arg in "$@"; do [ "$arg" = "--with-metrics" ] && WITH_METRICS=1; done
if [ "$WITH_METRICS" = "1" ]; then
  metrics=$(curl -fsS "$BASE_URL/api/metrics") || fail "/api/metrics 不可达（检查服务端 METRICS_ENABLED 与 nginx /api/ 路由）"
  for key in loom_db_pool_checkedout loom_thread_pool_borrowed loom_sse_connections_active \
    loom_celery_queue_depth loom_celery_unacked_total loom_event_loop_lag_seconds \
    loom_metric_series_overflow_total; do
    echo "$metrics" | grep -q "^$key" || fail "metrics 缺少 $key（服务端代码与本脚本版本不匹配？）"
  done
  echo "OK   metrics → 七组指标键齐备"
fi

echo
echo "=== 部署冒烟全部通过：$BASE_URL ==="
