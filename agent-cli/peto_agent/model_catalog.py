"""Model của mọi nguồn cho /models, /connect, /usage và ``peto models`` (lộ trình nhiều nguồn, M3–M5).

Mỗi model là một dict cùng dạng model máy chủ trả trong /me (``key``, ``label``, ``step_cost``, ``efforts``…); model của
nguồn trực tiếp có thêm ``source``, ``connection`` và ``model`` (mã model thật). Yêu thích và gần đây lưu trong
``config.json`` của hồ sơ người dùng như OpenCode lưu ``favorite``/``recent``, theo khóa nguồn|kết nối|model, tối đa
10 mục gần đây.
"""

from __future__ import annotations

from . import config, connections
from .bundle import assembly
from .providers import PETO, Selection
from .providers.chatgpt import ChatGPTSource
from .providers.openai_key import EFFORTS as OPENAI_EFFORTS, OUTPUT_CAP as OPENAI_OUTPUT_CAP, OpenAIKeySource

EFFORT_LABELS = {"none": "không suy luận", "low": "thấp", "medium": "vừa", "high": "cao",
                 "xhigh": "rất cao", "max": "tối đa"}
# Máy chủ cũ chưa có /model thì chỉ có Peto.
DEFAULT_MODELS = [{"key": "peto", "label": "Peto", "description": "Mặc định", "step_cost": 1}]
DIRECT_SOURCES = {OpenAIKeySource.id: OpenAIKeySource(), ChatGPTSource.id: ChatGPTSource()}
SOURCE_NAMES = {PETO: "Peto", OpenAIKeySource.id: "OpenAI", ChatGPTSource.id: "ChatGPT"}
# Chữ OpenAI yêu cầu cho chỗ hiện việc dùng gói (UI/UX guidelines); chủ web chọn giữ nguyên tiếng Anh (2026-10-21).
PLAN_IN_USE = "Using ChatGPT plan"
PLAN_FEATURE = "Use your ChatGPT plan"
CONTINUE = "Continue with ChatGPT"
# Tên hiện trong bảng chọn của các mã model thật; mã vẫn là thứ gõ sau /model.
DISPLAY = {"gpt-6-luna": "GPT-6 Luna", "gpt-5.6-terra": "GPT-5.6 Terra", "gpt-6.1-sol": "GPT-6.1 Sol"}
# Model trực tiếp chọn sẵn sau khi kết nối: rẻ trước, vì tiền tính vào tài khoản của chính người dùng.
DIRECT_PREFERENCE = ("gpt-6-luna", "gpt-5.6-terra", "gpt-6.1-sol")
RECENT_LIMIT = 10


def supported_efforts(model: dict) -> list[str]:
    values = model.get("efforts")
    known = [value for value in EFFORT_LABELS if value in values] if isinstance(values, list) else []
    return known or ["low", "medium", "high"]


def disabled_sources(server=()) -> set[str]:
    """Nguồn trực tiếp đang tắt (M6): ``disabled_sources`` trong config.json của người dùng, cộng danh sách máy chủ Peto
    báo trong /me. Kết nối và hội thoại của nguồn bị tắt vẫn còn; chỉ không chọn được model của nó."""
    values = config.load().get("disabled_sources")
    local = {value for value in values if isinstance(value, str)} if isinstance(values, list) else set()
    return {value for value in local | set(server or ()) if value in DIRECT_SOURCES}


def direct_models(disabled=()) -> list[dict]:
    """Model của các kết nối trực tiếp trên máy này. ``key`` là tên gõ sau /model: mã model thật, thêm @mã kết nối
    khi hai kết nối có cùng model. Nguồn đang tắt (``disabled_sources``) không có model nào."""
    rows, seen = [], set()
    off = disabled_sources(disabled)
    for item in connections.load_all():
        source = DIRECT_SOURCES.get(item.source)
        if source is None or item.source in off:
            continue
        names = item.extra.get("model_names") if isinstance(item.extra.get("model_names"), dict) else {}
        plan = item.source == ChatGPTSource.id
        for slug in source.models(item):
            key = slug if slug not in seen else f"{slug}@{item.id}"
            seen.add(slug)
            info = assembly.limits("openai", slug, OPENAI_OUTPUT_CAP)
            label = str(names.get(slug) or DISPLAY.get(slug, slug))
            note = PLAN_IN_USE if plan else "không tính bước Peto"
            rows.append({"key": key, "label": label, "description": f"{item.label} · {note}",
                         "source": item.source, "connection": item.id, "connection_label": item.label,
                         "model": slug, "step_cost": 0, "efforts": list(OPENAI_EFFORTS),
                         "context_limits": {name: info[name] for name in ("identity", "context", "input", "output")}})
    return rows


def entry_selection(entry: dict) -> tuple[str, str, str | None]:
    """(nguồn, model, kết nối) của một dòng trong danh sách model; dòng của máy chủ Peto không có nguồn."""
    return entry.get("source", PETO), entry.get("model", entry["key"]), entry.get("connection")


def entry_key(entry: dict) -> str:
    source, model, connection = entry_selection(entry)
    return f"{source}|{connection or ''}|{model}"


def category(entry: dict, entries: list[dict]) -> str:
    """Tên nhóm của model trong bảng chọn: "Peto", "OpenAI", hoặc "OpenAI · tên kết nối" khi có nhiều kết nối."""
    source, _, connection = entry_selection(entry)
    name = SOURCE_NAMES.get(source, source)
    if source == PETO:
        return name
    others = {item.get("connection") for item in entries if item.get("source") == source}
    if len(others) > 1:
        return f"{name} · {entry.get('connection_label') or connection}"
    return name


def source_label(source: str, connection: str | None) -> str:
    """Tên nguồn hiện cạnh tên model ở ô nhập ("OpenAI"), rỗng cho Peto."""
    if source == PETO:
        return ""
    name = SOURCE_NAMES.get(source, source)
    item = connections.get(connection) if connection else None
    others = [conn for conn in connections.load_all() if conn.source == source]
    if item is not None and len(others) > 1:
        return f"{name} · {item.label}"
    return name


class Catalog:
    """Model dùng được trong phiên: model Peto theo /me lúc mở phiên (rỗng khi chưa đăng nhập hay máy chủ không trả
    lời) cộng model của các kết nối trực tiếp, đọc lại mỗi lần để kết nối vừa thêm hiện ngay."""

    def __init__(self, peto_models: list[dict], *, account: str = "", logged_in: bool = False, problem: str = "",
                 transport: dict | None = None, disabled=()):
        self.peto = list(peto_models)
        self.account = account
        self.logged_in = logged_in
        # Lý do không có model Peto (máy chủ không trả lời…), để bảng chọn nói rõ thay vì im lặng thiếu.
        self.problem = problem
        # Giới hạn đường truyền máy chủ báo trong /me (context_transport), dùng lại khi danh sách model đổi.
        self.transport = transport
        # Nguồn trực tiếp máy chủ Peto báo đang tắt (/me disabled_sources, M6).
        self.disabled = tuple(disabled or ())

    def off(self) -> set[str]:
        return disabled_sources(self.disabled)

    def entries(self) -> list[dict]:
        return [*self.peto, *direct_models(self.disabled)]

    def find(self, source: str, model: str, connection: str | None) -> dict | None:
        return next((entry for entry in self.entries() if entry_selection(entry) == (source, model, connection)), None)

    def by_key(self, key: str) -> dict | None:
        return next((entry for entry in self.entries() if entry_key(entry) == key), None)


# ---- Yêu thích, gần đây và mặc định cho hội thoại mới -------------------------------------------------------------

def _keys(name: str) -> list[str]:
    values = config.load().get(name)
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


def favorites() -> list[str]:
    return _keys("favorite_models")


def recent() -> list[str]:
    return _keys("recent_models")


def toggle_favorite(entry: dict) -> bool:
    """Thêm hoặc bỏ yêu thích; trả True khi model vừa thành yêu thích."""
    settings = config.load()
    key = entry_key(entry)
    current = [value for value in settings.get("favorite_models") or [] if isinstance(value, str)]
    added = key not in current
    settings["favorite_models"] = [key, *current] if added else [value for value in current if value != key]
    config.save(settings)
    return added


def add_recent(entry: dict) -> None:
    """Model vừa chọn đứng đầu nhóm "Gần đây" của /models (tối đa 10, như OpenCode)."""
    settings = config.load()
    key = entry_key(entry)
    earlier = [value for value in settings.get("recent_models") or [] if isinstance(value, str) and value != key]
    settings["recent_models"] = [key, *earlier][:RECENT_LIMIT]
    config.save(settings)


def set_default(entry: dict) -> None:
    """Model mở sẵn cho các lần chạy peto sau (Ctrl+D trong /models, peto models default, peto connect). Đổi model
    trong một hội thoại không tự đổi mặc định (lộ trình M4)."""
    settings = config.load()
    source, model, connection = entry_selection(entry)
    if source == PETO:
        settings.pop("selection", None)
        settings["model"] = model
    else:
        settings["selection"] = {"source": source, "connection": connection, "model": model}
    config.save(settings)


def remember_selection(entry: dict) -> None:
    set_default(entry)
    add_recent(entry)


def default_key(settings: dict) -> str:
    """Khóa nguồn|kết nối|model của model mặc định đã lưu (để đánh dấu trong danh sách)."""
    chosen = settings.get("selection")
    if isinstance(chosen, dict) and chosen.get("source") not in {None, PETO}:
        return f"{chosen.get('source')}|{chosen.get('connection') or ''}|{chosen.get('model')}"
    model = settings.get("model")
    return f"{PETO}||{model}" if isinstance(model, str) else ""


def saved_direct(settings: dict, direct: list[dict]) -> dict | None:
    """Nguồn trực tiếp đã chọn làm mặc định trên máy này (peto connect, /models), nếu kết nối và model đó còn."""
    chosen = settings.get("selection")
    if not isinstance(chosen, dict) or chosen.get("source") in {None, PETO}:
        return None
    wanted = (chosen.get("source"), chosen.get("model"), chosen.get("connection"))
    return next((entry for entry in direct if entry_selection(entry) == wanted), None)


def forget_connection(connection_id: str) -> None:
    """Kết nối vừa bị xóa: bỏ khỏi yêu thích, gần đây và mặc định."""
    settings = config.load()
    marker = f"|{connection_id}|"
    for name in ("favorite_models", "recent_models"):
        values = settings.get(name)
        if isinstance(values, list):
            settings[name] = [value for value in values if not (isinstance(value, str) and marker in value)]
    chosen = settings.get("selection")
    if isinstance(chosen, dict) and chosen.get("connection") == connection_id:
        settings.pop("selection", None)
    config.save(settings)


def budget_rows(entries: list[dict]) -> list[dict]:
    """Giới hạn ngữ cảnh theo khóa ngân sách (Selection.budget_key): nguồn Peto theo mã model, nguồn trực tiếp theo
    nguồn, kết nối và mã model, để cùng tên model ở hai nguồn không lẫn số."""
    rows = []
    for entry in entries:
        source, model, connection = entry_selection(entry)
        key = entry["key"] if source == PETO else Selection(source, model, "low", connection).budget_key
        rows.append({**entry, "key": key})
    return rows
