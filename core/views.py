from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def spa_index(request):
    """返回管理端前端（frontend/dist/index.html）；未构建时给出构建提示。"""
    index = settings.FRONTEND_DIST / "index.html"
    if index.exists():
        resp = HttpResponse(index.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")
        resp["Cache-Control"] = "no-cache"
        return resp
    return render(request, "frontend_missing.html", status=503)
