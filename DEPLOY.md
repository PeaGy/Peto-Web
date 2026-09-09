# Đưa Peto Web lên VPS

Giả định: cùng VPS đang chạy bot (`/home/ubuntu/peto`, `peto.service`), và
`cloudflared` đã hoạt động cho `download.pearto.shop`.

Sau khi xong, web sẽ ở `https://peto.pearto.shop` (đổi tên tùy bạn) và Peto
đọc được trí nhớ từ bot.

**Không lệnh nào dưới đây được chạy hộ bạn — bạn tự chạy trên VPS.**

---

## 1. Chuẩn bị trên máy cá nhân

Chỉ cần đẩy code lên remote. Giao diện sẽ được build trên VPS (đã kiểm tra:
VPS có Node v22.22.1, thỏa yêu cầu `>=22.12.0` của Vite 8).

```bash
git push origin main
```

`frontend/dist` cố ý nằm trong `.gitignore` — bản build không đi qua git.

---

## 2. Lấy code về VPS

```bash
cd /home/ubuntu
git clone https://github.com/PeaGy/Peto-Web.git peto-web
cd peto-web

python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

Nếu repo để **private**, VPS sẽ bị hỏi mật khẩu. Cách gọn nhất là tạo một
Personal Access Token trên GitHub (quyền đọc repo là đủ) rồi clone bằng
`https://<token>@github.com/PeaGy/Peto-Web.git`. Token đó nằm trong
`.git/config` của VPS nên đừng dùng token có nhiều quyền hơn mức cần.

---

## 3. Build frontend trên VPS

```bash
cd /home/ubuntu/peto-web/frontend
npm ci
npm run build
```

Xong sẽ có `/home/ubuntu/peto-web/frontend/dist`. Backend tự tìm thấy thư mục
này và phục vụ giao diện luôn — không cần nginx.

`npm ci` cài đúng phiên bản trong `package-lock.json`, đừng dùng `npm install`
ở production.

---

## 4. Tạo `.env`

`.env` **không** đi theo `git pull` — phải tạo bằng tay trên VPS.

```bash
cd /home/ubuntu/peto-web
cp .env.example .env
nano .env
```

Điền:

```ini
PETO_AI_PROVIDER=xai

DISCORD_CLIENT_ID=<như trên máy bạn>
DISCORD_CLIENT_SECRET=<như trên máy bạn>
DISCORD_REDIRECT_URI=https://peto.pearto.shop/api/auth/discord/callback

PETO_ALLOWED_DISCORD_IDS=<4 ID của nhóm, cách nhau bằng dấu phẩy>
PETO_SESSION_SECRET=<sinh MỚI, đừng dùng lại khóa của máy cá nhân>
PETO_FRONTEND_URL=https://peto.pearto.shop

# Bắt buộc khi chạy HTTPS — không có dòng này thì trình duyệt
# sẽ không giữ cookie đăng nhập.
PETO_COOKIE_SECURE=true
```

Sinh khóa phiên mới:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Rồi khóa quyền đọc file:

```bash
chmod 600 .env
```

---

## 5. Đăng nhập xAI trên VPS

VPS không có trình duyệt, nên dùng chế độ thủ công:

```bash
cd /home/ubuntu/peto-web/backend
../.venv/bin/python -m xai_auth login --manual
```

Nó in ra một link. Mở link đó **trên máy cá nhân**, đăng nhập xAI. Trình duyệt
sẽ nhảy tới `http://127.0.0.1:56122/callback?...` và báo **không kết nối được**
— chuyện đó là bình thường và đúng như mong đợi. Copy nguyên địa chỉ trên thanh
URL, dán vào terminal SSH.

Kiểm tra:

```bash
../.venv/bin/python -m xai_auth status     # phải ra "Chế độ: oauth"
```

---

## 6. Cập nhật Discord Developer Portal

Vào application → **OAuth2** → **Redirects** → thêm:

```
https://peto.pearto.shop/api/auth/discord/callback
```

**Save Changes.** Giữ luôn cả redirect `localhost` cũ nếu bạn còn muốn chạy
local — Discord cho phép nhiều redirect.

---

## 7. Cài service

```bash
sudo cp /home/ubuntu/peto-web/deploy/peto-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now peto-web
sudo systemctl status peto-web --no-pager -l
```

Thử tại chỗ trước khi ra Internet:

```bash
curl -s http://127.0.0.1:8001/api/health
# {"ok":true,"provider":"xai"}
```

---

## 8. Cho Cloudflare Tunnel trỏ vào

Thêm hostname mới vào cấu hình `cloudflared` đang có (thường là
`/etc/cloudflared/config.yml`) — **thêm** vào danh sách `ingress`, đừng thay
mục của download gateway:

```yaml
ingress:
  - hostname: peto.pearto.shop
    service: http://127.0.0.1:8001
  - hostname: download.pearto.shop
    service: http://127.0.0.1:8765
  - service: http_status:404
```

Mục `http_status:404` phải luôn nằm cuối cùng.

```bash
sudo systemctl restart cloudflared
```

Rồi tạo bản ghi DNS cho `peto.pearto.shop` trỏ vào tunnel (Cloudflare
Dashboard, hoặc `cloudflared tunnel route dns <tên-tunnel> peto.pearto.shop`).

Mở https://peto.pearto.shop — phải thấy màn hình đăng nhập Discord.

---

## 9. Bật trí nhớ từ Discord

Giờ web và bot đã cùng máy, phần này mới dùng được.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Lấy **một** token đó, đặt vào **cả hai** `.env`:

```ini
# /home/ubuntu/peto/.env   (bot)
MEMORY_GATEWAY_TOKEN=<token>

# /home/ubuntu/peto-web/.env   (web)
PETO_MEMORY_GATEWAY_URL=http://127.0.0.1:8766
PETO_MEMORY_GATEWAY_TOKEN=<cùng token>
```

Khởi động lại cả hai:

```bash
sudo systemctl restart peto
sudo systemctl restart peto-web
```

Kiểm tra cổng trí nhớ đã mở:

```bash
curl -s http://127.0.0.1:8766/health
# {"status":"ok","service":"peto-memory-gateway"}
```

Cổng này **chỉ nghe loopback**. Đừng thêm nó vào `cloudflared`, đừng mở
firewall cho nó.

---

## Cập nhật về sau

```bash
cd /home/ubuntu/peto-web
git status --short          # có thay đổi lạ thì dừng lại xem, đừng ép pull
git pull --ff-only origin main
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci && npm run build && cd ..
sudo systemctl restart peto-web
sudo journalctl -u peto-web -n 50 --no-pager
```

---

## Khi hỏng thì xem gì

| Hiện tượng | Nguyên nhân hay gặp |
| --- | --- |
| Đăng nhập xong lại quay về màn hình đăng nhập | Thiếu `PETO_COOKIE_SECURE=true`, cookie bị trình duyệt bỏ |
| Discord báo `Invalid OAuth2 redirect_uri` | Chưa thêm redirect production vào Developer Portal |
| Vào web thấy 404 | Chưa build frontend, hoặc thiếu `frontend/dist` |
| `provider` là `mock` | Thiếu `PETO_AI_PROVIDER=xai` trong `.env` |
| Peto không nhớ gì từ Discord | Token hai bên không khớp, hoặc bot chưa restart |
| Bảo "chưa đăng nhập xAI" | Chưa chạy `xai_auth login --manual` trên VPS |

Log:

```bash
sudo journalctl -u peto-web -n 100 --no-pager -a -l
sudo journalctl -u peto -n 100 --no-pager -a -l
```

---

## Lưu ý an toàn

- `.env`, `backend/data/peto_web.db` và `backend/data/xai_tokens.json` **không
  bao giờ** được commit. `.gitignore` đã chặn sẵn.
- Dùng `PETO_SESSION_SECRET` **khác** giữa máy cá nhân và VPS.
- Chỉ Discord ID trong `PETO_ALLOWED_DISCORD_IDS` vào được. Muốn thêm bạn thì
  thêm ID rồi restart — không có đăng ký công khai.
- Bot và web **ăn chung hạn mức xAI** vì cùng tài khoản. Bị giới hạn tần suất
  thì đó là lý do.
