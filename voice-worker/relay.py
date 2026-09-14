"""Nhận việc từ VPS và chuyển tới bộ tạo giọng nội bộ; không mở cổng máy tính."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

LOCAL = "http://127.0.0.1:7862"


def main():
    base = os.environ.get("PETO_VOICE_SERVER_URL", "").rstrip("/")
    token = os.environ.get("PETO_VOICE_WORKER_TOKEN", "")
    url = urlsplit(base)
    if url.scheme != "https" or not url.netloc or url.username or url.query or url.fragment:
        raise SystemExit("PETO_VOICE_SERVER_URL phải là địa chỉ HTTPS của Peto.")
    if len(token) < 32:
        raise SystemExit("Cần PETO_VOICE_WORKER_TOKEN ngẫu nhiên dài ít nhất 32 ký tự, giống trên VPS.")

    def call(path, data=None, local=False, error=False):
        headers = {} if local else {"Authorization": f"Bearer {token}"}
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
        while True:
            try:
                state = json.loads(call("/health", local=True))
                if state.get("ok") and all(v in state.get("voices", []) for v in ["playful-1", "gentle-2"]):
                    call("/worker/heartbeat", {})
            except Exception:
                pass
            time.sleep(5)

    threading.Thread(target=heartbeat, daemon=True).start()
    print("Đang kết nối giọng nói với Peto. Giữ bộ tạo giọng và cửa sổ này chạy.", flush=True)
    while True:
        try:
            raw = call("/worker/next")
            if not raw:
                time.sleep(1)
                continue
            job = json.loads(raw)
            try:
                audio = call("/speak", {"text": job["text"], "voice": job["voice"]}, local=True)
            except Exception:
                call("/worker/result/" + job["id"], b"", error=True)
                continue
            call("/worker/result/" + job["id"], audio)
        except Exception:
            print("Kết nối giọng nói tạm gián đoạn; thử lại sau 5 giây.", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
