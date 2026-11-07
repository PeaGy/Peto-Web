"""Nguồn cập nhật tự động của ứng dụng Peto Agent cho Windows (từ 7/11/2026).

Bản Peto Agent không ký số nên ghi máy chủ "cập nhật bắt buộc" của nó, tức Peto Web, làm nơi hỏi bản mới:
``<origin>/api/agent/desktop/update/win-x64/<kênh>.yml`` (peto-harness ``apps/desktop/scripts/peto-update-feed.mjs``).
Ứng dụng (electron-updater) đọc tệp YAML đó, so phiên bản, rồi tải bộ cài theo link trong tệp và đối chiếu SHA-512.

Mỗi bản phát hành trên GitHub có ``stable.yml`` (do ``peto-release-assets.ts`` viết) cạnh bộ cài
``Peto-Agent-Setup-<bản>-x64.exe`` và tệp ``.blockmap``. Máy chủ chọn bản mới nhất (bỏ bản nháp, tính cả pre-release) có
``stable.yml`` dùng được: đọc tệp (tối đa 64 KB, chỉ theo chuyển hướng sang máy tải của GitHub), kiểm phiên bản khớp thẻ,
bộ cài có thật trong bản phát hành với đúng kích thước, rồi viết lại tệp chỉ với các trường cần thiết và link tải tuyệt
đối trên github.com. Bộ cài không đi qua máy chủ; ứng dụng tự lấy ``<bộ cài>.blockmap`` cạnh nó để tải phần thay đổi.

Ứng dụng hỏi khoảng 10 phút một lần; kết quả nhớ 10 phút (không có thì 2 phút) như trang /download/. Kênh ``nightly``
(Development trong Cài đặt) nhận cùng tệp. ``PETO_DESKTOP_UPDATES=false`` tắt hẳn: trả 404 và ứng dụng chỉ coi như lần
kiểm tra lỗi. Muốn ngừng phát một bản hỏng thì chuyển bản đó về nháp trên GitHub (hoặc xóa ``stable.yml`` của nó): tối
đa 10 phút sau máy chủ quay về bản trước. Máy đã lên bản hỏng thì vẫn ở đó, vì ứng dụng không bao giờ hạ phiên bản.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from core import config
from features.agent import desktop_release

logger = logging.getLogger("peto_web")

router = APIRouter(prefix="/api/agent/desktop")

TARGETS = {"win-x64"}
CHANNELS = {"stable.yml", "nightly.yml"}
METADATA_NAME = "stable.yml"
MAX_METADATA_BYTES = 64 * 1024
MAX_REDIRECTS = 3
MAX_CANDIDATES = 3
DOWNLOAD_HOSTS = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
SHA512 = re.compile(r"[A-Za-z0-9+/]{86}==\Z")
FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.exe\Z")

_cache: dict[str, tuple[float, str | None]] = {}
_lock = asyncio.Lock()


def _assets(item: dict, repo: str) -> dict[str, dict]:
    """Tệp đã tải lên xong của một bản phát hành, theo tên; chỉ nhận link tải trong đúng repo trên github.com."""
    found = {}
    for asset in item.get("assets") if isinstance(item.get("assets"), list) else []:
        if not isinstance(asset, dict) or asset.get("state", "uploaded") != "uploaded":
            continue
        name, url, size = asset.get("name"), asset.get("browser_download_url"), asset.get("size")
        if (isinstance(name, str) and isinstance(url, str)
                and url.startswith(f"https://github.com/{repo}/releases/download/")
                and isinstance(size, int) and not isinstance(size, bool) and size > 0):
            found[name] = {"url": url, "size": size}
    return found


async def _download(url: str) -> bytes:
    """Tải một tệp nhỏ của bản phát hành. Chuyển hướng chỉ sang máy tải của GitHub; quá lớn hay lạ thì raise."""
    async with httpx.AsyncClient(timeout=desktop_release.TIMEOUT_SECONDS, follow_redirects=False,
                                 transport=desktop_release._TRANSPORT) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parsed = httpx.URL(url)
            if parsed.scheme != "https" or parsed.host not in DOWNLOAD_HOSTS:
                raise ValueError("chuyển hướng ra ngoài GitHub")
            async with client.stream("GET", url, headers={"User-Agent": "peto-web"}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = str(parsed.join(response.headers.get("location", "")))
                    continue
                if response.status_code != 200:
                    raise ValueError(f"HTTP {response.status_code}")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_METADATA_BYTES:
                        raise ValueError("tệp quá lớn")
                return bytes(body)
    raise ValueError("quá nhiều chuyển hướng")


def _feed(raw: bytes, version: str, assets: dict[str, dict], published: object) -> str:
    """Viết lại stable.yml của một bản phát hành thành tệp cho ứng dụng; dữ liệu không khớp thì raise ValueError."""
    metadata = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(metadata, dict) or str(metadata.get("version")) != version:
        raise ValueError("phiên bản không khớp thẻ")
    files = metadata.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise ValueError("cần đúng một tệp")
    name, sha512, size = files[0].get("url"), files[0].get("sha512"), files[0].get("size")
    if not isinstance(name, str) or not FILENAME.match(name) or name not in assets:
        raise ValueError("bộ cài không có trong bản phát hành")
    if not isinstance(sha512, str) or not SHA512.match(sha512) or metadata.get("sha512", sha512) != sha512:
        raise ValueError("SHA-512 lạ")
    if not isinstance(size, int) or isinstance(size, bool) or size != assets[name]["size"]:
        raise ValueError("kích thước không khớp bộ cài")
    url = assets[name]["url"]
    date = published if isinstance(published, str) else metadata.get("releaseDate")
    try:
        datetime.fromisoformat(str(date))
    except ValueError:
        date = None
    feed = {"version": version, "files": [{"url": url, "sha512": sha512, "size": size}], "path": url, "sha512": sha512}
    if date is not None:
        feed["releaseDate"] = str(date)
    return yaml.safe_dump(feed, sort_keys=False, allow_unicode=False)


async def _fetch(repo: str) -> str | None:
    releases = await desktop_release.fetch_releases(repo)
    tried = 0
    for item in releases or []:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag = item.get("tag_name")
        version = desktop_release.VERSION.match(tag) if isinstance(tag, str) else None
        assets = _assets(item, repo)
        if not version or METADATA_NAME not in assets:
            continue
        if tried == MAX_CANDIDATES:
            break
        tried += 1
        try:
            return _feed(await _download(assets[METADATA_NAME]["url"]), version.group(1), assets,
                         item.get("published_at"))
        except (httpx.HTTPError, ValueError, UnicodeDecodeError, yaml.YAMLError) as err:
            logger.warning("Bỏ qua %s của bản %s khi dựng nguồn cập nhật Peto Agent: %s", METADATA_NAME, tag, err)
    return None


async def current_feed() -> str | None:
    """Tệp YAML của bản mới nhất cho ứng dụng, hoặc None (tắt, chưa có bản nào, GitHub lỗi). Không bao giờ raise."""
    repo = config.DESKTOP_RELEASES_REPO
    if not config.DESKTOP_UPDATES or not repo:
        return None
    async with _lock:
        cached = _cache.get(repo)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            feed = await _fetch(repo)
        except (httpx.HTTPError, ValueError) as err:
            logger.warning("Không đọc được GitHub Releases cho nguồn cập nhật Peto Agent: %s", type(err).__name__)
            feed = None
        _cache.clear()
        _cache[repo] = (time.monotonic() + (desktop_release.FOUND_SECONDS if feed else desktop_release.MISSING_SECONDS),
                        feed)
        return feed


@router.get("/update/{target}/{channel}")
async def update_feed(target: str, channel: str) -> Response:
    """Công khai, không cần đăng nhập: ứng dụng Peto Agent hỏi định kỳ."""
    feed = await current_feed() if target in TARGETS and channel in CHANNELS else None
    if feed is None:
        raise HTTPException(404, "Chưa có bản cập nhật Peto Agent nào.")
    return Response(feed, media_type="text/yaml; charset=utf-8", headers={"Cache-Control": "public, max-age=60"})
