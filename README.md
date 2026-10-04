# Peto Web

Giao diện chat riêng cho Peto, trợ lý AI trả lời trung thực và đi thẳng vào việc. Tên Peto lấy từ bot Discord
`Peto bot`; web này độc lập với bot, có database riêng.

## Có gì

- **Chat:** chữ, ảnh, đọc PDF/Word/tệp chữ, tạo tệp DOCX/PDF, slide PowerPoint, bảng tính Excel, vẽ sơ đồ, tìm web, chọn model (Peto, GPT-6).
- **Tạo ảnh:** tạo và sửa ảnh, thư viện ảnh.
- **Companion:** nhân vật Live2D/VRM, giọng nói, nghe bằng micro, trí nhớ.
- **Peto Agent:** CLI chạy trên máy bạn, làm việc với thư mục dự án.
- **Đăng nhập:** Discord, Google hoặc khách. Đăng ký mở cho mọi người.

Hướng dẫn dùng nằm ở `/docs/` trên site.

## Chạy thử

Cần Python 3.12+ và Node 22.12+.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env    # điền các biến cần dùng, xem bên dưới
```

Hai terminal:

```bash
cd backend && ../.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

Mở http://localhost:5173. Muốn thử giao diện mà không gọi AI, đặt `PETO_AI_PROVIDER=mock` trong `.env`.

Với xAI thật, đăng nhập một lần trên máy chạy server:

```bash
cd backend && ../.venv/Scripts/python.exe -m xai_auth login
```

## Cấu hình

Mọi biến môi trường được khai báo và giải thích trong [.env.example](.env.example).

- **Discord:** tạo application ở https://discord.com/developers/applications, lấy Client ID và Secret, thêm redirect
  `http://localhost:5173/api/auth/discord/callback`.
- **Google (tùy chọn):** OAuth client loại Web application; thiếu khóa thì nút Google tự ẩn.
- **Session:** `python -c "import secrets; print(secrets.token_urlsafe(32))"` cho `PETO_SESSION_SECRET`.

## Kiểm thử

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest
cd frontend && npm test && npm run build
.venv/Scripts/python.exe -m pytest agent-cli/tests
```

Test dùng nhà cung cấp giả và database tạm, không chạm dữ liệu thật.

Kiểm tra giao diện PC/mobile bằng trình duyệt: từ `frontend`, chạy `npx playwright install chromium` một lần,
rồi `npm run test:browser`. Bộ kiểm tra so sánh ảnh chuẩn và thử phục hồi sau mất mạng, không dùng lượt AI.
Xem [hướng dẫn và giới hạn](frontend/browser-tests/README.md). Workflow frontend chạy các kiểm tra khi push/PR,
không tự triển khai web.

## Tài liệu khác

- [CLAUDE.md](CLAUDE.md): kiến trúc và các quy ước của code.
- [backend/README.md](backend/README.md): cấu trúc backend và nơi thêm tính năng.
- [deploy/OPERATIONS.md](deploy/OPERATIONS.md): sao lưu, diễn tập khôi phục và báo cáo vận hành.
- [DEPLOY.md](DEPLOY.md): đưa lên VPS.
- [agent-cli/README.md](agent-cli/README.md): cài và dùng Peto Agent.
- [voice-worker/README.md](voice-worker/README.md): nối máy tạo giọng.
