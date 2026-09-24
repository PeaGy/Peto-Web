"""Thêm tính năng vào một CLI Python nhỏ: lệnh mới, cờ mới, cập nhật README."""

TITLE = "Thêm lệnh done và cờ --chua-xong cho todo-cli"
KIND = "tính năng"
PROJECT = "todo-cli"
MAX_STEPS = 14
PROMPT = """
Thêm cho todo-cli lệnh `done <id>` để đánh dấu một việc đã xong (id không có thì báo lỗi và thoát mã 1), và cờ
`--chua-xong` cho lệnh `list` để chỉ hiện việc chưa xong. Nhớ cập nhật README nha.
"""
SOLUTION_REPLY = "Đã thêm lệnh done và cờ --chua-xong, cập nhật README và thêm test."


def check(ctx):
    ok, detail = ctx.unittest()
    ctx.require("Test ẩn qua", ok, detail)
    readme = ctx.read("README.md")
    ctx.require("README có lệnh done và cờ --chua-xong", ctx.says(r"\bdone\b", r"--chua-xong", text=readme))
    ok, detail = ctx.unittest(hidden=False)
    ctx.require("Test của dự án vẫn qua", ok, detail)
    ctx.bonus("Có thêm test cho phần mới", ctx.touched("tests/*"), ", ".join(ctx.touched("tests/*")))
