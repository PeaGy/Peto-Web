"""Cách viết thời lượng và số token cho người đọc, dùng chung cho dòng tổng kết, /usage và báo cáo bài thi."""

from __future__ import annotations


def format_duration(seconds: float) -> str:
    minutes, rest = divmod(max(0, round(seconds)), 60)
    if not minutes:
        return f"{rest} giây"
    return f"{minutes} phút {rest} giây" if rest else f"{minutes} phút"


def format_tokens(count: int) -> str:
    """850, 1.2k, 18k, 1.3M."""
    if count < 1000:
        return str(count)
    if count < 9950:
        return f"{count / 1000:.1f}k".replace(".0k", "k")
    if count < 999_500:
        return f"{round(count / 1000)}k"
    return f"{count / 1_000_000:.1f}M".replace(".0M", "M")
