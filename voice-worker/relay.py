"""Nhận việc từ VPS và chuyển tới bộ tạo giọng nội bộ; không mở cổng máy tính."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

LOCAL = "http://127.0.0.1:7862"


def error_hint(error):
    """Chỉ hiện loại lỗi; không in URL, khóa hay nội dung phản hồi máy chủ."""
    if isinstance(error, urllib.error.HTTPError):
        hints = {
            401: "Khóa không khớp hoặc VPS chưa nạp PETO_VOICE_WORKER_TOKEN. Kiểm tra khóa và khởi động lại peto-web.",
            403: "Truy cập bị từ chối. Kiểm tra quyền truy cập và lớp bảo vệ Cloudflare.",
            404: "Không tìm thấy API hoặc lượt đọc đã hết hạn. Kiểm tra VPS đã cập nhật code và khởi động lại.",
            502: "Proxy không kết nối được dịch vụ Peto trên VPS.",
            503: "Dịch vụ tạm chưa sẵn sàng.",
        }
        return f"HTTP {error.code}: " + hints.get(error.code, "Máy chủ chưa chấp nhận yêu cầu.")
    if isinstance(error, json.JSONDecodeError):
        return "Phản hồi không phải JSON của API; có thể đang nhận trang HTML hoặc trang đăng nhập."
    if isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return "Không kết nối được máy chủ: kiểm tra mạng, địa chỉ, chứng chỉ HTTPS và dịch vụ đang chạy."
    return "Không xử lý được phản hồi (" + type(error).__name__ + ")."


def main():
    base = os.environ.get("PETO_VOICE_SERVER_URL", "").rstrip("/")
    token = os.environ.get("PETO_VOICE_WORKER_TOKEN", "")
    url = urlsplit(base)
    if url.scheme != "https" or not url.netloc or url.username or url.query or url.fragment:
        raise SystemExit("PETO_VOICE_SERVER_URL phải là địa chỉ HTTPS của Peto.")
    if len(token) < 32:
        raise SystemExit("Cần PETO_VOICE_WORKER_TOKEN ngẫu nhiên dài ít nhất 32 ký tự, giống trên VPS.")

    def call(path, data=None, local=False, error=False):
        headers = {"User-Agent": "Peto-Voice-Worker/1.0"}
        if not local:
            headers["Authorization"] = f"Bearer {token}"
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        if error:
            headers["X-Voice-Error"] = "1"
        request = urllib.request.Request((LOCAL if local else base + "/api/voice") + path, data=data, headers=headers)
        # Không chuyển khóa bí mật tới đích redirect.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=95 if local else 15) as response:
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError("Âm thanh quá lớn.")
            return body

    def heartbeat():
        ready = False
        while True:
            try:
                state = json.loads(call("/health", local=True))
            except Exception:
                ready = False
                print("Bộ tạo giọng trên máy chưa sẵn sàng ở cổng 7862. Chạy local-tts/start-speak.ps1 và đợi nạp model xong.", flush=True)
                time.sleep(5)
                continue
            if state.get("ok") and all(v in state.get("voices", []) for v in ["playful-1", "gentle-2"]):
                try:
                    call("/worker/heartbeat", {})
                    if not ready:
                        print("Bộ tạo giọng đã sẵn sàng và đã gửi trạng thái tới VPS.", flush=True)
                    ready = True
                except Exception as exc:
                    ready = False
                    print("Gửi trạng thái tới VPS: " + error_hint(exc), flush=True)
            else:
                ready = False
                print("Bộ tạo giọng chưa có đủ hai giọng đã cấu hình.", flush=True)
            time.sleep(5)

    threading.Thread(target=heartbeat, daemon=True).start()
    print("Đang kết nối giọng nói với Peto. Giữ bộ tạo giọng và cửa sổ này chạy.", flush=True)
    connected = False
    while True:
        try:
            raw = call("/worker/next")
            if not connected:
                print("Đã kết nối VPS, đang chờ yêu cầu đọc. Mở web Peto → Cài đặt → Giọng nói → nghe thử.", flush=True)
                connected = True
            if not raw:
                time.sleep(1)
                continue
            job = json.loads(raw)
            started = time.monotonic()
            print("Đã nhận yêu cầu, đang tạo âm thanh…", flush=True)
            try:
                audio = call("/speak", {"text": job["text"], "voice": job["voice"]}, local=True)
            except Exception as exc:
                print("Tạo giọng trên máy: " + error_hint(exc), flush=True)
                call("/worker/result/" + job["id"], b"", error=True)
                continue
            call("/worker/result/" + job["id"], audio)
            print(f"Đã gửi âm thanh về VPS sau {time.monotonic() - started:.1f} giây. Đang chờ yêu cầu tiếp theo.", flush=True)
        except Exception as exc:
            connected = False
            print("Kết nối VPS: " + error_hint(exc) + " Thử lại sau 5 giây.", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
