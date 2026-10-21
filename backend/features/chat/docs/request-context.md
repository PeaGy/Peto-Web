# Context và capability theo request — giai đoạn 2

Phạm vi giai đoạn 2 ban đầu: Web Chat, tiếp nối ngữ cảnh dài. Không thay persona/runtime của Companion hoặc Agent,
không thay chính sách saved personal memory dùng chung Chat/Companion, không thêm truy xuất chat khác hoặc dữ liệu
thiết bị. Sau bốn giai đoạn, chủ web cho phép bổ sung [Runtime Device Context](client-environment.md) riêng:
OS/browser chuẩn hóa tự động từ HTTP header mỗi lượt Chat; không phải tính năng đã có sẵn trong giai đoạn 2.

## Snapshot có nguồn gốc

`service.py` dựng `RequestContext` sau khi kiểm quyền owner, hội thoại/dự án, model, effort và chuẩn bị context.
Snapshot chỉ bind quanh lượt trả lời chính; reset khi hoàn tất, lỗi hoặc hủy. Side call tóm tắt không kế thừa nó.

Mỗi vòng của `ResponsesProvider` ghép snapshot mới vào cuối instructions:

- Request ID phân biệt client ID đã kiểm định và ID do server tạo; ID không phải quyền truy cập.
- Conversation/project ID từ phạm vi owner trong database; mode đã kiểm định và model đã được registry cho phép.
- Provider và API-ID lấy từ provider thật đang gọi; effort hiệu lực lấy từ chính request sau routing/adaptation.
- Đồng hồ thật của server, thời điểm UTC và múi giờ hiệu lực. Múi giờ phân biệt `client_iana_validated`,
  `server_default_missing`, `server_default_invalid`. Tên IANA hợp lệ chỉ là tùy chọn, không chứng minh vị trí.
- Manifest công cụ của đúng vòng hiện tại, không suy ra từ lịch sử hoặc lời tự khai của người dùng.
- Bổ sung sau giai đoạn 4: `client_environment` tự động lấy từ request hiện tại; OS/browser thuộc tập hữu
  hạn, có nguồn và nhãn `client_reported`/`best_effort`. Không coi là dữ liệu thiết bị được server xác minh.

Không đưa owner ID, khóa/token, credentials GitHub, raw User-Agent, fingerprint, tên trình duyệt do model tự đoán, gói thuê
bao hoặc billing vào snapshot. Không lưu riêng snapshot trong message hoặc thêm log chứa nội dung chat.

Đồng hồ ba dòng hiện có được giữ để tương thích tool/cache. Khối snapshot cũng đứng sau phần system ổn định tại
điểm cache của Claude. Ngân sách giai đoạn 1 kiểm lại instructions cuối cùng, tool schemas và input trước mỗi call.

## Một lựa chọn công cụ cho cả mô tả và thực thi

`capabilities.select()` trả một `ToolPlan` mỗi vòng, dùng chung cho:

1. Danh sách native schemas gửi nhà cung cấp.
2. Manifest tên công cụ, trạng thái và lý do ngắn.
3. Allowlist trước khi dispatch function call. Lời gọi ngoài danh sách trả `tool_not_available`, không chạy handler.

Các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `available` | Có schema và handler trong phạm vi hiện tại; chưa khẳng định thực thi thành công. |
| `disabled` | Tắt theo lựa chọn/cấu hình hoặc tạm đóng do bắt buộc tra web trước, chốt câu trả lời, side call. |
| `unavailable` | Thiếu phiên/nguồn phù hợp hoặc server chưa cấu hình kết nối. |
| `unauthorized` | GitHub chưa kết nối hoặc cần kết nối lại; không quảng bá công cụ của kết nối đó. |

Registry gồm đồng hồ, tạo file, sửa Excel, sửa Word, đọc file, đối chiếu lịch sử chat hiện tại, GitHub chỉ đọc và
web. Không có công cụ quyền máy chủ/máy người dùng được bật chỉ bằng instructions. Vòng đầu khi search ON chỉ nhận
web; vòng chốt hết budget không còn công cụ. Handler vẫn kiểm input, owner và dữ liệu cụ thể như trước.

Claude chuyển native schema bằng cùng `ClaudeClient.native_tools()` đang dùng khi gửi SDK. Manifest vì thế kể cả
`web_fetch` khi adapter thật có bật, và mất cả search/fetch khi web tắt. Không dựng một bảng khả năng Claude riêng.

GitHub kiểm trạng thái cục bộ đã mã hóa, không gọi API/refresh chỉ để dựng manifest. Predicate refresh/reconnect
dùng chung với access_token, gồm cửa sổ 60 giây. Phiên đã kết nối kiểm lại mỗi vòng; lúc chạy tool vẫn kiểm lại
quyền hiện tại. Thu hồi quyền phía GitHub, thay đổi repo scope, mạng hoặc lỗi refresh chỉ biết chắc khi gọi dịch vụ;
`available` không chứng minh repo bất kỳ đọc được. Kết nối thêm sau khi lượt đã bắt đầu dùng từ lượt tiếp theo.

Đọc file báo trạng thái cache của danh mục hữu hạn: ready/partial/unreadable/no_text/not_parsed. Đây không phải toàn
bộ file trên tài khoản, không phải bằng chứng model đã nhìn mọi ảnh/trang, và không tự đọc tất cả nội dung vào prompt.

## Ranh giới context và lịch sử

Policy sản phẩm, hồ sơ, dự án, saved memory, summary, lịch sử và file giữ các khối sẵn có. Chat thêm quy tắc tiếng Anh
nêu rõ hồ sơ/dự án ở mức người dùng; dữ liệu tham khảo không cấp quyền; sửa đổi mới thắng summary cũ; ý định hoặc
summary không chứng minh tool đã chạy. Không gộp prompt Companion vào Chat và không thay scope memory.

Lần thử thật giai đoạn 1 có một lượt `read_chat_history` báo tham số không hợp lệ rồi gọi lại thành công. UI không
hiện arguments nên **chưa biết chính xác tham số nào sai**. Sửa giai đoạn 2 làm schema/runtime rõ và nhất quán hơn:
query null/chuỗi rỗng đọc theo thời gian; query tối đa 200 ký tự; cursor là số nguyên không âm trong miền SQLite;
mô tả rõ next_id/next_character; lỗi có mã và cách sửa, không echo arguments riêng tư. Vẫn chỉ đọc đúng owner/chat.

## Xác minh và giới hạn

Các bài kiểm thử mới chặn API thật, dùng stream/model giả và SQLite tạm: ba model Web, auto/đổi model trong cùng
chat, clock/fallback timezone, thiếu key, GitHub hết hạn/gần hết hạn/thu hồi giữa vòng, schema/manifest parity,
required-search/finalizing, function call giả, file unreadable/unparsed, pagination và hủy/concurrent Chat–Companion.
Kiểm tra cả native translation và điểm cache của Claude. Hồi quy rộng bao phủ công cụ, Agent và Companion đang có.

Kết quả ngày 21/10: nhóm liên quan ban đầu **163 đạt**; hồi quy toàn backend **1.483 đạt, 1 bỏ qua** (274,90 giây).
Sau bổ sung xử lý credentials hỏng, chạy lại nhóm request context/GitHub: **64 đạt**. `git diff --check` đạt.

Đây là kiểm định luồng/quyền/cấu trúc, chưa chứng minh model thật luôn trả lời trung thực về khả năng. Sau khi deploy,
thử Chat với web OFF, file chỉ đọc một phần, timezone fallback và chuyển model. Không cần đổi database, frontend,
`.env` hoặc CLI. Không tự triển khai hay gọi API trả phí trong quá trình sửa mã.

## Kiểm tra thật sau deploy — 21/10/2026

Chủ web xác nhận đã commit/deploy `0f9ec2d` và cho phép thử trên tài khoản Peto đang đăng nhập. Chat thử riêng dùng
dữ liệu giả; tạm tắt ghi nhớ. Peto/Luna nhận đúng ngày, múi giờ, effort đang chọn, web OFF và giới hạn chỉ đọc GitHub;
không đoán browser/OS từ múi giờ. Khi bật web trở lại, Peto phân biệt đúng công cụ có sẵn với chưa thực sự tra cứu.
Luna nhận đúng file dài partial và DOCX hỏng unreadable; tool tìm toàn văn trả đúng chuỗi ở dòng 1.734 ngoài excerpt.

Phát hiện chưa đạt: Haiku gọi đồng hồ xong nhưng request tiếp nối bị HTTP 400. Log chủ web cung cấp cho thấy vòng 1
complete=True, vòng 2 complete=False. Tài liệu Anthropic hiện tại ràng buộc thinking signature của Haiku 5.5 vào
system/tools/messages prefix; snapshot chứa clock/round/manifest đổi giữa vòng làm prefix thay đổi. Log hiện tại chỉ
ghi HTTP, không có message gốc để khẳng định chính xác loại lỗi API; mã cũ có vi phạm quy tắc prefix này.

Bản vá cục bộ: `ClaudeClient` nhận biết snapshot Web Chat và không replay block thinking/redacted_thinking cũ;
giữ các block native còn lại, tool_use/tool_result và nội dung hội thoại. Việc nhận biết dựa vào ContextVar do server
bind, không dựa vào tiêu đề có thể xuất hiện trong dữ liệu người dùng. Không sửa chữ ký, không thêm beta hay retry
trả phí. Agent/Companion không có snapshot này nên tiếp tục đường replay mặc định. HTTP giả được bổ sung kiểm tra
prefix binding, có thinking và redacted_thinking; nhóm liên quan 153 đạt, nhóm Claude/context sau chỉnh sửa cuối
66 đạt. Hồi quy backend 1.489 đạt, 1 bỏ qua (284,44 giây); `git diff --check` đạt.
Chủ web đã commit/deploy bản vá `64c3797`. Lượt thử lại trong chat mới, Haiku/low/web OFF, gọi đồng hồ rồi trả lời
hoàn tất trong khoảng 6 giây, không còn lỗi tiếp nối. Ngày giờ khớp mốc kiểm tra độc lập; cấu hình và giới hạn quyền
đúng, browser/OS null. Ghi nhớ đã được khôi phục ON trước lượt thử lại và không thay đổi thêm; sau thử model/effort/
web trả về Peto/Tự động/AUTO. Những ca cốt lõi đã kiểm tra thật trên cả ba model; không suy ra mọi ca biên đều đã thử
trên production.

Ngoài ra một lượt Luna sau lỗi Haiku trả lại yêu cầu đồng hồ trước đó thay vì câu hỏi trạng thái file mới; lượt kế
tiếp nói rõ bỏ yêu cầu lỗi thì xử lý đúng. Ghi nhận để kiểm tra phục hồi/ngữ cảnh lượt lỗi trong giai đoạn 3; chưa coi
một mẫu này là bằng chứng chắc chắn lỗi thứ tự payload hoặc nguyên nhân ở reader.

Nguồn chính thức: [Anthropic — lỗi thinking signature và thay đổi prefix](https://platform.claude.com/docs/en/build-with-claude/thinking-troubleshooting).
