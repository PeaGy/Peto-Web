"""/models và /connect trong phiên (lộ trình nhiều nguồn, M4–M5; CLI 0.32.0–0.33.0).

Giao diện theo OpenCode (``component/dialog-model.tsx``, ``dialog-provider.tsx``; MIT): bảng "Chọn model" chia nhóm
Yêu thích, Gần đây rồi theo nguồn, Ctrl+A mở "Kết nối nguồn", Ctrl+F đánh dấu yêu thích; kết nối xong thì mở ngay bảng
model của kết nối đó. Khác OpenCode theo lộ trình M4: đổi model trong hội thoại không đổi mặc định cho các lần mở sau
(Ctrl+D đặt mặc định), và khóa API gõ vào hiện thành chấm. M5 thêm "Continue with ChatGPT" (dùng hạn mức gói ChatGPT,
``chatgpt_auth``) cạnh khóa API; chữ của OpenAI cho phần này giữ nguyên tiếng Anh theo chọn của chủ web.

Giao diện không có khung nổi (ống dẫn, ``PETO_AGENT_UI=classic``) dùng chữ: ``/model tên`` và ``peto connect`` ngoài
phiên. Khóa không bao giờ đi qua lệnh gạch chéo, lịch sử ô nhập hay tệp hội thoại.
"""

from __future__ import annotations

import webbrowser

from . import chatgpt_auth, commands, config, connections, credentials, model_catalog as catalog
from .providers import PETO
from .providers import chatgpt as chatgpt_provider
from .providers.openai_key import OpenAIKeySource
from .providers.transport import ProviderHTTPError
from .tui.dialog import Action, Option, PromptDialog, SelectDialog

RECENT_SHOWN = 5
KEY_PAGE = "platform.openai.com/api-keys"


def has_dialogs(ui) -> bool:
    return getattr(ui, "engine", None) is not None and hasattr(ui, "dialog")


def refresh(work, cat: catalog.Catalog) -> list[dict]:
    """Danh sách model vừa đổi (thêm, xóa kết nối): cập nhật gợi ý /model và giới hạn ngữ cảnh của phiên."""
    entries = cat.entries()
    commands.use_models(entries or catalog.DEFAULT_MODELS)
    work.configure_models(catalog.budget_rows(entries), cat.transport)
    return entries


# ---- Đổi model của hội thoại -----------------------------------------------------------------------------------

def label(entry: dict) -> str:
    return entry.get("label") or entry["key"]


def switch(ui, work, entry: dict) -> bool:
    """Đổi model của hội thoại đang mở (không đổi mặc định). Trả False khi không đổi được hay đang dùng rồi."""
    source, model, connection = catalog.entry_selection(entry)
    if (source, model, connection) == (work.source, work.model, work.connection):
        ui.line(f"  Đang dùng {label(entry)} rồi.", "dim")
        return False
    step_cost = int(entry.get("step_cost") or 1) if source == PETO else 0
    try:
        work.select(source, model, connection=connection, step_cost=step_cost)
    except RuntimeError as err:
        ui.failure(str(err))
        return False
    work.supported_efforts = catalog.supported_efforts(entry)
    work.model_label = label(entry)
    commands.use_efforts(work.supported_efforts)
    catalog.add_recent(entry)
    return True


def fix_effort(ui, work) -> None:
    """Mức suy nghĩ cũ không hợp model mới: hỏi mức mới (khung nổi), hoặc chọn "vừa" rồi báo."""
    supported = work.supported_efforts
    if work.effort in supported:
        return
    fallback = "medium" if "medium" in supported else supported[0]
    if has_dialogs(ui):
        names = dict(commands.EFFORT_CHOICES)
        options = [Option(catalog.EFFORT_LABELS[value].capitalize(), value=value, description=names.get(value, ""),
                          current=value == fallback) for value in supported]
        dialog = SelectDialog("Chọn mức suy nghĩ", options, search=False,
                              message=f"Model này không có mức {catalog.EFFORT_LABELS[work.effort]}.")
        result = ui.dialog(dialog)
        work.effort = result.option.value if result.kind == "select" else fallback
        return
    work.effort = fallback
    ui.line(f"  Model này không hỗ trợ mức trước đó; chuyển sang mức {catalog.EFFORT_LABELS[work.effort]}.", "dim")


def announce(ui, work, entry: dict) -> None:
    source = catalog.entry_selection(entry)[0]
    where = catalog.source_label(source, entry.get("connection"))
    effort = catalog.EFFORT_LABELS[work.effort]
    if source == chatgpt_provider.ChatGPTSource.id:
        ui.success(f"Hội thoại này giờ dùng {label(entry)} · {where} · mức {effort}. {catalog.PLAN_IN_USE}: tính vào "
                   f"hạn mức gói ChatGPT của bạn, không tính bước Peto. {chatgpt_provider.MANAGE_USAGE}.")
        return
    if source != PETO:
        ui.success(f"Hội thoại này giờ dùng {label(entry)} · {where} · mức {effort}; tiền tính vào tài khoản OpenAI "
                   "của bạn, không tính bước Peto.")
        return
    cost = (2 if work.effort in {"high", "xhigh", "max"} else 1) * work.model_step_cost
    ui.success(f"Hội thoại này giờ dùng {label(entry)} · mức {effort}"
               + (f"; mỗi bước tính {cost} bước." if cost > 1 else "."))


# ---- /models ---------------------------------------------------------------------------------------------------

def _model_options(work, cat: catalog.Catalog, only=None) -> list[Option]:
    entries = cat.entries()
    shown = [entry for entry in entries if only is None or only(entry)]
    current = (work.source, work.model, work.connection)
    default = catalog.default_key(config.load())
    by_key = {catalog.entry_key(entry): entry for entry in shown}

    def option(entry: dict, group: str, *, searchable: bool = True) -> Option:
        source = catalog.entry_selection(entry)[0]
        home = catalog.category(entry, entries)
        key = catalog.entry_key(entry)
        if group != home:
            # Trong Yêu thích và Gần đây, tên nguồn đứng sau tên model như OpenCode.
            description = home if home != label(entry) else ""
        else:
            description = str(entry.get("description") or "") if source == PETO else ""
        footer = "mặc định" if key == default else ""
        if source == PETO and not footer:
            cost = int(entry.get("step_cost") or 1)
            footer = f"{cost} bước"
        return Option(label(entry), value=key, description=description, footer=footer, category=group,
                      current=catalog.entry_selection(entry) == current, search_footer=home,
                      search_text=f"{entry['key']} {entry.get('model', '')}", searchable=searchable)

    options = []
    if only is None:
        favorites = [key for key in catalog.favorites() if key in by_key]
        options += [option(by_key[key], "Yêu thích", searchable=False) for key in favorites]
        recent = [key for key in catalog.recent() if key in by_key and key not in favorites][:RECENT_SHOWN]
        options += [option(by_key[key], "Gần đây", searchable=False) for key in recent]
    options += [option(entry, catalog.category(entry, entries)) for entry in shown]
    return options


def _model_actions(cat: catalog.Catalog) -> list[Action]:
    connected = bool(connections.load_all()) or cat.logged_in
    return [Action("Kết nối nguồn" if not connected else "Các nguồn", "ctrl+a", "connect", needs_option=False),
            Action("Yêu thích", "ctrl+f", "favorite"), Action("Đặt mặc định", "ctrl+d", "default")]


def models(ui, work, cat: catalog.Catalog, *, only=None, title: str = "Chọn model") -> bool:
    """Bảng chọn model. ``only``: chỉ model thỏa điều kiện (vừa kết nối xong một nguồn). Trả True khi đã đổi model."""
    empty = "Chưa có model nào. Bấm ctrl+a để kết nối một nguồn." if only is None else "Nguồn này chưa có model nào."
    dialog = SelectDialog(title, _model_options(work, cat, only), actions=_model_actions(cat), empty=empty)
    if not cat.peto and cat.problem and only is None:
        dialog.message = f"Model của Peto chưa hiện vì chưa lấy được tài khoản Peto ({cat.problem})."
    while True:
        result = ui.dialog(dialog)
        if result.kind == "close":
            return False
        entry = cat.by_key(result.option.value) if result.option is not None else None
        if result.kind == "select":
            if entry is None or not switch(ui, work, entry):
                return False
            fix_effort(ui, work)
            announce(ui, work, entry)
            return True
        if result.action == "connect":
            if sources(ui, work, cat):
                return True
            dialog.replace(_model_options(work, cat, only), keep=result.option.value if result.option else None)
            dialog.actions = _model_actions(cat)
            continue
        if entry is None:
            continue
        if result.action == "favorite":
            added = catalog.toggle_favorite(entry)
            dialog.replace(_model_options(work, cat, only), keep=result.option.value)
            dialog.message = f"Đã {'thêm' if added else 'bỏ'} {label(entry)} {'vào' if added else 'khỏi'} Yêu thích."
            dialog.message_tone = "success"
        elif result.action == "default":
            catalog.set_default(entry)
            dialog.replace(_model_options(work, cat, only), keep=result.option.value)
            dialog.message = f"Từ lần mở peto sau, hội thoại mới dùng {label(entry)}."
            dialog.message_tone = "success"


# ---- /connect --------------------------------------------------------------------------------------------------

def _openai_family() -> list[connections.Connection]:
    return [item for item in connections.load_all() if item.provider in {"openai", "chatgpt"}]


def _source_options(cat: catalog.Catalog) -> list[Option]:
    family = _openai_family()
    keys = [item for item in family if item.provider == "openai"]
    plans = [item for item in family if item.provider == "chatgpt"]
    if cat.logged_in:
        peto_footer = cat.account or "đã đăng nhập"
    else:
        peto_footer = "chưa đăng nhập"
    parts = (["ChatGPT"] if plans else []) + ([f"{len(keys)} khóa"] if keys else [])
    return [Option("Peto", value="peto", description="tài khoản Peto, tính bước mỗi ngày", category="Phổ biến",
                   gutter="✓" if cat.logged_in else "", footer=peto_footer),
            Option("OpenAI", value="openai", description="gói ChatGPT hay khóa API", category="Phổ biến",
                   gutter="✓" if family else "", footer=" · ".join(parts))]


def sources(ui, work, cat: catalog.Catalog) -> bool:
    """Bảng "Kết nối nguồn". Trả True khi người dùng đã chọn xong một model (bảng model của nguồn vừa kết nối)."""
    dialog = SelectDialog("Kết nối nguồn", _source_options(cat))
    while True:
        result = ui.dialog(dialog)
        if result.kind != "select":
            return False
        if result.option.value == "peto":
            if not cat.logged_in:
                dialog.message = "Máy này chưa đăng nhập Peto. Gõ /exit rồi chạy peto login, sau đó mở lại peto."
                dialog.message_tone = "warning"
                continue
            if not cat.peto:
                dialog.message = f"Chưa lấy được tài khoản Peto ({cat.problem or 'máy chủ không trả lời'})."
                dialog.message_tone = "warning"
                continue
            if models(ui, work, cat, only=lambda entry: entry.get("source", PETO) == PETO, title="Chọn model · Peto"):
                return True
            continue
        if accounts(ui, work, cat):
            return True
        dialog.replace(_source_options(cat), keep=result.option.value)


def methods(ui, work, cat: catalog.Catalog) -> bool:
    """"Kết nối OpenAI" như OpenCode: Continue with ChatGPT (dùng hạn mức gói) hay khóa API (tính tiền theo khóa).
    Không có các cách "Codex (legacy)" của OpenCode: chúng mượn client ID của Codex, lộ trình không cho."""
    dialog = SelectDialog("Kết nối OpenAI", [
        Option(catalog.CONTINUE, value="chatgpt", description=catalog.PLAN_FEATURE),
        Option("Khóa API", value="key", description="tính tiền vào tài khoản API OpenAI của bạn")])
    while True:
        result = ui.dialog(dialog)
        if result.kind != "select":
            return False
        if result.option.value == "key":
            return add_key(ui, work, cat)
        done, problem = sign_in_chatgpt(ui, work, cat)
        if done or not problem:
            return done
        dialog.message, dialog.message_tone = problem, "warning"


def _account_options(work) -> list[Option]:
    family = _openai_family()
    rows = [Option(catalog.CONTINUE, value="+chatgpt", description=catalog.PLAN_FEATURE, gutter="+",
                   gutter_tone="primary"),
            Option("Thêm khóa API", value="+key", description="dán khóa từ trang OpenAI", gutter="+",
                   gutter_tone="primary")]
    known = set()
    for item in family:
        if item.provider != "chatgpt":
            continue
        known.add(item.extra.get("sub"))
        if item.extra.get("status") == "signed_out":
            state = "cần đăng nhập lại"
        elif not item.extra.get("plan"):
            state = "chỉ đăng nhập, chưa bật dùng gói"
        else:
            state = ""
        rows.append(Option(item.label, value=item.id, description=state, category="Gói ChatGPT",
                           current=item.id == work.connection, footer=f"{len(item.models)} model" if state == "" else "",
                           footer_tone="muted"))
    for item in family:
        if item.provider == "openai":
            count = len(OpenAIKeySource().models(item))
            rows.append(Option(item.label, value=item.id, description=item.id, category="Khóa API",
                               current=item.id == work.connection, footer=f"{count} model"))
    for sub, row in chatgpt_auth.registrations().items():
        if sub not in known:
            rows.append(Option(row.get("email") or "Tài khoản ChatGPT", value=f"reg:{sub}", description="đăng nhập lại",
                               category="Đã đăng nhập trước đây"))
    return rows


def accounts(ui, work, cat: catalog.Catalog) -> bool:
    """OpenAI trên máy này: các tài khoản ChatGPT và khóa API. Thêm, đổi tên (Ctrl+R), xóa (Ctrl+D hai lần), chọn để xem
    model; tài khoản cần đăng nhập lại hay chưa bật dùng gói thì chọn là đăng nhập lại."""
    if not _openai_family() and not chatgpt_auth.registrations():
        return methods(ui, work, cat)
    dialog = SelectDialog("OpenAI", _account_options(work),
                          actions=[Action("Đổi tên", "ctrl+r", "rename"), Action("Xóa", "ctrl+d", "delete")])
    while True:
        result = ui.dialog(dialog)
        if result.kind == "close":
            return False
        value = result.option.value if result.option is not None else None
        item = connections.get(value) if isinstance(value, str) and not value.startswith(("+", "reg:")) else None
        if result.kind == "select":
            done, problem = _open_account(ui, work, cat, value, item)
            if done:
                return True
            if problem:
                dialog.message, dialog.message_tone = problem, "warning"
            dialog.replace(_account_options(work), keep=value)
            continue
        if item is None:
            continue
        if result.action == "rename":
            prompt = PromptDialog("Đổi tên", value=item.label, placeholder="Tên dễ nhớ", submit="lưu")
            answer = ui.dialog(prompt)
            renamed = connections.rename(item.id, answer.text) if answer.kind == "submit" else None
            if renamed is not None:
                refresh(work, cat)
                dialog.message = f"Đã đổi tên thành “{renamed.label}”."
                dialog.message_tone = "success"
            dialog.replace(_account_options(work), keep=value)
            continue
        # Xóa: lần đầu chỉ hỏi lại ngay trên dòng, như OpenCode.
        if dialog.armed != value:
            dialog.arm(value, f"Bấm ctrl+d lần nữa để xóa {item.label}")
            continue
        dialog.message = _delete(ui, work, cat, item)
        dialog.message_tone = "success"
        if not _openai_family() and not chatgpt_auth.registrations():
            return False
        dialog.replace(_account_options(work))


def _open_account(ui, work, cat, value, item) -> tuple[bool, str]:
    if value == "+key":
        return add_key(ui, work, cat), ""
    if value == "+chatgpt":
        return sign_in_chatgpt(ui, work, cat)
    if isinstance(value, str) and value.startswith("reg:"):
        return sign_in_chatgpt(ui, work, cat, sub=value[4:])
    if item is None:
        return False, ""
    if item.provider == "chatgpt" and (item.extra.get("status") == "signed_out" or not item.extra.get("plan")):
        return sign_in_chatgpt(ui, work, cat, connection=item, consent=not item.extra.get("plan"))
    only = lambda entry, wanted=item.id: entry.get("connection") == wanted
    return models(ui, work, cat, only=only, title=f"Chọn model · {item.label}"), ""


def _delete(ui, work, cat: catalog.Catalog, item: connections.Connection) -> str:
    """Xóa một kết nối trên máy này; tài khoản ChatGPT thì thu hồi refresh token ở OpenAI trước. Trả câu báo."""
    if item.provider == "chatgpt":
        revoked = False
        waiting = PromptDialog("Xóa đăng nhập ChatGPT", busy="Đang thu hồi đăng nhập ở OpenAI…")
        try:
            with ui.dialog_busy(waiting):
                revoked = chatgpt_auth.revoke(item.id)
        except KeyboardInterrupt:
            revoked = False
        message = (f"Đã đăng xuất {item.label} và xóa trên máy này." if revoked else
                   f"Đã xóa {item.label} trên máy này nhưng chưa xác nhận được việc thu hồi ở OpenAI. Ngắt Peto Agent "
                   "trong ChatGPT → Settings → Security and login → Login connections nếu cần.")
    else:
        message = (f"Đã xóa {item.label} trên máy này. Khóa vẫn còn hiệu lực ở tài khoản OpenAI; muốn vô hiệu hẳn thì "
                   "thu hồi ở " + KEY_PAGE + ".")
    connections.remove(item.id)
    catalog.forget_connection(item.id)
    entries = refresh(work, cat)
    if work.connection != item.id:
        return message
    # Hội thoại đang chạy bằng kết nối vừa xóa: chuyển sang model mặc định còn lại (Peto, hay nguồn khác), không âm
    # thầm.
    settings = config.load()
    fallback = (catalog.saved_direct(settings, [entry for entry in entries if entry.get("source")])
                or next((entry for entry in cat.peto if entry["key"] == settings.get("model")), None)
                or (cat.peto[0] if cat.peto else None)
                or next(iter(entries), None))
    if fallback is not None and switch(ui, work, fallback):
        fix_effort(ui, work)
        ui.line(f"  Kết nối đang dùng vừa bị xóa nên hội thoại này chuyển sang {label(fallback)}.", "yellow")
    elif fallback is None:
        ui.line("  Kết nối đang dùng vừa bị xóa và máy này không còn nguồn nào. Gõ /connect để thêm, hoặc /exit rồi "
                "peto login.", "yellow")
    return message


# ---- Continue with ChatGPT -------------------------------------------------------------------------------------

def sign_in_chatgpt(ui, work, cat: catalog.Catalog, *, connection=None, sub: str | None = None,
                    consent: bool = False, open_browser=None) -> tuple[bool, str]:
    """Đăng nhập ChatGPT trong trình duyệt (OAuth, M5) rồi chọn model của tài khoản. Trả (đã chọn model, câu báo lỗi)."""
    if not credentials.available():
        return False, ("Máy này không có kho khóa an toàn của Windows (DPAPI), nên peto không lưu đăng nhập. Nguồn trực "
                       "tiếp hiện chỉ chạy trên Windows.")
    attempt = chatgpt_auth.attempt_for(connection, sub=sub, consent=consent)
    state = {"cancel": False, "url": None}
    waiting = PromptDialog(catalog.CONTINUE, busy="Đang chờ đăng nhập trong trình duyệt… esc để thôi",
                           description="Peto Agent đã mở trình duyệt để bạn đăng nhập ChatGPT. Chọn Use your ChatGPT "
                                       "plan để các yêu cầu tính vào hạn mức gói ChatGPT của bạn, không tính bước Peto.")

    def on_key(key) -> None:
        if key.name == "escape":
            state["cancel"] = True
        elif key.name == "char" and key.text.lower() == "c" and state["url"]:
            ui.copy(state["url"])

    try:
        with ui.dialog_busy(waiting, on_key=on_key) as redraw:
            def on_url(url, opened) -> None:
                state["url"] = url
                if not opened:
                    waiting.description = ("Không mở được trình duyệt. " + ("Bấm c để chép địa chỉ đăng nhập rồi mở "
                                                                          "trong trình duyệt." if url else
                                                                          "Đăng nhập lại bằng peto connect chatgpt."))
                elif url:
                    waiting.description += " Trình duyệt chưa mở thì bấm c để chép địa chỉ đăng nhập."
                redraw()

            result = chatgpt_auth.sign_in(attempt, open_browser=open_browser or webbrowser.open,
                                          cancelled=lambda: state["cancel"], on_url=on_url)
            waiting.busy = "Đang lấy danh sách model của tài khoản…"
            redraw()
            item = chatgpt_auth.store(result, existing=connection)
    except KeyboardInterrupt:
        return False, ""
    except chatgpt_auth.AuthError as err:
        return False, "" if err.kind == "cancelled" else str(err)
    except (connections.ConnectionError_, credentials.CredentialError) as err:
        return False, str(err)
    refresh(work, cat)
    if not result.plan:
        return False, (f"Đã đăng nhập {result.email or 'ChatGPT'} nhưng chưa cho phép Peto Agent dùng gói. Chọn tài "
                       "khoản đó để bật Use your ChatGPT plan, hoặc dùng khóa API riêng.")
    welcome(ui)
    if not item.models:
        return False, ("Đã đăng nhập, nhưng chưa lấy được danh sách model của tài khoản. Chọn tài khoản đó để thử lại "
                       "sau ít phút.")
    only = lambda entry, wanted=item.id: entry.get("connection") == wanted
    return models(ui, work, cat, only=only, title=f"Chọn model · {item.label}"), ""


def welcome(ui) -> None:
    """Khung chào một lần ở lần đầu dùng gói, đúng chữ OpenAI yêu cầu ("You're using your ChatGPT plan", "Got it")."""
    settings = config.load()
    if settings.get("chatgpt_welcome_shown"):
        return
    dialog = SelectDialog("You're using your ChatGPT plan", [Option("Got it", value="ok")], search=False,
                          message="Các yêu cầu AI đủ điều kiện của Peto Agent sẽ tính vào hạn mức gói ChatGPT của bạn, "
                                  f"không tính bước Peto. Quản lý mức dùng ở {chatgpt_provider.USAGE_PAGE}.")
    dialog.message_tone = "text"
    ui.dialog(dialog)
    settings = config.load()
    settings["chatgpt_welcome_shown"] = True
    config.save(settings)


def check_problem(err: ProviderHTTPError) -> str:
    if err.status == 401:
        return "OpenAI không nhận khóa này (sai hoặc đã bị thu hồi)."
    if err.status == 403:
        return "Khóa này không có quyền đọc danh sách model. Kiểm tra quyền của khóa trên trang OpenAI."
    if err.status == 429:
        return "OpenAI đang giới hạn lượt cho khóa này. Đợi chút rồi thử lại."
    if err.status == 0:
        return "Không kết nối được OpenAI. Kiểm tra mạng rồi thử lại."
    return f"OpenAI không kiểm được khóa (HTTP {err.status}). Thử lại sau."


def secret_problem(secret: str) -> str:
    if not 20 <= len(secret) <= credentials.MAX_SECRET_CHARS or any(not 33 <= ord(char) <= 126 for char in secret):
        return "Đây không giống một khóa API OpenAI."
    return ""


def add_key(ui, work, cat: catalog.Catalog, *, endpoint: str | None = None) -> bool:
    """Ô dán khóa API OpenAI. Khóa hiện thành chấm, được kiểm bằng danh sách model (không tốn token) rồi lưu bằng DPAPI;
    xong thì mở bảng model của khóa đó. Trả True khi người dùng đã chọn model."""
    info = connections.PROVIDERS["openai"]
    endpoint = (endpoint or info["endpoint"]).rstrip("/")
    host = endpoint.split("://", 1)[-1].split("/", 1)[0]
    prompt = PromptDialog("Khóa API OpenAI", placeholder="sk-…", secret=True, submit="kiểm tra và lưu",
                          description=f"Lấy khóa ở {KEY_PAGE}. Khóa chỉ lưu trên máy này (mã hóa bằng tài khoản "
                                      f"Windows của bạn) và chỉ được gửi tới {host}. Tiền tính vào tài khoản OpenAI "
                                      "của bạn.")
    if not credentials.available():
        ui.failure("Máy này không có kho khóa an toàn của Windows (DPAPI), nên peto không lưu khóa. Nguồn trực tiếp "
                   "hiện chỉ chạy trên Windows.")
        return False
    while True:
        result = ui.dialog(prompt)
        if result.kind != "submit":
            prompt.value = ""
            return False
        secret = result.text
        if problem := secret_problem(secret):
            prompt.value, prompt.error = "", problem + " Chưa lưu gì."
            continue
        prompt.busy = "Đang kiểm tra khóa (chỉ đọc danh sách model, không tốn token)…"
        try:
            with ui.dialog_busy(prompt):
                found = OpenAIKeySource().check(endpoint, secret)
        except ProviderHTTPError as err:
            prompt.value, prompt.busy, prompt.error = "", "", check_problem(err) + " Chưa lưu gì."
            secret = ""
            continue
        except KeyboardInterrupt:
            prompt.value, prompt.busy = "", ""
            return False
        prompt.value, prompt.busy = "", ""
        if not found:
            prompt.error = "Khóa dùng được, nhưng tài khoản OpenAI này chưa có model nào Peto Agent hỗ trợ. Chưa lưu gì."
            secret = ""
            continue
        try:
            item = connections.add("openai", secret, label=connections.next_label("openai"), endpoint=endpoint,
                                   models=found)
        except (connections.ConnectionError_, credentials.CredentialError) as err:
            prompt.error = str(err)
            continue
        finally:
            secret = ""
        refresh(work, cat)
        ui.success(f"Đã kết nối “{item.label}” · {len(found)} model dùng được.")
        only = lambda entry, wanted=item.id: entry.get("connection") == wanted
        models(ui, work, cat, only=only, title=f"Chọn model · {item.label}")
        return True
