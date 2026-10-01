# Peto Docs

Trang công khai tại `/docs/`, tiếng Việt trước tiên. Không cần đăng nhập.

- Sửa bài hướng dẫn trong `articles.json`. Mỗi bài có slug cố định, tiêu đề, nhóm, mô tả, từ khóa và nội dung Markdown. Dùng tiêu đề cấp 2 để tạo mục lục.
- Các trang lệnh Agent, skills và MCP lấy cú pháp/chi tiết từ danh mục CLI mà backend đang phục vụ. Cập nhật danh mục CLI khi đổi hành vi lệnh.
- `/api/docs` cung cấp dữ liệu cho giao diện; `/api/docs/search?q=...` tìm kiếm không dấu; `/api/docs/<slug>.md` cung cấp bản văn bản.
- Peto dùng chính các bài này khi trả lời trong chat (Trò chuyện, Companion, nhập vai). Ở mỗi lượt, backend tìm trong 3 tin nhắn gần nhất của người dùng nguyên cụm tiêu đề hoặc từ khóa của bài (không dấu, trọn từ), rồi gắn tối đa 2 bài khớp nhất kèm liên kết. Người dùng không cần nhắc tên Peto. Đây là tra cứu từ khóa, không phải công cụ chạy lệnh trên máy người dùng.
- Viết từ khóa không dấu, viết thường. Từ khóa một chữ (`peto`, `tep`, `loi`) chỉ giúp ô tìm trên trang docs. Muốn Peto gắn bài vào câu trả lời thì dùng cụm từ hai chữ trở lên mà người dùng hay gõ khi hỏi đúng tính năng đó (`giong noi`, `doi nhan vat`, `tao anh`), lệnh CLI (`/mcp`), hoặc tên riêng trong `docs_api.DISTINCT_WORDS`. Tránh cụm chung chung như `nhan vat`, `boi canh`, `du lieu`: chúng làm bài bị gắn cả vào bài tập văn, sử hay câu hỏi lập trình. Khi đổi từ khóa, thêm câu ví dụ vào `backend/tests/test_docs_api.py`.
- Ảnh thương hiệu nằm trong `frontend/public/docs-assets/` (WebP giữ nền trong suốt; `pattern.svg` là mặt nạ họa tiết
  của trang đầu). Giao diện nằm trong `frontend/src/features/docs/`: khung chung, header và tìm kiếm trong `Docs.tsx`, trang đầu trong
  `DocsHome.tsx`, trang bài trong `DocsReader.tsx`, phần dùng chung trong `docsShared.tsx`, kiểu trong `docs.css`.

## Phát hành

Build frontend và triển khai cả frontend lẫn backend cùng phiên bản như website hiện có. Giữ thư mục `backend/docs_content` và danh mục Agent trong bản phát hành. FastAPI phục vụ `/docs/` và đường dẫn từng bài; reverse proxy cần chuyển các đường dẫn này về backend. Không cần thêm dịch vụ docs riêng.

## Kiểm tra

Chạy các test `test_docs_api.py`, `test_static_files.py`, `test_agent_guide.py` phía backend và `Docs.test.tsx` phía frontend. Kiểm tra một bài bằng đường dẫn trực tiếp, tìm kiếm không dấu, menu điện thoại và liên kết Markdown sau khi triển khai.
