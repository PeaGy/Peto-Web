# Sao lưu và báo cáo vận hành Peto

Công cụ chạy trên máy chủ, không có API công khai, không gọi AI và không đổi schema. Hiện chưa bật lịch trên VPS.
Trước khi bật, kiểm tra cơ chế sao lưu/snapshot đang có ở nhà cung cấp để tránh chạy hai lịch trùng nhau.

## Dữ liệu được giữ

`ops.backup` giữ database theo `PETO_WEB_DB` và toàn bộ thư mục `PETO_UPLOAD_DIR`. Database chứa hội thoại,
hồ sơ, ghi nhớ, quota, tài liệu và các tệp DOCX/PDF đã tạo; thư mục tải lên chứa tệp đính kèm và thư viện ảnh.
Không sao chép `.env`, token xAI, mã nguồn, log hoặc dữ liệu bot Discord. Cần giữ `.env` trong kho bí mật riêng
để dựng lại dịch vụ; xAI có thể đăng nhập lại. Bản sao dữ liệu chứa thông tin riêng tư, chưa mã hóa. Trên Linux,
công cụ tạo thư mục riêng quyền 700 và bản sao quyền 600; trên Windows cần dùng thư mục có quyền truy cập phù hợp.

Bản sao SQLite dùng [Backup API của SQLite](https://www.sqlite.org/backup.html), gồm cả phần đã commit còn trong WAL.
Toàn bộ tiến trình ghi dữ liệu vẫn phải dừng để tệp tải lên khớp với database. `--offline` xác nhận người chạy đã
làm việc này, không tự phát hiện hoặc dừng server. Nếu có nhiều worker/service cùng ghi vào dữ liệu, dừng tất cả.
Script mẫu dưới đây chỉ dừng `peto-web.service`; không ảnh hưởng bot Discord.

## Thử trên máy cá nhân

Từ thư mục `backend`, sau khi dừng backend đang dùng dữ liệu cần sao lưu:

```powershell
../.venv/Scripts/python.exe -m ops.backup create --offline --output ../backups --keep 7
../.venv/Scripts/python.exe -m ops.backup verify ../backups/<ten-ban-sao>.zip
../.venv/Scripts/python.exe -m ops.backup restore ../backups/<ten-ban-sao>.zip --destination ../restore-drill
```

Có thể chỉ định `--db` và `--uploads` khi thử với bộ dữ liệu riêng. Chạy từ `backend` giống server để các đường dẫn
tương đối trong cấu hình có cùng nghĩa. Verify/restore không cần nạp `.env`.

Mỗi bản có database, tệp và danh sách SHA-256/kích thước/số dòng từng bảng. Công cụ kiểm tra toàn bộ trước khi
công bố bản mới, chỉ sau đó mới bỏ các bản cũ vượt quá `--keep` (mặc định 7 bản thành công). Không xóa các tệp khác
trong thư mục sao lưu. Bản sao thiếu tệp, hỏng hash/database, có đường dẫn ngoài thư mục tải lên hoặc liên kết tượng
trưng/junction bị từ chối. Lỗi trước khi công bố bản mới không làm mất các bản cũ.

Khôi phục chỉ nhận thư mục **chưa tồn tại**, không ghi đè database đang dùng. Đường dẫn tệp được đổi trong database
khôi phục để trỏ vào thư mục mới. Mã kiểm tra trong archive áp dụng cho bản gốc, trước khi đổi đường dẫn.
Sao lưu và khôi phục trên cùng hệ điều hành; chuyển Windows/Linux cần chuyển đổi đường dẫn riêng.
Kiểm tra yêu cầu dung lượng trống: bản sao nén, snapshot SQLite và một lượt giải nén kiểm tra cùng tồn tại;
thư mục tạm hệ thống cũng phải đủ chỗ cho dữ liệu giải nén.

Nếu tiến trình bị tắt cưỡng bức, `.peto-backup-lock` và tệp `.partial` có thể còn lại. Chỉ dọn các mục này sau khi
xác minh không còn tiến trình sao lưu. Công cụ không tự phá khóa cũ để tránh hai lượt chạy đè nhau.

## Bật lịch trên VPS

Mẫu dùng project `/home/ubuntu/peto-web`, tài khoản `ubuntu`, dịch vụ `peto-web.service`, thư mục sao lưu
`/home/ubuntu/peto-backups`. Nếu thực tế khác, sửa `backup-peto.sh` và các unit trước. Không dùng thư mục nằm trong
`backend/data` hoặc uploads; service web không cần quyền truy cập bản sao. Chưa có cấu hình đẩy bản sao ra máy khác.

Script tạm dừng web trong lúc sao lưu và kiểm tra, sau đó mở lại nếu web đã chạy trước đó; lỗi bình thường cũng mở lại.
`ExecStopPost` dùng marker riêng để mở lại web nếu lượt sao lưu bị dừng bất thường. Web vốn đang dừng thì giữ dừng.
Không thao tác khởi động/dừng web bằng tay đồng thời với lượt sao lưu. Khoảng nghỉ phụ thuộc kích thước dữ liệu,
nên chọn giờ ít người dùng; các lượt chat đang chạy có thể bị ngắt khi service dừng.

```bash
cd /home/ubuntu/peto-web
sudo cp deploy/peto-backup.service deploy/peto-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start peto-backup.service
sudo journalctl -u peto-backup.service -n 50 --no-pager
systemctl is-active peto-web.service
```

Sau khi lần thử thành công, lấy tên archive vừa tạo và diễn tập vào thư mục mới:

```bash
cd /home/ubuntu/peto-web/backend
../.venv/bin/python -m ops.backup restore /home/ubuntu/peto-backups/<ten-ban-sao>.zip --destination /home/ubuntu/peto-restore-drill
```

Có thể mở backend tạm chỉ nghe loopback, dùng dữ liệu đã phục hồi, provider giả và khóa phiên riêng để kiểm tra:

```bash
PYTHON_DOTENV_DISABLED=1 PETO_AI_PROVIDER=mock PETO_MEMORY_GATEWAY_URL='' PETO_MEMORY_GATEWAY_TOKEN='' OPENAI_API_KEY='' PETO_SESSION_SECRET='khoa-phien-thu-rieng' PETO_COOKIE_SECURE=false PETO_WEB_DB=/home/ubuntu/peto-restore-drill/database/peto_web.db PETO_UPLOAD_DIR=/home/ubuntu/peto-restore-drill/uploads PETO_XAI_TOKEN_PATH=/home/ubuntu/peto-restore-drill/test-tokens.json ../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8011
```

Không đưa server thử vào Cloudflare Tunnel. Xác minh khởi động, lịch sử, tải ảnh/tệp và xem tài liệu trên bản thử;
test tự động đã kiểm tra schema hiện tại, đọc lịch sử và cách ly owner trên database khôi phục. Không chuyển dữ liệu
thử thành production tự động. Khi cần phục hồi thật, dừng dịch vụ và trỏ cấu hình tới database/uploads đã kiểm tra;
giữ dữ liệu cũ để có thể quay lại. `.env`/credential vẫn lấy từ nơi lưu bí mật riêng.

Sau diễn tập thành công:

```bash
sudo systemctl enable --now peto-backup.timer
systemctl list-timers peto-backup.timer
```

Timer chạy khoảng 03:30 **theo múi giờ máy chủ**, lệch tối đa 10 phút; không chạy bù ngay khi reboot.
Kiểm tra log nếu service báo lỗi. Một bản sao trên cùng VPS chỉ giúp phục hồi lỗi dữ liệu; cần sao chép thêm bản
đã kiểm tra sang nơi lưu riêng để chịu được mất VPS/ổ đĩa. Chưa chọn dịch vụ lưu ngoài nên bước này chưa tự động.

## Báo cáo vận hành

Backend bật INFO cho nhánh logger `peto_web` khi khởi động, ghi thời gian, model, effort và mã kết quả; không thêm
nội dung tin nhắn, khóa tài khoản hoặc credential vào các bản ghi thống kê. Công cụ chỉ đọc các trường thống kê,
không in log thô. Các log lỗi cũ vẫn theo cơ chế của provider.

Từ `backend` trên VPS:

```bash
journalctl -u peto-web.service --since '24 hours ago' --no-pager -o cat | ../.venv/bin/python -m ops.report
journalctl -u peto-web.service --since '7 days ago' --no-pager -o cat | ../.venv/bin/python -m ops.report --json
```

Hoặc đọc tệp log trên Windows:

```powershell
../.venv/Scripts/python.exe -m ops.report ../operations-output/server.log --json
```

Không đưa cùng bản ghi hai lần, ví dụ tệp log và bản journal chứa cùng thời điểm. Thời gian báo cáo là phạm vi log
đầu vào; công cụ không lọc ngày thêm lần nữa. Báo cáo tổng hợp theo model/effort/mode, số lượt hoàn tất/ngắt,
nguyên nhân kết thúc, p50/p95 tổng thời gian, phản hồi đầu, hàng chờ và chuẩn bị. Với Agent, phản hồi đầu là sự kiện
đầu tiên (có thể là suy nghĩ/công cụ), không nhất thiết là chữ hiển thị. Log cũ thiếu outcome chỉ đánh dấu incomplete.
Lỗi bị từ chối trước khi vào stream, như xác thực/đầu vào không hợp lệ, không nằm trong thống kê này.

`model_usage` có số token/cache và số lần tìm web quan sát được của provider chat/tiêu đề; không tính token suy luận
lần hai vì đã nằm trong output token. `purpose` là nhãn kỹ thuật hiện có, các tác vụ phụ dùng chung provider có thể
chung nhãn `title` hoặc `chat`; không coi đó là bảng chi phí chính xác theo tính năng. Agent có log timing riêng,
token đã lưu theo ngày có thể xem bằng `--db /duong-dan/peto_web.db`. Tùy chọn này cũng đọc tổng ký tự giọng theo tháng
và khoản USD đã dự trù trong `speech_budget`; khoản dự trù không phải hóa đơn. Nó tổng hợp **toàn bộ** ngày/tháng trong
database, không cùng phạm vi với journal. Không xuất thông tin tài khoản. Kết nối chỉ đọc, không tạo database mới.

Chi phí token là tùy chọn: `--rates /duong-dan/don-gia.json`. Đơn giá là USD trên một triệu token, khóa là **model ID
trong log**, không phải tên hiển thị `peto`, `luna`. File cần ba giá cho mỗi model, dạng sau (các số chỉ minh họa):

```json
{
  "model-id-trong-log": {"input": 1, "cached_input": 0.5, "output": 2}
}
```

Người vận hành điền và cập nhật giá phù hợp nhà cung cấp/gói sử dụng. Không có bảng giá hardcode có thể cũ.
Lượt thiếu usage/cache/đơn giá sẽ không được định giá; báo cáo chỉ rõ số lượt có giá trên tổng lượt gọi.
Phí tìm web, tạo ảnh, giọng nói, tác vụ Agent không có usage theo model trong log, thuế và usage ngoài Peto không
nằm trong ước tính token này. Đối chiếu billing của nhà cung cấp khi cần số tiền thực tế. Không cộng khoản dự trù TTS
vào tổng token. Công cụ không thu thập metrics vào database và không mở dashboard quản trị mới.

## Kiểm tra code

```powershell
cd backend
../.venv/Scripts/python.exe -m pytest tests/test_operations.py tests/test_chat.py tests/test_agent_api.py tests/test_startup.py
```

Kiểm tra dùng database/uploads giả: WAL, tài liệu BLOB, ảnh, hash hỏng, đường dẫn nguy hiểm, tệp thiếu, giữ bản cũ,
khóa chạy đồng thời, khôi phục schema hiện tại, báo cáo token/đơn giá và logger không nhân đôi. Không đọc dữ liệu thật.
Script VPS cũng được thử bằng lệnh hệ thống giả cho trường hợp web đang chạy/đang dừng và sao lưu thành công/thất bại.
Chưa thử bật unit trên máy Linux/VPS thực tế; cần hoàn tất lần chạy thủ công ở trên trước khi bật timer.
