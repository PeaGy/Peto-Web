"""Bản phát hành mới nhất của ứng dụng Peto Agent, cho trang tải /download/ (từ 5/11/2026).

Bộ cài nằm ở GitHub Releases của repo công khai ``DESKTOP_RELEASES_REPO``. Máy chủ đọc danh sách phát hành qua API công
khai của GitHub (không token, giới hạn 60 lượt mỗi giờ cho một địa chỉ IP) và nhớ kết quả 10 phút, lỗi thì 2 phút, nên
mỗi lượt xem trang không gọi GitHub. Chỉ nhận link tải trỏ về đúng repo đó trên github.com. Lỗi gì cũng chỉ làm trang
báo chưa có bản phát hành; trang vẫn còn hướng dẫn CLI.

Bản được chọn là bản mới nhất (không tính bản nháp) có ít nhất một bộ cài .exe, .msi hay .dmg, kể cả bản đánh dấu
pre-release, vì ứng dụng còn là bản xem trước.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core import config

logger = logging.getLogger("peto_web")

router = APIRouter(prefix="/api/agent/desktop")

API_URL = "https://api.github.com/repos/{repo}/releases"
PER_PAGE = 10
TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 2_000_000
FOUND_SECONDS = 600
MISSING_SECONDS = 120
MAX_INSTALLERS = 8
MAX_ASSET_BYTES = 4 * 1024 ** 3
VERSION = re.compile(r"v?([0-9][0-9A-Za-z.+-]{0,63})\Z")
DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")
NAME = re.compile(r"[^\x00-\x1f\x7f/\\]{1,200}\Z")

# Tests thay bằng httpx.MockTransport; chạy thật thì None (mạng thật).
_TRANSPORT: httpx.AsyncBaseTransport | None = None
_cache: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()


def _platform(name: str) -> tuple[str, str] | None:
    """Hệ điều hành và kiến trúc của một tệp bộ cài, đoán từ đuôi và tên tệp. Tệp không phải bộ cài trả None."""
    lower = name.lower()
    if lower.endswith((".exe", ".msi")):
        system = "windows"
    elif lower.endswith(".dmg"):
        system = "macos"
    else:
        return None
    tokens = set(re.split(r"[^a-z0-9_]+", lower))
    if tokens & {"arm64", "aarch64"}:
        arch = "arm64"
    elif "universal" in tokens:
        arch = "universal"
    elif tokens & {"x64", "amd64", "x86_64"}:
        arch = "x64"
    else:
        arch = ""
    return system, arch


def _installer(asset: object, repo: str) -> dict | None:
    if not isinstance(asset, dict) or asset.get("state", "uploaded") != "uploaded":
        return None
    name, url, size = asset.get("name"), asset.get("browser_download_url"), asset.get("size")
    if not isinstance(name, str) or not NAME.match(name):
        return None
    platform = _platform(name)
    if platform is None or not isinstance(url, str) or not url.startswith(f"https://github.com/{repo}/releases/download/"):
        return None
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_ASSET_BYTES:
        return None
    digest = asset.get("digest")
    match = DIGEST.match(digest) if isinstance(digest, str) else None
    return {"os": platform[0], "arch": platform[1], "name": name, "url": url, "size": size,
            "sha256": match.group(1) if match else None}


def _release(item: object, repo: str) -> dict | None:
    """Một bản phát hành dùng được cho trang tải, hoặc None (bản nháp, thiếu bộ cài, dữ liệu lạ)."""
    if not isinstance(item, dict) or item.get("draft"):
        return None
    tag = item.get("tag_name")
    version = VERSION.match(tag) if isinstance(tag, str) else None
    if not version:
        return None
    assets = item.get("assets") if isinstance(item.get("assets"), list) else []
    installers = [found for found in (_installer(asset, repo) for asset in assets) if found][:MAX_INSTALLERS]
    if not installers:
        return None
    published = item.get("published_at")
    try:
        datetime.fromisoformat(published)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        published = None
    notes = item.get("html_url")
    if not isinstance(notes, str) or not notes.startswith(f"https://github.com/{repo}/releases/"):
        notes = f"https://github.com/{repo}/releases"
    return {"available": True, "version": version.group(1), "published_at": published,
            "prerelease": bool(item.get("prerelease")), "notes_url": notes,
            "releases_url": f"https://github.com/{repo}/releases", "installers": installers}


async def _fetch(repo: str) -> dict | None:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "peto-web"}
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False, transport=_TRANSPORT) as client:
        async with client.stream("GET", API_URL.format(repo=repo), params={"per_page": PER_PAGE},
                                 headers=headers) as response:
            if response.status_code != 200:
                logger.warning("GitHub Releases trả HTTP %s cho trang tải Peto Agent", response.status_code)
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("phản hồi quá lớn")
    data = json.loads(bytes(body))
    if not isinstance(data, list):
        return None
    return next((found for found in (_release(item, repo) for item in data) if found), None)


def peek() -> dict | None:
    """Kết quả đã nhớ và còn hạn, không gọi GitHub (cho chữ <noscript> của trang tải)."""
    cached = _cache.get(config.DESKTOP_RELEASES_REPO)
    return cached[1] if cached and cached[0] > time.monotonic() else None


async def latest() -> dict:
    """Bản phát hành mới nhất có bộ cài, hoặc {"available": False}. Không bao giờ raise."""
    repo = config.DESKTOP_RELEASES_REPO
    if not repo:
        return {"available": False, "releases_url": None}
    missing = {"available": False, "releases_url": f"https://github.com/{repo}/releases"}
    async with _lock:
        cached = _cache.get(repo)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            result = await _fetch(repo)
        except (httpx.HTTPError, ValueError) as err:
            logger.warning("Không đọc được GitHub Releases cho trang tải Peto Agent: %s", type(err).__name__)
            result = None
        value = result or missing
        _cache.clear()
        _cache[repo] = (time.monotonic() + (FOUND_SECONDS if result else MISSING_SECONDS), value)
        return value


@router.get("/release")
async def release() -> JSONResponse:
    """Công khai, không cần đăng nhập: trang /download/ đọc khi mở."""
    return JSONResponse(await latest(), headers={"Cache-Control": "public, max-age=60"})
