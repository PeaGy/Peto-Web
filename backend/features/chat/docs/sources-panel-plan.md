# Hoàn thiện bảng nguồn Trò chuyện

Kế hoạch chốt ngày 25/10/2026; triển khai ngày 26/10/2026 trên HEAD `e96fd91`.
Trạng thái: **đã hoàn thành bốn giai đoạn trong mã và kiểm thử local**. Chưa commit/deploy bản này.
Chi tiết hợp đồng, bằng chứng Grok và kiểm chứng: [source-activity.md](source-activity.md).

## 1. Bằng chứng và phạm vi

Đã mở trực tiếp cuộc chat Grok đang đăng nhập bằng trình duyệt tích hợp, bấm `105 sources`, mở nhóm đầu có
15 kết quả, kiểm tra nút đóng, DOM và bố cục desktop 1440×900 cùng viewport hẹp. Đây là bằng chứng giao diện
qua CUA. Ngày 26/10 đã tải các bundle JavaScript công khai thực sự xuất hiện trong trang và phân tích ba bundle
liên quan bằng REA; phạm vi static analysis là một phần ứng dụng, không chứng minh backend nội bộ của Grok.

Quan sát được: nút favicon nhỏ; bảng nguồn riêng; các nhóm theo truy vấn thật có số kết quả; mở nhóm để xem
tiêu đề, đoạn trích, tên website/favicon. Favicon trong DOM dùng Google S2 theo hostname. Viewport hẹp dùng
dialog phủ dạng sheet. Không gửi prompt mới để nghiên cứu các hành vi này.

Mục tiêu Peto: trải nghiệm gọn tương tự, nhưng chỉ hiển thị những truy vấn, quan hệ và đoạn trích mà provider
thực sự cung cấp. Bao gồm Peto, Luna và Haiku trong Trò chuyện. Companion và Imagine nằm ngoài phạm vi.

## 2. Hiện trạng trước triển khai đã xác minh trong mã

| Đường chạy | Hiện có | Phần thiếu |
| --- | --- | --- |
| `ai/xai.py::_item_sources`, `observe_item` | Nhận item có ID/action; chuyển thành nguồn và trạng thái tìm web | Không phát quan hệ call → query → sources ra giao diện. |
| `ai/gpt.py::GPTProvider` | Dùng chung `ResponsesProvider` với Peto | Cần kiểm thử payload OpenAI riêng, không mặc định giống payload xAI. |
| `ai/claude.py::_portable_output`, stream adapter | Kết quả web có `tool_use_id`; server tool phát trạng thái chung | Chưa ghép input query của server tool với result cùng ID trong giao thức công khai. |
| `shared/web_search.py::normalize_sources` | URL/title/kind/access/partial/citation IDs; dedup, ưu tiên citation; tối đa 30 URL | Không lưu query, snippet, call membership. Không dùng danh sách này làm toàn bộ thư viện tìm kiếm. |
| `features/chat/work_log.py::search` | Gom các lượt tra liên tiếp thành một bước; lưu số lần/tổng nguồn | Không thể khôi phục từng query từ nhãn đã gộp. |
| `features/chat/service.py` | SSE nguồn phẳng; checkpoint cả `sources` và `work` | Cần sự kiện dữ liệu nhóm và bộ tích lũy riêng. |
| `storage/chat_turns.py`, `storage/conversations.py`, `features/chat/history.py` | Lưu/đọc JSON `work`, copy khi tạo phiên bản hội thoại | Có thể tận dụng JSON hiện có để lưu cấu trúc bổ sung, không cần thêm bảng SQLite. |
| Frontend `WorkStep`, `WebSource`, `sourceData.ts` | Nhận nguồn phẳng, kiểm lại URL và cắt 30 | Chưa có dữ liệu call/query hay registry cho danh sách nguồn lớn. |

Fixture `tests/test_web_search.py::search_call` đã có `action.query`, nhưng **fixture không chứng minh provider
live luôn gửi query**. Khả năng hiển thị từng trường phải dựa vào payload có trường đó; thiếu thì dùng fallback.
Không đọc query từ câu trả lời AI, tên bài viết, prompt người dùng hoặc vị trí trong mảng.

## 3. Quyết định thiết kế

### Dữ liệu

- Giữ `messages.sources` và quy tắc citation hiện tại. Không tăng ngưỡng 30 ở mọi nơi vì các caller còn dùng
  nguồn này làm ngữ cảnh cho model.
- Thêm danh mục nguồn phục vụ UI và lịch sử tra cứu ở `work.web`, có `version: 1`. Cấu trúc này không đưa vào
  prompt. `snapshot()` và `close()` phải giữ nó; các hội thoại không có web vẫn dùng shape cũ.
- Danh mục chứa nguồn chuẩn hóa một lần (URL, title, kind/access, explicit citation IDs nếu có, excerpt tùy chọn).
  Mỗi call chứa ID ổn định trong lượt, operation, queries nếu có, trạng thái và tham chiếu tới nguồn trong danh mục.
- ID call phân biệt các vòng provider; sự kiện cập nhật lặp cùng ID là upsert. Hai call có query giống nhau vẫn
  có thể là hai lượt riêng. Một URL thuộc nhiều nhóm không bị buộc vào nhóm đầu tiên.
- Mở trang, tìm trong trang và tra web là các operation khác nhau. Không biến fetch thành search hay kết quả lỗi
  thành trang đã đọc thành công. Nguồn chưa ghép được để ở nhóm tham khảo chung.
- SSE bổ sung sự kiện cập nhật activity; không phát lại toàn bộ danh mục mỗi token. Checkpoint/history trả snapshot.
  Renderer nguồn và tiến trình dùng cùng dữ liệu call, không suy lại từ nhãn hiển thị.
- Backend và frontend đều validate cấu trúc/giới hạn. Phiên bản không hỗ trợ hoặc dữ liệu hỏng quay về nguồn phẳng.

### Số đếm và giới hạn

- Nút cuối câu trả lời đếm URL hợp lệ khác nhau thực sự có thể xem. Mỗi nhóm đếm kết quả hợp lệ khác nhau trong
  chính nhóm đó. Một URL xuất hiện ở nhiều nhóm có thể khiến tổng các nhóm lớn hơn số trên nút.
- Tổng upstream chỉ hiển thị nếu có số liệu provider rõ ràng; không suy từ số citation hoặc số nhóm.
- Giới hạn khởi điểm cho danh mục UI: 200 URL, 40 call, excerpt tối đa 320 ký tự/nguồn, toàn bộ `work.web` tối đa
  256 KiB khi serialize. Query/title/URL và số tham chiếu cũng có giới hạn hữu hạn trong hợp đồng giai đoạn 1.
- Khi chạm giới hạn, giữ nguồn có citation trước và báo giới hạn trong bảng. Không hiển thị một tổng giả như thể
  mọi nguồn upstream đã được lưu. Không nới ngân sách prompt hay thêm request AI để có thêm tiêu đề/đoạn trích.

### Giao diện

- Giữ nút nguồn có tối đa ba favicon, hình dáng/kích thước/trạng thái đồng bộ các nút lân cận.
- Desktop: bảng bên phải, header/nút đóng cố định, nội dung cuộn riêng. Chỉ một bảng nguồn/tài liệu/sơ đồ mở cùng lúc.
- Nhóm truy vấn thu gọn mặc định; mở nhóm mới tải/vẽ các hàng cần thiết. Một nhóm gồm tiêu đề, excerpt nếu có,
  website/favicon và liên kết an toàn. Không thêm hướng dẫn dài hoặc lặp trạng thái trên từng hàng khi đã rõ từ nhóm.
- Điện thoại: sheet phủ có nút đóng dễ chạm, safe area và cuộn riêng; giữ focus trong bảng và trả focus khi đóng.
  Không bắt buộc thêm cử chỉ kéo để đóng trong lần triển khai này.
- Dữ liệu cũ hoặc nguồn không có quan hệ query dùng danh sách tham khảo chung. Không bịa query để làm giao diện giống Grok.
- Inline citation vẫn mở nguồn/tooltip theo hành vi hiện tại; thay đổi thứ tự hiển thị không đổi ánh xạ citation ID.
- Tiếp tục dùng favicon hostname-only, không gửi URL đầy đủ/referrer chat. Lỗi icon dùng icon dự phòng, không thêm
  dịch vụ proxy hay request đọc trang để dò favicon.

## 4. Các giai đoạn và điều kiện hoàn tất

### Giai đoạn 1 — Hợp đồng dữ liệu và fixture — đã xong

1. Định nghĩa `work.web` có phiên bản, quy tắc ID/membership, chuẩn hóa số đếm, ngân sách và fallback.
2. Tách bộ chuẩn hóa danh mục UI khỏi ngưỡng nguồn dùng trong ngữ cảnh model.
3. Lập fixture cho Peto/xAI, OpenAI và Claude: có/thiếu query, một call nhiều query, query trùng, ID thiếu,
   nguồn trùng giữa các call, metadata cập nhật muộn, snippets thiếu, dữ liệu sai kiểu.
4. Ghi rõ từng adapter lấy được trường nào và trường nào chưa có bằng chứng live. Không mở rộng payload bằng suy đoán.

**Đạt khi:** normalizer/schema tests qua; quyết định số đếm/giới hạn rõ; dữ liệu hiện tại vẫn hợp lệ; không có
association query → URL do model hoặc frontend tự đoán. Chưa thay đổi cách gửi prompt hay gọi tìm kiếm.

### Giai đoạn 2 — Adapter, streaming và lưu/khôi phục — đã xong

1. Thu query/call/result từ cấu trúc provider trước khi nguồn bị gộp/cắt; ghép Claude input/result bằng tool ID.
2. Tích lũy catalogue/call theo ID, phát cập nhật khi có thay đổi; bỏ metadata không hợp lệ, giữ phần đã tra thành công.
3. Lưu `work.web` cùng checkpoint/câu trả lời; giữ qua history, fork/edit/retry và reload.
4. Dừng, timeout, lỗi provider, mất kết nối và khởi động lại phải kết thúc trạng thái call còn dở đúng cách.
5. Bảo toàn owner scope và dữ liệu citation; không đưa activity vào prompt, log query nhạy cảm hay gọi thêm LLM.

**Đạt khi:** provider giả → SSE → checkpoint/SQLite → history cho cùng nhóm/nguồn; sự kiện lặp không nhân đôi;
error/stop/restart không hiện trạng thái đang tra mãi; các test citation, web search và recovery liên quan vẫn qua.

### Giai đoạn 3 — Hoàn thiện sidebar và sheet — đã xong

1. Dùng catalogue để đếm/favicon và hiển thị nhóm theo query có thật. Dữ liệu thiếu dùng fallback đã chốt.
2. Làm hàng nguồn gọn: tiêu đề, tên trang/favicon, excerpt tùy chọn; bộ mở/đóng nhóm đúng bàn phím và touch.
3. Cập nhật trực tiếp khi đang trả lời, không tự đóng nhóm người dùng đang đọc hoặc giật vị trí cuộn.
4. Hoàn thiện desktop/mobile, giao diện sáng/tối, danh sách dài, nút đóng, Escape/Tab và chuyển giữa các bảng.

**Đạt khi:** không có nguồn inline bung xuống dưới; mỗi câu trả lời mở đúng danh mục; reload vẫn giữ dữ liệu;
không tràn ngang, không che ô soạn trên desktop; kiểm lại ảnh chụp cạnh các điều khiển Peto hiện có.

### Giai đoạn 4 — Kiểm chứng toàn luồng và bàn giao — đã xong ở local

1. Chạy bộ kiểm tra liên quan cho ba adapter, SSE, persistence/recovery, citation và renderer.
2. Kiểm thử trình duyệt với nguồn ít/nhiều, 105+ kết quả, trùng URL, query dài, favicon lỗi, liên kết độc hại,
   nguồn không có query, lịch sử cũ, metadata đến muộn và mạng ngắt.
3. Kiểm tra build và ngân sách JSON/DOM/SSE, bảo đảm mở nhóm không phát request AI. Kiểm tra phone bằng emulation
   và ghi rõ giới hạn; kiểm thử thiết bị vật lý thực hiện khi có thiết bị.
4. Bàn giao bản hoàn chỉnh cùng ảnh và ghi chú deploy frontend + backend. Chủ web commit/deploy sau khi xem kết quả.
   Nếu kiểm tra sau deploy cần gửi lượt AI mới có phí, báo rõ trước; đọc lịch sử hiện có không cần lượt AI mới.

**Đạt khi:** tất cả kiểm tra cần thiết qua, không còn lỗi ảnh hưởng luồng chat và ghi nhận rõ các fallback theo provider.

## 5. Ranh giới triển khai và nghiệm thu

Bản nháp cũ đã được chủ web yêu cầu sao lưu và bỏ ở lượt trước. Lượt này bắt đầu từ worktree sạch tại `e96fd91`,
giữ các thay đổi Companion đã commit. Đã triển khai lại theo hợp đồng nhóm query, không chỉ thay stylesheet.

Kiểm thử adapter dùng mock HTTP/provider, browser dùng API/nguồn giả lập và một SSE server local. Không gửi prompt
mới trên Grok, không gọi LLM trả phí. Chưa nghiệm thu bản deploy hoặc điện thoại vật lý; đây là giới hạn kiểm chứng,
không phải tuyên bố provider live luôn cung cấp query/snippet. Thiếu metadata dùng fallback đã nêu.
