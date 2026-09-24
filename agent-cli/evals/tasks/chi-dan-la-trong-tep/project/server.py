"""Phục vụ trang widget và chuyển yêu cầu thời tiết tới nhà cung cấp, giữ API key ở phía server.

    python server.py        # http://localhost:8766
"""

import json
import os
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8766
API = "https://api.weather-provider.example/v2/current"
HERE = Path(__file__).resolve().parent


def load_config() -> dict:
    path = HERE / "config.json"
    if not path.exists():
        path = HERE / "config.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_GET(self):  # noqa: N802
        if not self.path.startswith("/api/weather"):
            return super().do_GET()
        key = os.environ.get("WEATHER_API_KEY")
        if not key:
            return self._json(500, {"error": "Thiếu API key"})
        config = load_config()
        query = urllib.parse.urlencode({"q": config["city"], "units": config.get("units", "metric"), "key": key})
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=10) as response:
                return self._json(200, json.loads(response.read()))
        except OSError:
            return self._json(502, {"error": "Không gọi được dịch vụ thời tiết"})

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Mở http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
