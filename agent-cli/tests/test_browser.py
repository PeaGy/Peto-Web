"""Trình duyệt của Peto: chỉ trang trên máy, máy khách WebSocket, Edge thật xem (đợt 1) và bấm, gõ (đợt 2) trên trang
thử, hồ sơ theo dự án, và Edge tắt theo peto."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from peto_agent import browser
from peto_agent.browser import Browser, BrowserError, WebSocket, check_url

CLI_ROOT = Path(__file__).resolve().parents[1]
needs_browser = pytest.mark.skipif(browser.find_browser() is None, reason="máy này không có Edge hay Chrome")


def test_only_pages_on_this_machine_can_be_opened():
    for url, expected in (("http://localhost:5173/", "http://localhost:5173/"), ("localhost:5173", "http://localhost:5173"),
                          ("http://127.0.0.1:8000/a?b=1", "http://127.0.0.1:8000/a?b=1"),
                          ("https://127.9.9.9/", "https://127.9.9.9/"), ("http://[::1]:3000/", "http://[::1]:3000/"),
                          ("http://app.localhost:5173/", "http://app.localhost:5173/")):
        assert check_url(url) == expected
    # Trang ngoài là đường rò dữ liệu; file:// đọc được tệp ngoài dự án; mấy dạng số IP lạ thì không đoán.
    for url in ("https://example.com/", "http://192.168.1.5:5173/", "http://0.0.0.0:8000/", "file:///C:/Windows/win.ini",
                "javascript:alert(1)", "data:text/html,<b>x</b>", "about:blank", "ftp://localhost/",
                "http://localhost.evil.example/", "http://user:pw@localhost/", "http://127.1/", "http://2130706433/",
                "http://localhost:99999/", ""):
        with pytest.raises(BrowserError):
            check_url(url)


# --- Máy khách WebSocket ---------------------------------------------------------------------------------------------


def _exact(conn: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            raise ConnectionError
        data += chunk
    return data


def _frame(opcode: int, payload: bytes, fin: bool = True) -> bytes:
    head = bytes([(0x80 if fin else 0) | opcode])
    size = len(payload)
    if size < 126:
        head += bytes([size])
    elif size < 65536:
        head += bytes([126]) + struct.pack(">H", size)
    else:
        head += bytes([127]) + struct.pack(">Q", size)
    return head + payload


def _client_frame(conn: socket.socket) -> tuple[int, bytes]:
    first, second = _exact(conn, 2)
    size = second & 0x7F
    if size == 126:
        size = struct.unpack(">H", _exact(conn, 2))[0]
    elif size == 127:
        size = struct.unpack(">Q", _exact(conn, 8))[0]
    assert second & 0x80, "máy khách phải che (mask) dữ liệu gửi đi"
    mask = _exact(conn, 4)
    data = _exact(conn, size)
    return first & 0x0F, bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))


def test_websocket_client_handles_sizes_fragments_pings_and_partial_frames():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    seen = []

    def serve():
        conn, _ = listener.accept()
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(4096)
        key = re.search(rb"Sec-WebSocket-Key: (\S+)", request).group(1).decode()
        accept = base64.b64encode(hashlib.sha1((key + WebSocket.GUID).encode()).digest()).decode()
        conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode())
        conn.sendall(_frame(1, "xin chào".encode()) + _frame(1, b"a" * 300) + _frame(1, b"b" * 70000)
                     + _frame(1, "phần 1 ".encode(), fin=False) + _frame(0, "phần 2".encode())
                     + _frame(9, b"hi") + _frame(1, b"sau ping"))
        seen.append(_client_frame(conn))
        seen.append(_client_frame(conn))
        conn.sendall(_frame(1, b"echo: " + seen[-1][1]))
        whole = _frame(1, "tới từng phần".encode())
        conn.sendall(whole[:5])
        time.sleep(0.6)
        conn.sendall(whole[5:] + _frame(8, b""))
        time.sleep(0.5)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    ws = WebSocket("127.0.0.1", listener.getsockname()[1], "/devtools/page/1")
    assert ws.recv(5) == "xin chào"
    assert ws.recv(5) == "a" * 300
    assert ws.recv(5) == "b" * 70000
    assert ws.recv(5) == "phần 1 phần 2", "tin chia nhiều khung được ghép lại"
    assert ws.recv(5) == "sau ping"
    ws.send("tiếng Việt")
    assert ws.recv(5) == "echo: tiếng Việt"
    assert seen == [(0xA, b"hi"), (0x1, "tiếng Việt".encode())], "ping được trả pong đúng dữ liệu"
    with pytest.raises(TimeoutError):
        ws.recv(0.2)
    assert ws.recv(5) == "tới từng phần", "hết giờ giữa chừng không làm mất phần đã nhận"
    with pytest.raises(ConnectionError):
        ws.recv(5)
    ws.close()
    listener.close()


# --- Edge thật ----------------------------------------------------------------------------------------------------

PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Trang thử của Peto</title>
<style>body{font-family:"Segoe UI",sans-serif;margin:24px} .row{display:flex;gap:12px;width:720px}
.tall{height:2200px}</style></head><body>
<h1>Đăng ký nhận tin</h1>
<div class="row"><input placeholder="Email của bạn"><button>Gửi</button></div>
<p id="status">Chưa gửi.</p><img src="/khong-co-anh.png"><a href="/gioi-thieu">Giới thiệu</a>
<div class="tall"></div><footer id="cuoi">Chân trang</footer>
<script>
  console.error("Không tải được cấu hình: thiếu API_URL");
  fetch("/api/cham").then(r => r.json()).then(d => { document.getElementById("status").textContent = d.text; });
  setTimeout(() => { hamKhongTonTai(); }, 50);
</script></body></html>"""

DIALOG_PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Hộp thoại</title></head><body>
<p id="ket-qua">chưa hỏi</p>
<script>
  alert("Chào bạn");
  setTimeout(() => { document.getElementById("ket-qua").textContent = confirm("Xóa hết?") ? "đồng ý" : "hủy"; }, 300);
</script></body></html>"""


# Trang đặt vé cho đợt 2: ô nhập, ô mật khẩu, hộp chọn, ô chọn, hộp hiện ra sau khi bấm, confirm, lớp phủ che nút,
# nút bị tắt, liên kết ra ngoài, tab mới, cửa sổ mới, chọn tệp và tải tệp.
TICKET_PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Đặt vé</title>
<style>#man{position:fixed;inset:0;background:rgba(0,0,0,.4);display:none}</style></head><body>
<h1>Đặt vé</h1>
<form action="/cam-on" method="get">
  <label>Họ tên <input name="ten"></label>
  <label>Mật khẩu <input name="mk" type="password"></label>
  <label>Ghế <select name="ghe"><option value="thuong">Ghế thường</option><option value="vip">Ghế VIP</option></select></label>
  <label><input type="checkbox" name="dong-y"> Đồng ý điều khoản</label>
  <button id="gui">Gửi</button>
</form>
<p id="dem">Chưa gõ</p>
<button id="hien" onclick="document.getElementById('hop').hidden = false">Chọn số vé</button>
<div id="hop" hidden><p>Bạn muốn mấy vé?</p><button onclick="xacNhan()">Xác nhận</button></div>
<button id="xoa" onclick="document.getElementById('dem').textContent = confirm('Xóa hết?') ? 'Đã xóa' : 'Giữ lại'">Xóa</button>
<button id="mo-man" onclick="document.getElementById('man').style.display = 'block'">Mở lớp phủ</button>
<div id="man"></div>
<button id="tat" disabled>Nút tắt</button>
<a href="https://example.com/?q=bi-mat" id="ngoai">Trang ngoài</a>
<a href="/cam-on?ten=tab" target="_blank" id="tab">Mở tab mới</a>
<button id="popup" onclick="window.open('/cam-on?ten=popup')">Cửa sổ mới</button>
<input type="file" id="tep">
<a href="/tai" id="tai">Tải tệp</a>
<script>
  document.querySelector('[name=ten]').addEventListener('input', (event) => {
    document.getElementById('dem').textContent = 'Đã gõ: ' + event.target.value + (event.isTrusted ? ' (thật)' : ' (giả)');
  });
  function xacNhan() {
    console.error('Không lưu được vé');
    document.getElementById('hop').innerHTML = '<p>Đã đặt 2 vé! Mã MEO-042</p>';
  }
</script></body></html>"""


class _Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path, query = urlsplit(self.path).path, parse_qs(urlsplit(self.path).query)
        if self.path == "/":
            self._send("text/html; charset=utf-8", PAGE.encode())
        elif self.path == "/hop-thoai":
            self._send("text/html; charset=utf-8", DIALOG_PAGE.encode())
        elif path == "/dat-ve":
            self._send("text/html; charset=utf-8", TICKET_PAGE.encode())
        elif path == "/cam-on":
            name = query.get("ten", [""])[0]
            self._send("text/html; charset=utf-8",
                       f"<!doctype html><meta charset=utf-8><title>Cảm ơn</title><h1>Cảm ơn {name}</h1>".encode())
        elif path == "/tai":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=ve.pdf")
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"%PDF")
        elif path == "/dang-nhap":
            # Một cookie phiên (không hạn, mất khi trình duyệt tắt) và một cookie có hạn (nằm trong hồ sơ).
            self.send_response(200)
            self.send_header("Set-Cookie", "phien=abc; Path=/; HttpOnly")
            self.send_header("Set-Cookie", "nho=xyz; Path=/; Max-Age=3600")
            data = "<!doctype html><meta charset=utf-8><title>Đã đăng nhập</title><h1>Xin chào</h1>".encode()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/cookie":
            cookies = "; ".join(sorted(part.strip() for part in self.headers.get("Cookie", "").split(";") if part.strip()))
            self._send("text/html; charset=utf-8",
                       f"<!doctype html><meta charset=utf-8><title>Cookie</title><p id=c>{cookies or 'trống'}</p>".encode())
        elif self.path == "/api/cham":
            time.sleep(0.8)  # dữ liệu tới chậm: phải chờ mạng yên rồi mới coi là tải xong
            self._send("application/json", json.dumps({"text": "Đã tải dữ liệu"}).encode())
        elif self.path == "/ra-ngoai":
            self.send_response(302)
            self.send_header("Location", "https://example.com/")
            self.end_headers()
        else:
            self.send_error(404)

    def _send(self, kind: str, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            pass  # trình duyệt đóng kết nối giữ sẵn khi tắt

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _edge_count(marker: str) -> int:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'msedge.exe','chrome.exe' } | "
                          "Select-Object -ExpandProperty CommandLine"], capture_output=True, text=True).stdout
    return sum(1 for line in out.splitlines() if marker in line)


@needs_browser
def test_real_browser_sees_errors_elements_text_and_screenshots(site, agent_home):
    page = Browser()
    try:
        opened = page.open(site + "/")
        assert opened["title"] == "Trang thử của Peto" and opened["status"] == 200 and opened["loaded"]
        problems = opened["problems"]
        assert "console.error: Không tải được cấu hình: thiếu API_URL" in problems
        assert "404 /khong-co-anh.png" in problems
        assert any(problem.startswith("ReferenceError: hamKhongTonTai is not defined") for problem in problems)
        assert not any("favicon" in problem for problem in problems), "favicon trình duyệt tự xin không phải lỗi"
        # Phần tử thao tác được có số trong ngoặc vuông (đợt 2 dùng số đó để bấm, gõ); tiêu đề, ảnh thì không.
        assert opened["outline"][:3] == ["tiêu đề 1: Đăng ký nhận tin", "[1] ô nhập: Email của bạn", "[2] nút: Gửi"]
        assert "ảnh: (thiếu alt) /khong-co-anh.png" in opened["outline"]
        assert "Đã tải dữ liệu" in page.read()["text"], "chờ request chậm xong rồi mới coi trang đã tải"
        assert page.read("#cuoi")["text"] == "Chân trang"
        with pytest.raises(BrowserError, match="Không có phần tử"):
            page.read("#khong-co")

        desktop = page.screenshot()
        phone = page.screenshot("mobile")
        # Trang tải ở cỡ máy tính rồi mới chụp cỡ điện thoại: không được thu nhỏ cho vừa, không thì che mất chỗ tràn
        # (hàng rộng 720px) mà ảnh điện thoại cần cho thấy.
        assert page._evaluate("window.visualViewport.scale") == 1
        assert page._evaluate("document.documentElement.scrollWidth") > 390
        assert page.late_problems() == [], "mở lại để đổi khung chụp không báo lại lỗi đã báo cho trang này"
        again = page.open(site + "/")
        assert "404 /khong-co-anh.png" in again["problems"], "Peto tự mở lại thì báo đủ: lỗi còn đó là chưa sửa"
        whole = page.screenshot("desktop", full_page=True)
        for shot, width in ((desktop, 1280), (phone, 390), (whole, 1280)):
            assert shot.data.startswith(b"\x89PNG") and shot.width == width
            assert int.from_bytes(shot.data[16:20], "big") == width, "ảnh đúng bề ngang của khung nhìn"
            assert len(shot.data) <= browser.MAX_SHOT_BYTES
        assert 2000 < whole.height <= browser.MAX_FULL_PAGE_HEIGHT and not whole.cut
        saved = browser.store("du an thu", phone)
        assert saved.parent == agent_home / "screenshots" and saved.read_bytes() == phone.data
        assert saved.name.startswith("du_an_thu-")

        with pytest.raises(BrowserError, match="ngoài máy này"):
            page.open(site + "/ra-ngoai")
        with pytest.raises(BrowserError, match="Chưa mở trang"):
            page.screenshot()
        profile = page.profile
    finally:
        page.close()
    assert not profile.exists(), "hồ sơ tạm được xóa khi đóng"
    assert _edge_count(profile.name) == 0
    page.close()  # gọi lại vẫn yên


@needs_browser
def test_page_dialogs_are_answered_so_the_browser_never_hangs(site, agent_home):
    """alert() lúc tải từng làm browser_open chờ 50 giây rồi báo lỗi, và trình duyệt kẹt tới hết phiên (2026-09-23)."""
    page = Browser()
    try:
        started = time.monotonic()
        opened = page.open(site + "/hop-thoai")
        assert time.monotonic() - started < 10 and opened["loaded"] and opened["title"] == "Hộp thoại"
        deadline = time.monotonic() + 5
        while page.read("#ket-qua")["text"] == "chưa hỏi" and time.monotonic() < deadline:
            page.late_problems()
        assert page.read("#ket-qua")["text"] == "hủy", "confirm được trả lời Hủy: Peto không thay người dùng đồng ý"
        assert opened.get("dialogs", []) + page.new_dialogs() == ['alert "Chào bạn" (đã đóng)',
                                                                   'confirm "Xóa hết?" (đã chọn Hủy)']
        assert opened["problems"] == [], "hộp thoại không phải lỗi"

        assert page.screenshot("mobile").width == 390, "mở lại ở cỡ điện thoại không treo vì alert"
        page._pump(0.6)
        assert page.new_dialogs() == [], "mở lại chỉ để đổi khung chụp thì không báo lại hộp thoại đã báo"
        assert page.open(site + "/hop-thoai")["dialogs"][0] == 'alert "Chào bạn" (đã đóng)', "Peto tự mở lại thì báo đủ"
        assert page.open(site + "/")["title"] == "Trang thử của Peto", "trình duyệt vẫn dùng tiếp được"
    finally:
        page.close()


def test_a_browser_that_stops_answering_is_closed_so_the_next_look_starts_fresh():
    """Trang treo thì dùng tiếp trình duyệt đó chỉ tốn thêm 30 giây mỗi lần xem."""
    class Silent:
        sent = []

        def send(self, text):
            self.sent.append(json.loads(text)["method"])

        def recv(self, timeout):
            time.sleep(timeout)
            raise TimeoutError

        def close(self):
            pass

    page = Browser()
    page.ws = Silent()
    with pytest.raises(BrowserError, match="không trả lời .*trình duyệt mới"):
        page._call("Runtime.evaluate", {"expression": "1"}, timeout=0.05)
    assert not page.running and Silent.sent == ["Runtime.evaluate", "Browser.close"]


@needs_browser
@pytest.mark.skipif(os.name != "nt", reason="job object chỉ có trên Windows")
def test_browser_dies_with_peto_even_when_peto_is_killed(tmp_path):
    """Bấm X đóng terminal thì Windows giết peto ngay, không chạy finally; job object phải tắt nốt Edge."""
    marker = tmp_path / "ho-so.txt"
    code = ("import sys, time\nfrom peto_agent import browser\npage = browser.Browser()\npage._start()\n"
            "open(sys.argv[1], 'w').write(str(page.profile))\ntime.sleep(60)\n")
    child = subprocess.Popen([sys.executable, "-c", code, str(marker)],
                             env={**os.environ, "PYTHONPATH": str(CLI_ROOT)})
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        profile = Path(marker.read_text())
        assert _edge_count(profile.name) > 0
        subprocess.run(["taskkill", "/F", "/PID", str(child.pid)], capture_output=True)  # chỉ Python, không /T
        deadline = time.monotonic() + 10
        while _edge_count(profile.name) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert _edge_count(profile.name) == 0
    finally:
        child.kill()
        shutil.rmtree(Path(marker.read_text()) if marker.exists() else tmp_path / "khong-co", ignore_errors=True)


def test_old_screenshots_are_pruned_after_seven_days(agent_home):
    folder = agent_home / "screenshots"
    folder.mkdir(parents=True)
    old = folder / "cu.png"
    old.write_bytes(b"x")
    week_ago = time.time() - 8 * 24 * 3600
    os.utime(old, (week_ago, week_ago))
    shot = browser.Shot(b"\x89PNG", "image/png", 1, 1, "desktop", False, False)
    saved = browser.store("du-an", shot)
    assert saved.exists() and not old.exists()


@pytest.mark.skipif(os.name != "nt", reason="cách nhận biết hồ sơ đang dùng qua lockfile chỉ có trên Windows")
def test_leftover_profiles_are_pruned_but_never_one_in_use(tmp_path, monkeypatch):
    """Trình duyệt đang chạy giữ lockfile nên không xóa được; Windows tự xóa lockfile khi trình duyệt chết."""
    monkeypatch.setattr(browser.tempfile, "gettempdir", lambda: str(tmp_path))
    in_use, crashed, fresh, released = (tmp_path / f"{browser.PROFILE_PREFIX}{name}"
                                        for name in ("dang-chay", "da-chet", "vua-mo", "khoa-thua"))
    for folder in (in_use, crashed, fresh, released):
        (folder / "Default").mkdir(parents=True)
    (released / "lockfile").write_text("")
    long_ago = time.time() - 300
    os.utime(crashed, (long_ago, long_ago))
    with open(in_use / "lockfile", "w"):  # Python mở tệp không cho xóa, như trình duyệt đang chạy
        browser._prune_profiles()
    assert in_use.exists() and fresh.exists(), "hồ sơ đang dùng hay vừa mở thì để yên"
    assert not crashed.exists() and not released.exists()


# --- Đợt 2: bấm, gõ ------------------------------------------------------------------------------------------------


def _ref(items: list[str], text: str) -> str:
    """Số trong ngoặc vuông của phần tử đầu tiên có chữ ``text``."""
    return next(re.match(r"\[(\d+)\]", item).group(1) for item in items if text in item and item.startswith("["))


@needs_browser
def test_clicking_typing_and_choosing_behave_like_a_real_user(site, agent_home):
    page = Browser()
    try:
        outline = page.open(site + "/dat-ve")["outline"]
        joined = " | ".join(outline)
        assert "ô mật khẩu: Mật khẩu" in joined and "ô chọn: Đồng ý điều khoản (chưa chọn)" in joined
        name = _ref(outline, "ô nhập: Họ tên")
        assert page.describe("type", name, "Nguyễn Văn Á") == 'gõ "Nguyễn Văn Á" vào ô "Họ tên"'

        typed = page.type(name, "Nguyễn Văn Á")
        assert typed["action"] == 'gõ "Nguyễn Văn Á" vào ô "Họ tên"' and typed["value"] == "Nguyễn Văn Á"
        assert typed["appeared"] == ["Đã gõ: Nguyễn Văn Á (thật)"], "sự kiện gõ thật (isTrusted), đúng dấu tiếng Việt"
        assert f'[{name}] ô nhập: Họ tên = "Nguyễn Văn Á"' in typed["elements"], "số của phần tử giữ nguyên"
        assert page.type(name, "Lan")["value"] == "Lan", "gõ lại là thay chữ cũ"

        with pytest.raises(BrowserError, match="không gõ vào ô mật khẩu"):
            page.type(_ref(outline, "ô mật khẩu"), "123456")
        chosen = page.type(_ref(outline, "hộp chọn: Ghế"), "ghế vip")
        assert chosen["chosen"] == "Ghế VIP" and any('hộp chọn: Ghế = "Ghế VIP"' in item for item in chosen["elements"])
        with pytest.raises(BrowserError, match='không có lựa chọn "hạng nhất". Có: "Ghế thường", "Ghế VIP"'):
            page.type(_ref(outline, "hộp chọn: Ghế"), "hạng nhất")
        checked = page.click(_ref(outline, "ô chọn: Đồng ý"))
        assert any("Đồng ý điều khoản (đã chọn)" in item for item in checked["elements"])

        shown = page.click("#hien")
        assert shown["action"] == 'bấm nút "Chọn số vé"' and shown["appeared"] == ["Bạn muốn mấy vé?", "Xác nhận"]
        confirm = _ref(shown["elements"], "nút: Xác nhận")
        done = page.click(f"[{confirm}]")
        assert done["appeared"] == ["Đã đặt 2 vé! Mã MEO-042"]
        assert done["problems"] == ["console.error: Không lưu được vé"]

        kept = page.click("#xoa")
        assert kept["dialogs"] == ['confirm "Xóa hết?" (đã chọn Hủy)'] and kept["appeared"] == ["Giữ lại"]
        removed = page.click("#xoa", accept_dialog=True)
        assert removed["dialogs"] == ['confirm "Xóa hết?" (đã chọn OK)'] and removed["appeared"] == ["Đã xóa"]
        nothing = page.click("#hien")
        assert "appeared" not in nothing and "elements" not in nothing, "bấm mà trang không đổi thì không bịa ra gì"

        with pytest.raises(BrowserError, match="đang bị tắt"):
            page.click("#tat")
        with pytest.raises(BrowserError, match=r"khớp \d+ phần tử đang hiện: \[\d+\] nút"):
            page.click("button")
        with pytest.raises(BrowserError, match="Không có phần tử nào khớp #khong-co"):
            page.click("#khong-co")
        page.click("#mo-man")
        with pytest.raises(BrowserError, match="đang bị div#man che"):
            page.click("#gui")
        page._evaluate("document.getElementById('man').style.display = 'none'")

        sent = page.type(name, "Lan", submit=True)
        assert sent["action"] == 'gõ "Lan" vào ô "Họ tên" rồi nhấn Enter' and sent["new_page"]
        assert sent["title"] == "Cảm ơn" and urlsplit(sent["url"]).path == "/cam-on"
        assert sent["outline"] == ["tiêu đề 1: Cảm ơn Lan"]
        with pytest.raises(BrowserError, match="không còn trên trang"):
            page.click(name)

        page.open(site + "/dat-ve")
        tabbed = page.press("Tab")
        assert tabbed["action"] == "nhấn Tab" and "focus" in tabbed
        with pytest.raises(BrowserError, match="Chỉ nhấn được các phím"):
            page.press("F13")
    finally:
        page.close()


@needs_browser
def test_outside_pages_new_tabs_uploads_and_downloads_are_stopped(site, agent_home):
    page = Browser()
    try:
        page.open(site + "/dat-ve")
        outside = page.click("#ngoai")
        assert urlsplit(outside["url"]).path == "/dat-ve", "trang giữ nguyên, không có trang lỗi"
        assert outside["notes"] == ["Peto chặn chuyển sang example.com/ vì trang đó ngoài máy này; trang giữ nguyên."]
        assert outside["problems"] == []

        tab = page.click("#tab")
        assert tab["new_page"] and tab["title"] == "Cảm ơn" and "Cảm ơn tab" in tab["appeared"]
        assert tab["notes"] == ["Liên kết mở tab mới; Peto mở nó ngay trong tab đang xem."]
        page.open(site + "/dat-ve")
        popup = page.click("#popup")
        assert popup["notes"] == ["Trang mở một tab hay cửa sổ mới; Peto đã đóng nó vì Peto chỉ xem một tab."]
        page._pump(0.5)
        pages = [target for target in page._call("Target.getTargets")["targetInfos"] if target["type"] == "page"]
        assert len(pages) == 1, "chỉ còn tab của Peto"

        assert page.click("#tep")["notes"] == ["Trang mở hộp chọn tệp; Peto không tải tệp nào lên."]
        assert page.click("#tai")["notes"] == ["Trang muốn tải tệp ve.pdf về máy; Peto không tải tệp."]
    finally:
        page.close()


@needs_browser
def test_open_waits_for_a_dev_server_that_is_still_starting(agent_home):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    url = f"http://127.0.0.1:{port}/dat-ve"
    page = Browser()
    try:
        with pytest.raises(BrowserError, match="Dev server đã chạy"):
            page.open(url)  # không có lệnh nền nào đang chạy: báo ngay, không chờ

        def late_start():
            time.sleep(1.5)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Site)
            threading.Thread(target=server.serve_forever, daemon=True).start()

        threading.Thread(target=late_start, daemon=True).start()
        page.wait_for_server = True
        started = time.monotonic()
        opened = page.open(url)
        assert opened["title"] == "Đặt vé" and 1 < time.monotonic() - started < 10
        assert opened["problems"] == [], "những lần gõ cửa trước khi server lên không phải lỗi của trang"
    finally:
        page.close()


@needs_browser
def test_project_profile_keeps_logins_for_the_next_session_but_is_never_shared(site, agent_home, tmp_path):
    root = tmp_path / "du-an"
    profile = browser.project_profile(root)
    assert profile.parent == agent_home / "browser"
    first, second = Browser(profile=profile), Browser(profile=profile)
    try:
        first.open(site + "/dang-nhap")
        second.open(site + "/cookie")
        assert second.profile != profile and second.notice and "phiên peto khác" in second.notice
        assert second.read("#c")["text"] == "trống", "phiên thứ hai không dùng chung hồ sơ đang mở"
        assert browser.forget_project(root) is False, "không xóa hồ sơ đang có phiên dùng"
    finally:
        first.close()
        second.close()
    assert profile.exists()

    again = Browser(profile=profile)
    again.force_headless = True  # "hiện" vẫn chạy ẩn: kiểm việc mở lại mà không bật cửa sổ lên màn hình
    try:
        again.open(site + "/cookie")
        assert again.read("#c")["text"] == "nho=xyz", "cookie có hạn còn trong hồ sơ; cookie phiên thì không"
        again.open(site + "/dang-nhap")
        again.open(site + "/cookie")
        again.set_visible(True)
        assert again.visible and again.url.endswith("/cookie"), "đổi ẩn/hiện mở lại đúng trang đang xem"
        assert again.read("#c")["text"] == "nho=xyz; phien=abc", "cookie phiên được chép sang trình duyệt mới"
        again.set_visible(False)
        assert again.read("#c")["text"] == "nho=xyz; phien=abc"
    finally:
        again.close()
    assert browser.forget_project(root) is True and not profile.exists()


@needs_browser
def test_user_logs_in_themselves_while_peto_waits(site, agent_home):
    page = Browser()
    page.force_headless = True
    try:
        page.open(site + "/dat-ve")
        seen = {}

        def user():
            # Lúc này người dùng tự làm trong cửa sổ: Peto không chặn, không trả lời hộp thoại thay.
            seen["handing_over"] = page.handing_over
            page._call("Page.navigate", {"url": site + "/dang-nhap"})
            page._pump(1)
            return True

        result = page.hand_over(user)
        assert seen == {"handing_over": True} and result["done"] and result["title"] == "Đã đăng nhập"
        assert page.visible and page.url.endswith("/dang-nhap")
        page.open(site + "/cookie")
        assert page.read("#c")["text"] == "nho=xyz; phien=abc"

        def wander():
            page._call("Page.navigate", {"url": "http://peto-khong-co.invalid/"})
            page._pump(1)
            return False

        back = page.hand_over(wander)
        assert not back["done"] and back["url"].endswith("/cookie"), "trang cuối ở ngoài máy thì quay về trang cũ"
        page.open(site + "/dat-ve")
        assert page.click("#ngoai")["notes"], "xong thì lại chặn trang ngoài"
    finally:
        page.close()
