# Ngữ cảnh dài của Web Chat — giai đoạn 1

## Hành vi

Peto, Luna và Haiku giữ một cửa sổ tin gần đây nguyên văn (`PETO_MAX_HISTORY`, mặc định 20 tin, không phải 20 lượt).
Khi có đủ phần cũ rời cửa sổ, backend tạo/cập nhật summary riêng của cuộc Chat. Lô nhỏ được giữ thêm nguyên văn nếu
còn ngân sách. Những tin không vừa cửa sổ hoặc chưa được tóm tắt không bị xóa: model nhận số tin chưa được đại diện
và công cụ đối chiếu lịch sử gốc của chính cuộc Chat đó. Thay model vẫn dùng cùng summary portable.
Mốc yêu cầu đầu chỉ trích tối đa 2.000 ký tự, có ID và cờ cắt ngắn; phần còn lại vẫn phải đối chiếu nguồn hoặc tóm tắt.

Summary lưu ràng buộc, dữ kiện, quyết định và việc còn dang dở với message ID nguồn. Yêu cầu mới và sửa đổi mới nhất
được ưu tiên hơn summary/mốc đầu. Lượt Stop và câu trả lời dở là dữ liệu lịch sử, không tự thành việc đang chờ.
Summary không được coi là quyền thực thi hay bằng chứng đã tạo/sửa thành công một tệp.

Trí nhớ cá nhân vẫn dùng chung Chat/Companion theo lựa chọn sản phẩm hiện tại. Tắt Trí nhớ không tắt context của một
cuộc Chat; hai kho có mục đích khác nhau. Thay đổi này không bật tìm kiếm các chat khác, không thêm project memory,
không thay persona/summary Companion hay runtime/quyền Agent.

## Lưu và phục hồi

- Bảng `chat_contexts`: owner, conversation/project, version, cursor theo message/ký tự, summary JSON, model nguồn
  (service/API-ID), thời điểm, dấu kiểm dữ liệu và dấu của summary trước. Không sao chép hay thay lịch sử gốc.
- Một lô tối đa 32 tin và 16.000 ký tự nguồn. Tin dài được chia đoạn có start/end/total; cursor chỉ tiến qua phần
  thực sự được đọc. Mỗi lượt chat chỉ xử lý tối đa một lô để giới hạn độ trễ và chi phí.
- Ghi summary trong transaction sau khi so lại nguồn và dấu của bản trước. Nguồn thay đổi trong khi model làm việc
  thì bỏ đề xuất mới. Summary lỗi/timeout/JSON sai không dời cursor, không ghi đè bản tốt. Stop truyền hủy xuống stream.
- Sửa/xóa tin thuộc prefix đã tóm tắt hoặc chuyển project sẽ vô hiệu summary. Nhánh mới tự dựng context từ lịch sử
  nhánh, không nhận summary của nhánh gốc. Xóa Chat xóa context. Không phải tải lại toàn bộ source cho mỗi request.
- Cache version 1 hỏng có thể dựng lại; gặp version tương lai thì báo cần cập nhật backend, không tự ghi đè.

Đây là kho summary của Chat. Phục hồi process crash giữa lưu reply và chốt turn, checkpoint công cụ và chính sách
retention là việc của giai đoạn 3; giai đoạn 1 không hứa exactly-once cho thao tác bên ngoài.

## Tra tin và tệp gốc

`read_chat_history` là native tool chỉ đọc đúng owner/cuộc Chat và không đọc các tin đến sau snapshot của lượt đang
chạy. Mỗi kết quả tối đa bốn tin, 4.000 ký tự/tin và 12.000 ký tự nội dung tổng, có phân trang message/ký tự. Có thể
tìm theo từ/cụm nguyên văn; phần trích bắt đầu gần chỗ khớp, không chỉ lấy đầu một tin dài. Trả nguồn web, trạng thái
Stop/incomplete và tên tệp đi cùng; nội dung lịch sử luôn là dữ liệu tham khảo.

Danh mục công cụ chứa metadata của tối đa 128 tệp tải lên và 128 phiên bản tài liệu đã xuất hiện trong cuộc Chat.
Prompt chỉ liệt kê 64 mục gần nhất; danh mục có đánh dấu giới hạn, không đồng nghĩa đã đọc nội dung. Tệp tải lên còn
có thể tra chính xác theo tên trong owner/chat ngay khi nằm ngoài danh mục. Trùng tên ưu tiên tệp xuất hiện sau.
Tài liệu tạo bởi Peto được kiểm lại owner/chat/phiên bản; công cụ đọc phần chữ nguồn đã lưu (Excel đọc workbook thật).
Không suy ra rằng đã nhìn lại mọi ảnh, công thức hoặc bố cục của tài liệu chỉ từ phần chữ này. Tài liệu tạo quá cũ
nằm ngoài danh mục hữu hạn có thể cần người dùng gửi lại. Không tự nạp toàn bộ tệp hay BLOB vào system prompt.
Ảnh vẫn theo giới hạn ảnh gần đây đang có; đọc lại tin/tên ảnh cũ không tự gửi lại pixel của ảnh đó cho model.
Nếu chi tiết hình không còn trong context, cần gửi lại ảnh; giai đoạn này không hứa phục hồi mọi ảnh cũ bằng summary.

## Ngân sách và vận hành

| Cấu hình | Mặc định | Ý nghĩa |
|---|---:|---|
| `PETO_MAX_HISTORY` | 20 | Số tin nguyên văn gần đây; có thể thu nhỏ khi cần để vừa ngân sách |
| `PETO_CHAT_CONTEXT_TOKENS` | 64000 | Giới hạn input ước lượng của ứng dụng; phạm vi 8192–400000 |
| `PETO_CHAT_SUMMARY_ENABLED` | 1 | Tắt bằng 0 để ngừng tạo/cập nhật summary; vẫn tra lịch sử gốc được |
| `PETO_CHAT_SUMMARY_TIMEOUT_SECONDS` | 20 | Timeout một lô, phạm vi 1–60 giây |
| `PETO_CHAT_CONTEXT_LIMITS` | `{}` | Override context/input/output theo API-ID thực |

Ví dụ cấu hình override trong `.env`:

```dotenv
PETO_CHAT_CONTEXT_LIMITS={"grok-4.7":{"context":500000,"input":64000,"output":8192}}
```

Giới hạn output còn bị chặn bởi cấu hình provider. API-ID lạ có fallback context 32.768/output tối đa 4.096, thay vì
đoán nó có khả năng như model quen thuộc. Danh mục Web dùng cùng snapshot ID đã đối chiếu trong tài liệu ngân sách
CLI, nhưng không import runtime hay quyền Agent.

Mỗi request thật, kể cả các vòng đọc/tạo/sửa công cụ tiếp theo, đều được ước lượng lại trước khi gửi. Không vừa
ngân sách thì báo rõ, giữ phần đã trả lời/lịch sử và yêu cầu chia nhỏ; không cắt đôi function call/result để cố gửi.
Estimator có biên dự phòng, ước lượng riêng cho ảnh thay vì đếm base64, giữ chỗ output, schema và tool results.
Nó không phải tokenizer/usage chính thức; token ảnh và reasoning mã hóa có thể khác ước lượng. Một request vẫn có
thể bị provider từ chối theo giới hạn thực của deployment; sửa override theo thông tin deployment khi cần.

Summary dùng đúng model đang chọn, low effort, tắt web và công cụ, tối đa 3.072 output token, không thêm lớp retry.
Nó **có tính phí/quota khi dùng provider thật**, tối đa một call/lượt Chat khi cần cập nhật. Thông thường chờ ít nhất
tám tin cũ chưa đại diện; tin rất dài/đoạn chưa đọc hết có thể kích hoạt sớm hơn. Có thể thêm tối đa timeout summary
vào độ trễ chuẩn bị; nhật ký sẵn có hiển thị bước chuẩn bị ngữ cảnh. Log kỹ thuật chỉ ghi model, ước lượng, giới hạn,
summary/gap và loại lỗi, không ghi nguyên văn chat. Provider usage của lượt summary dùng nhãn side call hiện có.

## Giới hạn chất lượng và nghiệm thu

Kiểm định JSON/source ID không chứng minh summary hiểu đúng hoặc nhớ đủ mọi ý. Summary ngắn có thể bỏ sót chi tiết;
model cần đối chiếu nguồn khi quyết định quan trọng. Chat cũ rất dài có thể tồn backlog qua nhiều lượt; server ghi rõ
gap, không khẳng định đã đọc toàn bộ. Cửa sổ recent, mốc đầu và lịch sử gốc là lớp hỗ trợ, không phải bộ nhớ vô hạn.

Kiểm thử tự động dùng dữ liệu giả, model giả/HTTP giả và SQLite tạm; không gọi API trả phí. Sau triển khai, kiểm tra
một Chat trên 20 tin: đặt ràng buộc ở đầu, sửa ở cuối, nhắc lại tệp cũ, đổi model, tắt Trí nhớ và bấm Stop trong bước
chuẩn bị. Theo dõi các dòng `chat_context` và usage side call. Chỉ sau khi kiểm tra thực tế đạt mới chuyển sang giai
đoạn 2 trong lộ trình; chất lượng model thật chưa được xác minh bằng các test giả.
