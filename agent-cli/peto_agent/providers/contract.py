"""Hợp đồng chung cho mọi nguồn model của Peto Agent (lộ trình nhiều nguồn, mốc M1–M2).

Mỗi lượt gọi model, dù là làm việc, tóm tắt, đặt tên, /btw, tóm tắt cuối hay agent con, đều thành một ``ModelRequest``
mang ``Selection`` đã chọn xong lúc tạo. Đổi model trên giao diện sau đó không làm lượt đang chạy đổi nguồn giữa chừng.
Selection chỉ chứa tham chiếu không bí mật: mã nguồn, mã kết nối, model và mức suy nghĩ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..client import ApiError

# Các lượt gọi model của CLI. "work" là bước làm việc thường; máy chủ Peto không nhận trường purpose cho nó.
PURPOSES = frozenset({"work", "compact", "title", "btw", "wrapup", "explore"})
# Nguồn Peto: lượt gọi đi qua máy chủ Peto, model là khóa của máy chủ (peto, luna, sol…).
PETO = "peto"
_SOURCE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_CONNECTION = re.compile(r"[A-Za-z0-9_-]{1,64}")


class ModelSourceError(ApiError):
    """Selection trỏ tới một nguồn chưa được đăng ký trong cổng yêu cầu. Không phải lỗi mạng: không tự thử lại."""

    def __init__(self, message: str):
        super().__init__(400, message)


def valid_source(value) -> bool:
    return isinstance(value, str) and bool(_SOURCE.fullmatch(value))


def valid_connection(value) -> bool:
    return value is None or (isinstance(value, str) and bool(_CONNECTION.fullmatch(value)))


@dataclass(frozen=True)
class Selection:
    """Nguồn model của một lượt gọi: chọn một lần, không đổi trong suốt lượt đó (kể cả các lần tự thử lại)."""

    source: str
    model: str
    effort: str
    connection: str | None = None

    def __post_init__(self):
        if not valid_source(self.source) or not valid_connection(self.connection):
            raise ValueError("Mã nguồn hoặc mã kết nối model không hợp lệ.")
        if not isinstance(self.model, str) or not self.model:
            raise ValueError("Chưa chọn model.")

    @property
    def budget_key(self) -> str:
        """Khóa của model trong danh mục ngân sách ngữ cảnh. Nguồn Peto giữ đúng khóa máy chủ như trước; nguồn khác
        thêm nguồn và kết nối, để cùng tên model ở hai nguồn không dùng chung số đo."""
        if self.source == PETO and self.connection is None:
            return self.model
        return f"{self.source}:{self.connection or ''}:{self.model}"

    def opaque_scope(self, identity: str | None = None) -> tuple[str, str, str]:
        """Phạm vi dùng lại được phần mờ (suy nghĩ mã hóa, chữ ký, lượt tìm web, mã item) của một model: cùng nguồn,
        cùng kết nối (tài khoản) và cùng model thực. ``identity`` là mã model thực khi danh mục biết."""
        return self.source, self.connection or "", identity or self.model

    def reference(self) -> dict:
        """Tham chiếu để ghi nhật ký: không chứa bí mật."""
        return {"source": self.source, "model": self.model, "effort": self.effort,
                **({"connection": self.connection} if self.connection else {})}


@dataclass(frozen=True)
class ModelRequest:
    purpose: str
    selection: Selection
    body: dict = field(repr=False)

    def __post_init__(self):
        if self.purpose not in PURPOSES:
            raise ValueError(f"Lượt gọi model không hợp lệ: {self.purpose}")
        if self.body.get("model") != self.selection.model or self.body.get("effort") != self.selection.effort:
            raise ValueError("Nội dung lượt gọi không khớp model hoặc mức suy nghĩ đã chọn.")
        declared = (self.body.get("context") or {}).get("purpose")
        if declared != (None if self.purpose == "work" else self.purpose):
            raise ValueError("Nội dung lượt gọi không khớp mục đích đã chọn.")
