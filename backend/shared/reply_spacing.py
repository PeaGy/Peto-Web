"""Khoảng trắng quanh những đoạn bị gỡ khỏi câu trả lời Companion (ghi chú riêng, thẻ cảm xúc).

Bong bóng Companion giữ nguyên dấu xuống dòng, nên khoảng trắng thừa hiện thành dòng trống. Trước đây bộ lọc stream chỉ
gộp dấu cách: câu mở đầu bằng ghi chú rồi xuống dòng ("<private>…</private>\\n\\nOkay") làm bong bóng trống mất hai dòng
đầu, dù tải lại trang thì hết (chủ web gặp ngày 2026-09-28). Luật chung cho stream lẫn lịch sử: đầu và cuối câu không có
khoảng trắng; hai bên chỗ gỡ giữa câu gộp làm một, giữ xuống dòng nếu có (lấy bên nhiều dòng hơn), không thì một dấu
cách. Khoảng trắng không dính chỗ gỡ nào thì giữ y như model viết.
"""

from __future__ import annotations


class Spacing:
    """Nhận lần lượt chữ thấy được và chỗ gỡ, phát chữ ra ngay nhưng giữ khoảng trắng cuối lại cho tới khi biết sau nó
    là chữ, chỗ gỡ hay hết câu. Chữ cắt ở đâu giữa các mảnh stream thì kết quả ghép lại vẫn như nhau."""

    def __init__(self) -> None:
        self._started = False
        # Khoảng trắng đang giữ, tách thêm một phần ở mỗi chỗ gỡ.
        self._gaps = [""]

    def cut(self) -> None:
        """Vừa gỡ một đoạn khỏi câu."""
        self._gaps.append("")

    def text(self, piece: str) -> str:
        """Chữ thấy được; trả phần phát ra được ngay. Hết câu thì bỏ khoảng trắng còn giữ, không cần gọi gì thêm."""
        body = piece.lstrip()
        self._gaps[-1] += piece[:len(piece) - len(body)]
        if not body:
            return ""
        core = body.rstrip()
        gap = self._gap() if self._started else ""
        self._started = True
        self._gaps = [body[len(core):]]
        return gap + core

    def _gap(self) -> str:
        if len(self._gaps) == 1:
            return self._gaps[0]
        lines = max(gap.count("\n") for gap in self._gaps)
        if lines:
            return "\n" * lines
        return " " if any(self._gaps) else ""
