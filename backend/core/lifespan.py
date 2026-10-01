"""Khởi động database, kiểm tra cấu hình và ghi trạng thái dịch vụ."""

from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from features.accounts import auth
import storage as db
from ai import get_provider
from shared.time_tools import resolve_timezone
from core.config import MEMORY_GATEWAY_TOKEN, MEMORY_GATEWAY_URL
from features.accounts.discord_memory import discord_memory
from core.operational_logging import configure_operational_logging
import logging

logger = logging.getLogger("peto_web")

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_operational_logging()
    resolve_timezone()  # Báo lỗi cấu hình sớm nếu thiếu dữ liệu múi giờ.
    await db.init_db()
    logger.info("Peto Web sẵn sàng — provider=%s", get_provider().name)
    mo = [name for name, ready in auth.available_providers().items() if ready]
    logger.info("Cách đăng nhập đang bật: %s", ", ".join(mo))
    # Không còn allowlist: nói thẳng ở log để người vận hành không tưởng nhầm
    # đây vẫn là bản riêng tư.
    logger.warning(
        "Đăng ký mở: bất kỳ ai mở được địa chỉ này đều dùng được và đều "
        "tiêu quota AI của máy chủ."
    )

    # Cấu hình nửa vời rất dễ xảy ra và trước đây im lặng hoàn toàn: đặt URL mà
    # quên token thì trí nhớ tắt lặng lẽ, người dùng chỉ thấy "Peto không nhớ gì".
    if discord_memory.enabled:
        logger.info("Trí nhớ từ Discord: BẬT (%s)", discord_memory.base_url)
    elif MEMORY_GATEWAY_URL or MEMORY_GATEWAY_TOKEN:
        missing = "PETO_MEMORY_GATEWAY_TOKEN" if not MEMORY_GATEWAY_TOKEN else "PETO_MEMORY_GATEWAY_URL"
        logger.warning(
            "Trí nhớ từ Discord: TẮT vì thiếu %s. Peto sẽ không nhớ gì từ bot.",
            missing,
        )
    else:
        logger.info("Trí nhớ từ Discord: tắt (chưa cấu hình).")
    yield

