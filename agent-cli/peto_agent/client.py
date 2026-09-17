"""Gọi máy chủ Peto bằng http.client của thư viện chuẩn.

- Bắt buộc HTTPS, trừ máy chủ chạy ngay trên máy này để thử nghiệm.
- Không theo chuyển hướng: token chỉ đi tới đúng địa chỉ đã cấu hình.
- Thông báo lỗi không chứa token hay phản hồi thô của máy chủ.
- Stream được đọc ở luồng phụ, nên Ctrl+C trên Windows dừng ngay; kết nối bị đóng để máy chủ biết mà ngừng.
"""

from __future__ import annotations

import http.client
import json
import queue
import socket
import ssl
import threading
from collections.abc import Iterator
from urllib.parse import urlsplit

USER_AGENT = "Peto-Agent-CLI/0.1"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_JSON_BYTES = 2 * 1024 * 1024
HINTS = {
    401: "Máy này chưa đăng nhập hoặc phiên đã hết hạn. Chạy peto login.",
    403: "Máy chủ từ chối yêu cầu này.",
    404: "Không tìm thấy API Peto Agent: máy chủ có thể chưa cập nhật.",
    413: "Dữ liệu gửi lên quá lớn.",
    429: "Máy chủ đang giới hạn lượt, thử lại sau nhé.",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def normalize_server(value: str) -> str:
    base = (value or "").strip().rstrip("/")
    parts = urlsplit(base)
    host = (parts.hostname or "").lower()
    secure = parts.scheme == "https" and bool(host)
    local = parts.scheme == "http" and host in LOOPBACK_HOSTS
    if not (secure or local) or parts.username or parts.password or parts.query or parts.fragment or parts.path:
        raise ValueError(
            "Địa chỉ máy chủ phải là HTTPS, ví dụ https://peto.example.com. "
            "Chỉ máy chủ chạy ngay trên máy này mới được dùng http."
        )
    return f"{parts.scheme}://{parts.netloc}"


def _error_message(response: http.client.HTTPResponse) -> str:
    status = response.status
    if 300 <= status < 400:
        return ("Máy chủ trả về chuyển hướng. Kiểm tra lại địa chỉ Peto; CLI không theo chuyển hướng để giữ an toàn "
                "cho token.")
    try:
        payload = json.loads(response.read(64 * 1024) or b"{}")
        if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
            return payload["detail"]
    except (ValueError, OSError, http.client.HTTPException):
        pass
    if status >= 500:
        return "Máy chủ Peto đang gặp sự cố, thử lại sau nhé."
    return HINTS.get(status, f"Máy chủ không nhận yêu cầu (HTTP {status}).")


class Client:
    def __init__(self, server: str, token: str | None = None, *, timeout: float = 30.0):
        self.server = normalize_server(server)
        self.token = token
        self.timeout = timeout
        parts = urlsplit(self.server)
        self._secure = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port

    def _connection(self, timeout: float) -> http.client.HTTPConnection:
        if self._secure:
            return http.client.HTTPSConnection(self._host, self._port, timeout=timeout,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self._host, self._port, timeout=timeout)

    def _send(self, method: str, path: str, body: dict | None, *, auth: bool, timeout: float):
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/event-stream"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.token:
                raise ApiError(401, HINTS[401])
            headers["Authorization"] = f"Bearer {self.token}"
        connection = self._connection(timeout)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
        except ssl.SSLError:
            connection.close()
            raise ApiError(0, "Không xác minh được chứng chỉ HTTPS của máy chủ Peto.") from None
        except (OSError, http.client.HTTPException):
            connection.close()
            raise ApiError(0, "Không kết nối được máy chủ Peto: kiểm tra mạng và địa chỉ máy chủ.") from None
        if response.status >= 300:
            message = _error_message(response)
            connection.close()
            raise ApiError(response.status, message)
        return connection, response

    def json(self, method: str, path: str, body: dict | None = None, *, auth: bool = True) -> dict:
        connection, response = self._send(method, path, body, auth=auth, timeout=self.timeout)
        try:
            raw = response.read(MAX_JSON_BYTES + 1)
        except (OSError, http.client.HTTPException):
            raise ApiError(0, "Kết nối tới máy chủ Peto bị ngắt.") from None
        finally:
            connection.close()
        if len(raw) > MAX_JSON_BYTES:
            raise ApiError(0, "Phản hồi của máy chủ lớn bất thường.")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            raise ApiError(0, "Phản hồi không phải JSON của Peto; có thể địa chỉ máy chủ sai.") from None
        if not isinstance(payload, dict):
            raise ApiError(0, "Phản hồi không đúng định dạng của Peto.")
        return payload

    def stream(self, path: str, body: dict, *, timeout: float = 600.0, on_idle=None) -> Iterator[dict]:
        """Đọc từng sự kiện SSE. Ctrl+C lúc đang chờ thì đóng kết nối rồi để KeyboardInterrupt đi tiếp.

        ``on_idle`` được gọi khoảng 5 lần mỗi giây khi chưa có sự kiện mới, để cập nhật dòng trạng thái.
        """
        connection, response = self._send("POST", path, body, auth=True, timeout=timeout)
        events: queue.Queue = queue.Queue()

        def reader() -> None:
            try:
                data: list[str] = []
                while line := response.readline():
                    text = line.decode("utf-8").rstrip("\r\n")
                    if text.startswith("data: "):
                        data.append(text[6:])
                    elif not text and data:
                        events.put(("event", json.loads("\n".join(data))))
                        data = []
                if data:
                    events.put(("event", json.loads("\n".join(data))))
                events.put(("end", None))
            except Exception as err:  # noqa: BLE001 - chuyển mọi lỗi đọc sang luồng chính
                events.put(("error", err))

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
                    yield value
                elif kind == "end":
                    finished = True
                    return
                else:
                    raise ApiError(0, "Kết nối tới máy chủ Peto bị ngắt giữa chừng.")
        finally:
            if not finished and connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
