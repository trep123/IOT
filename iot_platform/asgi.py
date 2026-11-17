import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iot_platform.settings")
django_asgi_app = get_asgi_application()

if os.getenv("IOT_SERVE_STATIC", "1") == "1":
    # 单机部署直接由 ASGI 进程提供管理端静态资源；生产可交给 Nginx（collectstatic 后关闭此开关）
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.conf import settings  # noqa: E402

from iot_platform.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)

if settings.IOT["EMBEDDED_SCHEDULER"]:
    from core.scheduler import start_background_scheduler  # noqa: E402

    start_background_scheduler()
