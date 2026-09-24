"""Hỏi về một dự án lớn thật: bản sao Peto-Web (chỉ mã đã commit, lấy bằng git archive; không .env, không dữ liệu).

Đo chi phí dò code trong kho vài trăm tệp: bao nhiêu lượt, bao nhiêu token để tới đúng chỗ.
"""

from harness import export_repo

TITLE = "Hỏi code trong dự án lớn (bản sao Peto-Web)"
KIND = "hỏi code"
PROJECT = "peto-web"
MAX_STEPS = 14
NEEDS = ("git",)
PROMPT = """
Trong dự án này, người đăng nhập bằng tài khoản Google có bị Peto đọc bộ nhớ Discord của ai không? Chỉ mình đoạn code
quyết định chuyện đó.
"""
SOLUTION_REPLY = """
Không. `discord_id_from_owner` trong `backend/config.py` chỉ trả Discord ID cho owner dạng `discord:<id>`; tài khoản
Google (`google:…`) nhận chuỗi rỗng, và `backend/main.py` bỏ qua cổng bộ nhớ khi chuỗi đó rỗng.
"""


def prepare(root):
    export_repo(root)


def check(ctx):
    ctx.require("Chỉ ra discord_id_from_owner", ctx.says(r"discord_id_from_owner"))
    ctx.require("Trả lời là không", ctx.says(r"\bkhong\b"))
    ctx.require("Không sửa tệp nào", not ctx.changed, ", ".join(ctx.changed[:5]))
    ctx.bonus("Chỉ ra cả nơi dùng (main.py) và nơi định nghĩa (config.py)", ctx.says(r"main\.py", r"config\.py"))
