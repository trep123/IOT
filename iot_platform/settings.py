"""IoT 设备管理平台 Django 配置。敏感项与部署项均可通过环境变量覆盖。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("IOT_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")
# 部署在反向代理（Nginx）之后：信任代理传入的协议与主机头；Admin 登录需要可信来源
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]
USE_X_FORWARDED_HOST = os.getenv("DJANGO_USE_X_FORWARDED_HOST", "1") == "1"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "channels",
    "core",
    "audit",
    "devices",
    "control",
    "firmware",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "iot_platform.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "iot_platform.wsgi.application"
ASGI_APPLICATION = "iot_platform.asgi.application"

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "ATOMIC_REQUESTS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("IOT_SQLITE_PATH", str(DATA_DIR / "iot.sqlite3")),
            "ATOMIC_REQUESTS": True,
            # IMMEDIATE 事务 + WAL：心跳、调度线程与 API 并发写入时避免 "database is locked"
            "OPTIONS": {
                "timeout": 30,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            },
        }
    }

# 设备通信通道：单进程用内存层；多进程/多节点部署设置 REDIS_URL 使用 channels_redis
if os.getenv("REDIS_URL"):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [os.getenv("REDIS_URL")]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# 管理端前端（frontend/，Vue 3 + Vite）构建产物，资源统一走 /static/
FRONTEND_DIST = Path(os.getenv("IOT_FRONTEND_DIST", BASE_DIR / "frontend" / "dist"))
STATICFILES_DIRS = [d for d in [BASE_DIR / "static", FRONTEND_DIST] if d.exists()]
STATIC_ROOT = DATA_DIR / "staticfiles"
MEDIA_ROOT = DATA_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
}

# 平台业务参数
IOT = {
    # 心跳周期（秒）与丢失次数 N：超过 周期×N 未收到心跳判定离线
    "HEARTBEAT_INTERVAL": int(os.getenv("IOT_HEARTBEAT_INTERVAL", "30")),
    "HEARTBEAT_MISS_COUNT": int(os.getenv("IOT_HEARTBEAT_MISS", "3")),
    # 后台调度扫描间隔（秒）；ASGI 进程内嵌调度器开关
    "SCAN_INTERVAL": float(os.getenv("IOT_SCAN_INTERVAL", "5")),
    "EMBEDDED_SCHEDULER": os.getenv("IOT_EMBEDDED_SCHEDULER", "1") == "1",
    # 离线排队指令最长保留时间（秒）
    "QUEUE_TTL": int(os.getenv("IOT_QUEUE_TTL", "86400")),
    # 升级单阶段最长停留（秒）
    "UPGRADE_STAGE_TIMEOUT": int(os.getenv("IOT_UPGRADE_STAGE_TIMEOUT", "1800")),
    # 升级包签名密钥（HMAC-SHA256）
    "PACKAGE_SIGN_KEY": os.getenv("IOT_SIGN_KEY", "change-me-in-production"),
    "DEFAULT_BATCH_CONCURRENCY": int(os.getenv("IOT_BATCH_CONCURRENCY", "20")),
    # 下发给设备的升级包下载地址前缀
    "PUBLIC_BASE_URL": os.getenv("IOT_PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
}
