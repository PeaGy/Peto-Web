# Runtime Device Context — Web Chat (2026-10-21)

Bổ sung được chủ web cho phép sau bốn giai đoạn Chat; OS/browser chưa nằm trong phần đã triển khai của giai đoạn 2.
Thiết kế cuối **tự động cấp OS và tên trình duyệt theo từng request**, không có công tắc Cài đặt, quyền lưu trong
localStorage hoặc cờ JSON. Thiết kế opt-in trước đó chưa commit và đã được gỡ theo yêu cầu chủ web.

## Luồng dữ liệu

1. Frontend gửi Chat như trước. Trình duyệt tự gửi các HTTP header thông thường; không cần đọc
   `navigator.userAgent`, gọi API Client Hints, thêm JSON device data hoặc cập nhật frontend đang deploy.
2. `service.chat` gọi `client_environment.normalize` khi dựng snapshot Web Chat. Normalizer nhận header của đúng
   request hiện tại, không đọc OS máy chủ hoặc dữ liệu thiết bị từ lịch sử. Companion không chạy bước này.
3. Ưu tiên brand/platform Client Hints hợp lệ, dùng User-Agent làm fallback. Không thêm `Accept-CH` hoặc xin hints
   độ entropy cao. Chỉ giữ các giá trị từ tập hữu hạn; bỏ chuỗi gốc, phiên bản, kiến trúc và model máy.
4. Snapshot `RequestContext` bất biến bind quanh câu trả lời chính. Mỗi vòng provider nhận `client_environment`
   có nguồn gốc và độ tin cậy; Peto/Luna dùng instructions, Haiku chuyển qua native system bằng adapter hiện có.
   Runtime block đứng sau điểm cache system ổn định của Claude và vẫn chịu kiểm ngân sách cuối.
5. ContextVar reset khi hoàn tất/lỗi/hủy. Đổi header trong cùng chat nhận giá trị mới; thiếu header thì unknown,
   không dùng lại thiết bị của lượt trước. Các request đồng thời cách ly dữ liệu.

Không thay provider params, compaction, persona/runtime Companion, Agent, DB schema, memory policy hoặc `.env`.

## Hợp đồng dữ liệu hữu hạn

Ví dụ một phần snapshot Web Chat:

```json
{
  "client_environment": {
    "os_family": {"value": "windows", "source": "client_hint_normalized"},
    "browser_family": {"value": "edge", "source": "client_hint_normalized"},
    "reliability": "best_effort",
    "trust": "client_reported"
  }
}
```

- OS: `windows`, `macos`, `ios`, `android`, `linux`, `chromeos`, `unknown`.
- Browser: `edge`, `chrome`, `firefox`, `safari`, `opera`, `chromium`, `unknown`.
- Nguồn: `client_hint_normalized`, `user_agent_normalized`, `unavailable`, `conflicting_client_headers`.

Chặn header quá dài (UA 1.024, platform 64, brands 512 ký tự), ký tự điều khiển và cấu trúc hints sai. Brand khớp
chính xác, bỏ GREASE. Các nguồn biết rõ nhưng mâu thuẫn hoặc nhiều brand cụ thể khác nhau → unknown; token Chrome
tương thích không phủ định Edge/Opera. JSON tùy ý do client gửi không trở thành metadata runtime.

UA thu gọn/giả mạo, trình duyệt chưa hỗ trợ, webview và iPad chế độ desktop có thể cho kết quả chung hoặc sai.
Đây là dữ liệu client tự báo đã chuẩn hóa, không phải phần cứng được server xác minh; không đủ để biết Windows
10/11, model điện thoại, laptop/desktop vật lý hoặc vị trí.

Prompt yêu cầu chỉ dùng khi liên quan hoặc khi người dùng hỏi, không tự nhắc lại snapshot trong câu trả lời thường.
Nếu thiếu/unknown, không suy OS/browser hiện tại từ lịch sử, timezone, viewport hoặc OS máy chủ. Không coi đây là
dữ kiện cá nhân lâu dài, gói thuê bao hay billing. Nhận diện này không dùng cho layout hoặc quyết định quyền truy cập.

## Lưu trữ và giới hạn

Không ghi raw User-Agent/hints hoặc cấu trúc `client_environment` vào message, rolling summary, usage event hay log
ứng dụng. Không có bộ nhớ thiết bị trên server. Summary chạy trước khi bind snapshot nên không nhận trực tiếp
metadata của request hiện tại.

Nếu người dùng hỏi và model trả lời “trình duyệt báo Windows/Edge”, **câu trả lời văn bản ấy vẫn là nội dung chat
bình thường được lưu theo chính sách hiện tại**, có thể xuất hiện trong lịch sử hoặc tóm tắt về sau. Không đổi
chính sách saved memory dùng chung Chat/Companion và không tạo Temporary Chat; hướng dẫn prompt không bảo đảm
tuyệt đối extractor/model không suy ra điều gì từ nội dung hội thoại.

## Kiểm chứng và triển khai

- `tests/test_client_environment.py`: dữ liệu desktop/mobile giả; CH/GREASE/UA fallback và header sai/giả/mâu thuẫn;
  Chat thông thường không có cờ vẫn đưa OS/browser đến payload native cuối của cả Peto/Luna/Haiku; đổi header rồi
  thiếu header trong cùng chat; cache Claude; đồng thời cách ly; không lưu metadata/log INFO; Companion không thu thập.
- `frontend/browser-tests/device-context.spec.ts`: App thật với API giả và chặn kết nối ngoài localhost;
  Chat gửi header thông thường, không có JSON metadata/cờ, không có công tắc thiết bị trong Tài khoản, không tràn ngang.
- Các test App/API, RequestContext/Claude và build frontend kiểm hồi quy. Kiểm thử giả không chứng minh chất lượng
  câu trả lời của model thật hoặc nhận diện đúng phần cứng vật lý.

Kết quả thiết kế cuối tự động: nhóm backend **101 đạt** (17,03 giây), nhóm App/API **143 đạt** (50,77 giây),
browser desktop/mobile giả lập **2 đạt** (8,5 giây); build production và diff check đạt. Số kiểm thử của thiết kế
opt-in trước đó không phải kết quả của lần sửa này. Mã frontend sản phẩm, App test và ChatRequest schema đã về
đúng HEAD; chỉ còn browser test bổ sung để chứng minh request không cần cờ và Tài khoản không còn công tắc.

Không gọi LLM trả phí, không tự commit/deploy. Sau commit, cập nhật và restart backend; không cần đổi `.env`,
migrate DB hoặc build lại frontend so với HEAD vì toàn bộ mã frontend sản phẩm đã về đúng bản committed. Nếu đã
build thử bản opt-in chưa commit trên máy thì build lại để thay dist đó. Chưa nghiệm thu bản mới trên VPS hoặc
điện thoại thật; không suy commit backend sản xuất từ hash frontend hoặc `/api/health`.

Tham chiếu giới hạn nhận diện: [MDN về UA](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/User-Agent),
[MDN về browser detection](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Browser_detection_using_the_user_agent),
[Client Hints](https://developer.mozilla.org/en-US/docs/Web/API/NavigatorUAData).
