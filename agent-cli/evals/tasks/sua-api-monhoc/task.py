"""Sửa API ASP.NET Core (giống bài tập MonHoc): GET môn không có trả 500 thay vì 404, POST tên trống vẫn thêm được."""

import json

TITLE = "Sửa API môn học C#: 404 và kiểm tra tên trống"
KIND = "sửa lỗi"
PROJECT = "MonHocApi"
MAX_STEPS = 20
NEEDS = ("dotnet",)
PROMPT = """
Gọi GET /api/monhoc/99 (môn không có) thì API trả lỗi 500, đáng lẽ phải là 404. Còn POST môn học có tên trống vẫn
thêm được, phải trả 400. Sửa giúp mình rồi chạy thử xem đúng chưa nha.
"""
SOLUTION_REPLY = "GetById dùng First nên ném lỗi khi không có môn; đổi sang FirstOrDefault và trả NotFound. Create kiểm tra tên trống và trả BadRequest."


def _json(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


def check(ctx):
    with ctx.dotnet_api() as (base, error):
        if not ctx.require("Build và chạy được", base, error):
            return
        status, _ = ctx.http("GET", f"{base}/api/monhoc/99")
        ctx.require("GET môn không có → 404", status == 404, f"nhận {status}")
        status, body = ctx.http("GET", f"{base}/api/monhoc/2")
        data = _json(body) or {}
        ctx.require("GET môn có → 200 đúng môn", status == 200 and data.get("ten") == "Cơ sở dữ liệu",
                    f"nhận {status} {body[:120]}")
        status, _ = ctx.http("POST", f"{base}/api/monhoc", {"ten": "", "soTinChi": 3})
        ctx.require("POST tên trống → 400", status == 400, f"nhận {status}")
        status, _ = ctx.http("POST", f"{base}/api/monhoc", {"ten": "   ", "soTinChi": 3})
        ctx.bonus("POST tên toàn dấu cách → 400", status == 400, f"nhận {status}")
        status, body = ctx.http("POST", f"{base}/api/monhoc", {"ten": "Mạng máy tính", "soTinChi": 3})
        created = _json(body) or {}
        ctx.require("POST hợp lệ → 201", status == 201 and created.get("ten") == "Mạng máy tính",
                    f"nhận {status} {body[:120]}")
        status, body = ctx.http("GET", f"{base}/api/monhoc")
        names = [item.get("ten") for item in _json(body) or [] if isinstance(item, dict)]
        ctx.require("Danh sách có môn vừa thêm, không có môn tên trống",
                    "Mạng máy tính" in names and not any(not (name or "").strip() for name in names), str(names))
