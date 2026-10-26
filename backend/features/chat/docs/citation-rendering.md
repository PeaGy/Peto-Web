# Audit và sửa citation rendering — 25/10/2026

Phạm vi: Web Chat, từ nguồn provider tới SSE, lịch sử và Markdown renderer. Không gọi LLM trả phí; không tự
commit/deploy. Không đổi persona, quyền công cụ, runtime Agent/Companion hoặc chính sách saved memory.

## Kết luận audit

Code Peto trước bản sửa không tự sinh `[web:n]`; provider chuyển `response.output_text.delta` thành chữ nguyên bản
và service chuyển tiếp/lưu nội dung đó. Vì chưa thu một response thật của chính lượt GTA5 trong ảnh, không kết luận
chính xác upstream phát marker bằng cơ chế nội bộ nào. Code và mock chứng minh hai điểm thiếu độc lập:

1. `normalize_sources` chỉ giữ URL/title/kind/access/partial; ID và vị trí citation của native annotation bị bỏ.
   Bởi vậy dù upstream có ID, metadata tới SSE và SQLite cũng không giữ được nó.
2. `ChatMessage` chỉ chạy Markdown chung; `WebSources` chỉ làm danh sách cuối bài. Không có bộ nối token trong chữ
   với nguồn nên `[web:21]` là text bình thường.

Danh sách URL/title **đã có** qua SSE và lịch sử, nhưng ID **chưa có** trong hợp đồng public cũ. Số `21` không phải
bằng chứng rằng URL thứ 21 trong mảng là nguồn tương ứng: mảng đã dedup, ưu tiên cited trước và giới hạn 30 nguồn.
Ảnh có `[web:26]` bên cạnh danh sách 20 nguồn càng không cho phép suy đoán bằng array index.

## Đường đi dữ liệu và bản sửa

| Bước | File và hành vi |
| --- | --- |
| Search/tool results | `backend/ai/xai.py::_item_sources`: lấy sources từ native search action hoặc URL annotation; `claude.py` đổi native search/fetch/citations sang giao thức chung. Không coi URL model tự viết là bằng chứng đã fetch. |
| Citation association | `shared/web_search.py::citation_ids`: giữ ID tường minh; có thể lấy ID từ đúng một marker tại span annotation được provider gắn URL. Không suy index, không dùng số source để đoán URL. |
| Provider text | Responses delta vẫn giữ chữ gốc. Claude Web Chat chèn marker `src:<hash>` ngay vị trí `citations_delta`; hash URL đã được kiểm tra, không đưa encrypted_index ra client. Các luồng không có Web Chat snapshot giữ cách cũ. |
| Backend/SSE | `features/chat/service.py` gộp nguồn qua cùng normalizer và phát `type=sources`; không thay schema sự kiện delta. ID giờ được giữ qua mọi lần normalize. |
| Persistence | `storage/chat_turns.py` checkpoint/final save JSON nguồn; `storage/conversations.py` và `features/chat/history.py` normalize khi đọc. ID còn nguyên sau lưu/tải lại; không cần migrate DB. |
| Browser streaming | `shared/api/api.ts` đọc events; `App.tsx::onSources` gọi `safeSources`. `sourceData.ts` giữ ID, lọc URL, gộp alias của cùng URL và phát hiện một ID có nhiều URL. |
| Rendering | `Citations.tsx` là remark AST plugin cho assistant: chuyển token thành node cite và component React có kiểm soát. Không replace bằng HTML và không bật rehype-raw. |
| Footer | Từ 26/10, `WebSources` là pill favicon mở `SourcesPanel` bên phải/sheet. Nhóm native query dùng `work.web`, dữ liệu cũ giữ fallback citation/search/page/tool/legacy. Xem [source-activity.md](source-activity.md). |

Hợp đồng nguồn thêm trường **tùy chọn**, ví dụ:

```json
{"url":"https://example.com/story","title":"Bài viết","kind":"citation","citation_ids":["web:21","web:26"]}
```

ID chấp nhận: `web:<digits>`, `x:<digits>`, `src:<16 hex>` và `turnNsearchN`/`turnNviewN`/`turnNfetchN`.
ID phải xuất hiện trong metadata hoặc được chứng minh bởi span native, không lấy từ ordinal của annotation/mảng.
Mỗi URL giữ tối đa 24 alias; giới hạn nguồn cũ vẫn là 30 và cited sources được ưu tiên. Không tăng prompt/log vô hạn.
Mỗi nhóm inline giới hạn 128 reference để chuỗi marker bất thường không tạo DOM hoặc phép gộp không giới hạn.

Native Markdown `[[N]](URL)` có URL khớp danh mục nguồn cũng được hiển thị thành badge; liên kết Markdown bình
thường giữ renderer an toàn hiện có. Prompt tìm web nhắc dùng native citations hoặc exact-source Markdown links,
không tự chế `[web:N]`/ID. Đây là hướng dẫn định dạng; tính đúng của renderer không dựa vào việc model luôn nghe lời.

## Streaming và fallback

- Marker hoàn chỉnh cùng metadata → link badge nhỏ. Các citation cạnh nhau được nhóm và dedup theo URL trong nhóm.
  Hover/focus dùng TooltipLayer hiện có, hiển thị title và URL; click mở tab nguồn với noopener/noreferrer.
- Marker hoàn chỉnh nhưng metadata chưa đến → badge chờ `…`; metadata đến sau sẽ cập nhật qua render bình thường.
- Prefix marker đang chia chunk được giữ kín. Native Markdown citation chưa đóng cũng được giữ, kể cả trường hợp
  GFM đã auto-link phần URL thành sibling node. Không sửa nội dung gốc đang lưu để xử lý trạng thái hiển thị.
- Khi lượt kết thúc, ID thiếu/sai/ambiguous hoặc marker bị ngắt → `?` có mô tả chưa xác định, không gán một URL đoán.
- Code fences, inline code, link labels và tin người dùng được giữ nguyên. Parser không biến ví dụ code thành citation.
- Native OpenAI marker được hỗ trợ khi có ID hoặc span native gắn nguồn rõ. Không tự phục hồi các ID chưa biết.

**Giới hạn lịch sử:** dữ liệu cũ chỉ có URL/title đã mất ID không thể được sửa chính xác chỉ từ mảng URL hiện còn.
Nguồn cuối bài vẫn mở được, marker chưa ánh xạ hiện trạng thái chưa xác định. Không tự gọi lại model hoặc gán URL
theo số. Nếu upstream tương lai chỉ gửi marker và không có bất kỳ association/URL annotation nào, cũng dùng fallback
này; cần payload provider có cấu trúc để xác minh thêm, không lấy câu trả lời model làm bằng chứng.

## An toàn và UX

Chỉ HTTP(S), không credentials, control characters, DEL, backslash hoặc URL quá 2.048 ký tự. Frontend kiểm lại metadata
độc lập với backend. Title là text React đã escape; không dùng dangerouslySetInnerHTML/eval. Từ 26/10, bảng nguồn dùng
favicon Google S2 với hostname công khai và no-referrer, local YouTube/GitHub SVG hoặc globe khi lỗi/host private;
không gửi URL đầy đủ hay nội dung chat để lấy icon. Chi tiết trong [source-activity.md](source-activity.md).
Metadata không hợp lệ không làm hỏng câu trả lời. Một ID trỏ hai URL khác nhau không tạo liên kết bừa.

Keyboard có focus ring và tooltip; hover chỉ áp dụng thiết bị có hover/pointer fine. Touch mở link trực tiếp, có
feedback và kích thước badge lớn hơn; thông tin nguồn cũng đọc được từ danh sách cuối bài. Không tắt browser zoom.
Không thêm animation cho marker stream. Tooltip dài wrap trong viewport. Chưa kiểm điện thoại vật lý hoặc screen reader.

| Before | After | Why |
| --- | --- | --- |
| `[web:21] [web:26]` hiện như chữ | Cụm badge nhỏ mở đúng URL có metadata | Đọc gọn và truy được nguồn gần claim. |
| Metadata chỉ có URL/title | Alias ID tùy chọn đi qua SSE/SQLite/history | Dedup/sort không phá liên kết ID với nguồn. |
| Chunk dở có thể lộ prefix/link | Giữ phần control syntax đang nhận | Tránh nhấp nháy và rò marker. |
| Không có cơ chế cho ID không tồn tại | Badge chờ/chưa xác định, không đoán URL | Tránh citation trông hợp lệ nhưng dẫn sai nguồn. |
| Nguồn chỉ dùng danh sách cuối bài | Thêm inline badges, giữ footer hiện có | Tương thích dữ liệu và provenance cũ. |

## Kiểm chứng và triển khai

`backend/tests/test_citations.py`: alias/span, URL không an toàn, provider fake → SSE → save/reload, owner scope,
metadata sớm/muộn, reply lỗi giữ citation và native Claude HTTP mock. Nhóm web search/Claude/stage4 kiểm hồi quy.

`frontend/tests/Citations.test.tsx`: mọi điểm chia chunk, mapping không theo array index, group/dedup, metadata muộn,
unknown/conflict/legacy, code/user text, native Markdown/OpenAI, title XSS và URL scheme. `WebSources`/API tests và
browser `citations.spec.ts` kiểm App stream/mở nguồn/tooltip/footer/F5 trên PC và mobile giả lập; request ngoài được mock.

Kết quả: toàn backend **1.841 đạt, 1 bỏ qua** (497,42 giây); toàn frontend **1.009 đạt** (153,06 giây). Sau giới hạn
cuối cho nhóm marker bất thường, nhóm citation/source/API chạy lại **33 đạt**; build production và diff check đạt.
Browser giai đoạn 4 **10 đạt**; citation PC/mobile giả lập **2 đạt**, lần cuối gồm URL dài khoảng 1.700 ký tự,
tooltip focus bằng bàn phím, mở tab nguồn được mock, footer, F5 và không tràn viewport. Đã xem screenshot hai bố cục.
Lần browser đầu chạy cùng các bộ test lớn có hai timeout ở màn Loading; chạy lại một worker đều đạt. Lỗi selector
test mới đã sửa để dùng accessible name đúng (mũi tên decorative aria-hidden) và focus qua Tab thực tế.

Sau commit/deploy cần **restart backend và build lại frontend**, reload tab để tải renderer mới. Không đổi `.env`,
model, key, API params hoặc CLI bundle. Bản sửa không chứng minh tính chính xác nội dung GTA5 hay mọi claim có citation.

Tài liệu provider đã đối chiếu:

- [xAI citations](https://docs.x.ai/developers/tools/citations): native Markdown và URL annotations khác với danh mục tất cả nguồn.
- [Anthropic web search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool): citation có URL/title và native streaming.
