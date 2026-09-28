# Peto Docs

Trang công khai tại `/docs/`, tiếng Việt trước tiên. Không cần đăng nhập.

- Sửa bài hướng dẫn trong `articles.json`. Mỗi bài có slug cố định, tiêu đề, nhóm, mô tả, từ khóa và nội dung Markdown. Dùng tiêu đề cấp 2 để tạo mục lục.
- Các trang lệnh Agent, skills và MCP lấy cú pháp/chi tiết từ danh mục CLI mà backend đang phục vụ. Cập nhật danh mục CLI khi đổi hành vi lệnh.
- `/api/docs` cung cấp dữ liệu cho giao diện; `/api/docs/search?q=...` tìm kiếm không dấu; `/api/docs/<slug>.md` cung cấp bản văn bản.
- Backend dùng cùng nội dung để bổ sung hướng dẫn cho câu hỏi liên quan đến Peto. Đây là tra cứu từ khóa, không phải công cụ chạy lệnh trên máy người dùng.
- Ảnh thương hiệu nằm trong `frontend/public/docs-assets/`; giao diện trong `frontend/src/Docs.tsx` và `docs.css`.

## Phát hành

Build frontend và triển khai cả frontend lẫn backend cùng phiên bản như website hiện có. Giữ thư mục `backend/docs_content` và danh mục Agent trong bản phát hành. FastAPI phục vụ `/docs/` và đường dẫn từng bài; reverse proxy cần chuyển các đường dẫn này về backend. Không cần thêm dịch vụ docs riêng.

## Kiểm tra

Chạy các test `test_docs_api.py`, `test_static_files.py`, `test_agent_guide.py` phía backend và `Docs.test.tsx` phía frontend. Kiểm tra một bài bằng đường dẫn trực tiếp, tìm kiếm không dấu, menu điện thoại và liên kết Markdown sau khi triển khai.
