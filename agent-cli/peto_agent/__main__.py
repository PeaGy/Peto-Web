"""Lệnh peto: đăng nhập, xem trạng thái, và mở phiên làm việc trong thư mục hiện tại."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from . import (__version__, commands, config, export, external_editor, history, line_editor, mentions, transcript,
               outputs, snapshot, updater, user_guide)
from .client import ApiError, Client
from .commands import fold
from .events import ToolDone
from .loop import Session, TaskLog, format_tokens
from .tools import FEATURES, NEW_FEATURES
from .ui import UI, enable_vt
from .workspace import Workspace, WorkspaceError
from .journal import DurabilityError

# Lệnh không nhận gì phía sau; gõ thêm chữ thì nhắc chứ không gửi cả câu cho Peto.
PLAIN_COMMANDS = {"/exit", "/new", "/help", "/usage", "/retry", "/diff", "/undo", "/compact", "/init", "/thinking", "/pending",
                  "/plan", "/timeline", "/fork", "/update", "/export", "/guide"}
EFFORT_LABELS = {"none": "không suy luận", "low": "thấp", "medium": "vừa", "high": "cao",
                 "xhigh": "rất cao", "max": "tối đa"}
# Giống STEP_COST của máy chủ: mức cao tính gấp đôi, nhân với số bước của model.
EFFORT_COST = {"none": 1, "low": 1, "medium": 1, "high": 2, "xhigh": 2, "max": 2}
# Máy chủ cũ chưa có /model thì chỉ có Peto.
DEFAULT_MODELS = [{"key": "peto", "label": "Peto", "description": "Mặc định", "step_cost": 1}]
# Tên tiếng Anh như lệnh khác; tên tiếng Việt cũ, gõ có dấu hay không dấu, vẫn nhận.
EFFORT_ALIASES = {"thap": "low", "thấp": "low", "low": "low", "vua": "medium", "vừa": "medium", "tb": "medium",
                  "medium": "medium", "cao": "high", "high": "high", "none": "none", "khong": "none",
                  "xhigh": "xhigh", "ratcao": "xhigh", "max": "max", "toida": "max"}


def split_command(text: str) -> tuple[str, str]:
    """"/effort cao" thành ("/effort", "cao"); chữ không có dạng lệnh thành ("", "").

    Tên lệnh so theo chữ thường không dấu, vì bộ gõ tiếng Việt có thể biến "/thoat" thành "/thoát". Chữ như
    "/api/users lỗi 500" có dấu gạch chéo thứ hai nên không bị coi là lệnh.
    """
    if not re.fullmatch(r"/[^\s/]*( .*)?", text):
        return "", ""
    name, _, value = text.partition(" ")
    # Tên tiếng Việt cũ (/moi, /thoat…) đổi về tên chính, để mọi chỗ chỉ so với một tên.
    return commands.canonical(fold(name)), value.strip()


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


def _steps_text(work: Session) -> str:
    """Số bước còn lại hôm nay, cập nhật sau mỗi bước theo máy chủ: "193/200"."""
    limit = int(work.steps_limit or 0)
    return f"{max(0, limit - int(work.steps_used or 0))}/{limit}"


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
        if updater.installed():
            ui.line(f"Có bản peto mới {latest} (máy này đang dùng {__version__}). Gõ /update để cập nhật.", "yellow")
            return
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
    """Nhận "luna", "Luna" hay "6 Luna"."""
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


def _supported_efforts(model: dict) -> list[str]:
    values = model.get("efforts")
    known = [value for value in EFFORT_LABELS if value in values] if isinstance(values, list) else []
    return known or ["low", "medium", "high"]


def _effort(me: dict) -> str:
    """Mức người dùng đã chọn bằng /effort trên máy này; chưa chọn thì theo mặc định của máy chủ."""
    supported = _supported_efforts(_model(_models(me)))
    for value in (config.load().get("effort"), me.get("default_effort"), "medium"):
        if value in supported:
            return value
    return supported[0]


def _change_effort(ui: UI, work: Session, value: str) -> None:
    supported = getattr(work, "supported_efforts", ["low", "medium", "high"])
    choices = ", ".join(f"/effort {effort}" for effort in supported)
    if not value:
        ui.line(f"  Mức suy nghĩ: {EFFORT_LABELS[work.effort]}. Đổi bằng {choices}.")
        ui.line("  Cao, rất cao và tối đa nhân đôi số bước của model; có thể chờ lâu và dùng nhiều token hơn.", "dim")
        return
    effort = EFFORT_ALIASES.get(fold(value).replace(" ", ""))
    if effort not in supported:
        ui.line(f"  Model hiện tại chỉ nhận {choices}.", "yellow")
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
    work.supported_efforts = _supported_efforts(model)
    commands.use_efforts(work.supported_efforts)
    if work.effort not in work.supported_efforts:
        work.effort = "medium" if "medium" in work.supported_efforts else work.supported_efforts[0]
        ui.line(f"  Model này không hỗ trợ mức trước đó; chuyển sang mức {EFFORT_LABELS[work.effort]}.", "dim")
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
    # Thời gian từng phần và token của yêu cầu gần nhất: cuối mỗi yêu cầu chỉ in một dòng, chi tiết xem ở đây.
    if work.metrics.calls["model"]:
        work.show_metrics()


RESUME_SHOWN = 20


def _resume(ui: UI, work: Session, value: str = "") -> None:
    """/resume: bảng hội thoại đã lưu của thư mục (mới nhất trước; tìm, đổi tên, xóa); /resume 2 mở thẳng cái thứ
    hai."""
    root, server = work.ws.root, work.client.server
    sessions = history.list_sessions(root, server)[:RESUME_SHOWN]
    if not sessions:
        ui.line("  Chưa có hội thoại nào được lưu ở thư mục này.", "dim")
        return
    if value:
        if not value.isdigit() or not 1 <= int(value) <= len(sessions):
            ui.line(f"  Gõ /resume để chọn trong danh sách, hoặc /resume 1 tới /resume {len(sessions)}.", "yellow")
            return
        saved = sessions[int(value) - 1]
    elif len(sessions) == 1:
        # Chỉ một hội thoại thì mở luôn như trước, khỏi phải chọn.
        saved = sessions[0]
    else:
        def rename(session_id: str, title: str) -> None:
            history.rename(root, server, session_id, title)
            if session_id == work.session_id:
                work.title = title
                work._announce_title()

        saved = ui.choose_session(sessions, work.session_id, rename=rename,
                                  delete=lambda session_id: history.delete(root, server, session_id))
        if saved is None:
            return
    if saved.id == work.session_id and work.items == saved.items:
        ui.line("  Đang ở đúng hội thoại này rồi.", "dim")
        return
    _open_session(ui, work, saved)


def _open_session(ui: UI, work: Session, saved: history.Saved) -> None:
    """Mở một hội thoại đã lưu (/resume, peto --resume sau /update): màn hình toàn phần vẽ lại cả hội thoại."""
    work.resume(saved.items, retryable=saved.retryable, model=saved.model, session_id=saved.id, title=saved.title,
                snapshots=saved.snapshots)
    ui.clear_conversation()
    ui.replay(work.items)
    ui.success(f"Đã mở lại hội thoại {history.when(saved.saved_at)}: \"{saved.title}\"")
    if saved.interrupted:
        # Bản lưu giữa yêu cầu: Peto bị đóng khi đang làm. Danh sách việc cho biết đã tới đâu.
        plan = history.last_plan(saved.items)
        if any(step["status"] != "done" for step in plan):
            ui.plan(plan)
        ui.line('  Yêu cầu cuối bị ngắt giữa chừng (cửa sổ đóng hoặc máy tắt). Gõ "làm tiếp" để Peto làm nốt.', "yellow")
    ui.line("  Peto không chạy lại lệnh nào; muốn sửa tệp thì sẽ đọc lại tệp trước.", "dim")
    if work.can_retry:
        ui.line("  Hội thoại này bị gián đoạn kết nối. Gõ /retry để thử lại bước chưa xong.", "yellow")


def _timeline(ui: UI, work: Session, *, fork: bool = False) -> None:
    """/timeline: các tin của bạn trong hội thoại đang mở, rồi Nhảy tới, Chép hay Tách từ đó; /fork chọn tin để tách
    (CLI 0.22.0, theo dialog-timeline và dialog-message của opencode)."""
    picks = [(position, item) for position, item in enumerate(work.items) if transcript.is_user(item)]
    # Bấm chuột vào một tin trên màn hình (CLI 0.24.0) cũng tới đây: mở thẳng menu của tin đó, không cần chọn lại.
    clicked = ui.take_clicked() if hasattr(ui, "take_clicked") else None
    if clicked is not None:
        index = next((number for number, (_, item) in enumerate(picks) if item is clicked), None)
        if index is None:
            return
    else:
        if not picks:
            ui.line("  Hội thoại này chưa có tin nào của bạn.", "dim")
            return
        rows = []
        for _, item in picks:
            text = " ".join(transcript.typed_text(item).split()) or "(chỉ có ảnh)"
            steer = history.raw_text(item).startswith(history.STEER_NOTE)
            rows.append((text if len(text) <= 80 else text[:79] + "…", "nhắn thêm lúc Peto đang làm" if steer else ""))
        index = ui.choose("Tách hội thoại từ tin nào" if fork else "Các tin của bạn", rows)
        if index is None:
            return
    position, item = picks[index]
    if fork:
        _fork(ui, work, position)
        return
    # Tin vừa bấm đã nằm ngay trên màn hình nên không cần "Nhảy tới".
    actions = ([("Nhảy tới", "cuộn màn hình tới tin này")] if getattr(ui, "fullscreen", False) and clicked is None
               else [])
    actions += [("Chép", "chép chữ của tin"), ("Tách hội thoại từ đây", "hội thoại mới gồm phần trước tin này")]
    # Ảnh chụp dự án (CLI 0.26.0, theo revert.ts của opencode): đưa tệp về đúng lúc trước tin này.
    point = work.restore_point(position)
    if point:
        actions.append(("Khôi phục tệp về lúc trước tin này", "/undo ngay sau đó trả lại như bây giờ"))
    choice = ui.choose(f"Tin {index + 1}", actions)
    if choice is None:
        return
    action = actions[choice][0]
    if action == "Nhảy tới":
        if not ui.jump_to(item):
            ui.line("  Không tìm thấy tin này trên màn hình.", "dim")
    elif action == "Chép":
        text = transcript.typed_text(item)
        if ui.copy(text):
            ui.success("Đã chép tin vào clipboard.")
        else:
            ui.prefill(text)
    elif action == "Khôi phục tệp về lúc trước tin này":
        work.restore_files(point, _short(transcript.typed_text(item)))
    else:
        _fork(ui, work, position)


def _short(text: str) -> str:
    text = " ".join(text.split()) or "(chỉ có ảnh)"
    return text if len(text) <= 40 else text[:39] + "…"


def _fork(ui: UI, work: Session, position: int) -> None:
    """Hội thoại mới gồm mọi thứ trước tin ở ``position``; chữ của tin đó nằm sẵn trong ô nhập (như /fork của opencode).
    Hội thoại cũ đã lưu sau mỗi bước nên vẫn nằm trong /resume."""
    item = work.items[position]
    text = transcript.typed_text(item)
    title = f"{work.shown_title() or 'Hội thoại'} (nhánh)"
    point = work.restore_point(position)
    if work.items:
        work.save()
    work.resume(work.items[:position], model=work.model, session_id=None, title=title, snapshots=work.snapshot_marks)
    ui.clear_conversation()
    ui.replay(work.items)
    if work.items:
        work.save()
    ui.success(f"Đã tách thành hội thoại mới \"{title}\"; hội thoại cũ vẫn mở lại được bằng /resume.")
    # Như opencode: tách nhánh thì hỏi có đưa cả tệp về lúc đó không (CLI 0.26.0, cần ảnh chụp của tin đó).
    if point and ui.choose("Khôi phục cả tệp về lúc trước tin đó?", [
            ("Không", "tệp giữ như bây giờ"), ("Khôi phục", "/undo ngay sau đó trả lại như bây giờ")]) == 1:
        work.restore_files(point, _short(text))
    ui.prefill(text)


def _update(ui: UI, work: Session) -> list[str] | None:
    """/update (CLI 0.22.0, như opencode): có bản mới thì chạy install.ps1 của máy chủ, rồi hỏi mở lại ngay. Trả lệnh
    mở lại peto bản mới, hoặc None."""
    try:
        me = work.client.json("GET", "/api/agent/me")
    except ApiError as err:
        ui.failure(err.message)
        return None
    latest = str(me.get("cli_version") or "")
    if _version(latest) <= _version(__version__):
        ui.line(f"  Đang dùng bản mới nhất ({__version__}).", "dim")
        return None
    if not updater.installed():
        ui.line(f"  Có bản peto {latest}, nhưng peto này không chạy từ bản cài bằng install.ps1 nên không tự cập nhật "
                "được. Thoát peto rồi chạy:", "yellow")
        ui.line(f"  irm {work.client.server}/install.ps1 | iex", "cyan")
        return None
    choice = ui.choose(f"Có bản peto {latest} (máy này đang dùng {__version__})",
                       [("Cập nhật ngay", "chạy install.ps1 của máy chủ, thường dưới một phút"), ("Để sau", "")])
    if choice != 0:
        return None

    def progress(seconds: float, output: str) -> None:
        lines = [line.strip() for line in output.replace("\r", "\n").split("\n") if line.strip()]
        ui.status(f"… Đang cài peto {latest} · {int(seconds)}s" + (f" │ {lines[-1]}" if lines else ""))

    try:
        result = updater.install(work.client.server, on_progress=progress)
    except KeyboardInterrupt:
        ui.clear_status()
        ui.line("  Đã dừng cập nhật; peto đang dùng vẫn chạy bình thường.", "yellow")
        return None
    ui.clear_status()
    # Khối lệnh như run_command, nhưng không qua preview: bản in chữ in preview thành câu hỏi "Muốn chạy lệnh".
    result = {**result, "command": f"irm {work.client.server}/install.ps1 | iex", "shell": "powershell"}
    ui.tool_finished(ToolDone("", "run_command", {}, result, {}))
    if result.get("exit_code") != 0:
        ui.failure("Cập nhật chưa xong; peto đang dùng vẫn chạy bình thường. Xem output ở trên.")
        return None
    choice = ui.choose(f"Đã cài peto {latest}", [("Mở lại ngay", "tiếp tục đúng hội thoại này trong bản mới"),
                                                  ("Để sau", "bản mới chạy từ lần mở peto sau")])
    if choice != 0:
        return None
    if work.items:
        work.save()
    return updater.restart_argv(work.session_id if work.items else None)


BTW_HINT = "Gõ câu hỏi sau /btw, ví dụ: /btw Peto đang sửa tệp nào?"


def _btw_problem(work: Session, question: str) -> str:
    """Vì sao chưa hỏi bên lề được: máy chủ cũ chưa có /btw, hay chưa gõ câu hỏi. Rỗng là hỏi được."""
    if "btw" not in work.tools.features:
        return "Máy chủ chưa hỗ trợ /btw. Cập nhật máy chủ Peto rồi thử lại."
    return "" if question.strip() else BTW_HINT


def _side_answer(work: Session, question: str) -> tuple[str, bool]:
    """Câu trả lời /btw và có phải lỗi không; không bao giờ ném lỗi (chạy cả ở luồng nền)."""
    try:
        return work.side_question(question), False
    except ApiError as err:
        return err.message, True
    except (OSError, ValueError):
        return "Không kết nối được máy chủ Peto.", True


def _aside(ui: UI, work: Session, text: str) -> str | None:
    """Màn hình gọi hàm này cho mọi tin vừa gửi (trong khóa của nó): /btw thì hỏi bên lề ở luồng riêng, kể cả lúc Peto
    đang làm, như opencode (CLI 0.23.0). Trả None nếu không phải /btw, "" nếu đã nhận, hay lời nhắc giữ chữ lại."""
    name, question = split_command(text)
    if name != "/btw":
        return None
    if problem := _btw_problem(work, question):
        return problem
    ui.ask_aside(question, lambda: _side_answer(work, question))
    return ""


def _btw(ui: UI, work: Session, question: str) -> None:
    """/btw trong bản chữ (không có màn hình của Peto): hỏi xong mới gõ tiếp được."""
    if problem := _btw_problem(work, question):
        ui.line(problem, "yellow")
        return
    ui.status("… Đang hỏi bên lề · Ctrl+C dừng")
    try:
        answer, failed = _side_answer(work, question)
    except KeyboardInterrupt:
        ui.clear_status()
        ui.line("Đã dừng câu hỏi bên lề.", "dim")
        return
    ui.clear_status()
    ui.side_answer(question, answer, failed=failed)


def _editor(ui: UI, initial: str) -> None:
    """/editor: soạn trong trình soạn của bạn, xong thì chữ nằm sẵn trong ô nhập, Enter mới gửi (CLI 0.23.0)."""
    cmd = external_editor.command()
    try:
        with ui.suspended(f"Đang soạn trong {external_editor.label(cmd)}: lưu rồi đóng tệp để quay lại Peto."):
            text = external_editor.edit(initial, cmd=cmd)
    except external_editor.EditorError as err:
        ui.failure(err.message)
        return
    if text is None:
        ui.line("  Không có chữ mới; ô nhập để nguyên.", "dim")
        return
    ui.prefill(text)


def _guide(ui: UI, work: Session) -> None:
    """/guide: sửa hướng dẫn chung (mọi dự án) hay AGENTS.md của dự án này trong trình soạn của /editor (CLI 0.25.0)."""
    shared = user_guide.path()
    project = work.ws.root / "AGENTS.md"
    choice = ui.choose("Sửa hướng dẫn cho Peto", [
        ("Hướng dẫn chung", f"áp cho mọi dự án · {shared}"),
        ("AGENTS.md của dự án này", "đi kèm mọi bước trong dự án này" + ("" if project.exists() else
                                                                         " · chưa có, sẽ tạo")),
    ])
    if choice is None:
        return
    target = shared if choice == 0 else project
    try:
        current = target.read_text(encoding="utf-8-sig") if target.exists() else ""
    except (OSError, UnicodeDecodeError) as err:
        ui.failure(f"Không đọc được {target}: {getattr(err, 'strerror', None) or type(err).__name__}.")
        return
    cmd = external_editor.command()
    try:
        with ui.suspended(f"Đang soạn {target.name} trong {external_editor.label(cmd)}: lưu rồi đóng tệp để quay lại "
                          "Peto."):
            text = external_editor.edit(current or (user_guide.TEMPLATE if choice == 0 else ""), cmd=cmd)
    except external_editor.EditorError as err:
        ui.failure(err.message)
        return
    if text is None:
        ui.line("  Không có gì đổi; tệp để nguyên.", "dim")
        return
    if choice == 0:
        work.write_user_guide(text)
    else:
        work.write_project_guide(text)


def _export(ui: UI, work: Session) -> None:
    """/export: hội thoại đang mở thành Markdown, lưu ở gốc dự án hay chép vào clipboard (CLI 0.23.0)."""
    if not any(transcript.is_user(item) for item in work.items):
        ui.line("  Hội thoại này chưa có gì để xuất.", "dim")
        return
    now = datetime.now()
    title = work.shown_title() or "Hội thoại với Peto"
    text = export.markdown(work.items, title=title, model=getattr(work, "model_label", "") or work.model,
                           folder=work.ws.root.name, when=now, version=__version__)
    name = f"peto-{export.slug(title)}-{now:%Y%m%d}.md"
    choice = ui.choose("Xuất hội thoại ra Markdown", [
        ("Lưu vào thư mục dự án", name + " · không ghi đè tệp có sẵn"),
        ("Chép vào clipboard", f"{len(text):,} ký tự".replace(",", ".")),
    ])
    if choice is None:
        return
    if choice == 1:
        if ui.copy(text):
            ui.success("Đã chép hội thoại (Markdown) vào clipboard.")
        else:
            ui.failure("Không chép được vào clipboard; chọn lưu vào thư mục dự án nhé.")
        return
    try:
        path = export.save(work.ws.root, text, title=title, when=now)
    except OSError as err:
        ui.failure(f"Không ghi được tệp: {err}")
        return
    ui.success(f"Đã xuất hội thoại ra {path.name}")
    # In liền một dòng để terminal nhận ra đường dẫn (Ctrl+bấm để mở).
    ui.line(f"  {path}", "dim")


def _toggle_plan(ui: UI) -> None:
    """/plan (cũng là Shift+Tab): đổi qua lại chế độ làm việc và Lập kế hoạch."""
    toggle = getattr(ui, "toggle_mode", None)
    if toggle is not None:
        mode = toggle()
    else:
        ui.mode = mode = "build" if ui.mode == "plan" else "plan"
    if mode == "plan":
        ui.line("  Chế độ Lập kế hoạch: Peto chỉ tìm hiểu và bàn kế hoạch, không sửa tệp hay thao tác trên trang. Lệnh "
                "vẫn hỏi bạn như thường. Gõ /plan hoặc bấm Shift+Tab để về chế độ làm việc.", "dim")
    else:
        ui.line("  Đã về chế độ làm việc: Peto sửa tệp, chạy lệnh như thường (vẫn hỏi bạn trước).", "dim")


def _resume_hint(saved: history.Saved) -> str:
    """Lời nhắc dưới ô nhập khi thư mục có hội thoại mở lại được."""
    if saved.interrupted:
        return f"/resume làm tiếp yêu cầu bị ngắt {history.when(saved.saved_at)}"
    return f"/resume mở hội thoại {history.when(saved.saved_at)}"


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


def _suggester(workspace: Workspace):
    """Bảng gợi ý của ô nhập: lệnh khi dòng bắt đầu bằng "/", đường dẫn tệp khi từ cuối bắt đầu bằng "@"."""
    files = mentions.Files(workspace)
    return lambda text: commands.suggestions(text) or mentions.suggest(text, files)


def too_broad(root: Path) -> bool:
    return root == Path(root.anchor) or root == Path.home().resolve()


def session(ui: UI, resume: str | None = None) -> int:
    """Phiên làm việc. ``resume``: mã hội thoại mở ngay (peto --resume, khi /update mở lại bản mới)."""
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
    commands.use_efforts(_supported_efforts(model))
    workspace = Workspace(root)
    if ui.editor is None:
        ui.editor = line_editor.create(ui.out, enable_vt, _suggester(workspace))
    try:
        folder = str(Path("~") / root.relative_to(Path.home()))
    except ValueError:
        folder = str(root)
    # Màn hình toàn phần (giao diện terminal) bật trước đầu phiên, để mascot nằm trong màn hình của Peto; ống dẫn và
    # input() không có màn hình này.
    if hasattr(ui, "start_footer"):
        ui.start_footer()
    ui.session_header(__version__, folder, model=model.get("label") or model["key"], effort=EFFORT_LABELS[effort])
    _update_notice(ui, client, me)
    saved_model = config.load().get("model")
    if isinstance(saved_model, str) and saved_model != model["key"]:
        ui.line(f"Tài khoản này không còn dùng được model {saved_model} nên peto dùng {model.get('label')}.", "yellow")
    work = Session(client, workspace, ui, log=TaskLog(root.name), effort=effort, model=model["key"],
                   model_step_cost=int(model.get("step_cost") or 1))
    work.steps_used, work.steps_limit = me.get("steps_used"), me.get("steps_limit")
    # Khả năng mới (đọc có số dòng, find_files, sửa khớp gần đúng) chỉ bật khi máy chủ đã hiểu chúng.
    offered = me.get("agent_features") if isinstance(me.get("agent_features"), list) else []
    work.tools.features = [*FEATURES, *(feature for feature in NEW_FEATURES if feature in offered)]
    work.supported_efforts = _supported_efforts(model)
    # Output đầy đủ của lệnh dài (CLI 0.25.0) chỉ giữ 7 ngày; kho ảnh chụp dự án (0.26.0) dọn mỗi ngày một lần.
    outputs.prune()
    if not os.environ.get("PETO_AGENT_NO_SNAPSHOTS"):
        snapshot.maintain()
    if (engine := getattr(ui, "engine", None)) is not None:
        # /btw gõ ở ô nhập được màn hình xử lý ngay, cả lúc Peto đang làm, không qua vòng lệnh bên dưới.
        engine.side = lambda text: _aside(ui, work, text)
    ui.folder_name = root.name
    ui.title(ui.tab_title())
    saved = history.load(root, client.server)
    # Hội thoại cũ mở lại được: nhắc ở dòng dưới ô nhập thay vì một dòng vàng giữa màn hình. Không có ô nhập (ống
    # dẫn, input()) thì không có dòng đó, nên in ra như cũ.
    resume_hint = _resume_hint(saved) if saved is not None else ""
    if resume and history.valid_id(resume) and (wanted := history.load(root, client.server, resume)) is not None:
        _open_session(ui, work, wanted)
        resume_hint = ""
    if resume_hint and ui.editor is None:
        if saved.interrupted:
            ui.line(f"Yêu cầu {history.when(saved.saved_at)} bị ngắt giữa chừng · gõ /resume để làm tiếp.", "yellow")
        else:
            ui.line(f"Có hội thoại {history.when(saved.saved_at)} ({saved.message_count} tin) · gõ /resume để mở lại.",
                    "dim")
    restart: list[str] | None = None
    try:
        while True:
            try:
                label = next((item.get("label") for item in models if item["key"] == work.model), None) or work.model
                work.model_label = label
                if work.items:
                    # Phiên đã có hội thoại (vừa hỏi, /init hay /resume): tệp lưu đã hoặc sẽ bị ghi đè, lời nhắc hết đúng.
                    resume_hint = ""
                footer = [f"còn {_steps_text(work)} bước"] if work.steps_limit else []
                if (share := work.context_share()) is not None:
                    # Để người dùng biết lúc nào nên /compact, hay lúc nào Peto sẽ tự tóm tắt.
                    footer.append(f"ngữ cảnh {min(100, round(share * 100))}% tới lúc tự tóm tắt")
                if resume_hint:
                    footer.append(resume_hint)
                text = ui.prompt(footer=" · ".join(footer),
                                 status=f"◉ {label} · {EFFORT_LABELS[work.effort]}").strip()
            except (EOFError, KeyboardInterrupt):
                ui.line()
                break
            if not text:
                continue
            if text.startswith('/'):
                try:
                    work.ack_control(text)
                except DurabilityError as error:
                    ui.failure(str(error))
                    continue
            name, value = split_command(text)
            if name in PLAIN_COMMANDS and value:
                ui.line(f"Lệnh {name} không nhận thêm gì phía sau.", "yellow")
                continue
            if name == '/pending':
                work.show_pending()
                continue
            if name == "/exit":
                break
            if name == "/new":
                # Hội thoại cũ vẫn nằm trong danh sách /resume; hội thoại mới có mã riêng từ lần lưu đầu.
                work.reset()
                ui.clear_conversation()
                ui.line("Đã bắt đầu hội thoại mới. Hội thoại cũ vẫn mở lại được bằng /resume.", "dim")
                continue
            if name == "/plan":
                _toggle_plan(ui)
                continue
            if name == "/help":
                _help(ui)
                continue
            if name == "/resume":
                _resume(ui, work, value)
                continue
            if name in {"/timeline", "/fork"}:
                _timeline(ui, work, fork=name == "/fork")
                continue
            if name == "/btw":
                _btw(ui, work, value)
                continue
            if name == "/editor":
                _editor(ui, value)
                continue
            if name == "/export":
                _export(ui, work)
                continue
            if name == "/guide":
                _guide(ui, work)
                continue
            if name == "/update":
                restart = _update(ui, work)
                if restart:
                    break
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
            if name == "/remember":
                work.note(value)
                continue
            if name == "/mcp":
                try:
                    work.tools.mcp.command(value)
                except (WorkspaceError, OSError) as err:
                    ui.failure(str(err))
                except (KeyboardInterrupt, EOFError):
                    ui.line("Đã dừng MCP.", "dim")
                continue
            if name == "/skill":
                if not value:
                    entries = work.tools.skills.catalog()
                    ui.line("Skills trong dự án (.peto/skills hoặc .agents/skills):", "dim")
                    for item in entries:
                        state = " · đã nạp" if item['name'] in work.tools.skills.loaded else ""
                        ui.line(f"  {item['name']}{state}: {item['description']}")
                    if not entries:
                        ui.line("  Chưa có skill hợp lệ.", "dim")
                    for error in work.tools.skills.errors:
                        ui.line(error, "yellow")
                else:
                    skill_name, _, task = value.partition(' ')
                    try:
                        result = work.tools.load_skill(skill_name)
                        work.items.append({'type': 'message', 'role': 'user', 'content':
                            'Tôi chọn skill sau cho công việc phù hợp trong hội thoại này. Skill không cấp thêm quyền.\n' +
                            json.dumps(result, ensure_ascii=False)})
                        work.save()
                        if task.strip():
                            work.run_task(task.strip(), ui.attached)
                    except (OSError, WorkspaceError) as err:
                        ui.failure(str(err))
                continue
            if name == "/permissions":
                work.permissions(value=value)
                continue
            if name == "/browser":
                if fold(value) not in {"", "clear", "xoa"}:
                    ui.line("Dùng /browser (hiện hoặc ẩn cửa sổ) hoặc /browser clear.", "yellow")
                else:
                    work.browser_window("xoa" if fold(value) in {"clear", "xoa"} else "")
                continue
            if name == "/usage":
                _usage(ui, work)
                continue
            if name == "/thinking":
                toggle = getattr(ui, "toggle_thoughts", None)
                if toggle is None:
                    ui.line("  Chỉ giao diện trong terminal mới hiện suy nghĩ của Peto.", "dim")
                elif toggle():
                    ui.line("  Đã bật: sau mỗi bước Peto in cả phần suy nghĩ model gửi về (không phải model nào cũng "
                            "gửi). Gõ /thinking lần nữa để tắt.", "dim")
                else:
                    ui.line("  Đã tắt: chỉ còn dòng \"+ Đã nghĩ\".", "dim")
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
    finally:
        # Lệnh nền và trình duyệt ẩn không sống lâu hơn phiên: đóng peto là dừng hết, kể cả khi thoát vì lỗi.
        stopped = work.tools.jobs.stop_all()
        work.tools.close_browser()
        work.tools.mcp.close()
        fullscreen = getattr(ui, "fullscreen", False)
        if hasattr(ui, "stop_footer"):
            ui.stop_footer()
        # In sau khi rời màn hình toàn phần, để còn lại trong terminal: người dùng cần biết dev server của họ đã dừng.
        if stopped:
            ui.line(f"Đã dừng {len(stopped)} lệnh nền: " + ", ".join(stopped), "dim")
    if restart:
        # /update: mở bản mới trong cùng cửa sổ, tiếp tục hội thoại vừa lưu; peto cũ chờ rồi thoát theo mã của nó.
        try:
            return subprocess.call(restart)
        except OSError as err:
            ui.failure(f"Không mở lại được peto bản mới ({err}). Gõ peto để mở, rồi /resume.")
            return 1
    # Màn hình toàn phần thoát ra là terminal sạch như trước khi gõ peto (như Claude Code), không chào thêm.
    if not fullscreen:
        ui.line("Tạm biệt!", "dim")
    return 0


def create_ui() -> UI:
    """Giao diện kiểu OpenCode khi output là terminal (chủ web chọn ngày 2026-10-12); ống dẫn, tệp và
    ``PETO_AGENT_UI=classic`` dùng bản in chữ cũ."""
    if os.environ.get("PETO_AGENT_UI", "").strip().lower() != "classic" and enable_vt(sys.stdout):
        from .tui.view import TerminalUI

        return TerminalUI()
    return UI()


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
    # /update mở lại bản mới bằng tham số này để tiếp tục đúng hội thoại; không phải lệnh người dùng gõ.
    parser.add_argument("--resume", metavar="MÃ", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    ui = create_ui()
    try:
        if args.command == "login":
            return login(ui, args.server)
        if args.command == "logout":
            return logout(ui)
        if args.command == "status":
            return status(ui)
        return session(ui, resume=args.resume)
    except DurabilityError as error:
        # Có thể lỗi ngay lúc đọc phiên, trước khi vào vòng lệnh có finally dọn terminal.
        if hasattr(ui, 'stop_footer'):
            ui.stop_footer()
        ui.failure(str(error))
        return 1
    except KeyboardInterrupt:
        ui.line()
        ui.line("Đã hủy.", "dim")
        return 130


if __name__ == "__main__":
    sys.exit(main())
