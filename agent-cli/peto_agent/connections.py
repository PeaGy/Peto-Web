"""Hồ sơ kết nối của nguồn model trực tiếp (lộ trình nhiều nguồn, M3).

Hồ sơ chỉ có thông tin không bí mật: mã kết nối, nhà cung cấp, tên do người dùng đặt, địa chỉ API và danh sách model
dùng được lúc kiểm. Khóa nằm riêng trong ``credentials`` (DPAPI). Tệp ở hồ sơ người dùng, không bao giờ đọc từ thư mục
dự án hay lịch sử hội thoại.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from . import config, credentials
from .atomic_file import write_text

VERSION = 1
# Nhà cung cấp hỗ trợ và địa chỉ API chính thức. Khóa chỉ được gửi tới đúng địa chỉ này; địa chỉ trên chính máy này
# (127.0.0.1, localhost) được nhận thêm cho máy chủ thử và proxy cục bộ.
PROVIDERS = {
    "openai": {"source": "openai-key", "label": "OpenAI (khóa API riêng)", "endpoint": "https://api.openai.com/v1"},
    # Đăng nhập ChatGPT để dùng hạn mức gói (M5): khóa là bộ token OAuth, không phải khóa API.
    "chatgpt": {"source": "chatgpt-plan", "label": "ChatGPT", "endpoint": "https://api.openai.com/v1"},
}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ConnectionError_(Exception):
    """Lỗi hồ sơ kết nối (tên riêng để không che ConnectionError có sẵn của Python)."""


@dataclass(frozen=True)
class Connection:
    id: str
    provider: str
    label: str
    endpoint: str
    created_at: float
    models: tuple[str, ...] = field(default_factory=tuple)
    # Thông tin không bí mật riêng của nhà cung cấp. ChatGPT: client_id được cấp, sub và email đã xác minh, plan (có
    # quyền dùng gói), status ("signed_out" khi phải đăng nhập lại), model_names (tên hiển thị theo tài khoản).
    extra: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        return PROVIDERS[self.provider]["source"]


def endpoint_allowed(provider: str, endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    if parts.username or parts.password or parts.query or parts.fragment:
        return False
    if endpoint.rstrip("/") == PROVIDERS[provider]["endpoint"]:
        return True
    return parts.scheme in {"http", "https"} and (parts.hostname or "").lower() in LOOPBACK


def _path():
    return config.home() / "connections.json"


def load_all() -> list[Connection]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or data.get("version") != VERSION or not isinstance(data.get("connections"), list):
        return []
    found = []
    for row in data["connections"]:
        try:
            item = Connection(id=row["id"], provider=row["provider"], label=str(row.get("label") or ""),
                              endpoint=row["endpoint"], created_at=float(row.get("created_at") or 0),
                              models=tuple(str(model) for model in row.get("models") or ()),
                              extra=dict(row["extra"]) if isinstance(row.get("extra"), dict) else {})
        except (KeyError, TypeError, ValueError):
            continue
        if item.provider in PROVIDERS and endpoint_allowed(item.provider, item.endpoint):
            found.append(item)
    return found


def get(connection_id: str | None) -> Connection | None:
    return next((item for item in load_all() if item.id == connection_id), None)


def _file() -> dict | None:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(items: list[Connection]) -> None:
    """Ghi hồ sơ. Dòng bản này không hiểu (nhà cung cấp của bản peto mới hơn) được giữ nguyên chứ không bị xóa; tệp
    do bản mới hơn ghi theo định dạng khác thì không ghi đè (M6: không ghi đè dữ liệu chưa hiểu)."""
    current = _file()
    if current is not None and isinstance(current.get("version"), int) and current["version"] > VERSION:
        raise ConnectionError_("connections.json do bản peto mới hơn ghi; cập nhật peto (/update) rồi thử lại.")
    known = {item.id for item in items}
    understood = {item.id for item in load_all()}
    kept = [row for row in (current or {}).get("connections") or []
            if isinstance(row, dict) and row.get("id") not in known and row.get("id") not in understood]
    rows = [{**asdict(item), "models": list(item.models)} for item in items] + kept
    write_text(_path(), json.dumps({"version": VERSION, "connections": rows}, ensure_ascii=False, indent=2))


def add(provider: str, secret: str | dict, *, label: str = "", endpoint: str | None = None,
        models: tuple[str, ...] = (), extra: dict | None = None) -> Connection:
    """Lưu khóa (DPAPI) rồi mới ghi hồ sơ; ghi hồ sơ lỗi thì xóa khóa vừa lưu. ``secret`` là dict khi đó là bộ token
    đăng nhập (ChatGPT)."""
    if provider not in PROVIDERS:
        raise ConnectionError_("Chưa hỗ trợ nhà cung cấp này.")
    endpoint = (endpoint or PROVIDERS[provider]["endpoint"]).rstrip("/")
    if not endpoint_allowed(provider, endpoint):
        raise ConnectionError_("Địa chỉ API không được phép: khóa chỉ đi tới địa chỉ chính thức của nhà cung cấp.")
    item = Connection(id=f"{provider}-{secrets.token_hex(4)}", provider=provider,
                      label=" ".join(label.split())[:60] or PROVIDERS[provider]["label"], endpoint=endpoint,
                      created_at=time.time(), models=tuple(models), extra=dict(extra or {}))
    if isinstance(secret, dict):
        credentials.save_record(item.id, secret)
    else:
        credentials.save(item.id, secret)
    try:
        _write([*load_all(), item])
    except (OSError, ConnectionError_) as err:
        credentials.delete(item.id)
        raise ConnectionError_(str(err) if isinstance(err, ConnectionError_) else "Không lưu được hồ sơ kết nối.")             from None
    return item


def update_models(connection_id: str, models: tuple[str, ...]) -> None:
    update(connection_id, models=tuple(models))


def update(connection_id: str, *, models: tuple[str, ...] | None = None, extra: dict | None = None) -> Connection | None:
    """Đổi danh sách model hay gộp thêm thông tin vào ``extra`` của một kết nối; trả kết nối mới."""
    found = None
    rows = []
    for item in load_all():
        if item.id == connection_id:
            changes = {}
            if models is not None:
                changes["models"] = tuple(models)
            if extra is not None:
                changes["extra"] = {**item.extra, **extra}
            item = found = Connection(**{**asdict(item), **changes, "models": changes.get("models", item.models)})
        rows.append(item)
    if found is not None:
        _write(rows)
    return found


def rename(connection_id: str, label: str) -> Connection | None:
    """Đổi tên dễ nhớ của kết nối (Ctrl+R trong /connect); trả kết nối mới, hay None khi không có kết nối này."""
    label = " ".join(label.split())[:60]
    items = load_all()
    found = None
    rows = []
    for item in items:
        if item.id == connection_id and label:
            item = found = Connection(**{**asdict(item), "label": label})
        rows.append(item)
    if found is not None:
        _write(rows)
    return found


def next_label(provider: str) -> str:
    """Tên mặc định của kết nối mới: tên nhà cung cấp, thêm số khi đã có kết nối cùng nhà cung cấp."""
    base = PROVIDERS[provider]["label"]
    taken = {item.label for item in load_all() if item.provider == provider}
    if base not in taken:
        return base
    return next(f"{base} {number}" for number in range(2, 1000) if f"{base} {number}" not in taken)


def remove(connection_id: str) -> bool:
    """Bỏ hồ sơ và khóa của kết nối trên máy này (không thu hồi khóa ở phía nhà cung cấp)."""
    items = load_all()
    kept = [item for item in items if item.id != connection_id]
    if len(kept) == len(items):
        return False
    _write(kept)
    credentials.delete(connection_id)
    return True
