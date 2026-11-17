import csv

from django.http import HttpResponse


def operator_of(request) -> str:
    user = getattr(request, "user", None)
    return user.get_username() if user and user.is_authenticated else "system"


def csv_response(filename: str, headers: list[str], rows) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")  # 让 Excel 正确识别 UTF-8
    writer = csv.writer(resp)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    return resp
