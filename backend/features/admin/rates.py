"""Đọc tệp đơn giá do chủ web khai (PETO_COST_RATES_FILE); cùng định dạng và cách kiểm tra với `ops.report --rates`."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core import config
from ops.report import validate_rates

logger = logging.getLogger("peto_web")

_cache: dict = {"key": None, "rates": {}, "status": "missing"}


def load() -> tuple[dict, str]:
    """(đơn giá theo slug, trạng thái): "missing" khi chưa khai, "invalid" khi tệp hỏng, "ok" khi dùng được.

    Đọc lại khi đường dẫn, thời điểm sửa hoặc kích thước tệp đổi; tệp hỏng không làm hỏng trang, chỉ thành
    "Chưa có đơn giá" cho mọi model.
    """
    raw_path = config.COST_RATES_FILE
    if not raw_path:
        return {}, "missing"
    path = Path(raw_path)
    try:
        stat = path.stat()
    except OSError:
        return {}, "invalid"
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if _cache["key"] == key:
        return _cache["rates"], _cache["status"]
    try:
        rates, status = validate_rates(json.loads(path.read_text(encoding="utf-8"))), "ok"
    except (OSError, ValueError) as err:
        # Không ghi nội dung tệp vào log, chỉ loại lỗi.
        logger.warning("Tệp đơn giá không dùng được: %s", type(err).__name__)
        rates, status = {}, "invalid"
    _cache.update(key=key, rates=rates, status=status)
    return rates, status
