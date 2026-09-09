# Peto Web

Giao diện chat riêng cho Peto, tách khỏi Discord. Bước 1: **chat chữ**.

Bot Discord (`Tracen Jukebox`) vẫn phát triển độc lập. Project này không đọc,
không ghi và không chia sẻ dữ liệu với bot cũ. Xem `PETO_WEB_HANDOFF.md` để
biết bối cảnh và những gì còn để ngỏ.

## Chạy

Cần Python 3.12+ và Node 20+.

```bash
# 1. Cài đặt
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 2. Cấu hình
cp .env.example .env      # rồi điền phần Discord, xem bên dưới

# 3. Đăng nhập xAI một lần trên máy chạy server
cd backend
../.venv/Scripts/python.exe -m xai_auth login
../.venv/Scripts/python.exe -m xai_auth status

# 4. Chạy — hai terminal
cd backend && ../.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

Mở http://localhost:5173. Dev server của Vite tự proxy `/api` sang backend nên
không cần cấu hình CORS khi chạy local.

### Cấu hình đăng nhập Discord

1. Vào https://discord.com/developers/applications, tạo application (hoặc dùng
   application sẵn có của bot).
2. Tab **OAuth2**: copy `CLIENT ID` và `CLIENT SECRET` vào `.env`.
3. Vẫn tab đó, thêm **Redirect**:
   `http://localhost:5173/api/auth/discord/callback`
4. Điền `PETO_ALLOWED_DISCORD_IDS` bằng Discord ID của từng người trong nhóm,
   cách nhau bằng dấu phẩy. **Rỗng nghĩa là không ai vào được.**
5. Sinh `PETO_SESSION_SECRET`:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`

Chưa biết Discord ID? Cứ đăng nhập thử — nếu chưa được cho phép, trang sẽ hiện
đúng ID của tài khoản đó để bạn thêm vào danh sách.

## Đưa lên VPS

Xem [DEPLOY.md](DEPLOY.md) — từng bước cho VPS đang chạy bot, kèm cách bật
trí nhớ từ Discord và bảng tra khi hỏng.

Ở production, backend phục vụ luôn giao diện đã build (`frontend/dist`), nên
chỉ cần một tiến trình và một cổng cho Cloudflare Tunnel trỏ vào — không cần
nginx. Lúc dev không có `dist` nên Vite vẫn lo phần giao diện như cũ.

## Kiểm thử

```bash
cd backend
../.venv/Scripts/python.exe -m pytest
```

Toàn bộ test chạy bằng nhà cung cấp giả và database tạm — không chạm dữ liệu thật.

## Kiến trúc

```
backend/
  main.py        FastAPI: /api/chat (SSE), /api/conversations, /api/health
  auth.py        Đăng nhập Discord OAuth2, cookie phiên có chữ ký
  persona.py     Tính cách Peto, đã tách khỏi Discord
  db.py          SQLite riêng; mọi truy vấn lọc theo owner
  rate_limit.py  Cooldown + đồng thời + hàng chờ có timeout
  xai_auth.py    OAuth xAI riêng của web + CLI login/status/logout
  config.py      Đọc biến môi trường
  ai/
    base.py      Interface ChatProvider — phần còn lại chỉ nói chuyện qua đây
    xai.py       Grok qua xAI Responses API, có stream
    mock.py      Trả lời giả, không gọi mạng
    routing.py   Chọn mức suy luận low/medium/high
frontend/
  src/api.ts     Đọc SSE bằng fetch (endpoint là POST nên không dùng EventSource)
  src/App.tsx    Màn hình đăng nhập + giao diện chat
```

### Đổi nhà cung cấp AI

Thêm một file trong `backend/ai/` cài đặt `ChatProvider`, đăng ký vào
`_PROVIDERS` trong `backend/ai/__init__.py`, rồi đặt `PETO_AI_PROVIDER`. Không
phải sửa route, database hay giới hạn tải.

Đặt `PETO_AI_PROVIDER=mock` bất cứ lúc nào để làm việc trên giao diện mà không
tốn hạn mức xAI.

## Danh tính

Đăng nhập bằng Discord OAuth2 với scope `identify`. Máy chủ tự đổi code lấy
token rồi tự hỏi Discord "người này là ai" — **không bao giờ** nhận Discord ID
do trình duyệt gửi lên. Phiên nằm trong cookie `HttpOnly` có chữ ký.

Discord ID đã xác minh được lưu ở bảng `users` và dùng làm `owner` của mọi hội
thoại (`discord:<id>`).

## Trí nhớ từ Discord (một chiều, chỉ đọc)

Peto trên web có thể đọc trí nhớ dài hạn mà bot Discord đã tích lũy về đúng
người đang đăng nhập, để giữ tính liên tục giữa hai nơi.

**Bật ở cả hai phía** (chỉ dùng được khi web và bot chạy **cùng máy**):

```bash
# Sinh một token dùng chung
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- Repo bot, trong `.env`: `MEMORY_GATEWAY_TOKEN=<token>`
- Peto Web, trong `.env`:
  `PETO_MEMORY_GATEWAY_URL=http://127.0.0.1:8766` và
  `PETO_MEMORY_GATEWAY_TOKEN=<cùng token>`

Rồi khởi động lại cả hai. Để trống token là tắt — web vẫn chat bình thường,
chỉ là Peto không nhớ gì từ Discord.

Giới hạn cố ý của phần này:

- **Một chiều.** Chuyện nói trên web không chảy ngược về trí nhớ Discord.
- **Chỉ bản tóm tắt** và ghi chú đã ghim; không lấy lịch sử chat thô, để không
  mang nguyên văn tin nhắn riêng ở DM sang một bề mặt khác.
- **Chỉ đọc.** Web không có đường nào ghi vào `bot_memory.db`.
- **Loopback.** Cổng của bot chỉ nghe `127.0.0.1`, không bao giờ đặt sau
  Cloudflare Tunnel.
- **Tôn trọng chế độ ẩn danh.** Ai đang bật ẩn danh thì không đọc gì cả.
- **Hỏng thì bỏ qua.** Bot tắt hay token sai thì chat vẫn chạy, chỉ mất trí nhớ.

## Ranh giới đang được giữ

- Prompt của web không chứa tên thật hay Discord ID của thành viên. Có test
  chặn (`tests/test_persona.py`).
- Peto ở web nói rõ là chưa có nhạc, ảnh, tìm kiếm hay giọng nói — không hứa hão.
- Database riêng và **file token xAI riêng**; không dùng chung file nào với
  production Discord.
- Không có credential AI nào xuống trình duyệt. Discord access token chỉ dùng
  một lần để đọc hồ sơ rồi bỏ, không lưu.
- Chỉ Discord ID trong `PETO_ALLOWED_DISCORD_IDS` mới vào được — chưa mở đăng ký
  công khai.
- Mọi truy vấn hội thoại lọc theo `owner` ở backend; biết ID của người khác cũng
  không đọc được.
- Chưa deploy public. Chỉ chạy local.

## Chưa có ở bước này

Upload ảnh, gọi công cụ, giọng nói, nhân vật 3D, đồng bộ trí nhớ với Discord, deploy.
