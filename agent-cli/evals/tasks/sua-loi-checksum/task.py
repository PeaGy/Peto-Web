"""Sửa lỗi nhỏ trong tool Python đọc file save (giống sas4-save-editor): checksum bỏ sót byte cuối."""

TITLE = "Sửa checksum trong tool đọc file save"
KIND = "sửa lỗi"
PROJECT = "save-tool"
MAX_STEPS = 12
PROMPT = """
Chạy test của save-tool thấy đỏ ở phần checksum, file save thật của game cũng bị báo sai checksum. Sửa giúp mình nha.
"""
SOLUTION_REPLY = "Hàm checksum bỏ sót byte cuối (data[:-1]); đã sửa để cộng mọi byte, test qua hết."


def check(ctx):
    ok, detail = ctx.unittest()
    ctx.require("Test ẩn qua", ok, detail)
    tests = ctx.touched("tests/*")
    ctx.require("Không sửa tệp test", not tests, ", ".join(tests))
    ctx.bonus("Chỉ sửa checksum.py", ctx.changed == ["savetool/checksum.py"], ", ".join(ctx.changed))
    ctx.bonus("Nói đúng nguyên nhân (bỏ sót byte cuối)", ctx.says(r"byte cuoi|\[:-1\]|cuoi cung"))
