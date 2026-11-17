#!/bin/sh
# 容器启动：等待数据库 → 迁移 → 收集静态资源 → 初始化管理员（及可选演示数据）→ 启动服务
set -e

if [ -n "$POSTGRES_DB" ]; then
  echo "[entrypoint] 等待 PostgreSQL ${POSTGRES_HOST:-127.0.0.1}:${POSTGRES_PORT:-5432} ..."
  python - <<'PY'
import os, time, psycopg
dsn = dict(dbname=os.environ["POSTGRES_DB"], user=os.getenv("POSTGRES_USER", "postgres"),
           password=os.getenv("POSTGRES_PASSWORD", ""), host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
           port=os.getenv("POSTGRES_PORT", "5432"))
for i in range(60):
    try:
        psycopg.connect(**dsn, connect_timeout=3).close()
        break
    except Exception as e:
        print("  数据库未就绪：", e.__class__.__name__); time.sleep(2)
else:
    raise SystemExit("数据库连接超时")
PY
fi

python manage.py migrate --noinput
# 版本文件存 MinIO 时：等待就绪、自动建桶，并把此前存在本地的升级包迁移过去
python manage.py storage_init --sync-local
python manage.py collectstatic --noinput -v0

python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
name, pwd = os.getenv("IOT_ADMIN_USER", "admin"), os.getenv("IOT_ADMIN_PASSWORD", "")
User = get_user_model()
u = User.objects.filter(username=name).first()
if u is None and pwd:
    u = User.objects.create_superuser(name, "", pwd)
    print(f"[entrypoint] 已创建管理员 {name}")
if u is not None:
    Token.objects.get_or_create(user=u)
PY

if [ "${IOT_INIT_DEMO:-0}" = "1" ]; then
  python manage.py init_demo --password "${IOT_ADMIN_PASSWORD:-admin123}" || true
fi

exec "$@"
