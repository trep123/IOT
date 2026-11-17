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

# 指定 MinIO 账号密码（版本文件存储；不指定则账号 admin、密码随机生成）
sudo bash deploy/deploy.sh --cn --minio-user admin --minio-password '<密码>' --minio-bucket iot
```

脚本依次完成：安装 Docker 与 Compose 插件（已安装则跳过）→ 获取代码 → 生成 `.env`（随机密钥、数据库密码、管理员密码）
→ 构建镜像（Node 编译前端 + Python 后端）→ 启动 `web`、`db`、`minio` 容器并等待健康检查
→ 配置宿主机 Nginx 反向代理（含 WebSocket）→ ufw 放行端口 → 自检并打印访问地址与管理员密码。

重复执行即为升级：会拉取最新代码、重建镜像，沿用 `.env` 中的端口、密钥与数据。

## 端口规划

| 组件 | 默认 | 说明 |
|---|---|---|
| Nginx（宿主机） | **8090** | 对外访问端口；被占用时自动顺延（8091、8092…），`--port` 指定 |
| web 容器 | 127.0.0.1:**18000** | 只监听本机，由 Nginx 转发；`--app-port` 指定 |
| PostgreSQL 容器 | 不映射 | 只在 Docker 内部网络可见，不与宿主机已有的 5432 冲突 |
| MinIO API | 不映射 | 平台在 Docker 内部通过 `http://minio:9000` 访问；设备经平台下载版本文件，无需直连 MinIO |
| MinIO 控制台 | 127.0.0.1:**19001** | 只监听本机；远程用 `ssh -L 19001:127.0.0.1:19001 <服务器>` 后浏览器打开 `http://127.0.0.1:19001`；`--minio-console-port` 指定 |

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
| `--minio-user U` | MinIO 账号，默认 `admin` |
| `--minio-password P` | MinIO 密码（至少 8 位）；不填沿用 `.env`，首次随机生成 |
| `--minio-bucket B` | 存储桶，默认 `iot`，不存在时平台启动时自动创建 |
| `--minio-endpoint URL` | 使用已有的外部 MinIO（如 `http://10.0.0.5:9000`），不再启动内置 MinIO |
| `--minio-console-port N` | 内置 MinIO 控制台端口，默认 19001 |
| `--no-minio` | 版本文件改存容器数据卷（本地磁盘） |

## 版本文件存储（MinIO）

- 默认随平台启动一个内置 MinIO 容器（`pgsty/minio`，MinIO 社区版构建；官方已停止发布 Docker 镜像，可在 `.env` 的 `IOT_MINIO_IMAGE` 换成其他兼容镜像）。
- 管理端「版本与升级包」上传的版本文件写入存储桶，对象键为 `packages/<版本号>/<时间>_<文件名>`；页面顶部显示存储类型、存储桶、文件数与连通状态，升级包列表显示每个文件的存储位置。
- 设备下载地址不变（`/api/upgrade-packages/<id>/download/`），平台从 MinIO 流式转发，设备不需要访问 MinIO。
- 从旧版本升级时，容器启动会执行 `python manage.py storage_init --sync-local`：自动建桶，并把原来存在本地数据卷中的升级包上传到 MinIO（已存在的跳过）。
- 相关变量（`.env`）：`IOT_MINIO_ENDPOINT`、`IOT_MINIO_ACCESS_KEY`、`IOT_MINIO_SECRET_KEY`、`IOT_MINIO_BUCKET`、`COMPOSE_PROFILES=minio`（启动内置 MinIO）。`IOT_MINIO_ENDPOINT` 为空时使用本地磁盘。

## 运维

```bash
cd /opt/iot
docker compose ps                    # 状态
docker compose logs -f web           # 日志
docker compose logs -f minio         # MinIO 日志
docker compose exec web python manage.py storage_init   # 检查对象存储连通性
docker compose restart web           # 重启
docker compose exec web python manage.py changepassword admin   # 修改管理员密码
docker compose exec db pg_dump -U iot iot > backup.sql          # 备份
cat backup.sql | docker compose exec -T db psql -U iot iot      # 恢复
```

- 配置全部在 `.env`，修改后 `docker compose up -d` 生效。
- 数据卷：`iot_db-data`（数据库）、`iot_minio-data`（MinIO 中的版本文件）、`iot_iot-data`（未启用 MinIO 时的版本文件、演示设备密钥）。
- 备份版本文件：`docker run --rm -v iot_minio-data:/d -v $PWD:/b alpine tar czf /b/minio.tgz -C /d .`
- HTTPS：在 Nginx 配置（`/etc/nginx/sites-available/iot-platform.conf`）中加证书即可，后端已识别 `X-Forwarded-Proto`；同时把 `.env` 的 `IOT_PUBLIC_BASE_URL` 改为 `https://...`。
- 设备接入地址：`ws://<服务器>:<port>/ws/device/<设备编号>/?ts=…&nonce=…&sign=…`（HTTPS 时为 `wss://`），签名方式与各语言示例见管理端「帮助 → 设备接入指南」。
