"""HTTP tới nhà cung cấp model của một kết nối trực tiếp (M3), bằng http.client của thư viện chuẩn.

- Chỉ gọi đúng địa chỉ API của kết nối (HTTPS, hoặc http trên chính máy này cho máy chủ thử). Không theo chuyển hướng,
  nên khóa không bao giờ bị mang sang máy khác.
- Lời báo lỗi không chứa khóa, phần đầu yêu cầu hay phản hồi thô; chỉ có mã trạng thái, mã lỗi và một câu đã cắt ngắn.
- Luồng SSE đọc ở luồng phụ như client Peto, nên Ctrl+C trên Windows dừng ngay và socket được đóng.
"""

from __future__ import annotations

import http.client
import json
import os
import queue
import socket
import ssl
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from .. import __version__

USER_AGENT = f"Peto-Agent-CLI/{__version__}"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 32 * 1024 * 1024
MAX_STREAM_BYTES = 128 * 1024 * 1024
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ProviderHTTPError(Exception):
    """Lỗi HTTP hay kết nối với nhà cung cấp. ``status`` 0 là không kết nối được hoặc luồng đứt."""

    def __init__(self, status: int, code: str = "", message: str = "", kind: str = "", param: str = ""):
        super().__init__(f"HTTP {status} {code}".strip())
        self.status, self.code, self.message, self.kind, self.param = status, code, message, kind, param


def _clip(value) -> str:
    return " ".join(str(value or "").split())[:300]


def _tlv(data: bytes, offset: int) -> tuple[int, int, int]:
    """(thẻ, đầu nội dung, cuối nội dung) của một phần tử DER."""
    tag, length = data[offset], data[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        if not 1 <= count <= 4:
            raise ValueError("độ dài DER không hợp lệ")
        length = int.from_bytes(data[offset:offset + count], "big")
        offset += count
    if offset + length > len(data):
        raise ValueError("DER bị cắt")
    return tag, offset, offset + length


def not_after(der: bytes) -> datetime | None:
    """Hạn cuối (notAfter) của một chứng chỉ X.509 dạng DER; None khi không đọc được (giữ chứng chỉ như cũ)."""
    try:
        _, start, _ = _tlv(der, 0)  # Certificate
        _, position, _ = _tlv(der, start)  # tbsCertificate
        tag, _, end = _tlv(der, position)
        if tag == 0xA0:  # version [0], có thể vắng
            tag, _, end = _tlv(der, end)
        for _ in range(2):  # signature, issuer (sau serialNumber)
            tag, _, end = _tlv(der, end)
        tag, start, _ = _tlv(der, end)  # validity
        if tag != 0x30:
            return None
        _, _, after = _tlv(der, start)  # notBefore
        tag, start, end = _tlv(der, after)  # notAfter
        text = der[start:end].decode("ascii")
        if tag == 0x17:  # UTCTime: năm 50–99 là 19xx (RFC 5280 mục 4.1.2.5.1)
            moment = datetime.strptime(text, "%y%m%d%H%M%SZ")
            if moment.year >= 2050:
                moment = moment.replace(year=moment.year - 100)
        elif tag == 0x18:
            moment = datetime.strptime(text, "%Y%m%d%H%M%SZ")
        else:
            return None
        return moment.replace(tzinfo=timezone.utc)
    except (IndexError, ValueError, UnicodeDecodeError):
        return None


_TLS_CONTEXT: ssl.SSLContext | None = None
_TLS_LOCK = threading.Lock()


def tls_context() -> ssl.SSLContext:
    """Ngữ cảnh TLS cho nhà cung cấp, kiểm chứng chỉ như mặc định của Python.

    Trên Windows, Python nạp cả kho chứng chỉ trung gian (CA) làm chứng chỉ tin cậy. Máy có bản ISRG Root X2 cũ do X1 ký
    (hết hạn 15/09/2025) trong kho đó thì OpenSSL chọn bản hết hạn trước bản còn hạn máy chủ gửi, và mọi trang dùng
    chuỗi Let's Encrypt qua X2 (như auth.openai.com) báo "certificate has expired" dù trình duyệt vẫn mở được (gặp khi
    đăng nhập ChatGPT, M5, 2026-10-21). Nên ở đây tự nạp kho ROOT và CA của Windows như Python làm, cùng quy tắc mục
    đích dùng, nhưng bỏ các chứng chỉ đã hết hạn. Các cờ kiểm giữ đúng như ``ssl.create_default_context()``."""
    global _TLS_CONTEXT
    with _TLS_LOCK:
        if _TLS_CONTEXT is None:
            _TLS_CONTEXT = _windows_context() if os.name == "nt" and hasattr(ssl, "enum_certificates") else None
            if _TLS_CONTEXT is None:
                _TLS_CONTEXT = ssl.create_default_context()
        return _TLS_CONTEXT


def _windows_context() -> ssl.SSLContext | None:
    default = ssl.create_default_context()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.options = default.options
    context.verify_flags = default.verify_flags
    context.minimum_version = default.minimum_version
    now = datetime.now(timezone.utc)
    loaded = 0
    for store in ("CA", "ROOT"):
        try:
            entries = ssl.enum_certificates(store)
        except OSError:
            continue
        for der, encoding, trust in entries:
            if encoding != "x509_asn" or not (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
                continue
            expiry = not_after(der)
            if expiry is not None and expiry < now:
                continue
            try:
                context.load_verify_locations(cadata=der)
                loaded += 1
            except ssl.SSLError:
                continue
    return context if loaded else None


class ProviderHTTP:
    def __init__(self, endpoint: str, headers: dict[str, str], *, timeout: float = 30.0):
        parts = urlsplit(endpoint)
        host = (parts.hostname or "").lower()
        if not (parts.scheme == "https" or (parts.scheme == "http" and host in LOOPBACK)) or not host:
            raise ValueError("Địa chỉ API phải là HTTPS.")
        self._secure = parts.scheme == "https"
        self._host, self._port = parts.hostname, parts.port
        self._base = parts.path.rstrip("/")
        self._headers = headers
        self.timeout = timeout

    def _connection(self, timeout: float):
        if self._secure:
            return http.client.HTTPSConnection(self._host, self._port, timeout=timeout, context=tls_context())
        return http.client.HTTPConnection(self._host, self._port, timeout=timeout)

    def _send(self, method: str, path: str, body: dict | None, timeout: float, *, form: dict | None = None):
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/event-stream", **self._headers}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            # OAuth (đăng nhập ChatGPT, M5): biểu mẫu trong thân yêu cầu, không bao giờ trên địa chỉ.
            data = urlencode(form).encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection = self._connection(min(self.timeout, timeout))
        try:
            connection.request(method, self._base + path, body=data, headers=headers)
            transport = connection.sock
            response = connection.getresponse()
            if transport is not None:
                transport.settimeout(timeout)
        except ssl.SSLError:
            connection.close()
            raise ProviderHTTPError(0, "tls", "Không xác minh được chứng chỉ HTTPS của nhà cung cấp.") from None
        except (OSError, http.client.HTTPException):
            connection.close()
            raise ProviderHTTPError(0, "connection", "Không kết nối được nhà cung cấp.") from None
        if response.status >= 300:
            code, kind, message, param = "", "", "", ""
            if 300 <= response.status < 400:
                code, message = "redirect", "Nhà cung cấp trả về chuyển hướng; Peto không theo để giữ an toàn cho khóa."
            else:
                try:
                    payload = json.loads(response.read(64 * 1024) or b"{}")
                    payload = payload if isinstance(payload, dict) else {}
                    error = payload.get("error")
                    if isinstance(error, dict):
                        code = str(error.get("code") or "")
                        kind = str(error.get("type") or "")
                        message = _clip(error.get("message"))
                        param = _clip(error.get("param"))
                    elif isinstance(error, str):
                        # Lỗi OAuth (RFC 6749 mục 5.2): {"error": "invalid_grant", "error_description": "..."}.
                        code, message = _clip(error), _clip(payload.get("error_description"))
                    elif isinstance(payload.get("detail"), str):
                        # Lỗi chặn trước luồng của đường ChatGPT: {"detail": "..."}, chỉ để chẩn đoán.
                        message = _clip(payload["detail"])
                except (ValueError, OSError, http.client.HTTPException):
                    pass
            status = response.status
            response.close()
            connection.close()
            raise ProviderHTTPError(status, code, message, kind, param)
        return connection, response, transport

    def json(self, method: str, path: str, body: dict | None = None, *, form: dict | None = None) -> dict:
        connection, response, _ = self._send(method, path, body, self.timeout, form=form)
        try:
            raw = response.read(MAX_JSON_BYTES + 1)
        except (OSError, http.client.HTTPException):
            raise ProviderHTTPError(0, "connection", "Kết nối tới nhà cung cấp bị ngắt.") from None
        finally:
            response.close()
            connection.close()
        if len(raw) > MAX_JSON_BYTES:
            raise ProviderHTTPError(0, "too_large", "Phản hồi của nhà cung cấp lớn bất thường.")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            raise ProviderHTTPError(0, "bad_json", "Phản hồi của nhà cung cấp không phải JSON.") from None
        if not isinstance(payload, dict):
            raise ProviderHTTPError(0, "bad_json", "Phản hồi của nhà cung cấp không đúng định dạng.")
        return payload

    def stream(self, path: str, body: dict, *, timeout: float = 600.0, on_idle=None) -> Iterator[dict]:
        """Từng sự kiện SSE (JSON trong dòng data). Dừng ở sự kiện kết thúc của Responses API hoặc khi luồng đóng."""
        connection, response, transport = self._send("POST", path, body, timeout)
        events: queue.Queue = queue.Queue()
        terminal = {"response.completed", "response.failed", "response.incomplete", "error"}

        def reader() -> None:
            try:
                data: list[str] = []
                size = total = 0
                while line := response.readline(MAX_EVENT_BYTES + 1):
                    total += len(line)
                    if len(line) > MAX_EVENT_BYTES or total > MAX_STREAM_BYTES:
                        raise ValueError("sự kiện quá lớn")
                    text = line.decode("utf-8").rstrip("\r\n")
                    if text.startswith("data:"):
                        size += len(text)
                        if size > MAX_EVENT_BYTES:
                            raise ValueError("sự kiện quá lớn")
                        data.append(text[5:].removeprefix(" "))
                    elif not text and data:
                        joined, data, size = "\n".join(data), [], 0
                        if joined.strip() == "[DONE]":
                            break
                        event = json.loads(joined)
                        events.put(("event", event))
                        if isinstance(event, dict) and event.get("type") in terminal:
                            break
                events.put(("end", None))
            except Exception as err:  # noqa: BLE001 - chuyển mọi lỗi đọc sang luồng chính
                events.put(("error", err))
            finally:
                response.close()

        threading.Thread(target=reader, daemon=True).start()
        finished = False
        try:
            while True:
                try:
                    kind, value = events.get(timeout=0.2)
                except queue.Empty:
                    if on_idle is not None:
                        on_idle()
                    continue
                if kind == "event":
                    if isinstance(value, dict):
                        yield value
                elif kind == "end":
                    finished = True
                    return
                else:
                    raise ProviderHTTPError(0, "stream", "Kết nối tới nhà cung cấp bị ngắt giữa chừng.")
        finally:
            if not finished and transport is not None:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
