from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from rest_framework.authtoken.models import Token

from .realtime import ADMIN_GROUP


class AdminEventConsumer(JsonWebsocketConsumer):
    """管理端实时推送：ws/admin/?token=<API Token>。"""

    def connect(self):
        token = self._token()
        user = self.scope.get("user")
        ok = bool(user and user.is_authenticated)
        if not ok and token:
            ok = Token.objects.filter(key=token).exists()
        if not ok:
            self.close(code=4401)
            return
        async_to_sync(self.channel_layer.group_add)(ADMIN_GROUP, self.channel_name)
        self.accept()

    def _token(self):
        from urllib.parse import parse_qs

        qs = parse_qs(self.scope.get("query_string", b"").decode())
        return (qs.get("token") or [None])[0]

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(ADMIN_GROUP, self.channel_name)

    def admin_event(self, event):
        self.send_json({"event": event["event"], "data": event["data"]})
