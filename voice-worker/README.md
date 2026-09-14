# Chia sẻ giọng Peto từ máy Windows qua VPS

Web gọi `/api/voice`; máy Windows chủ động nhận việc qua HTTPS, gọi bộ tạo giọng
ở `127.0.0.1:7862`, rồi gửi WAV về VPS. Người nghe không cài model hay cấp quyền mạng nội bộ.
Hai giọng giữ nguyên: `playful-1` và `gentle-2`.

## Cấu hình một lần

1. Đưa backend mới và frontend đã build lên VPS theo cách triển khai hiện tại.
2. Tạo một khóa ngẫu nhiên ít nhất 32 ký tự (ví dụ `secrets.token_urlsafe(32)` trong Python).
   Đặt `PETO_VOICE_WORKER_TOKEN` trong môi trường dịch vụ Peto trên VPS; khởi động lại dịch vụ.
   Không đặt khóa trong frontend, Git hay nội dung chat.
3. Trên Windows chương trình sẽ hỏi địa chỉ web và khóa khi chưa có biến môi trường.
   Nhập địa chỉ HTTPS của web Peto, không thêm `/api/voice`, và cùng khóa trên VPS.
   Khóa được nhập ẩn, chỉ giữ trong phiên PowerShell. Có thể cấu hình trước
   `PETO_VOICE_WORKER_TOKEN` và `PETO_VOICE_SERVER_URL` bằng biến môi trường nếu muốn.
4. Chạy `local-tts/start-speak.ps1` như trước, đợi model sẵn sàng.
5. Trong cửa sổ PowerShell thứ hai, chạy `voice-worker/start-relay.ps1`.
6. Đăng nhập Peto trên thiết bị khác, bật Giọng nói trong Cài đặt và bấm nghe thử.

Trong thư mục dự án trên VPS, sau khi code đã được commit/push từ máy phát triển:

```bash
git pull
cd frontend
npm ci
npm run build
cd ..
```

Tạo khóa ngay trong terminal riêng của bạn (không gửi vào chat):

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Thêm `PETO_VOICE_WORKER_TOKEN=<khóa vừa tạo>` vào tệp `.env` mà Peto đang dùng
hoặc môi trường systemd của dịch vụ; không commit tệp này. Sau đó:

```bash
sudo systemctl restart peto-web
```

Trên Windows, từ thư mục dự án, mở hai cửa sổ PowerShell:

```powershell
.\local-tts\start-speak.ps1
```

```powershell
.\voice-worker\start-relay.ps1
```

Nếu bộ tạo giọng đang chạy thì chỉ cần cửa sổ relay. Không bật thêm bản model thứ hai.

## Điều kiện vận hành

- Backend phải chạy **một tiến trình Uvicorn**, không dùng nhiều worker/replica: hàng chờ
  tạm nằm trong RAM. Chỉ chạy một relay Windows. Mở rộng cần hàng chờ dùng chung.
- Không cần Docker, mở cổng router hoặc công khai cổng 7862.
- Cả bộ tạo giọng, relay Windows và VPS cần hoạt động. Tắt relay để ngừng chia sẻ.
- Tối đa bốn lượt đang chờ/xử lý, mỗi tài khoản một lượt, 300 ký tự/lượt,
  một lượt tạo trên GPU mỗi lần. Máy bận báo thử lại; thời gian chờ tối đa 120 giây.
- Ngoại tuyến được phát hiện sau khoảng 15 giây không nhận tín hiệu. Chat chữ vẫn hoạt động.
- Hủy hoặc hết thời gian chờ sẽ xóa lượt trên VPS; GPU có thể phải hoàn tất câu đang tạo.
  Âm thanh về muộn bị bỏ, không chuyển sang người khác. Không lưu WAV trên VPS.
- Khởi động lại VPS sẽ mất hàng chờ; người nghe thử lại. Relay tự kết nối lại khi mất mạng.
- Máy Windows xử lý nội dung mà người dùng yêu cầu đọc. Không ghi nội dung đó trong log relay.

## Kiểm chứng trước khi dùng thật

Thử hai tài khoản trên hai thiết bị, cả hai giọng; tắt relay và thử lại sau 15 giây;
kiểm tra chat chữ vẫn dùng được. Các kiểm thử tự động dùng WAV giả để kiểm tra đường truyền,
không thay thế bước nghe thật qua mạng sau triển khai.
