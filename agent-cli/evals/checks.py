"""Chấm bài: hàm check(ctx) của từng bài dùng những công cụ ở đây.

Mỗi phép chấm là bắt buộc (require) hoặc phụ (bonus). Bài đạt khi mọi phép bắt buộc đều qua. Phép phụ ghi lại những
điều nên có (tự chạy test, cảnh báo người dùng…) để so giữa các lần chạy, không làm bài trượt.

Mẫu chữ (says, near) so trên chữ thường không dấu, nên viết mẫu cũng thường, không dấu: "khong thu lai", không phải
"Không thử lại".
"""

from __future__ import annotations

import contextlib
import fnmatch
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from peto_agent import browser as browser_module
from peto_agent.commands import fold
from peto_agent.runner import kill_tree

from policy import changed_files

HIDDEN_DIR = "_eval_hidden"


@dataclass
class Check:
    name: str
    ok: bool
    required: bool = True
    detail: str = ""


class Context:
    """Những gì một bài cần để chấm: thư mục sau khi Peto làm, lời Peto, công cụ đã gọi, câu hỏi quyền đã trả lời."""

    def __init__(self, root: Path, task_dir: Path, *, reply: str = "", text: str = "", calls=(), requests=()):
        self.root = root
        self.task_dir = task_dir
        self.reply = reply
        self.text = text or reply
        self.calls = list(calls)
        self.requests = list(requests)
        self.checks: list[Check] = []
        # Tính ngay, trước khi phép chấm nào chép test ẩn vào thư mục.
        self.changed = sorted(changed_files(root))

    # --- ghi kết quả --------------------------------------------------------------------------------------------

    def require(self, name: str, ok, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), True, str(detail)[:500]))
        return bool(ok)

    def bonus(self, name: str, ok, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), False, str(detail)[:500]))
        return bool(ok)

    # --- lời Peto ------------------------------------------------------------------------------------------------

    def says(self, *patterns: str, text: str | None = None) -> bool:
        """Mọi mẫu đều có trong lời Peto (mặc định cả yêu cầu), so không dấu."""
        folded = fold(self.text if text is None else text)
        return all(re.search(pattern, folded) for pattern in patterns)

    def near(self, first: str, second: str, window: int = 80, text: str | None = None) -> bool:
        """Có chỗ mẫu ``first`` và mẫu ``second`` cách nhau không quá ``window`` ký tự."""
        folded = fold(self.text if text is None else text)
        seconds = [match.start() for match in re.finditer(second, folded)]
        return any(abs(match.start() - other) <= window for match in re.finditer(first, folded) for other in seconds)

    # --- tệp -----------------------------------------------------------------------------------------------------

    def touched(self, *patterns: str) -> list[str]:
        """Tệp đã sửa, tạo hay xóa khớp một trong các mẫu (glob theo đường dẫn dùng /)."""
        return [path for path in self.changed if any(fnmatch.fnmatch(path, pattern) for pattern in patterns)]

    def read(self, rel: str) -> str:
        try:
            return (self.root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # --- công cụ, quyền --------------------------------------------------------------------------------------------

    def called(self, *names: str) -> list[dict]:
        return [call for call in self.calls if call["name"] in names]

    def asked(self, *kinds: str) -> list[dict]:
        return [request for request in self.requests if request.get("kind") in kinds]

    # --- chạy test -------------------------------------------------------------------------------------------------

    def unittest(self, *, hidden: bool = True, folder: str = "tests", timeout: int = 180) -> tuple[bool, str]:
        """Chạy test ẩn của bài (hoặc thư mục test của dự án) bằng Python của bộ chấm; trả (qua, tóm tắt)."""
        start = folder
        if hidden:
            target = self.root / HIDDEN_DIR
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(self.task_dir / "hidden", target)
            start = HIDDEN_DIR
        if not (self.root / start).is_dir():
            return False, f"không có thư mục {start}"
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        try:
            done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", start, "-t", "."],
                                  cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"test chạy quá {timeout} giây"
        finally:
            if hidden:
                shutil.rmtree(self.root / HIDDEN_DIR, ignore_errors=True)
        output = done.stdout + done.stderr
        ran = re.search(r"Ran (\d+) tests?", output)
        summary = (f"{ran.group(1)} test · " if ran else "") + (output.strip().splitlines() or ["không có output"])[-1]
        failures = [re.sub(r" \(.*\)$", "", line) for line in output.splitlines() if line.startswith(("FAIL:", "ERROR:"))]
        if failures:
            summary += " · " + "; ".join(line[:120] for line in failures[:4]) + (" …" if len(failures) > 4 else "")
        return done.returncode == 0 and bool(ran) and ran.group(1) != "0", summary

    # --- trang web -------------------------------------------------------------------------------------------------

    @contextlib.contextmanager
    def serve(self):
        """Phục vụ thư mục dự án trên 127.0.0.1 ở một cổng trống; trả địa chỉ gốc."""
        handler = partial(_QuietHandler, directory=str(self.root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()

    @contextlib.contextmanager
    def page(self, url: str, viewport: str = "desktop"):
        """Mở trang bằng Edge ẩn, hồ sơ tạm; trả (trình duyệt, kết quả mở trang). Lỗi console nằm ở result["problems"]."""
        page = browser_module.Browser()
        try:
            result = page.open(url, viewport)
            yield page, result
        finally:
            page.close()

    @staticmethod
    def evaluate(page, expression: str):
        return page._evaluate(expression)

    # --- API .NET --------------------------------------------------------------------------------------------------

    @contextlib.contextmanager
    def dotnet_api(self, *, timeout: int = 300):
        """Build rồi chạy API .NET của dự án trên một cổng trống; trả (địa chỉ gốc, lỗi build hay chạy)."""
        build = _run(["dotnet", "build", "-nologo", "-v", "q", "-clp:NoSummary"], self.root, timeout)
        if build.returncode != 0:
            yield None, "build lỗi: " + _tail(build.stdout + build.stderr)
            return
        port = _free_port()
        env = dict(os.environ, ASPNETCORE_ENVIRONMENT="Production", DOTNET_NOLOGO="1")
        process = subprocess.Popen(["dotnet", "run", "--no-build", "--no-launch-profile", "--urls",
                                    f"http://127.0.0.1:{port}"], cwd=self.root, env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    yield None, f"API tắt ngay khi chạy (mã {process.returncode})"
                    return
                with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
                time.sleep(0.5)
            else:
                yield None, "API không mở cổng sau 60 giây"
                return
            yield f"http://127.0.0.1:{port}", ""
        finally:
            kill_tree(process)

    @staticmethod
    def http(method: str, url: str, body=None, timeout: float = 15) -> tuple[int, str]:
        """Gọi HTTP tới máy này; trả (mã, chữ). Không kết nối được thì mã 0."""
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
        try:
            connection.request(method, parts.path + (f"?{parts.query}" if parts.query else ""), body=data,
                               headers={"Content-Type": "application/json"} if data is not None else {})
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        except OSError as err:
            return 0, str(err)
        finally:
            connection.close()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _run(argv: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    env = dict(os.environ, DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
    try:
        return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 1, "", f"quá {timeout} giây")


def _tail(text: str, lines: int = 6) -> str:
    kept = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return " · ".join(kept[-lines:])[:400]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
