#!/usr/bin/env bash
# =============================================================================
#  IoT 设备管理平台 · 一键部署（Ubuntu Server 22.04+ / 24.04 / 26.04）
#
#  做的事：安装 Docker → 获取代码 → 生成 .env（随机密钥/密码，重复执行会保留）
#        → 构建镜像（前端 + 后端）→ 启动 web + PostgreSQL + MinIO（版本文件存储）容器
#        → 配置宿主机 Nginx 反向代理（含 WebSocket）→ 放行防火墙端口 → 输出访问信息
#
#  端口：容器只监听 127.0.0.1:<APP_PORT>（默认 18000），对外由 Nginx 监听 <PORT>（默认 8090）；
#        PostgreSQL、MinIO API 不映射宿主机端口；MinIO 控制台只监听 127.0.0.1:<console>（默认 19001）。
#        端口都会检测，被占用时自动顺延到空闲端口。
#
#  用法（root）：
#    sudo bash deploy/deploy.sh                       # 在仓库目录内执行
#    curl -fsSL https://raw.githubusercontent.com/trep123/IOT/main/deploy/deploy.sh | sudo bash
#
#  常用参数：
#    --port 8090            对外端口（Nginx 监听）
#    --domain iot.example.com  使用域名，Nginx 在 80 端口按 server_name 转发（不再占用新端口）
#    --no-nginx             不配置 Nginx，容器直接监听 0.0.0.0:<port>
#    --cn                   使用国内 pip / npm 镜像源
#    --image-mirror PREFIX  基础镜像前缀，如 docker.m.daocloud.io/library/
#    --demo                 写入演示数据（10 台设备、指令模板、两个版本）
#    --dir /opt/iot         代码与配置目录（curl 方式执行时使用）
#    --branch main          拉取的分支
#    --public-url URL       下发给设备的平台地址（默认 http://<本机IP>:<port> 或 http://<domain>）
#    --uninstall            停止并删除容器（保留数据卷与 .env）
#
#  版本文件存储（MinIO）：
#    --minio-user admin         MinIO 账号（默认 admin）
#    --minio-password PWD       MinIO 密码（≥8 位；不填则沿用 .env，首次随机生成）
#    --minio-bucket iot         存储桶（默认 iot，不存在时自动创建）
#    --minio-endpoint URL       使用已有的外部 MinIO（如 http://10.0.0.5:9000），不再启动内置 MinIO 容器
#    --minio-console-port 19001 内置 MinIO 控制台端口（仅监听 127.0.0.1）
#    --no-minio                 版本文件改存容器数据卷（本地磁盘）
# =============================================================================
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/trep123/IOT.git}"
BRANCH="main"
INSTALL_DIR="/opt/iot"
PUBLIC_PORT=""
APP_PORT=""
DOMAIN=""
USE_NGINX="auto"
USE_CN=0
IMAGE_MIRROR=""
INIT_DEMO=0
PUBLIC_URL=""
UNINSTALL=0
MINIO_MODE=""          # builtin | external | none；空 = 沿用 .env，首次为 builtin
MINIO_USER=""
MINIO_PASSWORD=""
MINIO_BUCKET=""
MINIO_ENDPOINT=""
MINIO_CONSOLE_PORT=""
MINIO_IMAGE_DEFAULT="pgsty/minio:RELEASE.2026-08-04T00-00-00Z"   # MinIO 社区版构建（官方已停止发布 Docker 镜像）

c_green='\033[32m'; c_yellow='\033[33m'; c_red='\033[31m'; c_cyan='\033[36m'; c_off='\033[0m'
info()  { echo -e "${c_cyan}[IoT]${c_off} $*"; }
ok()    { echo -e "${c_green}[ OK]${c_off} $*"; }
warn()  { echo -e "${c_yellow}[WARN]${c_off} $*"; }
die()   { echo -e "${c_red}[FAIL]${c_off} $*" >&2; exit 1; }
trap 'die "第 ${LINENO} 行执行失败：${BASH_COMMAND}"' ERR

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PUBLIC_PORT="$2"; shift 2 ;;
    --app-port) APP_PORT="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --no-nginx) USE_NGINX=0; shift ;;
    --cn) USE_CN=1; shift ;;
    --image-mirror) IMAGE_MIRROR="$2"; shift 2 ;;
    --demo) INIT_DEMO=1; shift ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --public-url) PUBLIC_URL="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --minio-user) MINIO_USER="$2"; shift 2 ;;
    --minio-password) MINIO_PASSWORD="$2"; shift 2 ;;
    --minio-bucket) MINIO_BUCKET="$2"; shift 2 ;;
    --minio-endpoint) MINIO_ENDPOINT="$2"; MINIO_MODE=external; shift 2 ;;
    --minio-console-port) MINIO_CONSOLE_PORT="$2"; shift 2 ;;
    --no-minio) MINIO_MODE=none; shift ;;
    -h|--help) sed -n '2,41p' "$0"; exit 0 ;;
    *) die "未知参数：$1（--help 查看用法）" ;;
  esac
done

# ---------------------------------------------------------------- 工具函数
port_in_use() { ss -Hltn "sport = :$1" 2>/dev/null | grep -q .; }

pick_port() {  # pick_port <起始端口> <排除端口...>
  local p=$1; shift
  while port_in_use "$p" || [[ " $* " == *" $p "* ]]; do p=$((p + 1)); done
  echo "$p"
}

rand() {  # 不用 tr </dev/urandom | head，避免 pipefail 下的 SIGPIPE
  local n=${1:-32} s=""
  while ((${#s} < n)); do s+="$(head -c 96 /dev/urandom | tr -dc 'A-Za-z0-9')"; done
  echo "${s:0:n}"
}

env_get() { [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

compose() { docker compose "$@"; }

# ---------------------------------------------------------------- 1. 依赖
install_deps() {
  info "检查系统依赖 ..."
  local need=()
  command -v git  >/dev/null || need+=(git)
  command -v curl >/dev/null || need+=(curl)
  command -v ss   >/dev/null || need+=(iproute2)
  if ((${#need[@]})); then
    apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}"
  fi

  if ! command -v docker >/dev/null; then
    info "安装 Docker ..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io \
      || { curl -fsSL https://get.docker.com | sh; }
  fi
  systemctl enable --now docker >/dev/null 2>&1 || true

  if ! docker compose version >/dev/null 2>&1; then
    info "安装 Docker Compose 插件 ..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-compose-v2 2>/dev/null \
      || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-compose-plugin 2>/dev/null \
      || die "无法安装 docker compose 插件，请手动安装后重试"
  fi
  if ! docker buildx version >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-buildx 2>/dev/null || true
  fi
  ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)，$(docker compose version --short 2>/dev/null | sed 's/^/Compose /')"
}

# ---------------------------------------------------------------- 2. 代码
locate_source() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if [[ -n "$here" && -f "$here/../docker-compose.yml" && -f "$here/../manage.py" ]]; then
    PROJECT_DIR="$(cd "$here/.." && pwd)"
    info "使用当前仓库：$PROJECT_DIR"
    return
  fi
  PROJECT_DIR="$INSTALL_DIR"
  if [[ -d "$PROJECT_DIR/.git" ]]; then
    info "更新代码 $PROJECT_DIR（$BRANCH）..."
    git -C "$PROJECT_DIR" fetch --depth 1 origin "$BRANCH"
    git -C "$PROJECT_DIR" checkout -q "$BRANCH"
    git -C "$PROJECT_DIR" reset -q --hard "origin/$BRANCH"
  else
    info "克隆 $REPO_URL 到 $PROJECT_DIR ..."
    mkdir -p "$(dirname "$PROJECT_DIR")"
    git clone -q --depth 1 -b "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
  fi
}

# ---------------------------------------------------------------- 3. 配置
detect_ip() {
  local ip
  ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  [[ -n "$ip" ]] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "${ip:-127.0.0.1}"
}

write_env() {
  cd "$PROJECT_DIR"

  # Nginx：auto 时有 nginx 就用
  if [[ "$USE_NGINX" == "auto" ]]; then
    if command -v nginx >/dev/null; then USE_NGINX=1; else USE_NGINX=0; fi
  fi

  # 重复执行时沿用已有端口与密钥
  local old_app old_pub old_domain
  old_app="$(env_get IOT_APP_PORT)"; old_pub="$(env_get IOT_PUBLIC_PORT)"; old_domain="$(env_get IOT_DOMAIN)"
  [[ -n "$DOMAIN" ]] || DOMAIN="$old_domain"

  # 端口：先停掉本项目旧容器，避免把自己占用的端口判为冲突
  compose down >/dev/null 2>&1 || true

  if [[ "$USE_NGINX" == 1 ]]; then
    APP_PORT="${APP_PORT:-${old_app:-$(pick_port 18000)}}"
    port_in_use "$APP_PORT" && die "应用端口 $APP_PORT 已被占用，请用 --app-port 指定其他端口"
    if [[ -n "$DOMAIN" ]]; then
      PUBLIC_PORT=80
    else
      if [[ -z "$PUBLIC_PORT" ]]; then
        if [[ -n "$old_pub" && -f /etc/nginx/conf.d/iot-platform.conf ]] || [[ -n "$old_pub" && -f /etc/nginx/sites-enabled/iot-platform.conf ]]; then
          PUBLIC_PORT="$old_pub"                      # 端口已是我们自己的 Nginx 在监听
        else
          PUBLIC_PORT="$(pick_port 8090 "$APP_PORT")"
        fi
      elif port_in_use "$PUBLIC_PORT" && [[ "$PUBLIC_PORT" != "$old_pub" ]]; then
        die "对外端口 $PUBLIC_PORT 已被占用，请换一个（--port）"
      fi
    fi
    BIND=127.0.0.1
  else
    PUBLIC_PORT="${PUBLIC_PORT:-${old_pub:-$(pick_port 8090)}}"
    port_in_use "$PUBLIC_PORT" && die "端口 $PUBLIC_PORT 已被占用，请用 --port 指定其他端口"
    APP_PORT="$PUBLIC_PORT"
    BIND=0.0.0.0
  fi

  local host ip
  ip="$(detect_ip)"
  if [[ -n "$DOMAIN" ]]; then host="$DOMAIN"; else host="$ip:$PUBLIC_PORT"; fi
  [[ -n "$PUBLIC_URL" ]] || PUBLIC_URL="$(env_get IOT_PUBLIC_BASE_URL)"
  [[ -n "$PUBLIC_URL" ]] || PUBLIC_URL="http://$host"
  PUBLIC_URL="${PUBLIC_URL%/}"

  local secret sign pgpass adminpwd
  secret="$(env_get DJANGO_SECRET_KEY)";   [[ -n "$secret" ]]   || secret="$(rand 50)"
  sign="$(env_get IOT_SIGN_KEY)";          [[ -n "$sign" ]]     || sign="$(rand 40)"
  pgpass="$(env_get POSTGRES_PASSWORD)";   [[ -n "$pgpass" ]]   || pgpass="$(rand 24)"
  adminpwd="$(env_get IOT_ADMIN_PASSWORD)"; [[ -n "$adminpwd" ]] || adminpwd="$(rand 12)"
  ADMIN_PASSWORD="$adminpwd"

  local pip_index="https://pypi.org/simple" npm_reg="https://registry.npmjs.org"
  if [[ "$USE_CN" == 0 && "$(env_get PIP_INDEX_URL)" == *tsinghua* ]]; then USE_CN=1; fi
  if [[ "$USE_CN" == 0 ]]; then   # 官方源 6 秒内拿不到响应就自动切换国内源
    if ! curl -fsS -o /dev/null -m 6 https://pypi.org/simple/pip/ 2>/dev/null \
       || ! curl -fsS -o /dev/null -m 6 https://registry.npmjs.org/vite 2>/dev/null; then
      warn "官方 pip / npm 源访问缓慢，自动改用国内源（清华 PyPI、npmmirror）"
      USE_CN=1
    fi
  fi
  if [[ "$USE_CN" == 1 ]]; then
    pip_index="https://pypi.tuna.tsinghua.edu.cn/simple"
    npm_reg="https://registry.npmmirror.com"
  fi
  [[ -z "$IMAGE_MIRROR" ]] && IMAGE_MIRROR="$(env_get IOT_IMAGE_MIRROR)"
  [[ -n "$IMAGE_MIRROR" && "$IMAGE_MIRROR" != */ ]] && IMAGE_MIRROR="$IMAGE_MIRROR/"

  # ---- 版本文件存储（MinIO）----
  local old_endpoint old_profiles minio_endpoint="" minio_image="" profiles=""
  old_endpoint="$(env_get IOT_MINIO_ENDPOINT)"; old_profiles="$(env_get COMPOSE_PROFILES)"
  if [[ -z "$MINIO_MODE" ]]; then
    if [[ -f .env && -z "$old_endpoint" ]] && grep -q '^IOT_MINIO_ENDPOINT=' .env; then MINIO_MODE=none
    elif [[ -n "$old_endpoint" && "$old_profiles" != *minio* ]]; then MINIO_MODE=external; MINIO_ENDPOINT="$old_endpoint"
    else MINIO_MODE=builtin; fi
  fi
  [[ -n "$MINIO_USER" ]]     || MINIO_USER="$(env_get IOT_MINIO_ACCESS_KEY)";   [[ -n "$MINIO_USER" ]] || MINIO_USER=admin
  [[ -n "$MINIO_PASSWORD" ]] || MINIO_PASSWORD="$(env_get IOT_MINIO_SECRET_KEY)"; [[ -n "$MINIO_PASSWORD" ]] || MINIO_PASSWORD="$(rand 20)"
  [[ -n "$MINIO_BUCKET" ]]   || MINIO_BUCKET="$(env_get IOT_MINIO_BUCKET)";     [[ -n "$MINIO_BUCKET" ]] || MINIO_BUCKET=iot
  case "$MINIO_MODE" in
    builtin)
      ((${#MINIO_PASSWORD} >= 8)) || die "MinIO 密码至少 8 位（--minio-password）"
      profiles=minio
      minio_endpoint="http://minio:9000"
      minio_image="$(env_get IOT_MINIO_IMAGE)"
      if [[ -z "$minio_image" ]]; then
        minio_image="$MINIO_IMAGE_DEFAULT"
        [[ -n "$IMAGE_MIRROR" ]] && minio_image="${IMAGE_MIRROR%library/}$minio_image"
      fi
      [[ -n "$MINIO_CONSOLE_PORT" ]] || MINIO_CONSOLE_PORT="$(env_get IOT_MINIO_CONSOLE_PORT)"
      [[ -n "$MINIO_CONSOLE_PORT" ]] || MINIO_CONSOLE_PORT="$(pick_port 19001 "$APP_PORT" "$PUBLIC_PORT")"
      ;;
    external)
      [[ -n "$MINIO_ENDPOINT" ]] || die "--minio-endpoint 不能为空"
      minio_endpoint="${MINIO_ENDPOINT%/}"
      curl -s -o /dev/null -m 5 "$minio_endpoint/minio/health/live" || warn "暂时无法访问 $minio_endpoint，请确认容器内可达"
      ;;
    none) minio_endpoint="" ;;
  esac
  MINIO_SUMMARY="$MINIO_MODE|$minio_endpoint|$MINIO_BUCKET|$MINIO_USER|${MINIO_CONSOLE_PORT:-}"

  local origins="$PUBLIC_URL"
  [[ "$PUBLIC_URL" == "http://$ip:$PUBLIC_PORT" ]] || origins="$origins,http://$ip:$PUBLIC_PORT"
  [[ -n "$DOMAIN" ]] && origins="$origins,https://$DOMAIN"

  umask 077
  cat > .env <<EOF
# 由 deploy/deploy.sh 生成于 $(date '+%F %T')；修改后执行 docker compose up -d 生效
# ---- 端口 ----
IOT_BIND=$BIND
IOT_APP_PORT=$APP_PORT
IOT_PUBLIC_PORT=$PUBLIC_PORT
IOT_DOMAIN=$DOMAIN
# ---- Django ----
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$secret
DJANGO_ALLOWED_HOSTS=*
DJANGO_CSRF_TRUSTED_ORIGINS=$origins
# ---- 平台 ----
IOT_PUBLIC_BASE_URL=$PUBLIC_URL
IOT_SIGN_KEY=$sign
IOT_ADMIN_USER=admin
IOT_ADMIN_PASSWORD=$adminpwd
IOT_INIT_DEMO=$INIT_DEMO
IOT_HEARTBEAT_INTERVAL=30
IOT_HEARTBEAT_MISS=3
# ---- 数据库（容器内 PostgreSQL，不占用宿主机 5432）----
POSTGRES_DB=iot
POSTGRES_USER=iot
POSTGRES_PASSWORD=$pgpass
# ---- 版本文件存储（MinIO）----
# COMPOSE_PROFILES=minio 时随平台启动内置 MinIO；IOT_MINIO_ENDPOINT 为空时版本文件存容器数据卷
COMPOSE_PROFILES=$profiles
IOT_MINIO_IMAGE=$minio_image
IOT_MINIO_ENDPOINT=$minio_endpoint
IOT_MINIO_ACCESS_KEY=$MINIO_USER
IOT_MINIO_SECRET_KEY=$MINIO_PASSWORD
IOT_MINIO_BUCKET=$MINIO_BUCKET
IOT_MINIO_CONSOLE_PORT=${MINIO_CONSOLE_PORT:-19001}
# ---- 构建镜像源 ----
IOT_IMAGE_MIRROR=$IMAGE_MIRROR
PIP_INDEX_URL=$pip_index
NPM_REGISTRY=$npm_reg
EOF
  umask 022
  ok "配置已写入 $PROJECT_DIR/.env（对外端口 $PUBLIC_PORT，容器端口 $BIND:$APP_PORT）"
}

# ---------------------------------------------------------------- 4. 构建与启动
build_and_up() {
  cd "$PROJECT_DIR"
  info "构建镜像（首次约 3~8 分钟）..."
  compose build --pull web || compose build web
  info "启动容器 ..."
  compose up -d --remove-orphans

  info "等待服务就绪 ..."
  local status
  for _ in $(seq 1 90); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q web)" 2>/dev/null || echo starting)"
    [[ "$status" == healthy ]] && { ok "服务已就绪"; return; }
    sleep 2
  done
  compose logs --tail 80 web || true
  die "服务未在 3 分钟内就绪，请查看上面的日志（docker compose -f $PROJECT_DIR/docker-compose.yml logs web）"
}

# ---------------------------------------------------------------- 5. Nginx
setup_nginx() {
  [[ "$USE_NGINX" == 1 ]] || return 0
  info "配置 Nginx 反向代理 ..."
  local conf_dir link=""
  if [[ -d /etc/nginx/sites-available && -d /etc/nginx/sites-enabled ]]; then
    conf_dir=/etc/nginx/sites-available; link=/etc/nginx/sites-enabled/iot-platform.conf
  else
    conf_dir=/etc/nginx/conf.d
  fi
  local conf="$conf_dir/iot-platform.conf"
  [[ -f "$conf" ]] && cp "$conf" "$conf.bak.$(date +%s)"

  local listen="listen $PUBLIC_PORT;"
  [[ -f /proc/net/if_inet6 ]] && listen="$listen
    listen [::]:$PUBLIC_PORT;"
  local server_name="_"
  [[ -n "$DOMAIN" ]] && server_name="$DOMAIN"

  cat > "$conf" <<EOF
# IoT 设备管理平台（由 deploy/deploy.sh 生成）
map \$http_upgrade \$iot_connection_upgrade {
    default upgrade;
    ''      close;
}

upstream iot_platform {
    server 127.0.0.1:$APP_PORT;
    keepalive 16;
}

server {
    $listen
    server_name $server_name;

    client_max_body_size 1024m;      # 升级包上传
    proxy_read_timeout 3600s;        # 设备与管理端 WebSocket 长连接
    proxy_send_timeout 3600s;

    location / {
        proxy_pass http://iot_platform;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$iot_connection_upgrade;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
EOF
  [[ -n "$link" ]] && ln -sf "$conf" "$link"

  if ! nginx -t >/dev/null 2>&1; then
    nginx -t || true
    rm -f "$link"; [[ -n "$link" ]] || rm -f "$conf"
    die "Nginx 配置检查失败，已撤销 iot-platform.conf；可用 --no-nginx 直接暴露端口"
  fi
  systemctl reload nginx 2>/dev/null || nginx -s reload
  ok "Nginx 已监听 $PUBLIC_PORT → 127.0.0.1:$APP_PORT（配置：$conf）"
}

open_firewall() {
  if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$PUBLIC_PORT/tcp" >/dev/null && ok "ufw 已放行 $PUBLIC_PORT/tcp"
  fi
}

# ---------------------------------------------------------------- 6. 自检与输出
self_check() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PUBLIC_PORT/login" -H "Host: ${DOMAIN:-localhost}" || true)"
  [[ "$code" == 200 ]] && ok "页面自检通过（/login → 200）" || warn "页面自检返回 $code，请检查 Nginx / 容器日志"
}

summary() {
  local url="$PUBLIC_URL"
  echo
  echo -e "${c_green}================ 部署完成 ================${c_off}"
  echo "  管理端     $url/"
  echo "  管理员     admin / $ADMIN_PASSWORD   （首次创建时生效，记录在 .env 的 IOT_ADMIN_PASSWORD）"
  echo "  REST API   $url/api/        Django Admin  $url/admin/"
  echo "  设备接入   ${url/http/ws}/ws/device/<设备编号>/?ts=…&nonce=…&sign=…   （见管理端「帮助 → 设备接入指南」）"
  local m_mode m_ep m_bucket m_user m_console
  IFS='|' read -r m_mode m_ep m_bucket m_user m_console <<<"${MINIO_SUMMARY:-none||||}"
  case "$m_mode" in
    builtin)  echo "  版本文件   MinIO（内置容器）存储桶 $m_bucket，账号 $m_user（密码见 .env 的 IOT_MINIO_SECRET_KEY）"
              echo "             MinIO 控制台 http://127.0.0.1:$m_console （仅本机；远程用 ssh -L $m_console:127.0.0.1:$m_console 访问）" ;;
    external) echo "  版本文件   MinIO $m_ep 存储桶 $m_bucket" ;;
    *)        echo "  版本文件   容器数据卷（本地磁盘）" ;;
  esac
  echo "  目录       $PROJECT_DIR   （.env 保存密钥，请妥善保管）"
  echo
  echo "  常用命令（在 $PROJECT_DIR 下）："
  echo "    docker compose ps                 查看状态"
  echo "    docker compose logs -f web        查看日志"
  echo "    docker compose restart web        重启"
  echo "    sudo bash deploy/deploy.sh        更新代码后重新部署（保留数据与密钥）"
  echo "    docker compose exec db pg_dump -U iot iot > backup.sql   备份数据库"
  if [[ "$INIT_DEMO" == 1 ]]; then
    echo
    echo "  演示设备密钥：docker compose exec web cat /data/demo_devices.json"
    echo "  本机模拟设备：python3 simulator/device_sim.py --server $url --file demo_devices.json"
  fi
  echo -e "${c_green}==========================================${c_off}"
}

uninstall() {
  locate_source
  cd "$PROJECT_DIR"
  compose down --remove-orphans || true
  rm -f /etc/nginx/sites-enabled/iot-platform.conf /etc/nginx/sites-available/iot-platform.conf /etc/nginx/conf.d/iot-platform.conf
  command -v nginx >/dev/null && { nginx -t >/dev/null 2>&1 && systemctl reload nginx || true; }
  ok "已停止容器并移除 Nginx 配置；数据卷保留（彻底删除：docker compose down -v）"
}

main() {
  [[ $EUID -eq 0 ]] || die "请用 root 执行：sudo bash $0"
  . /etc/os-release 2>/dev/null || true
  info "系统：${PRETTY_NAME:-unknown}"
  [[ "${ID:-}" == ubuntu || "${ID_LIKE:-}" == *debian* ]] || warn "非 Ubuntu/Debian 系统，脚本未验证"
  if [[ "$UNINSTALL" == 1 ]]; then uninstall; exit 0; fi
  install_deps
  locate_source
  write_env
  build_and_up
  setup_nginx
  open_firewall
  self_check
  summary
}

# IOT_DEPLOY_SOURCE_ONLY=1 时只加载函数（便于测试）
[[ "${IOT_DEPLOY_SOURCE_ONLY:-0}" == 1 ]] || main
