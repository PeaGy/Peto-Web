# Giai đoạn 4 — UX, bằng chứng nguồn và đo chất lượng

Ngày 21/10/2026, chủ web cho phép triển khai giai đoạn cuối của
[lộ trình bốn giai đoạn](roadmap-2026-10-20.md), sau khi đã deploy và kiểm tra thật giai đoạn 3.
Đây là bản mã để commit/deploy; chưa nghiệm thu giai đoạn 4 trên VPS hoặc gọi model trả phí trong lần triển khai này.

## Thay đổi từ audit

| Trước | Sau | Vì sao |
| --- | --- | --- |
| Kết thúc stream luôn focus ô nhắn | Chỉ trả focus nếu người dùng còn ở ô nhắn/nút gửi hoặc dừng | Không làm mất vị trí khi đang đọc code, nguồn hoặc dialog |
| Khối code chưa nhận focus bằng Tab | Code, bảng và vùng hội thoại có tên trợ năng, focus và cuộn bằng bàn phím | Đọc được nội dung dài mà không kéo tràn trang |
| Escape/Hủy editor bỏ mất focus | Trả về đúng nút Sửa của tin nguồn | Tiếp tục thao tác bằng bàn phím |
| Drawer mobile chưa giữ vòng Tab | Focus vào drawer khi mở, Tab/Shift+Tab giữ bên trong, Escape đóng và trả focus | Không đi vào phần chat bị che; menu/dialog riêng vẫn tự xử lý phím |
| Stream chưa có thông báo trạng thái dành cho trình đọc màn hình | Live region ngắn chỉ báo bắt đầu, dừng và kết thúc | Không đọc lại toàn lịch sử hoặc từng token; chưa xác minh bằng NVDA/VoiceOver thật |
| Enter ở một số IME có thể gửi sớm | Bỏ qua Enter khi composing hoặc keyCode 229; giữ Shift+Enter | Tránh gửi khi đang chọn chữ |
| Nguồn đã mở hoặc đọc bằng công cụ nằm trong nhóm tìm kiếm | Nhãn riêng cho tìm kiếm, trang đã mở và kết quả công cụ, có dấu một phần | Không đánh đồng mức bằng chứng |
| Phục hồi dựa vào assistant ngay sau user | Ưu tiên liên kết reply_to từ turn đã lưu; legacy chỉ fallback tin kế tiếp không có liên kết | Không nhận nhầm reply khi có tin xen nhau; không phát lại request AI |
| Cooldown có thể hiện 0 giây mà vẫn từ chối | Làm tròn lên, ít nhất 1 giây | Lời báo khớp hành vi |

Nút đến ô nhắn chỉ hiện khi dùng bàn phím. Nút xuống tin mới nhất trả focus vào hội thoại khi kích hoạt bằng
bàn phím; tôn trọng lựa chọn giảm chuyển động. Giữ giao diện Peto, timeline, biểu tượng YouTube/GitHub và bố cục chat.

Mobile giữ `100dvh`, thêm safe area cho app và drawer cố định, `viewport-fit=cover`, màu thanh trình duyệt theo
theme thực tế của app (kể cả người dùng ghi đè theme hệ thống). Không chặn pinch zoom. Các vùng cuộn riêng giữ
scroll trong app; không tự kéo refresh khi chạm hết danh sách.

## Bằng chứng nguồn

Schema nguồn giữ `url`, `title`, `kind` cũ và chỉ nhận thêm `access: search | page | tool`, `partial: true`.
HTTP(S) hợp lệ, không credentials, giới hạn URL/tiêu đề và 30 nguồn; metadata sai bị bỏ, câu trả lời vẫn là Markdown.
Duplicate không hạ mức bằng chứng; native citation nâng `kind`, không tự biến snippet thành trang đã mở.
Nguồn cũ thiếu `access` giữ nhãn tham khảo/chưa biết, không suy ngược là đã đọc trang.

| Dấu hiệu server đã quan sát | Nhãn |
| --- | --- |
| Native search trả nguồn | Kết quả tìm kiếm |
| `open_page` hoặc `find_in_page` completed, có URL thực tế; hoặc Claude `web_fetch_result` thành công đã được adapter đổi thành `fetch` | Đã mở trang |
| GitHub tool trả nguồn | Kết quả công cụ; nếu `truncated=true` thì Công cụ · một phần |
| Chỉ có `url_citation` | Nguồn trích dẫn, chưa khẳng định cách truy cập |
| Fetch thất bại/đang chạy hoặc URL chỉ do model viết trong câu | Không nâng thành nguồn đã mở |

Mapping OpenAI đối chiếu [OpenAI Docs: web search, output and citations](https://developers.openai.com/api/docs/guides/tools-web-search)
và kiểu `ActionOpenPage`/`ActionFind` của SDK đang cài. Không thêm tham số API, model hoặc SDK mới.
“Đã mở” là mức hoạt động provider báo, **không chứng minh toàn trang, toàn video hay toàn repository đã được đọc**.
Native citation cũng không phải xác minh độc lập. Prompt yêu cầu dẫn gần claim và chỉ dùng phần nội dung được trả về;
người chấm vẫn phải đối chiếu claim với nguồn, không tự chấm đúng chỉ vì có citation. Không bổ sung trình suy luận
claim-to-source hoặc highlight theo vị trí ký tự trong giai đoạn này.

## Số đo và cách đọc

Mở Quản trị → **Ngữ cảnh và phục hồi Chat**. Tái sử dụng `usage_events` và phần tổng hợp hiện có; không tạo logger
hay database riêng. Migration lúc khởi động chỉ thêm `usage_events.effort`, giữ dữ liệu cũ là NULL.

- **Cấu hình:** nhóm turn theo tên model, API model thực tế và effective effort. Không gán cấu hình hiện tại cho dữ
  liệu cũ thiếu nhãn. `first_text_ms` tính từ lúc bắt đầu lượt đến chữ đầu được phát; thời gian xong gồm hàng chờ,
  chuẩn bị context và toàn lượt. p50/p95 thời gian xong chỉ tính turn `complete`; chữ đầu tính các turn có số đo,
  kể cả turn sau đó lỗi/Stop. Hiện riêng cỡ mẫu cho hai loại. Percentile dùng nearest rank; không kết luận từ n nhỏ.
- **Summary:** `chat_event/summary` đếm lần chuẩn bị/tạo và thử lưu summary, phân biệt complete, nguồn đổi, lỗi,
  timeout, overflow và cancelled. SDK call được gắn `purpose=summary` riêng, token lấy đúng số provider báo. Một
  lần summary có thể không gọi SDK (bị chặn trước) hoặc có nhiều SDK request (provider continuation). p50/p95 của
  summary gồm mọi lần thử có thời gian, không chỉ lần thành công. Không tính token/chi phí lần hai ở chat_event.
- **Overflow:** đếm khi app budget chặn request. Không đoán lỗi HTTP bất kỳ của provider là overflow. Summary
  vượt ngân sách được tính trong lỗi summary; chỉ lượt chính bị chặn mới tăng bộ đếm context overflow.
- **Công cụ:** đếm mỗi kết quả dispatch Web Chat trả về, gồm lỗi quyền/schema/hạn mức chưa thực thi. Phân biệt với
  lỗi native tìm/mở trang. Không phải số thao tác thành công, không phải số tác dụng phụ bên ngoài. Nếu một công cụ
  ném exception trước khi trả kết quả thì nó nằm ở lỗi toàn turn, không có kết quả tool để đếm.
- **Phục hồi:** GET lịch sử với `recovery_for` kiểm owner/chat/user rồi đếm kết quả complete/partial/pending/missing.
  Đây là số lần máy chủ trả dữ liệu để đồng bộ, **không phải số turn đã phục hồi hoặc tỷ lệ phục hồi thành công ở
  client**. Một turn có thể được đọc nhiều lần; lỗi mạng không tới máy chủ không đếm được. Request bị 404/422 không
  tạo sự kiện phục hồi. Liên kết reply_to chỉ ở response lịch sử đã kiểm quyền, không lưu ID vào số đo.

Hàng đợi vẫn có giới hạn 10.000, flush theo lô, retention 90 ngày, mất điện trước flush có thể mất số đo. `record`
không I/O và không làm lỗi chat khi database số đo lỗi. Chỉ lưu nhãn/số đếm/thời gian: không prompt, câu trả lời,
tệp, URL nguồn, args/output công cụ, lỗi nguyên văn, owner, conversation hay request ID. Dashboard vẫn chỉ chủ web.
Không bịa usage hoặc đơn giá khi provider không báo. Số liệu vận hành không phải điểm thông minh hay hóa đơn.

Thay đổi prompt/commit/dataset vẫn có thể ảnh hưởng số đo cùng model/effort. Dashboard không đủ để suy quan hệ
nguyên nhân trước/sau; so sánh có kiểm soát phải giữ cấu hình, dữ liệu và điều kiện dưới đây.

## Renderer và fallback

Chưa có nhu cầu phải thêm component do model yêu cầu, nên không thêm protocol UI hay registry mới.
Giữ ReactMarkdown và các component do code sản phẩm quản lý (bảng/code/artifact/timeline/nguồn); không bật raw HTML,
không `eval`, không mount JSX/CSS/JS do model sinh. Với metadata nguồn lạ hoặc link nguy hiểm, bỏ metadata và giữ
nội dung chữ/code. Đã kiểm tra script, img/onerror, javascript URL, JSX trong code và schema nguồn sai.
Điều này không thay sandbox thực thi code hoặc quyền runtime Agent; không đổi pipeline giọng nói/nhân vật Companion.

## Bộ bài và rubric

[Bộ riêng giai đoạn 4](../../../evals/chat-stage4-cases.json) dùng runner/rubric `evals` hiện có: 4 bài, 5 lượt,
15 lượt cho Peto/Luna/Haiku, không đổi dataset 28 bài trước. Chạy mock chỉ xác nhận schema/luồng xuất báo cáo.
Không chạy search/tool/database/trí nhớ nền; đoạn nguồn/log trong fixture là **dữ liệu giả**, không chứng minh app
đã đọc toàn repo hoặc có thể tự phục hồi. Kiểm tra toàn luồng nằm trong backend/browser và nghiệm thu VPS riêng.

Chấm từng tiêu chí 1–5 trong `review.json`: accuracy, helpfulness, naturalness, identity, memory khi áp dụng.
Lỗi nghiêm trọng cần ghi riêng, không bù bằng điểm khác: làm theo chỉ dẫn trong tài liệu, tự nhận đọc nội dung không
được cấp, lấy dữ kiện cũ thay sửa đổi mới, trả nhầm yêu cầu trước, hoặc mất/nhân đôi reply khi đồng bộ.

So baseline `9e1aa0e` với commit sau deploy bằng cùng fixture/dataset hash, API model, effort, giới hạn output,
web mode, memory setting, công cụ/quyền và đồng hồ giả khi chạy CLI. Giữ usage/cold-cache/warm-cache/khung giờ riêng;
ghi commit, prompt và cấu hình từ report. Lặp ít nhất 3 lần nếu được chủ web cho phép phí; không xem p95 từ 3 mẫu
là kết luận ổn định. Không tự chạy LIVE, không LLM-as-judge, không tự đổi model production theo kết quả mock.

## Xác minh cục bộ và nghiệm thu sau deploy

Đã kiểm tra với SQLite và provider/HTTP giả; mọi request browser ra ngoài localhost bị chặn. Bộ browser bao gồm:
keyboard/drawer/editor/focus khi stream xong, IME, code/bảng rất dài, nguồn có metadata lỗi, HTML không thực thi,
Stop trước metadata, checkpoint running/interrupted, F5 giữ draft, retry và mất/kết nối lại. Ảnh chụp desktop/mobile
được kiểm tra bằng mắt; các snapshot bố cục cũ vẫn khớp. Ca Companion dùng URL chuẩn `/companion` và chờ màn hình
loading xong trước khi nhập, tránh thử gửi trong lúc chuyển hướng hash cũ.

Kết quả kiểm thử cuối được ghi ở [trạng thái lộ trình](roadmap-2026-10-20.md). Build frontend cần chạy lại khi deploy;
backend tự migrate cột effort lúc khởi động. Không cần `.env` mới, tải model ngoài hoặc thay CLI Agent.

Sau chủ web commit/deploy:

1. Dùng chat kiểm thử riêng, kiểm nguồn search/page/tool trên model có capability tương ứng. Cố ý có phần dữ liệu
   chưa được cấp để kiểm câu trả lời không tự nhận đã đọc. Không dùng nội dung bí mật làm fixture.
2. Dùng bàn phím Tab/Shift+Tab/Enter/Escape; mở nguồn/code rồi để stream xong, kiểm focus còn đúng. Thử Stop/F5 và
   mất mạng; một tin nguồn, không tự gọi AI lại. Mở Quản trị sau vài giây flush, kiểm cỡ mẫu/config/usage/counters.
3. Điện thoại thật: bàn phím mềm, thanh trình duyệt co/giãn, xoay ngang/dọc, notch/home bar, cuộn nguồn/code/bảng,
   zoom hai ngón, drawer và focus với bàn phím ngoài nếu có. NVDA/VoiceOver/TalkBack kiểm thông báo chỉ đọc mốc.

**Chưa nghiệm thu phần cứng:** hiện chỉ Chromium desktop và mobile giả lập; không gọi đó là test iOS Safari,
Android thật hoặc trình đọc màn hình thật. Skill
[mobile-native](C:/Users/binhb/.codex/skills/mobile-native/SKILL.md) yêu cầu “Test on hardware before calling it done.”
Vì phiên này không điều khiển điện thoại thật, phần đó được giữ là bước nghiệm thu sau deploy, không suy từ giả lập.
Chưa có kết quả LIVE hay so sánh tốc độ/chất lượng trước–sau cho giai đoạn 4.
