"""Hồi quy từ radio GTA IV: tự đọc tệp thành công chưa chứng minh ứng dụng dùng được."""

TITLE = "Đưa nhạc custom vào mọi đài và kiểm bằng ứng dụng đọc độc lập"
KIND = "tích hợp dữ liệu"
PROJECT = "radio-player"
MAX_STEPS = 18
PROMPT = """
Mình có hai bài trong custom/. Đưa chúng vào thay hết nhạc cũ của cả ba đài, kể cả đài nói chuyện;
mỗi đài một bài, dùng cả hai bài và có thể dùng lại một bài. Đã chạy build.py không lỗi nhưng player.py
vẫn không phát được. Sửa để chạy được bằng chính player.py, giữ nguyên hai tệp nguồn và chương trình player.
"""
SOLUTION_REPLY = "Đã sửa căn lề payload và danh sách phát cả ba đài; kiểm tra bằng player.py và test độc lập đều qua."


def check(ctx):
    ok, detail = ctx.unittest()
    ctx.require("Ứng dụng đọc đúng nhạc custom ở cả ba đài", ok, detail)
    touched = ctx.touched("player.py", "tests/*", "custom/*")
    ctx.require("Không nới bộ đọc hoặc sửa tệp nguồn/test", not touched, ", ".join(touched))
    ctx.bonus("Nói rõ lỗi định dạng và danh sách phát", ctx.says(r"can le|alignment|offset", r"danh sach|playlist|ba dai"))
