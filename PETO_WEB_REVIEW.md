# Rà soát Peto Web — 09/09/2026

> Cập nhật sau khi người dùng duyệt sửa: các lỗi 1–5 bên dưới đã được xử lý.
> Đã bổ sung kiểm tra quyền mỗi yêu cầu, lưu phản hồi chưa hoàn tất, giữ bản nháp
> trước xác nhận, chặn kết quả tải hội thoại cũ, sửa trạng thái Dừng, hỏi lại trí
> nhớ mỗi lượt, tải thêm lịch sử, xác nhận xóa, bảng Markdown, ghi chú PDF và
> bố cục chat gọn hơn. 118 test backend + 11 test frontend đạt; build đạt.
> Nội dung bên dưới giữ lại làm bản ghi phát hiện **trước khi sửa**.

Đã đọc code và chạy giao diện hiện tại với backend, tài khoản, hội thoại và nhà cung cấp AI giả. Không đọc `.env`, token hay dữ liệu hội thoại thật; không sửa mã ứng dụng, không gọi AI thật hoặc thao tác VPS.

## Kết luận

Nền React/TypeScript + FastAPI hiện tại phù hợp để phát triển tiếp. Tông tím tối nhất quán, bố cục cơ bản gọn. Ưu tiên sửa tính đúng đắn của hội thoại, quyền truy cập và khả năng phục hồi lỗi trước khi mở rộng giọng nói/3D.

## Lỗi cần sửa sớm

### 1. P1 — Thu hồi tài khoản chưa vô hiệu hóa phiên đang đăng nhập

Vị trí: `backend/auth.py:87–92`, `backend/auth.py:207`.

Danh sách tài khoản được phép chỉ được kiểm tra ở callback đăng nhập. Các API sau đó chỉ kiểm tra chữ ký và tuổi cookie. Nếu quản trị viên bỏ một Discord ID khỏi danh sách rồi khởi động lại với cùng khóa ký, phiên cũ vẫn dùng được đến khi hết hạn; mặc định là 30 ngày.

Đã xác minh bằng tài khoản giả: với danh sách cho phép rỗng, cookie đã ký vẫn đọc được `/api/conversations` và nhận HTTP 200. Đây là quyền truy cập của tài khoản bị thu hồi, không phải bằng chứng đọc chéo tài khoản.

Đề xuất: kiểm tra trạng thái được phép trong dependency xác thực dùng chung và `/api/auth/me`; có bài kiểm thử cho phiên cũ sau khi thu hồi quyền.

### 2. P1 — Chuyển nhanh hội thoại làm nội dung và hội thoại được chọn lệch nhau

Vị trí: `frontend/src/App.tsx:276–285`.

`conversationId` đổi ngay khi bấm, còn kết quả tải tin nhắn được áp dụng bất kể người dùng đã chuyển đi. Đã mô phỏng A tải chậm 4 giây, bấm A rồi B: thanh bên chọn **B — Bài tập Python**, nhưng khung chat hiện nội dung cuối tuần của A. Nếu gửi tiếp, yêu cầu dùng ID B dù người dùng đang đọc A.

Đề xuất: hủy/bỏ qua kết quả tải cũ, cập nhật ID và nội dung nhất quán, có trạng thái đang tải. Áp dụng cả khi chuyển sang “Trò chuyện mới” trong lúc yêu cầu cũ chưa xong.

### 3. P2 — Câu trả lời dở dang mất khỏi lịch sử khi AI lỗi

Vị trí: `backend/main.py:365–389`.

Các nhánh lỗi nhà cung cấp, timeout và lỗi bất ngờ kết thúc trước bước lưu phần đã nhận. Đã mô phỏng nhà cung cấp phát một đoạn rồi báo lỗi: một sự kiện nội dung được gửi tới giao diện, nhưng database không có tin nhắn assistant. Mở lại hội thoại sẽ mất đoạn đã thấy, và lượt tiếp theo không có đoạn đó trong ngữ cảnh.

Đề xuất: lưu phần đã nhận cùng trạng thái chưa hoàn tất; giao diện cho phép thử lại và không trình bày nó như câu trả lời hoàn chỉnh.

### 4. P2 — Gửi thất bại làm mất bản nháp và không có đường gửi lại thuận tiện

Vị trí: `frontend/src/App.tsx:315–316`, `frontend/src/App.tsx:372–394`.

Ô soạn và tệp chờ gửi được xóa trước khi máy chủ xác nhận. Đã mô phỏng HTTP 400: tin vẫn xuất hiện như bong bóng đã gửi, ô soạn trống, không có nút thử lại. Chuyển hội thoại hoặc tải lại sẽ mất nội dung chưa được lưu; tệp phải chọn lại.

Đề xuất: giữ bản nháp cho đến khi được nhận, hoặc lưu trạng thái gửi thất bại cùng nội dung/tệp để có thể thử lại mà không tạo bản trùng.

### 5. P2 — Đã dừng nhưng vẫn hiện dấu đang trả lời

Vị trí: `frontend/src/App.tsx:398–401`, `frontend/src/App.tsx:550–557`.

Đã dùng phản hồi chậm rồi bấm Dừng trước khi nhận chữ. Nút Dừng biến mất nhưng ba dấu chấm vẫn chạy, vì bong bóng assistant rỗng luôn được render thành trạng thái typing, không phụ thuộc `streaming`.

Đề xuất: xóa placeholder rỗng hoặc chuyển sang trạng thái đã dừng; chỉ hiển thị typing cho lượt đang thực sự chạy.

## Điểm cần điều chỉnh thêm

- **Trí nhớ và ẩn danh:** `backend/discord_memory.py:69–72` trả dữ liệu cache trước khi hỏi gateway. Khi gateway được bật, nếu người dùng bật ẩn danh hoặc xóa trí nhớ trên Discord sau một lần đọc, web có thể tiếp tục dùng bản cũ tới hết TTL, mặc định 5 phút. Đây là kết luận từ code web; chưa kiểm tra hệ thống Discord đang chạy. Cần cơ chế làm mất hiệu lực cache hoặc xác minh quyền sử dụng trí nhớ trước mỗi lượt.
- **Hội thoại cũ:** `backend/db.py:165` giới hạn danh sách ở 50, API/UI chưa có phân trang hoặc tìm kiếm. Sau khi vượt 50 cuộc, những cuộc cũ không còn đường mở qua danh sách hiện tại dù vẫn nằm trong database.
- **Xóa hội thoại:** nút × thực hiện xóa ngay, không có xác nhận hoặc hoàn tác (`frontend/src/App.tsx:298`). Nên có xác nhận hoặc cơ chế khôi phục, nhất là trên màn hình cảm ứng. Không thử xóa dữ liệu thật.
- **PDF:** giao diện quảng bá “Tệp chữ và PDF”, nhưng `backend/attachments.py:242–244` không trích nội dung PDF; AI chỉ nhận tên tệp. Đây là giới hạn được ghi trong code, cần nói rõ trên giao diện khi chọn PDF để người dùng không hiểu nhầm rằng Peto đọc được tài liệu.
- **Bảng Markdown:** đã đưa câu trả lời mẫu chứa bảng vào hội thoại. Giao diện hiện nguyên các dấu `|`, không có phần tử bảng, ở cả máy tính và điện thoại. `react-markdown` hiện chưa được bổ sung hỗ trợ bảng GFM. Nếu Peto thường giải bài hoặc so sánh nội dung, nên bổ sung hiển thị bảng và cuộn ngang trong bảng.
- **Tự cuộn:** `frontend/src/App.tsx:196–198` cuộn xuống cuối mỗi khi tin nhắn thay đổi, kể cả đang nhận từng đoạn. Nên chỉ tự cuộn khi người dùng đang gần cuối; khi họ đọc tin cũ, hiện nút xuống tin mới.
- **Tài liệu:** README vẫn nói chưa có upload/đồng bộ/triển khai ở một số đoạn, trong khi code đã có upload và kết nối đọc trí nhớ. Cần cập nhật “đã có / chưa có / đã kiểm tra”, không suy ra trạng thái VPS từ code local.

## Nhận xét màu sắc và bố cục

- Giữ nền tối và điểm nhấn tím hiện tại là lựa chọn hợp lý. Chữ chính và các nút quan trọng phân biệt được bằng mắt trong các màn hình đã xem; chưa thực hiện kiểm định accessibility đầy đủ.
- Trên màn hình rộng, tin nhắn người dùng và Peto nằm khá xa nhau. Có thể đặt vùng nội dung và ô soạn vào một cột giữa có chiều rộng tối đa để mắt ít phải di chuyển.
- Chỉnh màu liên kết cho đồng bộ với bảng màu, hoàn thiện bảng và khối mã trước khi thêm hiệu ứng trang trí.
- Màn hình chào hiện ưu tiên thông tin định dạng tệp và mức suy nghĩ. Có thể dùng vài gợi ý trò chuyện bấm được để tạo cảm giác gần gũi hơn; đây là góp ý thiết kế, không phải lỗi.
- Avatar chữ P đủ dùng ở giai đoạn này. Có thể thay bằng hình nhận diện Peto khi chốt phong cách nhân vật.

## Kiểm tra đã thực hiện và giới hạn

- Bộ kiểm thử backend hiện có: **107 passed**, 18,51 giây, dữ liệu giả và database tạm.
- TypeScript kiểm tra thành công; Vite build thành công, 174 modules.
- UI chạy với frontend build mới và backend local dùng AI giả; đã thử trạng thái tải hội thoại, gửi lỗi và dừng phản hồi.
- Xem bố cục ở 1366 × 900 và 390 × 844. Nội dung mẫu trên điện thoại có chiều rộng trang 390 px, không tràn ngang. Chưa thử bàn phím ảo hoặc Safari trên thiết bị thật.
- Các kiểm tra bổ sung xác nhận: phiên bị thu hồi vẫn truy cập được; câu trả lời dở dang không được lưu. Đồng thời ghi nhận yêu cầu bị cooldown từ chối vẫn được lưu thành tin user, cần cân nhắc bổ sung trạng thái gửi để lịch sử rõ ràng.
- Lệnh npm mặc định trên máy trỏ tới file không tồn tại; đã kiểm tra build bằng các công cụ TypeScript/Vite cài sẵn trong dự án. Đây là vấn đề môi trường máy, chưa phải lỗi ứng dụng.
- Chưa đánh giá chất lượng phản hồi của model thật, xác thực Discord/xAI thật, cấu hình production hoặc tải đồng thời trên VPS. Bộ test đạt không có nghĩa những phần này đã được xác minh.

Thứ tự đề xuất: sửa mục 1–2 trước, tiếp theo 3–5 và cơ chế ẩn danh, sau đó hoàn thiện trải nghiệm tệp, lịch sử và trình bày.
