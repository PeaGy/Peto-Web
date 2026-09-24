"""Hỏi về code C (giống phần C của sas4-save-editor): phải đọc kỹ, vì main.c ghi đè thời gian chờ mặc định."""

TITLE = "Hỏi timeout và thử lại trong code C"
KIND = "hỏi code"
PROJECT = "sas-net"
MAX_STEPS = 12
PROMPT = """
Khi chạy `sas-net sync game.sav`, mỗi request HTTP chờ tối đa bao lâu thì bị coi là timeout? Nếu lỗi thì có thử lại
không, tối đa mấy lần, trường hợp nào thì không thử lại? Chỉ mình đúng chỗ trong code nha.
"""
SOLUTION_REPLY = """
Khi chạy `sas-net sync`, mỗi request chờ tối đa 15 giây: `src/main.c` đặt `options.timeout_ms = 15 * 1000` cho lệnh
sync, ghi đè mặc định 10 giây (`DEFAULT_TIMEOUT_MS 10000` trong `include/config.h`). Lỗi thì có thử lại: `http_post`
trong `src/http.c` thử lại tối đa 3 lần (`RETRY_LIMIT 3`, tổng 4 lần gửi), chờ 500, 1000 rồi 2000 ms giữa các lần.
`should_retry` chỉ thử lại khi lỗi mạng (status 0) hoặc lỗi 5xx; lỗi 4xx thì không thử lại.
"""


def check(ctx):
    ctx.require("Nói đúng 15 giây cho lệnh sync", ctx.says(r"\b15\s*(s|giay)\b|\b15[.,]?000\b|15\s*\*\s*1000"))
    ctx.require("Chỉ ra main.c (nơi đặt 15 giây)", ctx.says(r"main\.c"))
    ctx.require("Nói đúng số lần thử lại (3 lần, tổng 4 lần gửi)",
                ctx.near(r"\b3\b|\bba\b", r"thu lai|retry|retries|lan") or ctx.near(r"\b4\b|\bbon\b", r"tong|lan gui"))
    ctx.require("Nói lỗi 4xx thì không thử lại", ctx.near(r"4xx|\b4\d\d\b|phia client", r"khong", 120))
    ctx.require("Chỉ ra http.c (vòng thử lại)", ctx.says(r"http\.c"))
    ctx.require("Không sửa tệp nào", not ctx.changed, ", ".join(ctx.changed))
    ctx.bonus("Nói mặc định 10 giây trong config.h bị ghi đè",
              ctx.says(r"\b10\s*(s|giay)\b|\b10[.,]?000\b", r"config\.h"))
    ctx.bonus("Nói thời gian chờ giữa các lần thử lại", ctx.says(r"\b500\b"))
