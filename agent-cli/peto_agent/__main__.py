"""Lệnh peto: đăng nhập, xem trạng thái, và mở phiên làm việc trong thư mục hiện tại."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, config, history
from .client import ApiError, Client
from .loop import Session, TaskLog
from .ui import UI
from .workspace import Workspace

HELP_LINE = ("Gõ yêu cầu cho Peto. /moi: hội thoại mới · /resume: mở lại hội thoại trước · /effort: mức suy nghĩ · "
             "/thoat: thoát · Ctrl+C: dừng yêu cầu đang chạy")
EFFORT_LABELS = {"low": "thấp", "medium": "vừa", "high": "cao"}
# Gõ không dấu cho dễ, như /moi và /thoat; có dấu hay tên tiếng Anh cũng nhận.
EFFORT_ALIASES = {"thap": "low", "thấp": "low", "low": "low", "vua": "medium", "vừa": "medium", "tb": "medium",
                  "medium": "medium", "cao": "high", "high": "high"}


def _saved_client(ui: UI) -> Client | None:
    settings = config.load()
    if not settings.get("server") or not settings.get("token"):
        ui.failure("Máy này chưa đăng nhập Peto Agent. Chạy: peto login")
        return None
    try:
        return Client(settings["server"], settings["token"])
    except ValueError as err:
        ui.failure(str(err))
        return None


def _steps_left(me: dict) -> str:
    limit = int(me.get("steps_limit") or 0)
    return f"{max(0, limit - int(me.get('steps_used') or 0))}/{limit}"


def _effort(me: dict) -> str:
    """Mức người dùng đã chọn bằng /effort trên máy này; chưa chọn thì theo mặc định của máy chủ."""
    for value in (config.load().get("effort"), me.get("default_effort")):
        if value in EFFORT_LABELS:
            return value
    return "medium"


def _change_effort(ui: UI, work: Session, value: str) -> None:
    if not value:
        ui.line(f"  Mức suy nghĩ: {EFFORT_LABELS[work.effort]}. Đổi bằng /effort thap, /effort vua hoặc /effort cao.")
        ui.line("  Mức cao suy nghĩ kỹ hơn nhưng mỗi bước tính 2 bước.", "dim")
        return
    effort = EFFORT_ALIASES.get(value.lower())
    if effort is None:
        ui.line("  Chỉ có /effort thap, /effort vua hoặc /effort cao.", "yellow")
        return
    work.effort = effort
    settings = config.load()
    settings["effort"] = effort
    config.save(settings)
    ui.success(f"Đã chuyển sang mức {EFFORT_LABELS[effort]}" + ("; mỗi bước tính 2 bước." if effort == "high" else "."))


def _resume(ui: UI, work: Session) -> None:
    saved = history.load(work.ws.root, work.client.server)
    if saved is None:
        ui.line("  Chưa có hội thoại nào được lưu ở thư mục này.", "dim")
        return
    if work.items == saved.items:
        ui.line("  Đang ở đúng hội thoại gần nhất rồi.", "dim")
        return
    work.resume(saved.items)
    ui.success(f"Đã mở lại hội thoại {history.when(saved.saved_at)}:")
    for who, text in history.recap(saved.items):
        ui.line(f"    {who} › {text}", "dim")
    ui.line("  Peto không chạy lại lệnh nào; muốn sửa tệp thì sẽ đọc lại tệp trước.", "dim")


def login(ui: UI, server_arg: str | None) -> int:
    settings = config.load()
    server = server_arg or os.environ.get("PETO_AGENT_SERVER") or settings.get("server") or config.default_server()
    if not server:
        try:
            server = ui.reader("Địa chỉ Peto (https://…): ")
        except EOFError:
            server = ""
    try:
        client = Client(server)
    except ValueError as err:
        ui.failure(str(err))
        return 2
    if settings.get("token") and settings.get("server") == client.server:
        # Đăng nhập lại thì thu hồi token cũ của máy này, để danh sách máy trên web không bị trùng.
        try:
            Client(client.server, settings["token"]).json("POST", "/api/agent/logout")
        except ApiError:
            pass
    try:
        started = client.json("POST", "/api/agent/device/start", {"name": config.device_name()}, auth=False)
    except ApiError as err:
        ui.failure(err.message)
        return 1
    code = str(started.get("user_code", ""))
    link = started.get("verification_url") or f"{client.server}/?agent_code={code}"
    ui.line("Mở liên kết này trên trình duyệt đã đăng nhập Peto bằng Discord hoặc Google:")
    ui.line(f"  {link}", "cyan")
    ui.line(f"Mã trên máy này: {code}. Chỉ bấm Cho phép khi mã trên web giống hệt.")
    if not os.environ.get("PETO_AGENT_NO_BROWSER"):
        try:
            webbrowser.open(link)
        except Exception:  # noqa: BLE001 - không mở được trình duyệt thì người dùng tự mở liên kết
            pass
    interval = max(1, int(started.get("interval") or 3))
    deadline = time.monotonic() + max(30, int(started.get("expires_in") or 600))
    ui.line("Đang chờ bạn bấm Cho phép… (Ctrl+C để hủy)", "dim")
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            issued = client.json("POST", "/api/agent/device/token",
                                 {"device_code": str(started.get("device_code", ""))}, auth=False)
        except ApiError as err:
            if err.status == 428:
                continue
            ui.failure(err.message)
            return 1
        if not issued.get("token"):
            ui.failure("Máy chủ chưa cấp token. Chạy lại peto login nhé.")
            return 1
        settings.update(server=client.server, token=issued["token"], device_name=issued.get("device_name", ""))
        config.save(settings)
        ui.success(f"Đã kết nối {issued.get('device_name') or 'máy này'} với tài khoản {issued.get('account', '')}.")
        return 0
    ui.failure("Hết thời gian chờ. Chạy lại peto login nhé.")
    return 1


def logout(ui: UI) -> int:
    settings = config.load()
    if settings.get("token") and settings.get("server"):
        try:
            Client(settings["server"], settings["token"]).json("POST", "/api/agent/logout")
        except (ApiError, ValueError):
            pass
    settings.pop("token", None)
    config.save(settings)
    ui.success("Đã đăng xuất Peto Agent trên máy này.")
    return 0


def status(ui: UI) -> int:
    client = _saved_client(ui)
    if client is None:
        return 1
    try:
        me = client.json("GET", "/api/agent/me")
    except ApiError as err:
        ui.failure(err.message)
        return 1
    ui.line(f"Đã đăng nhập {client.server} · tài khoản {me.get('account')} · máy {me.get('device_name')} · "
            f"mức {EFFORT_LABELS[_effort(me)]} · hôm nay còn {_steps_left(me)} bước.")
    return 0


def too_broad(root: Path) -> bool:
    return root == Path(root.anchor) or root == Path.home().resolve()


def session(ui: UI) -> int:
    client = _saved_client(ui)
    if client is None:
        return 1
    root = Path.cwd().resolve()
    if too_broad(root):
        ui.failure("Mở Peto Agent trong thư mục dự án, không phải cả ổ đĩa hay thư mục người dùng.")
        return 2
    try:
        me = client.json("GET", "/api/agent/me")
    except ApiError as err:
        ui.failure(err.message)
        return 1
    effort = _effort(me)
    ui.line(f"{ui.paint('Peto Agent', 'cyan')} · {root.name} · {me.get('account')} · mức {EFFORT_LABELS[effort]} · "
            f"hôm nay còn {_steps_left(me)} bước")
    ui.line(HELP_LINE, "dim")
    work = Session(client, Workspace(root), ui, log=TaskLog(root.name), effort=effort)
    saved = history.load(root, client.server)
    if saved is not None:
        ui.line(f"Có hội thoại {history.when(saved.saved_at)} ({saved.message_count} tin) · gõ /resume để mở lại.",
                "yellow")
    while True:
        try:
            text = ui.prompt().strip()
        except (EOFError, KeyboardInterrupt):
            ui.line()
            break
        if not text:
            continue
        if text in {"/thoat", "/exit", "/quit"}:
            break
        if text == "/moi":
            # Hội thoại cũ vẫn mở lại được bằng /resume cho tới khi hội thoại mới được lưu đè sau yêu cầu đầu tiên.
            work.reset()
            ui.line("Đã bắt đầu hội thoại mới.", "dim")
            continue
        if text == "/help":
            ui.line(HELP_LINE, "dim")
            continue
        if text == "/resume":
            _resume(ui, work)
            continue
        if text == "/effort" or text.startswith("/effort "):
            _change_effort(ui, work, text[len("/effort"):].strip())
            continue
        if re.fullmatch(r"/[A-Za-z]+", text):
            ui.line("Không có lệnh này. Gõ /help để xem các lệnh.", "yellow")
            continue
        work.run_task(text)
    ui.line("Tạm biệt!", "dim")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Khi output bị chuyển sang tệp hay ống dẫn, Windows dùng bảng mã cũ và vỡ tiếng Việt; ép UTF-8. Stdin dùng
    # utf-8-sig vì Windows PowerShell 5.1 chèn BOM vào đầu dữ liệu truyền qua ống, làm lệnh ở dòng đầu không khớp.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8-sig" if stream is sys.stdin else "utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="peto", description="Nhờ Peto sửa code ngay trong thư mục dự án trên máy bạn.")
    parser.add_argument("--version", action="version", version=f"peto {__version__}")
    commands = parser.add_subparsers(dest="command")
    login_parser = commands.add_parser("login", help="kết nối máy này với tài khoản Peto")
    login_parser.add_argument("--server", help="địa chỉ Peto, ví dụ https://peto.example.com")
    commands.add_parser("logout", help="ngắt kết nối máy này")
    commands.add_parser("status", help="xem tài khoản và số bước còn lại hôm nay")
    args = parser.parse_args(argv)
    ui = UI()
    try:
        if args.command == "login":
            return login(ui, args.server)
        if args.command == "logout":
            return logout(ui)
        if args.command == "status":
            return status(ui)
        return session(ui)
    except KeyboardInterrupt:
        ui.line()
        ui.line("Đã hủy.", "dim")
        return 130


if __name__ == "__main__":
    sys.exit(main())
