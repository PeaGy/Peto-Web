# Backend Peto Web

Backend chia theo tính năng. `main.py` chỉ khởi tạo ứng dụng, gắn router và phục vụ frontend.

```text
backend/
  main.py                # Điểm chạy uvicorn main:app
  xai_auth.py            # Giữ lệnh python -m xai_auth login/status/logout
  core/                  # Cấu hình, khởi động, giới hạn tải, nhận diện, static
  ai/                    # Provider, danh mục model, routing effort, đăng nhập xAI
  features/
    accounts/            # Đăng nhập, hồ sơ, đọc trí nhớ Discord
    chat/                # Chat, lịch sử, phiên bản hội thoại, đặt tiêu đề
    projects/            # Dự án, hướng dẫn riêng, tài liệu chung và ngữ cảnh được chọn
    companion/           # API, ghi nhớ, cảm xúc, ghi chú riêng
    imagine/             # Tạo/sửa ảnh và thư viện
    documents/           # Đọc, tạo, xuất và xem tài liệu
    agent/               # API Agent, công cụ, bộ cài, hướng dẫn CLI
    docs/                # API hướng dẫn, tìm kiếm và ngữ cảnh cho Peto
    voice/               # API giọng nói và gọi dịch vụ tạo giọng
  storage/               # Schema và truy vấn SQLite theo nhóm dữ liệu
  prompts/               # Trợ lý, nhập vai, Companion, Agent, sơ đồ, hồ sơ
  shared/                # Tệp, công cụ đọc/tìm tệp, thời gian, nguồn web, SSE
  tests/                 # Kiểm tra với provider giả và dữ liệu tạm
  assets/                # Font và tài nguyên xuất tài liệu
  docs_content/          # Nội dung hướng dẫn công khai
  data/                  # Dữ liệu chạy; không đưa vào Git
```

## Luồng chat

- `features/chat/api.py`: nhận yêu cầu, trả lịch sử và tệp; đăng ký `/api/chat`.
- `schemas.py`: định nghĩa dữ liệu gửi lên và giới hạn lựa chọn.
- `service.py`: kiểm tra quyền, xếp hàng, gọi AI, stream SSE và lưu câu trả lời. Timeout/hủy vẫn giữ phần đã phát.
- `history.py`: chọn lịch sử, phân bổ nội dung tài liệu, lọc ghi chú/cảm xúc khỏi dữ liệu công khai.
- `prompt_context.py`: ghép persona với hướng dẫn, hồ sơ và trí nhớ của đúng tài khoản.
- `titles.py`, `conversations.py`: đặt tiêu đề, đổi tên, ghim và tạo nhánh khi sửa tin nhắn.

## Thêm hoặc sửa tính năng

Đặt router và logic trong thư mục tương ứng dưới `features/`. Các module dùng chung nằm trong `shared/`; code provider
nằm trong `ai/`. Không import `main.py` từ tính năng. Gắn router mới trước `static_files.mount()` trong `main.py`.

`storage/__init__.py` là giao diện truy vấn chung. SQL chia thành `users`, `conversations`, `attachments`, `documents`,
`imagine`, `agent`, `usage`, `memory`; khởi tạo và nâng cấp bảng nằm trong `schema.py`. Kết nối dùng chung ở
`storage/connection.py`. Mọi thao tác trên dữ liệu tài khoản phải giữ kiểm tra `owner`.

Prompt chia theo ngữ cảnh trong `prompts/`. Phần nhập vai chỉ nằm trong `roleplay.py`; không đưa vào prompt trợ lý,
Agent hay Companion. Cách ghép ngữ cảnh theo tài khoản nằm ở `features/chat/prompt_context.py`.

Khi viết test, patch module sở hữu hàm: provider chat ở `features.chat.service`, ngân sách nội dung tài liệu ở
`features.chat.history`, database cho test nâng cấp ở `storage.connection`. Patch lớp provider thay vì instance dùng chung.

## Chạy và kiểm tra

Từ thư mục gốc dự án:

```powershell
cd backend
../.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
../.venv/Scripts/python.exe -m pytest
```

Giữ nguyên `.env` tại gốc dự án, đường dẫn database/upload/token hiện có và lệnh systemd `uvicorn main:app`.
Tách thư mục không yêu cầu chuyển dữ liệu hay đổi API. Test đặt cấu hình giả trước khi import ứng dụng và không
gọi AI thật. Quy tắc chi tiết nằm trong `../CLAUDE.md`.

## Vận hành

`ops/` chứa công cụ sao lưu, kiểm tra/khôi phục vào thư mục riêng và tổng hợp log tốc độ/token/chi phí ước tính.
Hướng dẫn cùng cấu hình timer VPS nằm ở [deploy/OPERATIONS.md](../deploy/OPERATIONS.md). Chưa tự bật lịch hoặc
thay dữ liệu đang dùng. Sao lưu gồm database và uploads; `.env`/credential lưu riêng.
