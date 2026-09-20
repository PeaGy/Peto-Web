"""Lệnh peto: đăng nhập, xem trạng thái, và mở phiên làm việc trong thư mục hiện tại."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, commands, config, history, line_editor
from .client import ApiError, Client
from .commands import fold
from .loop import Session, TaskLog, format_tokens
from .ui import UI, enable_vt
from .workspace import Workspace

HINT_WITH_MENU = "Gõ yêu cầu cho Peto · / chọn lệnh · Alt+V dán ảnh · Ctrl+C dừng yêu cầu"
HINT_PLAIN = "Gõ yêu cầu cho Peto · /help xem các lệnh · Ctrl+C dừng yêu cầu"
# Lệnh không nhận gì phía sau; gõ thêm chữ thì nhắc chứ không gửi cả câu cho Peto.
PLAIN_COMMANDS = {"/thoat", "/exit", "/quit", "/moi", "/help", "/resume", "/usage", "/retry", "/diff", "/undo",
                  "/compact", "/init"}
EFFORT_LABELS = {"low": "thấp", "medium": "vừa", "high": "cao"}
# Giống STEP_COST của máy chủ: mức cao tính gấp đôi, nhân với số bước của model.
EFFORT_COST = {"low": 1, "medium": 1, "high": 2}
# Máy chủ cũ chưa có /model thì chỉ có Peto.
DEFAULT_MODELS = [{"key": "peto", "label": "Peto", "description": "Mặc định", "step_cost": 1}]
# Gõ không dấu cho dễ, như /moi và /thoat; có dấu hay tên tiếng Anh cũng nhận.
EFFORT_ALIASES = {"thap": "low", "thấp": "low", "low": "low", "vua": "medium", "vừa": "medium", "tb": "medium",
                  "medium": "medium", "cao": "high", "high": "high"}


def split_command(text: str) -> tuple[str, str]:
    """"/effort cao" thành ("/effort", "cao"); chữ không có dạng lệnh thành ("", "").

    Tên lệnh so theo chữ thường không dấu, vì bộ gõ tiếng Việt có thể biến "/thoat" thành "/thoát". Chữ như
    "/api/users lỗi 500" có dấu gạch chéo thứ hai nên không bị coi là lệnh.
    """
    if not re.fullmatch(r"/[^\s/]*( .*)?", text):
        return "", ""
    name, _, value = text.partition(" ")
    return fold(name), value.strip()


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


def _version(value: object) -> tuple[int, ...]:
    """"0.2.0" thành (0, 2, 0); chuỗi lạ thành () để không bao giờ nhắc nhầm."""
    try:
        return tuple(int(part) for part in str(value).split("."))
    except ValueError:
        return ()


def _update_notice(ui: UI, client: Client, me: dict) -> None:
    latest = me.get("cli_version")
    if _version(latest) > _version(__version__):
        # Lệnh cài nằm riêng một dòng: dòng dài bị terminal cắt ngang giữa lệnh thì khó chép.
        ui.line(f"Có bản peto mới {latest} (máy này đang dùng {__version__}). Thoát peto rồi chạy lệnh cài để cập nhật:",
                "yellow")
        ui.line(f"  irm {client.server}/install.ps1 | iex", "cyan")


def _usage_parts(me: dict) -> list[str]:
    parts = [f"hôm nay còn {_steps_left(me)} bước"]
    tokens = me.get("tokens_used")
    # Máy chủ cũ chưa trả số token thì bỏ phần này.
    if isinstance(tokens, int):
        parts.append(f"đã dùng {format_tokens(tokens)} token")
    return parts


def _models(me: dict) -> list[dict]:
    """Model tài khoản này được dùng, theo thứ tự máy chủ trả (Peto đứng đầu)."""
    models = [model for model in me.get("models") or []
              if isinstance(model, dict) and isinstance(model.get("key"), str)]
    return models or DEFAULT_MODELS


def _find_model(value: str, models: list[dict]) -> dict | None:
    """Nhận "luna", "Luna" hay "5.6 Luna"."""
    wanted = fold(value).replace(" ", "")
    for model in models:
        label = fold(str(model.get("label") or "")).split()
        if wanted in {fold(model["key"]), "".join(label), label[-1] if label else ""}:
            return model
    return None


def _model(models: list[dict]) -> dict:
    """Model đã chọn bằng /model trên máy này, nếu tài khoản còn được dùng; không thì model đầu (Peto)."""
    saved = config.load().get("model")
    return next((model for model in models if model["key"] == saved), models[0])


def _cost(work: Session) -> int:
    return EFFORT_COST[work.effort] * work.model_step_cost


def _cost_note(work: Session) -> str:
    cost = _cost(work)
    return f"mỗi bước tính {cost} bước" if cost > 1 else ""


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
    note = _cost_note(work)
    ui.success(f"Đã chuyển sang mức {EFFORT_LABELS[effort]}" + (f"; {note}." if note else "."))


def _change_model(ui: UI, work: Session, value: str, models: list[dict]) -> None:
    choices = ", ".join(f"/model {model['key']}" for model in models)
    if not value:
        current = next((model for model in models if model["key"] == work.model), models[0])
        ui.line(f"  Model: {current.get('label') or current['key']}. Đổi bằng {choices}.")
        width = max(len(model["key"]) for model in models)
        for key, description in map(commands.model_option, models):
            ui.line(f"    {key.ljust(width)}  {description}", "dim")
        return
    model = _find_model(value, models)
    if model is None:
        ui.line(f"  Tài khoản này không dùng được model đó. Chọn {choices}.", "yellow")
        return
    label = model.get("label") or model["key"]
    if model["key"] == work.model:
        ui.line(f"  Đang dùng {label} rồi.", "dim")
        return
    work.set_model(model["key"], int(model.get("step_cost") or 1))
    settings = config.load()
    settings["model"] = model["key"]
    config.save(settings)
    note = _cost_note(work)
    ui.success(f"Đã chuyển sang {label}" + (f"; {note}." if note else "."))


def _help(ui: UI) -> None:
    width = max(len(command.name) for command in commands.COMMANDS)
    for command in commands.COMMANDS:
        ui.line(f"  {command.name.ljust(width)}  {command.description}", "dim")
    ui.line("  Ctrl+C dừng yêu cầu đang chạy.", "dim")
    if ui.editor is not None:
        ui.line("  ↑/↓ gọi lại tin đã gửi. Alt+V dán ảnh trong clipboard, hoặc kéo tệp ảnh thả vào cửa sổ.", "dim")


def _usage(ui: UI, work: Session) -> None:
    try:
        me = work.client.json("GET", "/api/agent/me")
    except ApiError as err:
        ui.failure(err.message)
        return
    parts = _usage_parts(me)
    if work.context_tokens:
        parts.append(f"hội thoại này {format_tokens(work.context_tokens)} token")
    model = next((model for model in _models(me) if model["key"] == work.model), {})
    note = _cost_note(work)
    parts.append(f"{model.get('label') or work.model} · mức {EFFORT_LABELS[work.effort]}" + (f", {note}" if note else ""))
    summary = " · ".join(parts)
    ui.line(f"  {summary[:1].upper()}{summary[1:]}.")


def _resume(ui: UI, work: Session) -> None:
    saved = history.load(work.ws.root, work.client.server)
    if saved is None:
        ui.line("  Chưa có hội thoại nào được lưu ở thư mục này.", "dim")
        return
    if work.items == saved.items:
        ui.line("  Đang ở đúng hội thoại gần nhất rồi.", "dim")
        return
    work.resume(saved.items, retryable=saved.retryable, model=saved.model)
    ui.success(f"Đã mở lại hội thoại {history.when(saved.saved_at)}:")
    for who, text in history.recap(saved.items):
        ui.line(f"    {who} › {text}", "dim")
    ui.line("  Peto không chạy lại lệnh nào; muốn sửa tệp thì sẽ đọc lại tệp trước.", "dim")
    if work.can_retry:
        ui.line("  Hội thoại này bị gián đoạn kết nối. Gõ /retry để thử lại bước chưa xong.", "yellow")


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
    model = _model(_models(me))
    ui.line(f"Đã đăng nhập {client.server} · tài khoản {me.get('account')} · máy {me.get('device_name')} · "
            f"{model.get('label') or model['key']} · mức {EFFORT_LABELS[_effort(me)]} · {' · '.join(_usage_parts(me))} · "
            f"peto {__version__}.")
    _update_notice(ui, client, me)
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
    models = _models(me)
    model = _model(models)
    commands.use_models(models)
    if ui.editor is None:
        ui.editor = line_editor.create(ui.out, enable_vt)
    ui.session_header(__version__, str(root), str(me.get("account") or ""), EFFORT_LABELS[effort], _steps_left(me),
                      HINT_WITH_MENU if ui.editor is not None else HINT_PLAIN, model=model.get("label") or model["key"])
    _update_notice(ui, client, me)
    saved_model = config.load().get("model")
    if isinstance(saved_model, str) and saved_model != model["key"]:
        ui.line(f"Tài khoản này không còn dùng được model {saved_model} nên peto dùng {model.get('label')}.", "yellow")
    work = Session(client, Workspace(root), ui, log=TaskLog(root.name), effort=effort, model=model["key"],
                   model_step_cost=int(model.get("step_cost") or 1))
    saved = history.load(root, client.server)
    if saved is not None:
        ui.line(f"Có hội thoại {history.when(saved.saved_at)} ({saved.message_count} tin) · gõ /resume để mở lại.",
                "yellow")
    while True:
        try:
            try:
                folder = str(Path("~") / root.relative_to(Path.home()))
            except ValueError:
                folder = str(root)
            label = next((item.get("label") for item in models if item["key"] == work.model), None) or work.model
            text = ui.prompt(footer=f"{label} · mức {EFFORT_LABELS[work.effort]} · {folder}").strip()
        except (EOFError, KeyboardInterrupt):
            ui.line()
            break
        if not text:
            continue
        name, value = split_command(text)
        if name in PLAIN_COMMANDS and value:
            ui.line(f"Lệnh {name} không nhận thêm gì phía sau.", "yellow")
            continue
        if name in {"/thoat", "/exit", "/quit"}:
            break
        if name == "/moi":
            # Hội thoại cũ vẫn mở lại được bằng /resume cho tới khi hội thoại mới được lưu đè sau yêu cầu đầu tiên.
            work.reset()
            ui.line("Đã bắt đầu hội thoại mới.", "dim")
            continue
        if name == "/help":
            _help(ui)
            continue
        if name == "/resume":
            _resume(ui, work)
            continue
        if name == "/retry":
            work.retry_task()
            continue
        if name in {"/diff", "/undo", "/compact", "/init"}:
            try:
                {"/diff": work.show_diff, "/undo": work.undo, "/compact": work.compact,
                 "/init": work.init_guide}[name]()
            except (KeyboardInterrupt, EOFError):
                ui.line("Đã dừng.", "dim")
            continue
        if name == "/permissions":
            if value not in {"", "clear"}:
                ui.line("Dùng /permissions hoặc /permissions clear.", "yellow")
            else:
                work.permissions(clear=value == "clear")
            continue
        if name == "/usage":
            _usage(ui, work)
            continue
        if name == "/effort":
            _change_effort(ui, work, fold(value))
            continue
        if name == "/model":
            _change_model(ui, work, value, models)
            continue
        if name and not value:
            ui.line("Không có lệnh này. Gõ /help để xem các lệnh.", "yellow")
            continue
        work.run_task(text, ui.attached)
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
