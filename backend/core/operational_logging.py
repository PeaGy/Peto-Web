"""Bật log vận hành trong tiến trình uvicorn mà không ghi thêm nội dung người dùng."""
import logging


def configure_operational_logging():
    logger = logging.getLogger("peto_web")
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "peto_operational", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.peto_operational = True
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
