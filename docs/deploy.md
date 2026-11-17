# 部署（Docker 一键部署）

适用于 Ubuntu Server 22.04 / 24.04 / 26.04（其他 Debian 系未验证）。

## 一键部署

```bash
# 方式一：在服务器上克隆仓库后执行
git clone https://github.com/trep123/IOT.git /opt/iot && cd /opt/iot
sudo bash deploy/deploy.sh

# 方式二：直接执行（代码会克隆到 /opt/iot）
curl -fsSL https://raw.githubusercontent.com/trep123/IOT/main/deploy/deploy.sh | sudo bash

# 国内网络：pip / npm 走国内源，基础镜像走镜像站
sudo bash deploy/deploy.sh --cn --image-mirror docker.m.daocloud.io/library/
```

脚本依次完成：安装 Docker 与 Compose 插件（已安装则跳过）→ 获取代码 → 生成 `.env`（随机密钥、数据库密码、管理员密码）
→ 构建镜像（Node 编译前端 + Python 后端）→ 启动 `web` 与 `db` 容器并等待健康检查
→ 配置宿主机 Nginx 反向代理（含 WebSocket）→ ufw 放行端口 → 自检并打印访问地址与管理员密码。

重复执行即为升级：会拉取最新代码、重建镜像，沿用 `.env` 中的端口、密钥与数据。

## 端口规划

| 组件 | 默认 | 说明 |
|---|---|---|
| Nginx（宿主机） | **8090** | 对外访问端口；被占用时自动顺延（8091、8092…），`--port` 指定 |
| web 容器 | 127.0.0.1:**18000** | 只监听本机，由 Nginx 转发；`--app-port` 指定 |
| PostgreSQL 容器 | 不映射 | 只在 Docker 内部网络可见，不与宿主机已有的 5432 冲突 |

已占用 80、8000、8080、5000、5432 等端口的服务器可直接使用默认值。使用域名时（`--domain iot.example.com`），
Nginx 在已有的 80 端口上按 `server_name` 转发，不新增端口。没有 Nginx 或不想改动 Nginx 时用 `--no-nginx`，
容器直接监听 `0.0.0.0:<port>`。

## 参数

| 参数 | 说明 |
|---|---|
| `--port N` | 对外端口 |
| `--app-port N` | 容器映射到本机的端口 |
| `--domain D` | 使用域名（80 端口，按域名转发） |
| `--no-nginx` | 不配置 Nginx |
| `--cn` | pip 使用清华源，npm 使用 npmmirror |
| `--image-mirror P` | 基础镜像前缀（node / python / postgres），如 `docker.m.daocloud.io/library/` |
| `--demo` | 写入演示数据（10 台设备、指令模板、1.0.0 与 1.1.0 两个版本） |
| `--public-url URL` | 下发给设备的平台地址（升级包下载、文档展示），默认 `http://<本机IP>:<port>` |
| `--dir D` | `curl` 方式执行时的安装目录，默认 `/opt/iot` |
| `--branch B` | 拉取的分支，默认 `main` |
| `--uninstall` | 停止容器并移除 Nginx 配置（保留数据卷与 `.env`） |

## 运维

```bash
cd /opt/iot
docker compose ps                    # 状态
docker compose logs -f web           # 日志
docker compose restart web           # 重启
docker compose exec web python manage.py changepassword admin   # 修改管理员密码
docker compose exec db pg_dump -U iot iot > backup.sql          # 备份
cat backup.sql | docker compose exec -T db psql -U iot iot      # 恢复
```

- 配置全部在 `.env`，修改后 `docker compose up -d` 生效。
- 数据卷：`iot_db-data`（数据库）、`iot_iot-data`（升级包、演示设备密钥）。
- HTTPS：在 Nginx 配置（`/etc/nginx/sites-available/iot-platform.conf`）中加证书即可，后端已识别 `X-Forwarded-Proto`；同时把 `.env` 的 `IOT_PUBLIC_BASE_URL` 改为 `https://...`。
- 设备接入地址：`ws://<服务器>:<port>/ws/device/<设备编号>/?secret=<接入密钥>`（HTTPS 时为 `wss://`）。
