"""Phục vụ bản build bằng fallback thật để kiểm thử trình duyệt, không mở database hay gọi dịch vụ ngoài."""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from core import static_files


async def identity():
    """Danh tính giả cho ảnh xem trước, tránh gọi Discord trong kiểm thử."""
    return {'name': 'Peto', 'avatar_url': None}


static_files.get_app_identity = identity
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/api/routing-health')
async def health():
    """Endpoint đăng ký trước fallback phải tiếp tục trả JSON."""
    return {'ok': True}


if not static_files.mount(app, ROOT / 'frontend' / 'dist'):
    raise RuntimeError('Cần build frontend trước khi kiểm thử routing trên FastAPI.')

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=5179)
