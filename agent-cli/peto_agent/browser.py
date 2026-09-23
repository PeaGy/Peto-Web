"""Trình duyệt để Peto xem và thao tác trang web đang chạy trên máy người dùng.

Chủ web chọn từ bản phác ngày 2026-09-23:

- Đợt 1 (0.10.0): Edge (hoặc Chrome) chạy ẩn, ảnh chụp được lưu để người dùng mở xem, mỗi lần xem báo kèm tối đa 5
  lỗi, và xem trang trên máy không hỏi quyền (như đọc tệp).
- Đợt 2 (0.11.0): bấm, gõ, nhấn phím, hỏi quyền một lần cho mỗi trang (tools.py). Cửa sổ vẫn ẩn, hiện khi người dùng gõ
  /trinhduyet hoặc khi Peto nhờ họ đăng nhập. Peto không bao giờ gõ vào ô mật khẩu: người dùng tự đăng nhập trong cửa
  sổ, và hồ sơ trình duyệt riêng của từng dự án (không phải Edge của người dùng) giữ đăng nhập sang phiên sau.

Cách làm và ranh giới:

- Chỉ dùng thư viện chuẩn: điều khiển trình duyệt qua giao thức DevTools (CDP) bằng một máy khách WebSocket nhỏ. Bấm và
  gõ là sự kiện chuột, bàn phím thật (trang thấy isTrusted), không phải gọi hàm JavaScript thay người dùng.
- Chỉ trang trên máy (localhost, 127.x, ::1, *.localhost). Trang ngoài là đường rò dữ liệu (Peto đọc tệp rồi mở một địa
  chỉ, hay gửi một form, mang theo nội dung đó) và là chỗ trang lạ nhét chỉ dẫn vào; file:// thì đọc được tệp ngoài dự
  án. Mọi lần trang chính chuyển ra ngoài máy (link, form, chuyển hướng, JavaScript) bị chặn trước khi request rời máy.
- Edge là ứng dụng có cửa sổ nên không tắt theo console như lệnh nền. Trên Windows, nó được tạo ở trạng thái tạm dừng,
  gắn vào một job object "tắt hết khi đóng" rồi mới chạy: peto chết kiểu gì (kể cả bấm X đóng cửa sổ terminal) thì
  Windows cũng tắt cả cây tiến trình Edge. Đã thử ngày 2026-09-23.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import http.client
import ipaddress
import itertools
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from . import runner
from .config import browser_profiles_dir, screenshots_dir
from .workspace import WorkspaceError

# Khung nhìn: (rộng, cao, giả lập điện thoại, tên hiện cho người dùng).
VIEWPORTS = {"desktop": (1280, 800, False, "máy tính"), "mobile": (390, 844, True, "điện thoại")}
VIEWPORT_ALIASES = {"desktop": "desktop", "may tinh": "desktop", "máy tính": "desktop", "pc": "desktop",
                    "mobile": "mobile", "phone": "mobile", "dien thoai": "mobile", "điện thoại": "mobile"}
START_TIMEOUT = 20.0
LOAD_TIMEOUT = 20.0
# Sau sự kiện load, chờ mạng yên 0,5 giây (tối đa 5 giây) để trang dựng bằng JavaScript kịp hiện.
QUIET_SECONDS = 0.5
MAX_SETTLE_SECONDS = 5.0
CALL_TIMEOUT = 30.0
MAX_MESSAGE_BYTES = 64 * 1024 * 1024
MAX_PROBLEMS = 200
MAX_PROBLEM_CHARS = 300
MAX_KNOWN = 2000
MAX_OUTLINE = 80
MAX_TEXT_CHARS = 20000
MAX_TRACKED_REQUESTS = 5000
# Ảnh gửi cho model: máy chủ nhận tối đa 3 MB mỗi ảnh; giữ dưới 2 MB, quá thì chuyển JPEG.
MAX_SHOT_BYTES = 2_000_000
MAX_FULL_PAGE_HEIGHT = 4000
SCREENSHOT_DAYS = 7
PROFILE_PREFIX = "peto-browser-"
STALE_PROFILE_SECONDS = 24 * 3600
STARTING_PROFILE_SECONDS = 60
# Hồ sơ riêng của từng dự án (giữ đăng nhập); dự án không mở lại 30 ngày thì hồ sơ bị dọn.
PROJECT_PROFILE_DAYS = 30
PROFILE_LOCK = "peto.lock"
LAST_USED = "peto-last-used"
# Request bị hủy khi trang chuyển đi hay tải lại không phải lỗi của trang.
IGNORED_FAILURES = {"net::ERR_ABORTED"}
# Dev server vừa chạy nền có thể chưa nghe cổng: browser_open chờ tối đa chừng này thay vì báo lỗi ngay.
SERVER_WAIT_SECONDS = 15.0
NOT_LISTENING = {"net::ERR_CONNECTION_REFUSED", "net::ERR_CONNECTION_RESET", "net::ERR_EMPTY_RESPONSE"}
# Sau một thao tác: chờ xem trang có chuyển đi không, rồi chờ mạng yên và DOM yên (hiệu ứng, dữ liệu tới muộn).
NAVIGATION_GRACE = 0.3
DOM_QUIET_MS = 250
MAX_DOM_WAIT_MS = 2000
MAX_APPEARED_LINES = 12
MAX_APPEARED_CHARS = 1500
MAX_DIFF_WORDS = 6000
MAX_CHANGED_ELEMENTS = 25
MAX_TYPED_CHARS = 5000
# Phím Peto được nhấn: tên → (key, code, mã phím Windows, chữ gõ ra, modifiers; 8 là Shift).
KEYS = {
    "Enter": ("Enter", "Enter", 13, "\r", 0), "Escape": ("Escape", "Escape", 27, "", 0),
    "Tab": ("Tab", "Tab", 9, "", 0), "Shift+Tab": ("Tab", "Tab", 9, "", 8),
    "Backspace": ("Backspace", "Backspace", 8, "", 0), "Delete": ("Delete", "Delete", 46, "", 0),
    "Space": (" ", "Space", 32, " ", 0),
    "ArrowUp": ("ArrowUp", "ArrowUp", 38, "", 0), "ArrowDown": ("ArrowDown", "ArrowDown", 40, "", 0),
    "ArrowLeft": ("ArrowLeft", "ArrowLeft", 37, "", 0), "ArrowRight": ("ArrowRight", "ArrowRight", 39, "", 0),
    "Home": ("Home", "Home", 36, "", 0), "End": ("End", "End", 35, "", 0),
    "PageUp": ("PageUp", "PageUp", 33, "", 0), "PageDown": ("PageDown", "PageDown", 34, "", 0),
}
KEY_ALIASES = {"esc": "Escape", "return": "Enter", "spacebar": "Space", " ": "Space", "shift tab": "Shift+Tab",
               "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight"}
# Trường của cookie mà Storage.setCookies nhận lại được.
COOKIE_FIELDS = ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite", "priority", "sourceScheme",
                 "sourcePort", "partitionKey")

_shot_numbers = itertools.count(1)


class BrowserError(WorkspaceError):
    """Lỗi hiện cho người dùng và trả cho Peto như lỗi công cụ."""


def find_browser() -> str | None:
    """Edge có sẵn trên Windows; không có thì Chrome. ``PETO_AGENT_BROWSER`` chỉ tới tệp chạy khác nếu cần."""
    override = os.environ.get("PETO_AGENT_BROWSER")
    if override:
        return override if Path(override).is_file() else None
    candidates = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates += [Path(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                           Path(base, "Google", "Chrome", "Application", "chrome.exe")]
    for path in candidates:
        if path.is_file():
            return str(path)
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if found := shutil.which(name):
            return found
    return None


def is_local(host: str | None) -> bool:
    """Máy này: localhost, *.localhost (trình duyệt tự trỏ về máy mình, không hỏi DNS), 127.x và ::1."""
    host = (host or "").strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _local_url(url: str) -> bool:
    parts = urlsplit(url or "")
    return parts.scheme in {"http", "https"} and is_local(parts.hostname)


def check_url(url: str) -> str:
    """Địa chỉ được phép mở: http(s) tới chính máy này. "localhost:5173" thiếu http:// thì được thêm vào."""
    text = (url or "").strip()
    if text and "://" not in text and not text.lower().startswith(("file:", "javascript:", "data:", "about:")):
        text = "http://" + text
    try:
        parts = urlsplit(text)
        host = parts.hostname
        _ = parts.port  # cổng sai (chữ, quá 65535) thì ném ValueError
    except ValueError:
        raise BrowserError(f"Địa chỉ không hợp lệ: {url}") from None
    if parts.scheme not in {"http", "https"} or not is_local(host) or parts.username or parts.password:
        raise BrowserError("Peto chỉ mở trang chạy trên máy (localhost, 127.0.0.1); trang ngoài và địa chỉ file://, "
                           "javascript:, data: không mở được.")
    return text


def _short(url: str, base: str) -> str:
    """Địa chỉ gọn cho dòng lỗi: cùng máy chủ với trang thì bỏ phần đầu."""
    base_parts, parts = urlsplit(base), urlsplit(url)
    if (parts.scheme, parts.netloc) == (base_parts.scheme, base_parts.netloc):
        url = parts.path + (f"?{parts.query}" if parts.query else "")
    return url if len(url) <= 160 else url[:159] + "…"


def _outside(url: str) -> str:
    """Trang ngoài bị chặn, viết gọn và bỏ phần sau dấu ?, vì đó thường là dữ liệu vừa định gửi đi."""
    parts = urlsplit(url)
    text = f"{parts.netloc}{parts.path}" if parts.netloc else url
    return text if len(text) <= 80 else text[:79] + "…"


def _clip(text: str, limit: int = MAX_PROBLEM_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def viewport_label(key: str) -> str:
    width, height, _, label = VIEWPORTS[key]
    return f"{label} {width}×{height}"


def key_name(key: str) -> str:
    """Tên phím chuẩn trong KEYS từ chữ model gửi ("esc", "enter", "shift+tab"); phím lạ thì báo lỗi."""
    text = " ".join(str(key or "").replace("+", " + ").split()).replace(" + ", "+")
    for name in KEYS:
        if name.lower() == text.lower():
            return name
    alias = KEY_ALIASES.get(text.lower().replace("+", " "))
    if alias:
        return alias
    raise BrowserError("Chỉ nhấn được các phím: " + ", ".join(KEYS) + ".")


class WebSocket:
    """Máy khách WebSocket tối thiểu (RFC 6455) cho DevTools: chữ, ping/pong, tin chia nhiều khung.

    Chỉ lấy một khung ra khỏi bộ đệm khi đã nhận đủ, nên hết thời gian chờ giữa chừng không làm lệch luồng dữ liệu.
    """

    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, host: str, port: int, path: str, timeout: float = CALL_TIMEOUT):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
                          .encode())
        self.buffer = bytearray()
        self.partial = bytearray()
        while b"\r\n\r\n" not in self.buffer:
            self._fill()
        end = self.buffer.index(b"\r\n\r\n") + 4
        head = bytes(self.buffer[:end])
        del self.buffer[:end]
        accept = base64.b64encode(hashlib.sha1((key + self.GUID).encode()).digest())
        if b" 101 " not in head.split(b"\r\n", 1)[0] or accept not in head:
            raise ConnectionError("Trình duyệt từ chối kết nối DevTools.")

    def _fill(self) -> None:
        chunk = self.sock.recv(1 << 20)
        if not chunk:
            raise ConnectionError("Trình duyệt đã đóng kết nối.")
        self.buffer += chunk

    def _frame(self) -> tuple[int, bool, bytes] | None:
        """Một khung trọn vẹn lấy ra từ bộ đệm (opcode, fin, dữ liệu), hoặc None nếu chưa nhận đủ byte."""
        buffer = self.buffer
        if len(buffer) < 2:
            return None
        size, offset = buffer[1] & 0x7F, 2
        if size == 126:
            if len(buffer) < 4:
                return None
            size, offset = struct.unpack(">H", buffer[2:4])[0], 4
        elif size == 127:
            if len(buffer) < 10:
                return None
            size, offset = struct.unpack(">Q", buffer[2:10])[0], 10
        if size > MAX_MESSAGE_BYTES:
            raise ConnectionError("Tin nhắn DevTools quá lớn.")
        mask_size = 4 if buffer[1] & 0x80 else 0
        if len(buffer) < offset + mask_size + size:
            return None
        mask = bytes(buffer[offset:offset + mask_size])
        start = offset + mask_size
        payload = bytes(buffer[start:start + size])
        opcode, fin = buffer[0] & 0x0F, bool(buffer[0] & 0x80)
        del buffer[:start + size]
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, fin, payload

    def send(self, data: str | bytes, opcode: int = 0x1) -> None:
        payload = data.encode() if isinstance(data, str) else data
        size = len(payload)
        if size < 126:
            header = bytes([0x80 | opcode, 0x80 | size])
        elif size < 65536:
            header = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", size)
        else:
            header = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", size)
        mask = os.urandom(4)
        repeated = (mask * (size // 4 + 1))[:size]
        masked = (int.from_bytes(payload, "big") ^ int.from_bytes(repeated, "big")).to_bytes(size, "big")
        self.sock.sendall(header + mask + masked)

    def recv(self, timeout: float) -> str:
        """Một tin chữ. Hết ``timeout`` giây mà chưa đủ tin thì ném TimeoutError; dữ liệu đã nhận vẫn được giữ."""
        deadline = time.monotonic() + timeout
        while True:
            frame = self._frame()
            if frame is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError
                self.sock.settimeout(left)
                self._fill()
                continue
            opcode, fin, payload = frame
            if opcode == 0x9:
                self.send(payload, 0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise ConnectionError("Trình duyệt đã đóng kết nối.")
            self.partial += payload
            if len(self.partial) > MAX_MESSAGE_BYTES:
                raise ConnectionError("Tin nhắn DevTools quá lớn.")
            if fin:
                message = bytes(self.partial)
                self.partial.clear()
                return message.decode("utf-8")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class _Job:
    """Job object của Windows với cờ tắt hết khi đóng: đóng handle, hay peto chết, là mọi tiến trình trong job tắt."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", ctypes.c_ulonglong * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                        wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("không tạo được job object")
        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise OSError("không đặt được giới hạn cho job object")

    def adopt(self, pid: int) -> None:
        """Gắn tiến trình đang tạm dừng vào job rồi cho chạy, để mọi tiến trình con nó tạo sau đó đều nằm trong job."""
        ntdll = self.ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = [self.ctypes.c_void_p]
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME
        process = self.kernel.OpenProcess(0x0100 | 0x0001 | 0x0800, False, pid)
        if not process:
            raise OSError("không mở được tiến trình trình duyệt")
        try:
            assigned = self.kernel.AssignProcessToJobObject(self.handle, process)
            if ntdll.NtResumeProcess(process) != 0:
                raise OSError("không cho trình duyệt chạy tiếp được")
            if not assigned:
                # Không nằm trong job thì bấm X đóng terminal sẽ để sót trình duyệt chạy ngầm: thà không mở.
                raise OSError("không gắn được trình duyệt vào job object")
        finally:
            self.kernel.CloseHandle(process)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


@dataclass
class Shot:
    data: bytes
    mime: str
    width: int
    height: int
    viewport: str
    full_page: bool
    cut: bool


class _Feed:
    """Những gì trang báo mà Peto cần biết (lỗi, hộp thoại, việc Peto chặn), trả theo kiểu "mới từ lần báo trước".

    Điều đã báo cho trang đang xem nằm trong ``known``, dùng chung giữa các loại: mở lại trang chỉ để đổi khung chụp
    thì không báo lại đúng những điều ấy.
    """

    def __init__(self, known: set[str]):
        self.known = known
        self.items: list[str] = []

    def add(self, text: str) -> None:
        text = _clip(text)
        if text and text not in self.items and text not in self.known and len(self.items) < MAX_PROBLEMS:
            self.items.append(text)

    def fresh(self) -> list[str]:
        items, self.items = self.items, []
        if len(self.known) > MAX_KNOWN:
            self.known.clear()
        self.known.update(items)
        return items


class Browser:
    """Một trình duyệt cho cả phiên peto: mở khi Peto xem trang lần đầu, đóng khi phiên kết thúc.

    ``profile`` là hồ sơ riêng của dự án, giữ đăng nhập sang phiên sau; None thì dùng hồ sơ tạm, xóa khi đóng. Trình
    duyệt không đổi được giữa ẩn và hiện khi đang chạy, nên đổi là mở lại với cùng hồ sơ.
    """

    def __init__(self, executable: str | None = None, profile: Path | None = None):
        self.executable = executable
        self.project_profile = profile
        self.profile: Path | None = None
        self.temporary = True
        self.lock = None
        self.visible = False
        # Test đặt True: "hiện" vẫn chạy ẩn, để kiểm việc mở lại trình duyệt mà không bật cửa sổ lên màn hình.
        self.force_headless = False
        # Lời nhắc cho người dùng khi phải dùng hồ sơ tạm thay cho hồ sơ của dự án.
        self.notice: str | None = None
        self.process: subprocess.Popen | None = None
        self.job: _Job | None = None
        self.ws: WebSocket | None = None
        self.target: str | None = None
        self.next_id = 0
        self.viewport: str | None = None
        self.frame: str | None = None
        self.url: str | None = None
        # Cookie phiên (không hạn) chỉ sống trong trình duyệt đang chạy: nhớ ở đây để mở lại (đổi ẩn/hiện, cửa sổ bị
        # đóng) vẫn còn đăng nhập. Cookie có hạn đã nằm trong hồ sơ. Chỉ giữ trong bộ nhớ, không ghi ra đĩa.
        self.session_cookies: list[dict] = []
        self.handing_over = False
        self.accept_dialog = False
        self.wait_for_server = False
        self.known: set[str] = set()
        self._reset_page()

    # --- vòng đời ------------------------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        # Theo kết nối DevTools chứ không theo tiến trình đã mở: Edge có thể tự mở lại chính nó rồi thoát tiến trình
        # đầu (xem _launch_env). Kết nối hỏng thì trình duyệt bị tắt, lần xem sau mở lại.
        return self.ws is not None

    @property
    def origin(self) -> str:
        parts = urlsplit(self.url or "")
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def name(self) -> str:
        executable = (self.executable or find_browser() or "").lower()
        return "Chrome" if "chrome" in executable else "Edge"

    def _acquire_profile(self) -> None:
        """Chọn hồ sơ cho cả phiên: hồ sơ của dự án nếu không phiên peto nào khác đang giữ, không thì hồ sơ tạm."""
        if self.profile is not None:
            return
        if self.project_profile is not None:
            _prune_project_profiles(keep=self.project_profile)
            try:
                self.project_profile.mkdir(parents=True, exist_ok=True)
                self.lock = _hold(self.project_profile)
                self.profile, self.temporary = self.project_profile, False
                _touch(self.project_profile / LAST_USED)
                _name_profile(self.profile)
                return
            except OSError:
                self.notice = ("Hồ sơ trình duyệt của dự án này đang được một phiên peto khác dùng, nên phiên này dùng "
                               "hồ sơ tạm: không có đăng nhập đã nhớ.")
        _prune_profiles()
        self.profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))
        self.temporary = True
        self.lock = _hold(self.profile)
        _name_profile(self.profile)

    def _start(self) -> None:
        if self.running:
            return
        self._stop()
        executable = self.executable or find_browser()
        if not executable:
            raise BrowserError("Máy này chưa có Microsoft Edge hay Google Chrome nên Peto chưa xem trang được.")
        try:
            self._acquire_profile()
            # Hồ sơ của dự án còn tệp cổng của lần chạy trước: đọc nhầm nó là nối vào một cổng đã chết.
            (self.profile / "DevToolsActivePort").unlink(missing_ok=True)
        except OSError as err:
            raise BrowserError(f"Không tạo được hồ sơ trình duyệt ({err}).") from None
        headless = self.force_headless or not self.visible
        args = [executable, "--remote-debugging-port=0", f"--user-data-dir={self.profile}", "--no-first-run",
                "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                "--disable-background-networking", "--disable-component-update", "--hide-scrollbars", "--mute-audio",
                "--hide-crash-restore-bubble", "--disk-cache-size=52428800",
                # Cửa sổ hiện mà bị terminal che vẫn phải vẽ tiếp, không thì chờ khung hình và chụp ảnh đều treo.
                "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
                "--window-size=1280,800" if headless else "--window-size=1320,940", "about:blank"]
        if headless:
            args.insert(1, "--headless=new")
        try:
            if os.name == "nt":
                self.job = _Job()
                self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL, env=_launch_env(),
                                                creationflags=0x00000004)  # CREATE_SUSPENDED
                self.job.adopt(self.process.pid)
            else:
                self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL, env=_launch_env(), start_new_session=True)
            port = self._devtools_port()
            self.ws = WebSocket("127.0.0.1", port, self._page_path(port))
            for domain in ("Page", "Runtime", "Log", "Network"):
                self._call(f"{domain}.enable")
            self.target = self._call("Target.getTargetInfo")["targetInfo"]["targetId"]
            self.frame = self._call("Page.getFrameTree")["frameTree"]["frame"]["id"]
            # Tab mới trang tự mở bị đóng (Peto chỉ xem một tab); tải xuống bị từ chối.
            self._call("Target.setDiscoverTargets", {"discover": True})
            self._call("Browser.setDownloadBehavior", {"behavior": "deny", "eventsEnabled": True})
            self._guard(True)
            if self.session_cookies:
                self._call("Storage.setCookies", {"cookies": self.session_cookies})
            self.viewport = None
            self._set_viewport("desktop")
        except (OSError, ConnectionError, ValueError, KeyError, StopIteration) as err:
            self._stop()
            raise BrowserError(f"Không mở được trình duyệt ({err}).") from None

    def _guard(self, on: bool) -> None:
        """Chặn trang chính chuyển ra ngoài máy và hộp chọn tệp. Chỉ tắt khi người dùng tự đăng nhập trong cửa sổ."""
        if on:
            self._call("Fetch.enable", {"patterns": [{"resourceType": "Document", "requestStage": "Request"}]})
        else:
            self._call("Fetch.disable")
        self._call("Page.setInterceptFileChooserDialog", {"enabled": on})

    def _devtools_port(self) -> int:
        """Trình duyệt ghi cổng DevTools vào tệp DevToolsActivePort trong hồ sơ khi đã sẵn sàng.

        Tiến trình đầu thoát với mã 0 chưa phải là lỗi: Edge có thể đã tự mở lại chính nó (cùng hồ sơ), nên cứ chờ tệp.
        """
        path = self.profile / "DevToolsActivePort"
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() not in (None, 0):
                raise OSError(f"trình duyệt thoát ngay, mã {self.process.returncode}")
            try:
                lines = path.read_text(encoding="utf-8").split()
                if len(lines) >= 2:
                    return int(lines[0])
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        raise OSError("trình duyệt không mở cổng DevTools")

    @staticmethod
    def _page_path(port: int) -> str:
        # http.client không đi qua proxy của hệ thống như urllib, nên luôn tới đúng 127.0.0.1.
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("GET", "/json/list")
            targets = json.loads(connection.getresponse().read())
        finally:
            connection.close()
        page = next(target for target in targets if target.get("type") == "page")
        return "/" + page["webSocketDebuggerUrl"].split("/", 3)[3]

    def _stop(self) -> None:
        """Tắt trình duyệt nhưng giữ hồ sơ: đổi ẩn/hiện, mất kết nối, trang treo."""
        ws, process, job = self.ws, self.process, self.job
        self.ws = self.process = self.job = None
        if ws is not None:
            try:
                ws.send(json.dumps({"id": 0, "method": "Browser.close", "params": {}}))
            except OSError:
                pass
            ws.close()
        if process is not None:
            try:
                process.wait(3)
            except subprocess.TimeoutExpired:
                pass
        if job is not None:
            # Đóng job là Windows tắt nốt mọi tiến trình của trình duyệt còn sót.
            job.close()
        if process is not None:
            try:
                process.wait(3)
            except subprocess.TimeoutExpired:
                runner.kill_tree(process)
            # Tiến trình đầu có thể đã thoát từ lâu (Edge tự mở lại chính nó), còn các tiến trình trong job chết sau
            # vài chục ms. Mở lại ngay trên hồ sơ chưa được nhả thì Edge mới chuyển việc sang Edge cũ đang chết, và
            # /trinhduyet xoa tưởng hồ sơ còn người dùng (gặp ngày 2026-09-23): chờ hồ sơ được nhả hẳn.
            if self.profile is not None:
                _released(self.profile, 5.0)

    def close(self) -> None:
        """Hết phiên: tắt trình duyệt, nhả hồ sơ; hồ sơ tạm bị xóa, hồ sơ của dự án được giữ. Gọi nhiều lần cũng được."""
        self._stop()
        self.url = None
        profile, temporary, lock = self.profile, self.temporary, self.lock
        self.profile = self.lock = None
        if lock is not None:
            lock.close()
        if profile is None:
            return
        if not temporary:
            _touch(profile / LAST_USED)
            return
        # Trình duyệt vừa tắt có thể còn giữ tệp một lúc: thử lại vài lần; còn sót thì lần mở sau dọn.
        for _ in range(15):
            shutil.rmtree(profile, ignore_errors=True)
            if not profile.exists():
                break
            time.sleep(0.2)

    def _lose(self) -> str:
        """Trình duyệt đóng ngoài ý Peto (người dùng tắt cửa sổ, trình duyệt chết): lần xem sau mở lại, chạy ẩn."""
        closed_window = self.visible and not self.force_headless
        self._stop()
        self.visible = False
        self.url = None
        return ("Cửa sổ trình duyệt đã bị đóng; lần xem sau Peto mở lại trình duyệt chạy ẩn (vẫn còn đăng nhập)."
                if closed_window else "Mất kết nối với trình duyệt; lần xem sau sẽ mở lại.")

    def set_visible(self, visible: bool) -> None:
        """Hiện hay ẩn cửa sổ. Đổi là mở lại trình duyệt với cùng hồ sơ và cookie phiên, rồi mở lại trang đang xem."""
        if visible == self.visible and (self.running or not visible):
            if self.running and visible:
                self._call("Page.bringToFront")
            return
        url, viewport = self.url, self.viewport
        if self.running:
            self._remember_cookies()
            self._stop()
        self.visible = visible
        if not visible and not url:
            return
        self._start()
        if url:
            self._load(url, viewport)
        if visible:
            self._call("Page.bringToFront")

    # --- DevTools ------------------------------------------------------------------------------------------------

    def _send(self, method: str, params: dict) -> None:
        """Gửi lệnh không chờ trả lời, dùng khi đang ở giữa một _call: chờ lồng nhau sẽ nuốt mất câu trả lời của lệnh
        ngoài. Câu trả lời tới sau thì _event bỏ qua."""
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))

    def _call(self, method: str, params: dict | None = None, *, timeout: float = CALL_TIMEOUT) -> dict:
        if self.ws is None:
            raise BrowserError("Trình duyệt chưa mở.")
        self.next_id += 1
        wanted = self.next_id
        deadline = time.monotonic() + timeout
        try:
            self.ws.send(json.dumps({"id": wanted, "method": method, "params": params or {}}))
            while True:
                message = json.loads(self.ws.recv(max(0.01, deadline - time.monotonic())))
                if message.get("id") == wanted:
                    if "error" in message:
                        raise BrowserError(_clip(message["error"].get("message", "")))
                    return message.get("result", {})
                self._event(message)
        except TimeoutError:
            # Trang treo (vòng lặp JavaScript chạy mãi, dev server không trả lời) thì dùng tiếp trình duyệt này chỉ
            # chờ thêm 30 giây mỗi lần: tắt hẳn để lần xem sau mở trình duyệt mới.
            self._stop()
            self.url = None
            raise BrowserError(f"Trình duyệt không trả lời sau {int(timeout)} giây (trang bị treo?); lần xem sau "
                               "sẽ mở trình duyệt mới.") from None
        except (ConnectionError, OSError, ValueError):
            raise BrowserError(self._lose()) from None

    def _pump(self, seconds: float) -> None:
        """Đọc các sự kiện tới trong ``seconds`` giây: lỗi console tới muộn, request còn đang chạy."""
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            try:
                self._event(json.loads(self.ws.recv(left)))
            except TimeoutError:
                return
            except (ConnectionError, OSError, ValueError):
                raise BrowserError(self._lose()) from None

    def _drain(self) -> None:
        """Đọc hết sự kiện dồn lại lúc không ai đọc (người dùng đang dùng cửa sổ), tới khi yên 0,2 giây, tối đa 3 giây."""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                self._event(json.loads(self.ws.recv(0.2)))
            except TimeoutError:
                return
            except (ConnectionError, OSError, ValueError):
                raise BrowserError(self._lose()) from None

    def _reset_page(self) -> None:
        self.problems = _Feed(self.known)
        self.dialogs = _Feed(self.known)
        self.notes = _Feed(self.known)
        self.inflight: set[str] = set()
        self.requests: dict[str, str] = {}
        self.last_network = time.monotonic()
        self.loaded = False
        # Trang chính đang tải, đã thôi tải (xong, lỗi hay bị chặn), vừa sang tài liệu mới, vừa bị chặn ra ngoài.
        self.loading = self.stopped = self.navigated = False
        self.blocked: str | None = None
        self.downloads: set[str] = set()
        self.status: int | None = None

    def _problem(self, text: str) -> None:
        self.problems.add(text)

    def _dialog(self, params: dict) -> None:
        """Trả lời ngay hộp thoại alert/confirm/prompt của trang.

        Hộp thoại chặn trang tới khi có người trả lời; không ai trả lời thì mọi lệnh sau đều treo (gặp ngày 2026-09-23:
        trang gọi alert() lúc tải làm browser_open chờ 50 giây rồi báo lỗi, và trình duyệt kẹt tới hết phiên). alert thì
        đóng; confirm và prompt thì chọn Hủy, trừ khi Peto xin chọn OK cho đúng thao tác gây ra nó (accept_dialog), để
        Peto không thay người dùng đồng ý một việc có thể đổi dữ liệu; beforeunload thì cho rời trang vì chính Peto
        đang mở trang khác. Lúc người dùng tự dùng cửa sổ thì để họ trả lời.
        """
        if self.handing_over:
            return
        kind = params.get("type") or "alert"
        accept = kind in {"alert", "beforeunload"} or self.accept_dialog
        self._send("Page.handleJavaScriptDialog", {"accept": accept})
        if kind == "beforeunload":
            return
        answer = "đã đóng" if kind == "alert" else "đã chọn OK" if accept else "đã chọn Hủy"
        self.dialogs.add(f"{kind} \"{_clip(params.get('message', ''), 120)}\" ({answer})")

    def _paused(self, params: dict) -> None:
        """Request tài liệu (trang, khung) bị giữ lại để xét: trang chính ra ngoài máy thì chặn, còn lại cho đi."""
        url = (params.get("request") or {}).get("url", "")
        if params.get("frameId") != self.frame or _local_url(url):
            self._send("Fetch.continueRequest", {"requestId": params.get("requestId")})
            return
        # Trả 204 thì trình duyệt bỏ lần chuyển trang và giữ nguyên trang đang xem; request không rời khỏi máy.
        self.blocked = url
        self._send("Fetch.fulfillRequest", {"requestId": params.get("requestId"), "responseCode": 204,
                                            "responseHeaders": []})
        self.notes.add(f"Peto chặn chuyển sang {_outside(url)} vì trang đó ngoài máy này; trang giữ nguyên.")

    def _popup(self, info: dict) -> None:
        if info.get("type") != "page" or info.get("openerId") != self.target or self.handing_over:
            return
        self._send("Target.closeTarget", {"targetId": info.get("targetId")})
        self.notes.add("Trang mở một tab hay cửa sổ mới; Peto đã đóng nó vì Peto chỉ xem một tab.")

    def _event(self, message: dict) -> None:
        method, params = message.get("method"), message.get("params") or {}
        base = self.url or ""
        if method == "Fetch.requestPaused":
            self._paused(params)
        elif method == "Page.javascriptDialogOpening":
            self._dialog(params)
        elif method == "Target.targetCreated":
            self._popup(params.get("targetInfo") or {})
        elif method in {"Browser.downloadWillBegin", "Page.downloadWillBegin"}:
            if params.get("guid") not in self.downloads:
                self.downloads.add(params.get("guid"))
                name = params.get("suggestedFilename")
                self.notes.add(f"Trang muốn tải tệp {name} về máy; Peto không tải tệp." if name
                               else "Trang muốn tải một tệp về máy; Peto không tải tệp.")
        elif method == "Page.fileChooserOpened":
            self.notes.add("Trang mở hộp chọn tệp; Peto không tải tệp nào lên.")
        elif method == "Page.frameStartedLoading" and params.get("frameId") == self.frame:
            self.loading, self.loaded, self.stopped = True, False, False
        elif method == "Page.frameStoppedLoading" and params.get("frameId") == self.frame:
            self.loading, self.stopped = False, True
        elif method == "Page.frameNavigated" and not (params.get("frame") or {}).get("parentId"):
            self.navigated = True
            self.requests.clear()
        elif method == "Page.loadEventFired":
            self.loaded = True
        elif method == "Network.requestWillBeSent":
            request = params.get("requestId")
            self.inflight.add(request)
            if len(self.requests) < MAX_TRACKED_REQUESTS:
                self.requests[request] = (params.get("request") or {}).get("url", "")
            self.last_network = time.monotonic()
        elif method in {"Network.loadingFinished", "Network.loadingFailed"}:
            request = params.get("requestId")
            self.inflight.discard(request)
            self.last_network = time.monotonic()
            if method == "Network.loadingFailed" and not params.get("canceled") \
                    and params.get("errorText") not in IGNORED_FAILURES:
                url = self.requests.get(request, "")
                if params.get("type") == "Document" and url == self.blocked:
                    return  # chính lần chuyển trang Peto vừa chặn
                self._problem(f"request hỏng: {params.get('errorText')} {_short(url, base)}".rstrip())
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            status, url = int(response.get("status") or 0), response.get("url") or ""
            if params.get("type") == "Document" and params.get("frameId") == self.frame:
                if status != 204 or url != self.blocked:
                    self.status = status
            elif status >= 400 and not urlsplit(url).path.endswith("/favicon.ico"):
                self._problem(f"{status} {_short(url, base)}")
        elif method == "Runtime.consoleAPICalled" and params.get("type") in {"error", "warning", "assert"}:
            words = [str(arg.get("value", arg.get("description", arg.get("type", ""))))
                     for arg in params.get("args") or []]
            self._problem(f"console.{params['type']}: {' '.join(words)}")
        elif method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails") or {}
            text = (details.get("exception") or {}).get("description") or details.get("text") or "lỗi JavaScript"
            where = details.get("url")
            place = f" ({_short(where, base)}:{int(details.get('lineNumber') or 0) + 1})" if where else ""
            self._problem(text.splitlines()[0] + place)
        elif method == "Log.entryAdded":
            entry = params.get("entry") or {}
            # Lỗi mạng, console và JavaScript đã báo ở trên; ở đây chỉ lấy lỗi khác của trình duyệt (bảo mật, CSP…).
            if entry.get("level") == "error" and entry.get("source") not in {"network", "console-api", "javascript"}:
                self._problem(entry.get("text", ""))

    def new_problems(self) -> list[str]:
        """Lỗi mới kể từ lần báo trước, để lỗi hiện muộn (sau khi dev server nạp lại code) vẫn tới được Peto."""
        return self.problems.fresh()

    def new_dialogs(self) -> list[str]:
        """Hộp thoại trang đã mở (và Peto đã trả lời) kể từ lần báo trước; báo riêng vì hộp thoại không phải lỗi."""
        return self.dialogs.fresh()

    def new_notes(self) -> list[str]:
        """Việc Peto chặn hay bỏ qua (trang ngoài, tab mới, tải tệp) kể từ lần báo trước."""
        return self.notes.fresh()

    def _report(self, result: dict) -> dict:
        """Thêm lỗi, hộp thoại và việc bị chặn mới vào kết quả; loại nào không có thì không có khóa đó."""
        result["problems"] = self.new_problems()
        for key, feed in (("dialogs", self.dialogs), ("notes", self.notes)):
            if fresh := feed.fresh():
                result[key] = fresh
        return result

    def _remember_cookies(self) -> None:
        if not self.running:
            return
        try:
            cookies = self._call("Storage.getCookies").get("cookies") or []
        except BrowserError:
            return
        self.session_cookies = [{field: cookie[field] for field in COOKIE_FIELDS if field in cookie}
                                for cookie in cookies if cookie.get("session")]

    # --- xem trang -----------------------------------------------------------------------------------------------

    @staticmethod
    def _viewport_key(name: str | None) -> str:
        key = VIEWPORT_ALIASES.get(str(name or "desktop").strip().lower())
        if key is None:
            raise BrowserError("viewport chỉ nhận desktop (máy tính 1280×800) hoặc mobile (điện thoại 390×844).")
        return key

    def _set_viewport(self, name: str | None) -> str:
        key = self._viewport_key(name)
        if key != self.viewport:
            width, height, mobile, _ = VIEWPORTS[key]
            self._call("Emulation.setDeviceMetricsOverride",
                       {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})
            self._call("Emulation.setTouchEmulationEnabled", {"enabled": mobile})
            self.viewport = key
        return key

    def _settle(self, started: float) -> None:
        """Chờ trang tải xong (hay thôi tải) rồi chờ mạng yên, để không chụp phải trang trắng lúc JavaScript còn dựng."""
        deadline = started + LOAD_TIMEOUT
        while not (self.loaded or self.stopped) and time.monotonic() < deadline:
            self._pump(min(0.1, max(0.01, deadline - time.monotonic())))
        self._quiet()

    def _quiet(self) -> None:
        settle_until = time.monotonic() + MAX_SETTLE_SECONDS
        while time.monotonic() < settle_until:
            if not self.inflight and time.monotonic() - self.last_network >= QUIET_SECONDS:
                return
            self._pump(0.1)

    def _repaint(self) -> None:
        """Chờ hai khung hình để trang kịp vẽ lại; có hạn giờ vì cửa sổ bị thu nhỏ thì không có khung hình nào."""
        self._call("Runtime.evaluate", {"expression": "new Promise(r => { requestAnimationFrame(() => "
                                                       "requestAnimationFrame(r)); setTimeout(r, 300); })",
                                        "awaitPromise": True})

    def _restore_window(self) -> None:
        """Cửa sổ hiện mà bị thu nhỏ thì trình duyệt thôi vẽ và không chụp được: đưa nó về cỡ thường trước."""
        if not self.visible or self.force_headless or self._evaluate("document.visibilityState") != "hidden":
            return
        window = self._call("Browser.getWindowForTarget")
        self._call("Browser.setWindowBounds", {"windowId": window["windowId"], "bounds": {"windowState": "normal"}})
        self._pump(0.3)

    def _evaluate(self, expression: str):
        result = self._call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise BrowserError(_clip((details.get("exception") or {}).get("description") or details.get("text", "")))
        return (result.get("result") or {}).get("value")

    def _script(self, script: str, *args):
        """Gọi một hàm JavaScript trong trang, có sẵn phần dùng chung (tên phần tử, số thứ tự), với tham số JSON."""
        call = "(" + script.replace("/*PRELUDE*/", PRELUDE) + ")(" + \
               ", ".join(json.dumps(arg, ensure_ascii=False) for arg in args) + ")"
        return self._evaluate(call)

    def _require_page(self) -> None:
        if self.url is None or not self.running:
            raise BrowserError("Chưa mở trang nào: gọi browser_open trước.")

    def open(self, url: str, viewport: str | None = None) -> dict:
        """Mở (hoặc tải lại) một trang trên máy; trả tiêu đề, mã trạng thái, lỗi và các phần tử đang hiện.

        Peto chủ động mở lại (thường sau khi sửa code) thì báo lại đủ lỗi: lỗi còn đó nghĩa là chưa sửa được.
        """
        self.known.clear()
        result = self._report(self._load(url, viewport))
        self._remember_cookies()
        return result

    def _leave(self, message: str):
        """Trang vừa mở hóa ra ngoài máy (chuyển hướng): về trang trắng rồi báo lỗi."""
        self._call("Page.navigate", {"url": "about:blank"})
        self.url = None
        raise BrowserError(message)

    def _load(self, url: str, viewport: str | None) -> dict:
        target = check_url(url)
        self._start()
        key = self._set_viewport(viewport)
        self._reset_page()
        self.url = target
        started = time.monotonic()
        waiting_until = started + (SERVER_WAIT_SECONDS if self.wait_for_server else 0)
        while True:
            result = self._call("Page.navigate", {"url": target}, timeout=LOAD_TIMEOUT + 10)
            if result.get("errorText") not in NOT_LISTENING or time.monotonic() >= waiting_until:
                break
            self._pump(0.5)  # dev server chưa nghe cổng: chờ rồi thử lại
            self._reset_page()
        def blocked() -> str:
            return (f"Trang chuyển sang {urlsplit(self.blocked).hostname or self.blocked}, ngoài máy này; Peto chỉ "
                    "xem trang trên máy.")

        if self.blocked:
            self._leave(blocked())
        if result.get("errorText"):
            self.url = None
            raise BrowserError(f"Không mở được {target} ({result['errorText']}). Dev server đã chạy và đúng cổng chưa? "
                               "Chạy nó bằng start_command rồi đọc output để lấy đúng địa chỉ.")
        if result.get("loaderId"):
            self._settle(started)
        else:
            self._pump(QUIET_SECONDS)  # chỉ đổi phần # của địa chỉ: không có lần tải mới
        if self.blocked:
            self._leave(blocked())
        seconds = time.monotonic() - started
        page = self._script(SNAPSHOT_SCRIPT, MAX_OUTLINE, False) or {}
        final = page.get("url") or target
        if not _local_url(final):
            self._leave(f"Trang chuyển sang {urlsplit(final).hostname or final}, ngoài máy này; Peto chỉ xem trang "
                        "trên máy.")
        self.url = final
        return {"url": final, "title": page.get("title") or "", "status": self.status, "viewport": key,
                "seconds": round(seconds, 1), "loaded": self.loaded, "outline": page.get("outline") or [],
                "elements": page.get("total", 0), "text_chars": page.get("chars", 0)}

    def screenshot(self, viewport: str | None = None, full_page: bool = False) -> Shot:
        """Chụp trang đang mở. Khung khác khung đang dùng thì mở lại trang ở khung đó rồi mới chụp.

        Đổi khung trên trang đã tải (hay tải lại) thì Chrome giữ tỉ lệ thu phóng cũ: trang máy tính chuyển sang điện
        thoại bị thu nhỏ cho vừa, che mất đúng chỗ bị tràn cần thấy (gặp ngày 2026-09-23). Mở lại từ đầu thì giống
        điện thoại thật lần đầu vào trang: trang có meta viewport ở tỉ lệ 1, trang không có thì thu nhỏ như thường.
        Lỗi của lần mở lại được báo qua late_problems.
        """
        self._require_page()
        key = self._viewport_key(viewport) if viewport else self.viewport
        if key != self.viewport:
            self._load(self.url, key)
        width, height, _, _ = VIEWPORTS[key]
        self._restore_window()
        self._repaint()
        params: dict = {"format": "png"}
        cut = False
        if full_page:
            content = self._call("Page.getLayoutMetrics").get("cssContentSize") or {}
            total = int(content.get("height") or height)
            cut = total > MAX_FULL_PAGE_HEIGHT
            height = max(1, min(total, MAX_FULL_PAGE_HEIGHT))
            params.update(clip={"x": 0, "y": 0, "width": width, "height": height, "scale": 1},
                          captureBeyondViewport=True)
        data = base64.b64decode(self._call("Page.captureScreenshot", params)["data"])
        mime = "image/png"
        for quality in (85, 70, 50):
            if len(data) <= MAX_SHOT_BYTES:
                break
            params.update(format="jpeg", quality=quality)
            data = base64.b64decode(self._call("Page.captureScreenshot", params)["data"])
            mime = "image/jpeg"
        if len(data) > MAX_SHOT_BYTES:
            raise BrowserError("Ảnh chụp quá lớn; chụp phần đang hiện thay vì cả trang.")
        return Shot(data, mime, width, height, key, bool(full_page), cut)

    def read(self, selector: str | None = None) -> dict:
        self._require_page()
        target = "document.body" if not selector else f"document.querySelector({json.dumps(selector)})"
        try:
            text = self._evaluate(f"(() => {{ const el = {target}; return el ? el.innerText : null; }})()")
        except BrowserError as err:
            raise BrowserError(f"Selector không hợp lệ: {selector} ({err})") from None
        if text is None:
            raise BrowserError(f"Không có phần tử nào khớp {selector}." if selector else "Trang chưa có nội dung.")
        lines = [" ".join(line.split()) for line in str(text).splitlines()]
        text = "\n".join(line for line in lines if line)
        return {"url": self.url, "text": text[:MAX_TEXT_CHARS], "chars": len(text),
                "truncated": len(text) > MAX_TEXT_CHARS}

    def late_problems(self) -> list[str]:
        """Lỗi tới sau lần báo trước: đọc thêm sự kiện một chút rồi trả phần mới."""
        if self.running:
            self._pump(0.2)
        return self.new_problems()

    # --- thao tác ------------------------------------------------------------------------------------------------

    def _find(self, target: str, prepare: bool = False) -> dict:
        """Phần tử theo số trong danh sách phần tử ([3]) hoặc CSS selector; lỗi thì nói rõ vì sao không dùng được."""
        target = str(target or "").strip()
        if not target:
            raise BrowserError("Thiếu phần tử cần thao tác: số trong danh sách phần tử (ví dụ 3) hoặc CSS selector.")
        found = self._script(FIND_SCRIPT, target, prepare) or {}
        error = found.get("error")
        what = found.get("desc") or target
        if error == "gone":
            raise BrowserError(f"Phần tử {target} không còn trên trang (trang đã đổi). Dùng số trong danh sách phần tử "
                               "của kết quả mới nhất, hoặc gọi browser_open để xem lại.")
        if error == "selector":
            raise BrowserError(f"CSS selector không hợp lệ: {target}.")
        if error == "none":
            raise BrowserError(f"Không có phần tử nào khớp {target}.")
        if error == "many":
            raise BrowserError(f"{target} khớp {found.get('count')} phần tử đang hiện: "
                               + "; ".join(found.get("sample") or []) + ". Dùng số trong ngoặc vuông.")
        if error == "hidden":
            raise BrowserError(f"{what} đang bị ẩn nên người dùng không thao tác được.")
        if error == "offscreen":
            raise BrowserError(f"{what} không cuộn vào màn hình được (kích thước 0 hoặc nằm ngoài khung).")
        return found

    def describe(self, kind: str, target: str | None = None, text: str | None = None, submit: bool = False,
                 key: str | None = None) -> str:
        """Câu tả thao tác sắp làm ("bấm nút "Gửi""), để hỏi quyền trước. Không đổi gì trên trang."""
        self._require_page()
        if kind == "press":
            return f"nhấn {key_name(key)}"
        return _action_text(kind, self._find(target), text, submit)

    def click(self, target: str, accept_dialog: bool = False) -> dict:
        return self._act("click", target=target, accept_dialog=accept_dialog)

    def type(self, target: str, text: str, submit: bool = False, accept_dialog: bool = False) -> dict:
        return self._act("type", target=target, text=text, submit=submit, accept_dialog=accept_dialog)

    def press(self, key: str, accept_dialog: bool = False) -> dict:
        return self._act("press", key=key, accept_dialog=accept_dialog)

    def _act(self, kind: str, *, target: str | None = None, text: str | None = None, submit: bool = False,
             key: str | None = None, accept_dialog: bool = False) -> dict:
        self._require_page()
        before = self._script(SNAPSHOT_SCRIPT, MAX_OUTLINE * 2, True) or {}
        self.loading = self.stopped = self.navigated = False
        self.blocked = None
        self.accept_dialog = accept_dialog
        extra: dict = {}
        try:
            if kind == "press":
                name = key_name(key)
                self._key(name)
                action = f"nhấn {name}"
            else:
                found = self._find(target, prepare=True)
                extra = self._click(found) if kind == "click" else self._type(found, text or "", submit)
                action = _action_text(kind, found, extra.get("chosen", text), submit)
                if found.get("retargeted"):
                    self.notes.add("Liên kết mở tab mới; Peto mở nó ngay trong tab đang xem.")
            self._after_action()
        finally:
            self.accept_dialog = False
        after = self._script(SNAPSHOT_SCRIPT, MAX_OUTLINE * 2, True) or {}
        final = after.get("url") or self.url
        if not _local_url(final):
            self._leave(f"Trang chuyển sang {urlsplit(final).hostname or final}, ngoài máy này.")
        self.url = final
        result = {"action": action, "url": final, "title": after.get("title") or "", **extra,
                  **_changes(before, after, new_page=self.navigated)}
        if kind == "press" and after.get("focus"):
            result["focus"] = after["focus"]
        self._remember_cookies()
        return self._report(result)

    def _mouse(self, x: float, y: float) -> None:
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self._call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left",
                                                    "clickCount": 0 if kind == "mouseMoved" else 1})

    def _key(self, name: str) -> None:
        key, code, number, text, modifiers = KEYS[name]
        base = {"key": key, "code": code, "windowsVirtualKeyCode": number, "nativeVirtualKeyCode": number,
                "modifiers": modifiers}
        self._call("Input.dispatchKeyEvent", {"type": "keyDown" if text else "rawKeyDown", **base,
                                              **({"text": text, "unmodifiedText": text} if text else {})})
        self._call("Input.dispatchKeyEvent", {"type": "keyUp", **base})

    def _reachable(self, found: dict) -> None:
        if found.get("disabled"):
            raise BrowserError(f"{found['desc']} đang bị tắt nên bấm không có tác dụng.")
        if found.get("covered"):
            raise BrowserError(f"{found['desc']} đang bị {found['covered']} che nên người dùng không bấm được. Đóng "
                               "phần che trước (nút đóng, Escape) rồi thử lại.")

    def _click(self, found: dict) -> dict:
        if found.get("kind") == "select":
            raise BrowserError("Đây là hộp chọn: dùng browser_type với chữ của lựa chọn cần chọn.")
        self._reachable(found)
        self._mouse(found["x"], found["y"])
        return {}

    def _type(self, found: dict, text: str, submit: bool) -> dict:
        kind = found.get("kind")
        if found.get("secret"):
            raise BrowserError("Peto không gõ vào ô mật khẩu. Cần đăng nhập thì gọi browser_login để người dùng tự đăng "
                               "nhập trong cửa sổ trình duyệt.")
        if len(text) > MAX_TYPED_CHARS:
            raise BrowserError(f"Chữ cần gõ dài quá {MAX_TYPED_CHARS} ký tự.")
        if kind == "select":
            chosen = self._script(CHOOSE_SCRIPT, found["ref"], text) or {}
            if not chosen.get("chosen"):
                options = ", ".join(f'"{option}"' for option in chosen.get("options") or [])
                raise BrowserError(f"{found['desc']} không có lựa chọn \"{text}\". Có: {options or '(trống)'}.")
            if submit:
                self._key("Enter")
            return {"chosen": chosen["chosen"]}
        if kind != "text":
            raise BrowserError(f"{found['desc']} không gõ chữ vào được; ô chọn, nút và liên kết thì dùng "
                               "browser_click.")
        self._reachable(found)
        if found.get("readonly"):
            raise BrowserError(f"{found['desc']} chỉ đọc, không gõ vào được.")
        # Bấm vào ô như người dùng để trang thấy focus thật, rồi chọn hết chữ cũ để gõ đè.
        self._mouse(found["x"], found["y"])
        if not self._script(SELECT_ALL_SCRIPT, found["ref"]):
            raise BrowserError(f"{found['desc']} biến mất ngay khi được bấm vào nên không gõ được.")
        if text:
            self._call("Input.insertText", {"text": text})
        else:
            self._key("Delete")
        value = self._script(VALUE_SCRIPT, found["ref"])
        if submit:
            self._key("Enter")
        return {"value": _clip(value, 200)} if isinstance(value, str) else {}

    def _after_action(self) -> None:
        """Chờ hậu quả của thao tác: trang mới thì chờ tải xong; không thì chờ mạng yên và DOM thôi đổi."""
        deadline = time.monotonic() + NAVIGATION_GRACE
        while time.monotonic() < deadline and not self.loading:
            self._pump(0.05)
        if self.loading:
            self._settle(time.monotonic())
        else:
            self._quiet()
        try:
            self._call("Runtime.evaluate", {"expression": DOM_QUIET_SCRIPT, "awaitPromise": True})
        except BrowserError:
            if not self.running:
                raise
            # Trang chuyển đi giữa lúc đang chờ: chờ trang mới tải xong.
            self._settle(time.monotonic())

    # --- người dùng tự làm trong cửa sổ ---------------------------------------------------------------------------

    def hand_over(self, wait: Callable[[], bool]) -> dict:
        """Hiện cửa sổ ở trang đang xem để người dùng tự đăng nhập, rồi chờ ``wait()`` (họ quay lại terminal).

        Trong lúc đó Peto không chặn trang ngoài (đăng nhập bằng Discord, Google phải qua trang của họ), không trả lời
        hộp thoại thay và không đóng cửa sổ bật lên. Xong thì bật lại các chặn, bỏ những lỗi của các trang đăng nhập và
        đọc lại trang đang mở. Trang cuối cùng ở ngoài máy thì quay về trang Peto đang xem trước đó.
        """
        self._require_page()
        back = self.url
        self.set_visible(True)
        self.handing_over = True
        try:
            self._guard(False)
            self._call("Page.bringToFront")
            done = wait()
        finally:
            self.handing_over = False
        try:
            self._guard(True)
            self._drain()
        except BrowserError:
            raise BrowserError("Cửa sổ trình duyệt đã bị đóng trước khi xong. Gọi browser_open để mở lại trang.")                 from None
        # Lỗi, hộp thoại của các trang đăng nhập không phải của trang đang làm.
        for feed in (self.problems, self.dialogs, self.notes):
            feed.fresh()
        self.inflight.clear()
        page = self._script(SNAPSHOT_SCRIPT, MAX_OUTLINE, False) or {}
        if not _local_url(page.get("url") or ""):
            self._load(back, self.viewport)
            page = self._script(SNAPSHOT_SCRIPT, MAX_OUTLINE, False) or {}
        self.url = page.get("url") or back
        self._remember_cookies()
        return {"done": done, "url": self.url, "title": page.get("title") or "", "outline": page.get("outline") or []}


def _action_text(kind: str, found: dict, text: str | None, submit: bool) -> str:
    """"bấm nút "Gửi"", "gõ "2" vào ô "Số vé"", "chọn "VIP" trong hộp chọn "Ghế"", để hỏi quyền và in ra terminal."""
    role, name = found.get("role") or "phần tử", found.get("name") or ""
    label = f'{role} "{_clip(name, 60)}"' if name else f"{role} [{found.get('ref')}]"
    if kind == "click":
        return f"bấm {label}"
    if found.get("kind") == "select":
        return f'chọn "{_clip(text or "", 60)}" trong {label}' + (" rồi nhấn Enter" if submit else "")
    place = label.replace("ô nhập ", "ô ", 1)
    if not text:
        return f"xóa chữ trong {place}" + (" rồi nhấn Enter" if submit else "")
    return f'gõ "{_clip(text, 60)}" vào {place}' + (" rồi nhấn Enter" if submit else "")


def _new_lines(before: list[str], after: list[str]) -> list[str]:
    """Dòng chữ có chữ mới sau thao tác, so theo từng từ chứ không theo dòng.

    innerText gộp các phần tử cùng dòng (nút, liên kết) thành một dòng; một hộp hiện ra giữa hai nút làm dòng đó tách
    đôi, và so theo dòng thì báo cả hai nửa là "mới". So theo từ thì chỉ dòng nào có từ thật sự mới mới được báo, và
    báo cả dòng để còn ngữ cảnh ("Số vé: 2" chứ không chỉ "2"). Trang quá nhiều chữ thì so theo dòng cho nhanh.
    """
    words = [(word, index) for index, line in enumerate(after) for word in line.split()]
    old = [word for line in before for word in line.split()]
    if len(old) > MAX_DIFF_WORDS or len(words) > MAX_DIFF_WORDS:
        seen = set(before)
        return [line for index, line in enumerate(after) if line not in seen and line not in after[:index]]
    touched: set[int] = set()
    matcher = difflib.SequenceMatcher(None, old, [word for word, _ in words], autojunk=False)
    for tag, _, _, start, end in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            touched.update(index for _, index in words[start:end])
    return [after[index] for index in sorted(touched)]


def _changes(before: dict, after: dict, *, new_page: bool) -> dict:
    """Những gì đổi sau thao tác: địa chỉ, dòng chữ mới hiện, phần tử mới hiện hoặc vừa đổi trạng thái."""
    result: dict = {}
    if new_page:
        result["new_page"] = True
    elif (after.get("url") or "") != (before.get("url") or ""):
        result["moved"] = True
    appeared, total = [], 0
    for line in _new_lines(before.get("lines") or [], after.get("lines") or []):
        if len(appeared) >= MAX_APPEARED_LINES or total >= MAX_APPEARED_CHARS:
            break
        appeared.append(_clip(line, 200))
        total += len(appeared[-1])
    if appeared:
        result["appeared"] = appeared
    if new_page:
        result["outline"] = (after.get("outline") or [])[:MAX_OUTLINE]
    else:
        old = set(before.get("outline") or [])
        changed = [item for item in after.get("outline") or [] if item not in old]
        if changed:
            result["elements"] = changed[:MAX_CHANGED_ELEMENTS]
    return result


# --- JavaScript chạy trong trang --------------------------------------------------------------------------------------

# Phần dùng chung: số thứ tự của phần tử (giữ nguyên tới khi trang sang tài liệu khác, vì nằm trên window), vai trò và
# tên gần đúng như trình đọc màn hình, trạng thái. Không bao giờ đọc chữ trong ô mật khẩu (secret): kể cả ô đang bật
# "hiện mật khẩu" (đổi sang type=text) vẫn được nhận ra qua autocomplete, tên, id, placeholder.
PRELUDE = r"""
  const P = window[Symbol.for('peto')] || (window[Symbol.for('peto')] = {map: new WeakMap(), refs: [], next: 1});
  const INTERACTIVE = 'a[href],button,input:not([type=hidden]),textarea,select,summary,[role=button],[role=link],'
    + '[role=tab],[role=menuitem],[role=checkbox],[role=radio],[role=switch],[role=option],[role=combobox],'
    + '[role=textbox],[contenteditable=""],[contenteditable=true],[onclick]';
  const TEXTLESS = ['checkbox', 'radio', 'submit', 'button', 'reset', 'image', 'file', 'range', 'color'];
  const clean = (text, max) => {
    const value = String(text || '').replace(/\s+/g, ' ').trim();
    return value.length > max ? value.slice(0, max - 1) + '…' : value;
  };
  const shown = (el) => el.checkVisibility
    ? el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) : el.getClientRects().length > 0;
  const ref = (el) => {
    let n = P.map.get(el);
    if (!n) { n = P.next++; P.map.set(el, n); P.refs[n] = new WeakRef(el); }
    return n;
  };
  const byRef = (n) => { const el = P.refs[n] && P.refs[n].deref(); return el && el.isConnected ? el : null; };
  const typeOf = (el) => (el.getAttribute('type') || '').toLowerCase();
  const secret = (el) => {
    if (el.tagName !== 'INPUT') return false;
    if (typeOf(el) === 'password' || /password/i.test(el.getAttribute('autocomplete') || '')) return true;
    const hints = [el.name, el.id, el.getAttribute('placeholder'), el.getAttribute('aria-label')].join(' ');
    return /pass(word|wd)?(?![a-z])|pwd|mật khẩu|mat[-_ ]?khau/i.test(hints);
  };
  const kindOf = (el) => {
    const tag = el.tagName.toLowerCase(), type = typeOf(el), aria = el.getAttribute('role');
    if (tag === 'input') {
      if (type === 'checkbox' || type === 'radio') return 'check';
      if (type === 'file') return 'file';
      if (['submit', 'button', 'reset', 'image', 'range', 'color'].includes(type)) return 'other';
      return 'text';
    }
    if (tag === 'select') return 'select';
    if (tag === 'textarea' || el.isContentEditable || aria === 'textbox') return 'text';
    if (['checkbox', 'radio', 'switch'].includes(aria)) return 'check';
    return 'other';
  };
  const roleOf = (el) => {
    const tag = el.tagName.toLowerCase(), type = typeOf(el), aria = (el.getAttribute('role') || '').toLowerCase();
    if (tag === 'input') {
      if (secret(el)) return 'ô mật khẩu';
      return {checkbox: 'ô chọn', radio: 'ô chọn tròn', submit: 'nút', button: 'nút', reset: 'nút', image: 'nút',
              file: 'ô chọn tệp', range: 'thanh trượt', color: 'ô chọn màu'}[type] || 'ô nhập';
    }
    const byRole = {button: 'nút', link: 'liên kết', tab: 'thẻ', menuitem: 'mục menu', checkbox: 'ô chọn',
                    radio: 'ô chọn tròn', switch: 'công tắc', option: 'lựa chọn', combobox: 'hộp chọn',
                    textbox: 'ô nhập'}[aria];
    if (byRole) return byRole;
    const byTag = {a: 'liên kết', button: 'nút', textarea: 'ô nhập', select: 'hộp chọn', summary: 'mục mở rộng',
                   h1: 'tiêu đề 1', h2: 'tiêu đề 2', h3: 'tiêu đề 3', img: 'ảnh'}[tag];
    if (byTag) return byTag;
    return el.isContentEditable ? 'ô soạn thảo' : 'phần tử bấm được';
  };
  const nameOf = (el) => {
    const tag = el.tagName.toLowerCase(), type = typeOf(el);
    const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map((id) => { const item = id && document.getElementById(id); return item ? item.innerText : ''; }).join(' ');
    const label = clean(el.getAttribute('aria-label') || labelled, 80);
    if (label) return label;
    if (tag === 'img' || (tag === 'input' && type === 'image')) return clean(el.getAttribute('alt'), 80);
    if (el.labels && el.labels.length) {
      // Nhãn bọc cả ô (<label>Ghế <select>…</select></label>): bỏ chữ của chính các ô ra khỏi tên.
      const text = clean([...el.labels].map((item) => {
        const copy = item.cloneNode(true);
        copy.querySelectorAll('input,select,textarea,button').forEach((control) => control.remove());
        return copy.textContent;
      }).join(' '), 80);
      if (text) return text;
    }
    if (tag === 'input' && ['submit', 'button', 'reset'].includes(type)) return clean(el.value, 80);
    if (['input', 'textarea', 'select'].includes(tag)) {
      return clean(el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('name'), 80);
    }
    return clean(el.innerText || el.getAttribute('title') || el.getAttribute('placeholder'), 80);
  };
  const stateOf = (el) => {
    const tag = el.tagName.toLowerCase(), type = typeOf(el), aria = el.getAttribute('role');
    let state = '';
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') state += ' (bị tắt)';
    if (tag === 'input' && (type === 'checkbox' || type === 'radio')) {
      state += el.checked ? ' (đã chọn)' : ' (chưa chọn)';
    } else if (['checkbox', 'radio', 'switch'].includes(aria)) {
      state += el.getAttribute('aria-checked') === 'true' ? ' (đã chọn)' : ' (chưa chọn)';
    }
    if (el.hasAttribute('aria-expanded')) {
      state += el.getAttribute('aria-expanded') === 'true' ? ' (đang mở)' : ' (đang đóng)';
    }
    if (secret(el)) {
      if (el.value) state += ' (đã nhập)';
    } else if (tag === 'select') {
      const option = el.selectedOptions && el.selectedOptions[0];
      if (option) state += ' = "' + clean(option.text, 40) + '"';
    } else if ((tag === 'textarea' || (tag === 'input' && !TEXTLESS.includes(type))) && el.value) {
      state += ' = "' + clean(el.value, 40) + '"';
    }
    return state;
  };
  const describe = (el) => roleOf(el) + ': ' + (nameOf(el) || '(không có tên)') + stateOf(el);
  const entry = (el) => (el.matches(INTERACTIVE) ? '[' + ref(el) + '] ' : '') + describe(el);
"""

# Tiêu đề, địa chỉ và các phần tử đang hiện: tiêu đề, liên kết, nút, ô nhập, ảnh (ảnh thiếu alt được ghi rõ; ảnh
# alt="" là ảnh trang trí nên bỏ qua). Phần tử thao tác được có số trong ngoặc vuông. Kèm các dòng chữ trên trang khi
# cần so trước và sau một thao tác.
SNAPSHOT_SCRIPT = r"""(max, withLines) => {
  /*PRELUDE*/
  const outline = [];
  let total = 0;
  for (const el of document.querySelectorAll('h1,h2,h3,img,' + INTERACTIVE)) {
    if (!shown(el)) continue;
    const interactive = el.matches(INTERACTIVE);
    if (el.tagName === 'IMG' && !interactive && el.getAttribute('alt') === '') continue;
    total += 1;
    if (outline.length >= max) continue;
    if (el.tagName === 'IMG' && !interactive && !el.hasAttribute('alt')) {
      outline.push('ảnh: (thiếu alt) ' + (el.getAttribute('src') || '').slice(-60));
    } else {
      outline.push(entry(el));
    }
  }
  const text = document.body ? document.body.innerText : '';
  const active = document.activeElement;
  const result = {url: location.href, title: document.title, outline, total, chars: text.length,
                  focus: active && active !== document.body && active.matches && active.matches(INTERACTIVE)
                    ? entry(active) : null};
  if (withLines) {
    result.lines = text.split('\n').map((line) => line.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 4000);
  }
  return result;
}"""

# Tìm phần tử theo số hoặc CSS selector. Khi sắp thao tác (prepare): cuộn nó vào giữa màn hình, lấy điểm giữa, xem có
# gì đè lên không (lớp phủ, hộp thoại che), và đổi liên kết, form mở tab mới thành mở ngay trong tab này.
FIND_SCRIPT = r"""(target, prepare) => {
  /*PRELUDE*/
  let el = null;
  const number = /^\s*\[?\s*(\d+)\s*\]?\s*$/.exec(target);
  if (number) {
    el = byRef(Number(number[1]));
    if (!el) return {error: 'gone'};
  } else {
    let all;
    try { all = [...document.querySelectorAll(target)]; } catch (error) { return {error: 'selector'}; }
    const visible = all.filter(shown);
    if (!visible.length) return {error: all.length ? 'hidden' : 'none'};
    if (visible.length > 1) {
      return {error: 'many', count: visible.length,
              sample: visible.slice(0, 5).map((item) => '[' + ref(item) + '] ' + describe(item))};
    }
    el = visible[0];
  }
  const info = {ref: ref(el), role: roleOf(el), name: nameOf(el), desc: describe(el), kind: kindOf(el),
                secret: secret(el), disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                readonly: !!el.readOnly};
  if (!shown(el)) return {...info, error: 'hidden'};
  if (!prepare) return info;
  el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
  const box = el.getBoundingClientRect();
  const x = box.left + box.width / 2, y = box.top + box.height / 2;
  if (!box.width || !box.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) {
    return {...info, error: 'offscreen'};
  }
  const top = document.elementFromPoint(x, y);
  const labels = el.labels ? [...el.labels] : [];
  if (top && top !== el && !el.contains(top) && !top.contains(el) && !labels.some((label) => label.contains(top))) {
    const cover = top.closest(INTERACTIVE) || top;
    info.covered = cover.matches(INTERACTIVE) ? describe(cover)
      : cover.tagName.toLowerCase() + (cover.id ? '#' + cover.id : '')
        + (cover.classList.length ? '.' + [...cover.classList].slice(0, 2).join('.') : '');
  }
  const opener = el.closest('a[target]') || (el.form && el.form.getAttribute('target') ? el.form : null);
  if (opener && !['', '_self', '_top', '_parent'].includes((opener.getAttribute('target') || '').toLowerCase())) {
    opener.setAttribute('target', '_self');
    info.retargeted = true;
  }
  return {...info, x, y};
}"""

# Chọn trong hộp chọn theo chữ hiện của lựa chọn (không phân biệt hoa thường), rồi theo value, rồi theo chữ chứa.
CHOOSE_SCRIPT = r"""(n, wanted) => {
  /*PRELUDE*/
  const el = byRef(n);
  if (!el || !el.options) return {};
  const norm = (text) => String(text).replace(/\s+/g, ' ').trim().toLowerCase();
  const options = [...el.options];
  const pick = options.find((option) => norm(option.text) === norm(wanted))
    || options.find((option) => option.value === wanted)
    || (norm(wanted) ? options.find((option) => norm(option.text).includes(norm(wanted))) : null);
  if (!pick) return {options: options.map((option) => clean(option.text, 40)).slice(0, 15)};
  el.focus();
  el.value = pick.value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return {chosen: clean(pick.text, 60)};
}"""

# Chọn hết chữ đang có trong ô để chữ gõ vào thay thế nó.
SELECT_ALL_SCRIPT = r"""(n) => {
  /*PRELUDE*/
  const el = byRef(n);
  if (!el) return false;
  el.focus();
  if (typeof el.select === 'function') {
    el.select();
  } else {
    const range = document.createRange();
    range.selectNodeContents(el);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  return true;
}"""

# Chữ đang có trong ô sau khi gõ, để Peto thấy trang có nhận đủ không (maxlength, ô số…). Ô mật khẩu thì không đọc.
VALUE_SCRIPT = r"""(n) => {
  /*PRELUDE*/
  const el = byRef(n);
  if (!el || secret(el)) return null;
  return el.isContentEditable ? el.innerText : el.value;
}"""

# Chờ DOM thôi đổi 250 ms (tối đa 2 giây) sau thao tác: hiệu ứng mở hộp thoại, danh sách hiện dần.
DOM_QUIET_SCRIPT = """new Promise((resolve) => {
  let timer = null, cap = null;
  const finish = () => { observer.disconnect(); clearTimeout(timer); clearTimeout(cap); resolve(true); };
  const observer = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(finish, %d); });
  observer.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  timer = setTimeout(finish, %d);
  cap = setTimeout(finish, %d);
})""" % (DOM_QUIET_MS, DOM_QUIET_MS, MAX_DOM_WAIT_MS)


def _launch_env() -> dict[str, str]:
    """Môi trường cho trình duyệt, bỏ __COMPAT_LAYER.

    Windows có khi gắn lớp tương thích (ví dụ ``__COMPAT_LAYER=DetectorsAppHealth``) vào cả cây tiến trình của một ứng
    dụng. Edge thấy biến này thì tự mở lại chính nó không kèm lớp đó rồi thoát tiến trình đầu (gặp ngày 2026-09-23).
    Bỏ biến trước thì Edge chạy thẳng; nếu vẫn tự mở lại thì tiến trình mới là con của tiến trình đầu, nên vẫn nằm
    trong job và vẫn bị tắt theo peto.
    """
    return {key: value for key, value in os.environ.items() if key.upper() != "__COMPAT_LAYER"}


def _name_profile(profile: Path) -> None:
    """Đặt tên hồ sơ là "Peto" trước lần mở đầu, để cửa sổ hiện "… - Peto - Microsoft Edge" chứ không phải "Personal"
    như hồ sơ thường của người dùng (thấy ngày 2026-09-23): nhìn là biết cửa sổ của Peto."""
    state = profile / "Local State"
    if state.exists():
        return
    try:
        state.write_text(json.dumps({"profile": {"info_cache": {"Default": {
            "name": "Peto", "is_using_default_name": False, "shortcut_name": "Peto"}}}}), encoding="utf-8")
    except OSError:
        pass


def _touch(path: Path) -> None:
    try:
        path.touch()
    except OSError:
        pass


def _released(profile: Path, seconds: float) -> bool:
    """Chờ tối đa ``seconds`` giây cho tới khi không trình duyệt nào còn chạy trên hồ sơ: trên Windows, trình duyệt giữ
    tệp lockfile suốt lúc chạy (không xóa được) và Windows xóa nó khi tiến trình cuối cùng chết."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            (profile / "lockfile").unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)


def _hold(profile: Path):
    """Giữ tệp peto.lock mở suốt phiên, để phiên peto khác biết hồ sơ này đang có chủ: không dùng chung, không dọn nhầm.

    Windows không cho tiến trình khác xóa tệp đang mở; hệ khác dùng khóa flock. Trình duyệt còn chạy trên hồ sơ (giữ
    tệp lockfile của nó) cũng tính là đang có chủ. Hồ sơ đang có chủ thì ném OSError.
    """
    path = profile / PROFILE_LOCK
    if os.name == "nt":
        try:
            path.unlink()  # tệp của một phiên đã tắt thì xóa được
        except FileNotFoundError:
            pass
        handle = open(path, "x", encoding="utf-8")  # noqa: SIM115 (giữ mở tới hết phiên)
    else:
        import fcntl

        handle = open(path, "a", encoding="utf-8")  # noqa: SIM115
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise
    if not _released(profile, 2.0):
        handle.close()
        raise OSError("hồ sơ đang được một trình duyệt khác dùng")
    return handle


def _held(profile: Path) -> bool:
    """Hồ sơ đang có phiên peto khác giữ: trên Windows là tệp peto.lock còn đó mà không xóa được."""
    lock = profile / PROFILE_LOCK
    if not lock.exists():
        return False
    if os.name != "nt":
        import fcntl

        try:
            with open(lock, "a", encoding="utf-8") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        return False
    try:
        lock.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return False


def _prune_profiles() -> None:
    """Xóa hồ sơ tạm không trình duyệt nào còn dùng, thường của lần peto bị tắt đột ngột (job đã tắt trình duyệt
    nhưng không ai kịp xóa thư mục). Không được đụng hồ sơ của một phiên peto khác đang chạy song song.

    Trên Windows, trình duyệt giữ tệp ``lockfile`` trong hồ sơ suốt lúc chạy nên không xóa được tệp đó, và Windows tự
    xóa tệp ấy khi trình duyệt chết (đã thử ngày 2026-09-23). Peto cũng giữ ``peto.lock`` suốt phiên, kể cả lúc trình
    duyệt tắt giữa chừng để đổi ẩn/hiện. Vậy hồ sơ không có peto.lock đang bị giữ, xóa được lockfile hay không còn
    lockfile mà thư mục đã yên hơn một phút, là không ai dùng; thư mục mới hơn có thể của một phiên vừa mở và trình
    duyệt chưa kịp tạo lockfile. Hệ khác cho xóa cả tệp đang mở, nên chỉ dọn hồ sơ cũ hơn một ngày.
    """
    now = time.time()
    try:
        folders = [path for path in Path(tempfile.gettempdir()).glob(PROFILE_PREFIX + "*") if path.is_dir()]
    except OSError:
        return
    for path in folders:
        try:
            age = now - path.stat().st_mtime
            if os.name != "nt":
                if age < STALE_PROFILE_SECONDS:
                    continue
            elif _held(path):
                continue
            elif (path / "lockfile").exists():
                (path / "lockfile").unlink()
            elif age < STARTING_PROFILE_SECONDS:
                continue
        except OSError:
            continue
        shutil.rmtree(path, ignore_errors=True)


def project_profile(root: Path) -> Path:
    """Hồ sơ trình duyệt riêng của một dự án, trong %LOCALAPPDATA%\\PetoAgent\\browser: giữ đăng nhập người dùng tự
    làm trong cửa sổ của Peto (chủ web chọn ngày 2026-09-23). Tên có mã băm đường dẫn để hai dự án trùng tên không
    dùng chung."""
    key = os.path.normcase(str(root))
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in root.name)[:40] or "du-an"
    return browser_profiles_dir() / f"{safe}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"


def forget_project(root: Path) -> bool:
    """/trinhduyet xoa: xóa hồ sơ của dự án (đăng nhập, cookie, dữ liệu trang). False khi phiên peto khác đang dùng."""
    profile = project_profile(root)
    if not profile.exists():
        return True
    if _held(profile) or not _released(profile, 3.0):
        return False
    for _ in range(15):
        shutil.rmtree(profile, ignore_errors=True)
        if not profile.exists():
            return True
        time.sleep(0.2)
    return not profile.exists()


def _prune_project_profiles(keep: Path | None = None) -> None:
    """Dọn hồ sơ của những dự án 30 ngày chưa mở lại trình duyệt, trừ hồ sơ đang có phiên giữ."""
    cutoff = time.time() - PROJECT_PROFILE_DAYS * 24 * 3600
    try:
        folders = [path for path in browser_profiles_dir().iterdir() if path.is_dir() and path != keep]
    except OSError:
        return
    for path in folders:
        try:
            used = (path / LAST_USED).stat().st_mtime if (path / LAST_USED).exists() else path.stat().st_mtime
            if used >= cutoff or _held(path):
                continue
        except OSError:
            continue
        shutil.rmtree(path, ignore_errors=True)


def store(project: str, shot: Shot) -> Path | None:
    """Lưu ảnh để người dùng mở xem, giữ 7 ngày. Không lưu được thì thôi: Peto vẫn nhận ảnh."""
    folder = screenshots_dir()
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in project)[:40] or "du-an"
    extension = "png" if shot.mime == "image/png" else "jpg"
    path = folder / f"{safe}-{datetime.now():%m%d-%H%M%S}-{next(_shot_numbers)}.{extension}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(shot.data)
    except OSError:
        return None
    cutoff = time.time() - SCREENSHOT_DAYS * 24 * 3600
    try:
        for old in folder.iterdir():
            if old.is_file() and old.stat().st_mtime < cutoff:
                old.unlink()
    except OSError:
        pass
    return path
