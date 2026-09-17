"""Bộ cài một dòng cho lệnh peto: ``irm https://<địa chỉ Peto>/install.ps1 | iex``.

- ``GET /install.ps1`` trả script PowerShell ``agent-cli/install.ps1`` đã điền địa chỉ Peto, đường dẫn tải gói và mã
  băm SHA-256 của gói. Đường dẫn này nằm ngoài ``/api`` nên phải đăng ký trước route bắt mọi đường dẫn của frontend.
- ``GET /api/agent/download/<tên gói>`` trả gói wheel của ``agent-cli``. Máy chủ tự đóng gói bằng ``zipfile`` từ
  ``pyproject.toml`` và mã nguồn, không cần setuptools, rồi kèm ``peto_agent/default_server.txt`` chứa địa chỉ Peto để
  ``peto login`` khỏi phải hỏi.

Cả hai route dựng lại gói mỗi lần gọi. Ngày giờ trong zip cố định nên cùng mã nguồn và địa chỉ luôn ra cùng một chuỗi
byte, và mã băm ghi trong script khớp gói tải về ngay sau đó. Địa chỉ lấy từ chính yêu cầu, vì ``PETO_FRONTEND_URL``
thường để trống; sau Cloudflare Tunnel, uvicorn chạy với ``--proxy-headers`` nên thấy đúng https và tên miền thật. Không
phải https thì không cài, trừ máy chủ chạy ngay trên máy này, giống quy tắc CLI dùng khi gửi token.

Ai mở được trang Peto đều tải được bộ cài; trong gói chỉ có mã nguồn CLI, không có bí mật.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
import tomllib
import zipfile
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from config import BASE_DIR

logger = logging.getLogger("peto_web.agent_install")
router = APIRouter(tags=["agent"])

CLI_DIR = BASE_DIR.parent / "agent-cli"
DOWNLOAD_PATH = "/api/agent/download"
DEFAULT_SERVER_FILE = "peto_agent/default_server.txt"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
NOT_READY = "Máy chủ Peto chưa sẵn sàng bộ cài peto. Thử lại sau nhé."
NOT_HTTPS = "Máy chủ Peto này không chạy HTTPS nên không cài peto qua mạng được. Dùng địa chỉ https:// của Peto."
NO_STORE = {"Cache-Control": "no-store"}
# Mọi tệp trong zip mang cùng ngày giờ và quyền, để cùng mã nguồn luôn ra cùng một gói.
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")
_SAFE_PART = re.compile(r"[A-Za-z0-9.]+")


@dataclass(frozen=True)
class Wheel:
    filename: str
    data: bytes
    sha256: str


def public_origin(request: Request) -> str | None:
    """``scheme://host[:port]`` mà người dùng đã gọi; ``None`` nếu không phải https hay máy chủ trên chính máy này."""
    try:
        host = (request.url.hostname or "").lower()
        port = request.url.port
    except ValueError:
        return None
    scheme = request.url.scheme
    if not (scheme == "https" or (scheme == "http" and host in LOOPBACK_HOSTS)):
        return None
    if host == "::1":
        netloc = "[::1]"
    elif _HOSTNAME.fullmatch(host):
        netloc = host
    else:
        return None
    return f"{scheme}://{netloc}:{port}" if port else f"{scheme}://{netloc}"


def cli_version() -> str:
    """Phiên bản ``peto`` máy chủ đang phát, để CLI cũ biết mà nhắc cập nhật; chuỗi rỗng khi không đọc được."""
    try:
        project = tomllib.loads((CLI_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        return str(project["project"]["version"])
    except (OSError, KeyError, TypeError, ValueError):
        return ""


def install_command(request: Request) -> str:
    """Lệnh cài một dòng cho đúng trang người dùng đang mở; chuỗi rỗng khi trang đó không cài qua mạng được."""
    server = public_origin(request)
    return f"irm {server}/install.ps1 | iex" if server else ""


def _record_hash(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def build_wheel(server: str) -> Wheel:
    """Đóng ``agent-cli`` thành wheel thuần Python, kèm địa chỉ Peto mặc định."""
    project = tomllib.loads((CLI_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    meta = project["project"]
    name = re.sub(r"[-_.]+", "_", str(meta["name"])).lower()
    version = str(meta["version"])
    if not _SAFE_PART.fullmatch(name.replace("_", "")) or not _SAFE_PART.fullmatch(version):
        raise ValueError("Tên hoặc phiên bản trong agent-cli/pyproject.toml không hợp lệ.")
    dist_info = f"{name}-{version}.dist-info"

    files: list[tuple[str, bytes]] = []
    for package in project["tool"]["setuptools"]["packages"]:
        for path in sorted((CLI_DIR / package).rglob("*.py")):
            if "__pycache__" not in path.parts:
                files.append((path.relative_to(CLI_DIR).as_posix(), path.read_bytes()))
    files.append((DEFAULT_SERVER_FILE, f"{server}\n".encode("utf-8")))

    metadata = ["Metadata-Version: 2.1", f"Name: {meta['name']}", f"Version: {version}"]
    if meta.get("description"):
        metadata.append(f"Summary: {meta['description']}")
    if meta.get("requires-python"):
        metadata.append(f"Requires-Python: {meta['requires-python']}")
    scripts = "".join(f"{command} = {target}\n" for command, target in meta.get("scripts", {}).items())
    files += [
        (f"{dist_info}/METADATA", ("\n".join(metadata) + "\n").encode("utf-8")),
        (f"{dist_info}/WHEEL", b"Wheel-Version: 1.0\nGenerator: peto-web\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
        (f"{dist_info}/entry_points.txt", f"[console_scripts]\n{scripts}".encode("utf-8")),
    ]
    record = "".join(f"{path},{_record_hash(content)},{len(content)}\n" for path, content in files)
    files.append((f"{dist_info}/RECORD", f"{record}{dist_info}/RECORD,,\n".encode("utf-8")))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files:
            info = zipfile.ZipInfo(path, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    data = buffer.getvalue()
    return Wheel(filename=f"{name}-{version}-py3-none-any.whl", data=data, sha256=hashlib.sha256(data).hexdigest())


def _script(text: str) -> Response:
    # Windows PowerShell 5.1 chỉ đọc đúng tiếng Việt khi Content-Type ghi rõ charset.
    return Response(text, media_type="text/plain; charset=utf-8", headers=NO_STORE)


def _ps_quoted(value: str) -> str:
    """Nội dung cho chuỗi nháy đơn của PowerShell: chỉ cần nhân đôi dấu nháy đơn."""
    return value.replace("'", "''")


def _error_script(message: str) -> str:
    return f"Write-Host '✗ {_ps_quoted(message)}' -ForegroundColor Red\n"


# Route đồng bộ: FastAPI chạy trong threadpool, nên đọc tệp và nén zip không chặn vòng sự kiện.
@router.get("/install.ps1", include_in_schema=False)
def install_script(request: Request) -> Response:
    server = public_origin(request)
    if server is None:
        return _script(_error_script(NOT_HTTPS))
    try:
        wheel = build_wheel(server)
        template = (CLI_DIR / "install.ps1").read_text(encoding="utf-8-sig")
    except (OSError, KeyError, TypeError, ValueError):
        logger.exception("Không dựng được bộ cài peto")
        return _script(_error_script(NOT_READY))
    values = {
        "__PETO_SERVER__": server,
        "__PETO_WHEEL_URL__": f"{server}{DOWNLOAD_PATH}/{wheel.filename}",
        "__PETO_WHEEL_NAME__": wheel.filename,
        "__PETO_WHEEL_SHA256__": wheel.sha256,
    }
    for placeholder, value in values.items():
        template = template.replace(placeholder, _ps_quoted(value))
    return _script(template)


@router.get(DOWNLOAD_PATH + "/{filename}", include_in_schema=False)
def download_wheel(filename: str, request: Request) -> Response:
    server = public_origin(request)
    if server is None:
        raise HTTPException(status_code=404, detail=NOT_HTTPS)
    try:
        wheel = build_wheel(server)
    except (OSError, KeyError, TypeError, ValueError):
        logger.exception("Không dựng được gói peto")
        raise HTTPException(status_code=503, detail=NOT_READY) from None
    if filename != wheel.filename:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói này. Chạy lại lệnh cài peto nhé.")
    headers = {**NO_STORE, "Content-Disposition": f'attachment; filename="{wheel.filename}"'}
    return Response(wheel.data, media_type="application/octet-stream", headers=headers)
