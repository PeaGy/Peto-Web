"""Trình duyệt chạy ẩn để Peto xem trang web đang chạy trên máy người dùng (đợt 1: chỉ xem, không bấm hay gõ).

Chủ web chọn ngày 2026-09-23: Edge (hoặc Chrome) chạy ẩn, ảnh chụp được lưu để người dùng mở xem, mỗi lần xem báo kèm
tối đa 5 lỗi, và xem trang trên máy không hỏi quyền (như đọc tệp).

- Chỉ dùng thư viện chuẩn: điều khiển trình duyệt qua giao thức DevTools (CDP) bằng một máy khách WebSocket nhỏ.
- Hồ sơ trình duyệt riêng trong thư mục tạm, xóa khi đóng: không có tài khoản, cookie hay tiện ích của người dùng.
- Chỉ mở http(s) tới máy này (localhost, 127.x, ::1, *.localhost). Trang ngoài là đường rò dữ liệu (Peto đọc tệp rồi
  mở một địa chỉ chứa nội dung đó) và là chỗ trang lạ nhét chỉ dẫn vào; file:// thì đọc được tệp ngoài dự án.
- Edge là ứng dụng có cửa sổ nên không tắt theo console như lệnh nền. Trên Windows, nó được tạo ở trạng thái tạm dừng,
  gắn vào một job object "tắt hết khi đóng" rồi mới chạy: peto chết kiểu gì (kể cả bấm X đóng cửa sổ terminal) thì
  Windows cũng tắt cả cây tiến trình Edge. Đã thử ngày 2026-09-23.
"""

from __future__ import annotations

import base64
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
from urllib.parse import urlsplit

from . import runner
from .config import screenshots_dir
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
MAX_OUTLINE = 60
MAX_TEXT_CHARS = 20000
MAX_TRACKED_REQUESTS = 5000
# Ảnh gửi cho model: máy chủ nhận tối đa 3 MB mỗi ảnh; giữ dưới 2 MB, quá thì chuyển JPEG.
MAX_SHOT_BYTES = 2_000_000
MAX_FULL_PAGE_HEIGHT = 4000
SCREENSHOT_DAYS = 7
PROFILE_PREFIX = "peto-browser-"
STALE_PROFILE_SECONDS = 24 * 3600
STARTING_PROFILE_SECONDS = 60
# Request bị hủy khi trang chuyển đi hay tải lại không phải lỗi của trang.
IGNORED_FAILURES = {"net::ERR_ABORTED"}

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
        raise BrowserError("Đợt này Peto chỉ xem trang chạy trên máy (localhost, 127.0.0.1); trang ngoài và "
                           "địa chỉ file://, javascript:, data: không mở được.")
    return text


def _short(url: str, base: str) -> str:
    """Địa chỉ gọn cho dòng lỗi: cùng máy chủ với trang thì bỏ phần đầu."""
    base_parts, parts = urlsplit(base), urlsplit(url)
    if (parts.scheme, parts.netloc) == (base_parts.scheme, base_parts.netloc):
        url = parts.path + (f"?{parts.query}" if parts.query else "")
    return url if len(url) <= 160 else url[:159] + "…"


def _clip(text: str, limit: int = MAX_PROBLEM_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def viewport_label(key: str) -> str:
    width, height, _, label = VIEWPORTS[key]
    return f"{label} {width}×{height}"


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


class Browser:
    """Một trình duyệt chạy ẩn cho cả phiên peto: mở khi Peto xem trang lần đầu, đóng khi phiên kết thúc."""

    def __init__(self, executable: str | None = None):
        self.executable = executable
        self.process: subprocess.Popen | None = None
        self.profile: Path | None = None
        self.job: _Job | None = None
        self.ws: WebSocket | None = None
        self.next_id = 0
        self.viewport: str | None = None
        self.frame: str | None = None
        self.url: str | None = None
        # Lỗi đã báo cho trang đang xem: mở lại chỉ để đổi khung chụp thì không báo lại đúng những lỗi ấy.
        self.known: set[str] = set()
        self._reset_page()

    # --- vòng đời ------------------------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        # Theo kết nối DevTools chứ không theo tiến trình đã mở: Edge có thể tự mở lại chính nó rồi thoát tiến trình
        # đầu (xem _launch_env). Kết nối hỏng thì _call đóng hết, lần xem sau mở lại.
        return self.ws is not None

    def _start(self) -> None:
        if self.running:
            return
        self.close()
        executable = self.executable or find_browser()
        if not executable:
            raise BrowserError("Máy này chưa có Microsoft Edge hay Google Chrome nên Peto chưa xem trang được.")
        _prune_profiles()
        self.profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))
        args = [executable, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={self.profile}",
                "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                "--disable-background-networking", "--disable-component-update", "--hide-scrollbars", "--mute-audio",
                "--window-size=1280,800", "about:blank"]
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
            self.frame = self._call("Page.getFrameTree")["frameTree"]["frame"]["id"]
            self.viewport = None
            self._set_viewport("desktop")
        except (OSError, ConnectionError, ValueError, KeyError, StopIteration) as err:
            self.close()
            raise BrowserError(f"Không mở được trình duyệt ({err}).") from None

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

    def close(self) -> None:
        """Đóng trình duyệt và xóa hồ sơ tạm. Gọi nhiều lần cũng được, kể cả khi kết nối đã mất."""
        ws, process, job, profile = self.ws, self.process, self.job, self.profile
        self.ws = self.process = self.job = self.profile = None
        self.url = None
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
        if profile is not None:
            # Trình duyệt vừa tắt có thể còn giữ tệp một lúc: thử lại vài lần; còn sót thì lần mở sau dọn.
            for _ in range(15):
                shutil.rmtree(profile, ignore_errors=True)
                if not profile.exists():
                    break
                time.sleep(0.2)

    # --- DevTools ------------------------------------------------------------------------------------------------

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
            # chờ thêm 30 giây mỗi lần: đóng hẳn để lần xem sau mở trình duyệt mới.
            self.close()
            raise BrowserError(f"Trình duyệt không trả lời sau {int(timeout)} giây (trang bị treo?); lần xem sau "
                               "sẽ mở trình duyệt mới.") from None
        except (ConnectionError, OSError, ValueError):
            self.close()
            raise BrowserError("Mất kết nối với trình duyệt; lần xem sau sẽ mở lại.") from None

    def _pump(self, seconds: float) -> None:
        """Đọc các sự kiện tới trong ``seconds`` giây: lỗi console tới muộn, request còn đang chạy."""
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            try:
                self._event(json.loads(self.ws.recv(left)))
            except TimeoutError:
                return
            except (ConnectionError, OSError, ValueError):
                self.close()
                raise BrowserError("Mất kết nối với trình duyệt; lần xem sau sẽ mở lại.") from None

    def _reset_page(self) -> None:
        self.problems: list[str] = []
        self.reported = 0
        self.dialogs: list[str] = []
        self.dialogs_reported = 0
        self.inflight: set[str] = set()
        self.requests: dict[str, str] = {}
        self.last_network = time.monotonic()
        self.loaded = False
        self.status: int | None = None

    def _problem(self, text: str) -> None:
        text = _clip(text)
        if text and text not in self.problems and text not in self.known and len(self.problems) < MAX_PROBLEMS:
            self.problems.append(text)

    def _dialog(self, params: dict) -> None:
        """Trả lời ngay hộp thoại alert/confirm/prompt của trang.

        Hộp thoại chặn trang tới khi có người trả lời; không ai trả lời thì mọi lệnh sau đều treo (gặp ngày 2026-09-23:
        trang gọi alert() lúc tải làm browser_open chờ 50 giây rồi báo lỗi, và trình duyệt kẹt tới hết phiên). Peto chỉ
        xem nên alert thì đóng, confirm và prompt thì chọn Hủy (không thay người dùng đồng ý một việc có thể đổi dữ
        liệu), còn beforeunload thì cho rời trang vì chính Peto đang mở trang khác.
        """
        kind = params.get("type") or "alert"
        accept = kind in {"alert", "beforeunload"}
        self.next_id += 1
        # Gửi thẳng, không qua _call: đang ở giữa một _call khác, chờ lồng nhau sẽ nuốt mất câu trả lời của lệnh ngoài.
        self.ws.send(json.dumps({"id": self.next_id, "method": "Page.handleJavaScriptDialog",
                                 "params": {"accept": accept}}))
        if kind == "beforeunload":
            return
        text = f"{kind} \"{_clip(params.get('message', ''), 120)}\" ({'đã đóng' if accept else 'đã chọn Hủy'})"
        if text not in self.dialogs and text not in self.known:
            self.dialogs.append(text)

    def _event(self, message: dict) -> None:
        method, params = message.get("method"), message.get("params") or {}
        base = self.url or ""
        if method == "Page.javascriptDialogOpening":
            self._dialog(params)
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
                self._problem(f"request hỏng: {params.get('errorText')} {_short(url, base)}".rstrip())
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            status, url = int(response.get("status") or 0), response.get("url") or ""
            if params.get("type") == "Document" and params.get("frameId") == self.frame:
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
        fresh = self.problems[self.reported:]
        self.reported = len(self.problems)
        self.known.update(fresh)
        return fresh

    def new_dialogs(self) -> list[str]:
        """Hộp thoại trang đã mở (và Peto đã trả lời) kể từ lần báo trước; báo riêng vì hộp thoại không phải lỗi."""
        fresh = self.dialogs[self.dialogs_reported:]
        self.dialogs_reported = len(self.dialogs)
        self.known.update(fresh)
        return fresh

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
        """Chờ sự kiện load rồi chờ mạng yên, để ảnh không chụp phải trang trắng lúc JavaScript còn đang dựng."""
        deadline = started + LOAD_TIMEOUT
        while not self.loaded and time.monotonic() < deadline:
            self._pump(min(0.1, deadline - time.monotonic()))
        settle_until = time.monotonic() + MAX_SETTLE_SECONDS
        while time.monotonic() < settle_until:
            if not self.inflight and time.monotonic() - self.last_network >= QUIET_SECONDS:
                return
            self._pump(0.1)

    def _repaint(self) -> None:
        """Chờ hai khung hình, để trang kịp vẽ lại sau khi đổi khung nhìn."""
        self._call("Runtime.evaluate", {"expression": "new Promise(r => requestAnimationFrame(() => "
                                                       "requestAnimationFrame(r)))", "awaitPromise": True})

    def _evaluate(self, expression: str):
        result = self._call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise BrowserError(_clip((details.get("exception") or {}).get("description") or details.get("text", "")))
        return (result.get("result") or {}).get("value")

    def _require_page(self) -> None:
        if self.url is None or not self.running:
            raise BrowserError("Chưa mở trang nào: gọi browser_open trước.")

    def open(self, url: str, viewport: str | None = None) -> dict:
        """Mở (hoặc tải lại) một trang trên máy; trả tiêu đề, mã trạng thái, lỗi và các phần tử đang hiện.

        Peto chủ động mở lại (thường sau khi sửa code) thì báo lại đủ lỗi: lỗi còn đó nghĩa là chưa sửa được.
        """
        self.known = set()
        result = {**self._load(url, viewport), "problems": self.new_problems()}
        if dialogs := self.new_dialogs():
            result["dialogs"] = dialogs
        return result

    def _load(self, url: str, viewport: str | None) -> dict:
        target = check_url(url)
        self._start()
        key = self._set_viewport(viewport)
        self._reset_page()
        self.url = target
        started = time.monotonic()
        result = self._call("Page.navigate", {"url": target}, timeout=LOAD_TIMEOUT + 10)
        if result.get("errorText"):
            self.url = None
            raise BrowserError(f"Không mở được {target} ({result['errorText']}). Dev server đã chạy và đúng cổng chưa? "
                               "Chạy nó bằng start_command rồi đọc output để lấy đúng địa chỉ.")
        if result.get("loaderId"):
            self._settle(started)
        else:
            self._pump(QUIET_SECONDS)  # chỉ đổi phần # của địa chỉ: không có lần tải mới
        seconds = time.monotonic() - started
        page = self._evaluate(OUTLINE_SCRIPT % MAX_OUTLINE) or {}
        final = page.get("url") or target
        if not is_local(urlsplit(final).hostname):
            self._call("Page.navigate", {"url": "about:blank"})
            self.url = None
            raise BrowserError(f"Trang chuyển sang {urlsplit(final).hostname or final}, ngoài máy này; đợt này Peto "
                               "chỉ xem trang localhost.")
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


# Tiêu đề, địa chỉ và các phần tử đang hiện: tiêu đề, liên kết, nút, ô nhập, ảnh (ảnh thiếu alt được ghi rõ). Tên
# tính gần đúng như trình đọc màn hình: aria-label, chữ, alt, placeholder, title, giá trị.
OUTLINE_SCRIPT = """(() => {
  const roles = {h1: 'tiêu đề 1', h2: 'tiêu đề 2', h3: 'tiêu đề 3', a: 'liên kết', button: 'nút', select: 'hộp chọn',
                 textarea: 'ô nhập', img: 'ảnh'};
  const nodes = document.querySelectorAll('h1,h2,h3,a[href],button,input:not([type=hidden]),textarea,select,img,'
                                          + '[role=button],[role=link]');
  const outline = [];
  for (const el of nodes) {
    if (outline.length >= %d) break;
    if (!el.getClientRects().length) continue;
    const tag = el.tagName.toLowerCase();
    const aria = el.getAttribute('role');
    let role = aria === 'button' ? 'nút' : aria === 'link' ? 'liên kết' : roles[tag] || tag;
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      role = {checkbox: 'ô chọn', radio: 'ô chọn tròn', submit: 'nút', button: 'nút'}[type] || 'ô nhập';
    }
    if (tag === 'img' && !el.getAttribute('alt')) {
      outline.push('ảnh: (thiếu alt) ' + (el.getAttribute('src') || '').slice(-60));
      continue;
    }
    const name = (el.getAttribute('aria-label') || (tag === 'img' ? el.getAttribute('alt') : el.innerText)
      || el.getAttribute('placeholder') || el.getAttribute('title') || el.value || '').replace(/\\s+/g, ' ').trim();
    outline.push(role + ': ' + (name.slice(0, 80) || '(không có tên)'));
  }
  return {url: location.href, title: document.title, outline: outline, total: nodes.length,
          chars: document.body ? document.body.innerText.length : 0};
})()"""


def _launch_env() -> dict[str, str]:
    """Môi trường cho trình duyệt, bỏ __COMPAT_LAYER.

    Windows có khi gắn lớp tương thích (ví dụ ``__COMPAT_LAYER=DetectorsAppHealth``) vào cả cây tiến trình của một ứng
    dụng. Edge thấy biến này thì tự mở lại chính nó không kèm lớp đó rồi thoát tiến trình đầu (gặp ngày 2026-09-23).
    Bỏ biến trước thì Edge chạy thẳng; nếu vẫn tự mở lại thì tiến trình mới là con của tiến trình đầu, nên vẫn nằm
    trong job và vẫn bị tắt theo peto.
    """
    return {key: value for key, value in os.environ.items() if key.upper() != "__COMPAT_LAYER"}


def _prune_profiles() -> None:
    """Xóa hồ sơ tạm không trình duyệt nào còn dùng, thường của lần peto bị tắt đột ngột (job đã tắt trình duyệt
    nhưng không ai kịp xóa thư mục). Không được đụng hồ sơ của một phiên peto khác đang chạy song song.

    Trên Windows, trình duyệt giữ tệp ``lockfile`` trong hồ sơ suốt lúc chạy nên không xóa được tệp đó, và Windows tự
    xóa tệp ấy khi trình duyệt chết (đã thử ngày 2026-09-23). Vậy xóa được lockfile, hay không còn lockfile mà thư mục
    đã yên hơn một phút, là không ai dùng; thư mục mới hơn có thể của một phiên vừa mở và trình duyệt chưa kịp tạo
    lockfile. Hệ khác cho xóa cả tệp đang mở, nên chỉ dọn hồ sơ cũ hơn một ngày.
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
            elif (path / "lockfile").exists():
                (path / "lockfile").unlink()
            elif age < STARTING_PROFILE_SECONDS:
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
