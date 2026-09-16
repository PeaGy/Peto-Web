# Tạo, sửa bản nháp và tải tài liệu

## Cách dùng

1. Trong **Trò chuyện**, bấm **+ → Viết tài liệu** rồi mô tả tài liệu cần soạn.
   Peto trả lời trong chat và mở bản nháp khi viết xong.
2. Hoặc bấm **Tạo tài liệu** dưới một câu trả lời đã có để dùng nội dung đó.
3. Xem bản nháp, bấm **Chỉnh nội dung** để sửa tên hoặc nội dung.
   Ô sửa dùng Markdown: giữ các dấu tiêu đề, danh sách và bảng khi cần giữ
   định dạng. Có thể chuyển lại **Xem trước** bất cứ lúc nào.
4. Bấm **Lưu**, **Tải DOCX** hoặc **Tải PDF**. Nếu có thay đổi, Peto lưu một
   phiên bản mới trước khi xuất; tải lại bản đã lưu không tạo thêm phiên bản.
5. Tài liệu đã lưu xuất hiện trên ô nhắn của hội thoại. Mở lại để sửa hoặc
   chọn một phiên bản cũ rồi tải xuống. Sửa từ bản cũ sẽ tạo phiên bản mới.

Tên tài liệu và nội dung được lưu trên máy chủ theo tài khoản. Tài khoản
khách vẫn phụ thuộc vào cookie của trình duyệt. Bản nháp chưa bấm lưu chỉ
nằm trong trang đang mở; đóng khi chưa lưu sẽ có lời nhắc. Xóa hội thoại
cũng xóa tài liệu và các phiên bản thuộc hội thoại đó.

## Phạm vi bản đầu

- Xuất tiêu đề, đoạn văn, chữ đậm/nghiêng/gạch ngang, danh sách, trích dẫn,
  đoạn code và bảng đơn giản; giữ địa chỉ nguồn tham khảo trong tệp.
- PDF có font Noto Sans đi kèm, hỗ trợ tiếng Việt và tiếng Anh. Ký tự chưa
  có trong font (ví dụ một số emoji, chữ Hán) được báo rõ để sửa hoặc tải
  DOCX; không âm thầm xuất thành ô vuông.
- Khung xem trước hiển thị **nội dung**, chưa mô phỏng chính xác trang in.
  DOCX và PDF được dựng riêng; cách ngắt trang có thể khác nhau.
- Mỗi bản tối đa 60.000 ký tự, bảng tối đa 100 dòng gồm tiêu đề và 8 cột;
  mỗi tài liệu tối đa 20 phiên bản, mỗi tài khoản tối đa 100 tài liệu.
- Chưa xuất hình ảnh, sơ đồ hay công thức LaTeX. Chưa chỉnh trực tiếp PDF,
  chưa OCR, chưa giữ nguyên bố cục/chú thích của DOCX tải lên. Tệp đính kèm
  vẫn được đọc bằng chức năng đọc tài liệu hiện có; có thể nhờ Peto viết
  lại nội dung thành một bản nháp mới.
- Có thể nhờ Peto sửa lại bằng tin nhắn rồi tạo tài liệu từ câu trả lời mới;
  bản đầu chưa có thao tác yêu cầu AI sửa trực tiếp phiên bản đang mở.

## Cập nhật lên VPS

Không cần thêm biến môi trường, Word, LibreOffice, GPU hay dịch vụ chuyển
đổi trả phí. Sau khi code đã được đưa lên Git, SSH vào VPS, đến thư mục
Peto-Web rồi chạy:

```bash
git pull
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
sudo systemctl restart peto-web
sudo systemctl status peto-web --no-pager
```

Backend tự thêm hai bảng SQLite khi khởi động; giữ nguyên các hội thoại cũ.
Các bản nháp nằm trong database riêng của web, không liên quan bộ tạo giọng.
Tệp DOCX/PDF được dựng khi tải, không lưu thêm bản xuất trên ổ đĩa VPS.
Mỗi tiến trình chỉ xuất một tệp cùng lúc để hạn chế tải CPU.

## Kiểm chứng

`backend/tests/test_document_export.py` kiểm tra quyền sở hữu, truy cập ẩn
danh, phiên bản cũ, xung đột khi lưu đồng thời, xóa theo hội thoại, giới hạn,
nội dung tiếng Việt, nguồn tham khảo, bảng nhiều trang và tạo bản nháp qua chat.
`frontend/tests/DocumentWorkspace.test.tsx` kiểm tra sửa/lưu trước khi tải,
giữ bản nháp khi lỗi, nhắc thay đổi chưa lưu và tải đúng phiên bản đang xem.

Tệp PDF mẫu đã được render và kiểm tra bố cục. DOCX đã được mở lại bằng
thư viện để kiểm tra nội dung/cấu trúc; môi trường kiểm thử Windows chưa có
LibreOffice đi kèm nên chưa xác nhận hình thức từng trang DOCX bằng bộ render.
