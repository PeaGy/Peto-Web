# Bảng nguồn Trò chuyện — 26/10/2026

Đã triển khai bốn giai đoạn trong [kế hoạch](sources-panel-plan.md) trên HEAD `e96fd91`.
Phạm vi: Web Chat Peto/xAI, Luna/OpenAI và Haiku/Claude. Chưa commit hoặc deploy bản này.
Không sửa UI Companion/Imagine, không thêm model, thư viện hoặc request AI.

## Tham chiếu Grok và mức độ bằng chứng

Đã mở trực tiếp cuộc chat Grok đang đăng nhập, bấm `105 sources`, mở nhóm đầu có 15 nguồn, kiểm tra DOM,
computed styles và bố cục rộng/hẹp. Không gửi prompt mới. Quan sát này chứng minh hành vi UI, không chứng minh
backend Grok hoặc mức metadata mà API của Peto sẽ nhận.

Ngày 26/10, đã tải 230 script công khai từ các URL `cdn.grok.com` thực sự có trong trang, không xuất cookie/token.
REA `analyze_javascript_application` phân tích static ba bundle liên quan, không thực thi bundle:

| Bundle công khai | Dữ kiện đọc được |
| --- | --- |
| `395li57uktfm2.js` | Export `SourcesPill`, `FaviconStack`, `WebSearchResultCard`, `getGoogleFaviconUrl`. Pill dùng `responseId` để mở/đóng cùng bảng nguồn; lấy kết quả từ `useSearchResults`. |
| `1h0zv2no6264t.js` | Cấu hình công cụ `webSearch`, `queryArg: query`, kết quả loại `web`. |
| `3g6pmqu1mzq8v.js` | Hiển thị trace, dòng “Thinking about your request” và pill nguồn. Không dùng dữ kiện này để bịa bước suy nghĩ cho Peto. |

REA parent evidence: `ev_bfd181917acdc6237332b1154df1b0f0fd8de901000056808fed8457aeba96bd`;
summary evidence: `ev_6f2bad8b5bbfc6ab4114f83fb5f3b982896a31c4550178b0f2fb1875fad943ef`.
Root artifact SHA-256: `0a1fb41c171ab0d3197a0ffaf1b4f50ef2ec65cf9fb5072af6a8c481c1d4a418`.
Ba file được parse, 402.020 byte, không lỗi parse. Semantic/application coverage **một phần** do giới hạn graph
100.000 node; không tuyên bố đã khôi phục toàn bộ mã Grok. Bundle chỉ nằm trong thư mục bằng chứng ngoài repo.

Đo DOM: bảng nguồn 480 px ở viewport 1440 px; query 14/21 px, padding 12×24 px, hàng hai dòng 65 px;
query monospace và số đếm trong ô viền nhỏ. Card có title/snippet rồi favicon/tên website, không thêm mũi tên
ở mỗi card. Pill cao khoảng 31 px; tối đa ba icon trong vòng tròn 20 px, chồng 12 px. Cả DOM và bundle cho thấy
icon ứng viên theo source URL; các nguồn cùng website có thể lặp favicon. Grok dùng Google S2 theo hostname.
Peto tái dựng hành vi bằng component riêng và biến màu của Peto, không đưa mã bundle của Grok vào sản phẩm.

Manifest, bundle và ảnh tham chiếu nằm ngoài repo tại thư mục `grok-sources-20261026` trong thư mục bằng chứng
của cuộc chat Codex. Ảnh Peto local nằm trong `peto-sources-20261026` cùng gốc. Đường dẫn tuyệt đối trong báo cáo bàn giao.

## Hợp đồng dữ liệu

Giữ nguyên `messages.sources` tối đa 30 URL và citation aliases hiện có. Không dùng số thứ tự của array để suy
citation. Danh mục UI riêng nằm trong trường **tùy chọn** `work.web`:

```json
{
  "version": 1,
  "sources": [{
    "url": "https://example.com/story",
    "title": "Bài viết",
    "kind": "result",
    "access": "search",
    "snippet": "Đoạn trích công khai do provider cung cấp"
  }],
  "calls": [{
    "id": "xAI:1:native-id",
    "kind": "search",
    "operation": "search",
    "queries": ["truy vấn có trong payload công cụ"],
    "state": "done",
    "source_urls": ["https://example.com/story"]
  }]
}
```

- `kind`: `search` hoặc `page`; `operation` tùy chọn: `search`, `fetch`, `open_page`, `find_in_page`.
- `state`: `live`, `done`, `failed`, `stopped`. Cập nhật lặp không mở lại call đã kết thúc.
- ID có provider/vòng/native ID. Thiếu native ID không tạo call giả; nguồn hợp lệ vẫn nằm trong danh mục chung.
- Một native call nhiều query vẫn là một nhóm; không suy query nào ứng với URL nào nếu payload không chứng minh.
- Registry dedup URL. Một URL có thể thuộc nhiều call. Pill đếm URL khác nhau xem được; mỗi nhóm đếm membership
  khác nhau trong chính nhóm đó. Không cộng tổng nhóm để làm số pill, không hiển thị tổng upstream không kiểm chứng.
- Giới hạn: 200 URL, 40 call, 256 KiB JSON UTF-8; URL 2.048, title 200, snippet 320, ID 128 ký tự;
  mỗi call tối đa 8 query × 500 ký tự và 200 URL tham chiếu. Nguồn citation được ưu tiên khi phải cắt.
- Khi cắt, `truncated: true` và bảng báo chỉ hiển thị phần đã lưu. Không tăng ngân sách prompt để có đủ danh mục.
- Chỉ lấy snippet/description/cited_text dạng plaintext có thật. Không lấy từ encrypted content, không gọi AI
  để viết snippet, không suy query từ prompt/title/câu trả lời hay nhãn timeline.
- Call lỗi không đưa nguồn mới chưa thành công vào registry. Quan hệ nguồn đã thành công trước đó được giữ.
- Dữ liệu hỏng/phiên bản không hỗ trợ dùng nguồn phẳng an toàn. Không yêu cầu migrate SQLite.

## Pipeline và file liên quan

1. `shared/source_activity.py`: validator, registry có giới hạn, upsert, stop và đọc snapshot cũ.
2. `ai/xai.py`: lấy metadata native trước khi `normalize_sources` gộp/cắt 30; cả GPTProvider dùng chung đường
   Responses. Annotation và nguồn GitHub được giữ làm nguồn chưa ghép query khi không có association.
3. `ai/claude.py`: ghép `server_tool_use.id` với `tool_use_id`; đọc input hoàn chỉnh ở block stop, giữ qua pause.
   Metadata bổ sung dùng sự kiện nội bộ `peto.source_activity`. **Không đổi `_portable_output`**, replay native,
   thinking signatures, tool schemas hoặc request arguments. Việc này tránh phá so khớp replay của Claude.
4. Các adapter chỉ phát activity khi có Web Chat `RequestContext`; không đổi protocol Companion/Agent.
5. `features/chat/work_log.py` tích lũy và phát `{type: 'source_activity', web: snapshot}` khi metadata thay đổi,
   không phát theo từng token. Snapshot/close giữ `work.web`.
6. `features/chat/service.py` chuyển event và dùng checkpoint hiện có. `storage/chat_turns.py` kiểm lại trước lưu,
   dừng call live khi stop/lỗi/restart. `features/chat/history.py` kiểm lại khi đọc. Owner scope không đổi.
7. `features/chat/conversations.py::fork` vốn copy JSON `work` trong prefix; test mới chứng minh giữ danh mục và
   không copy câu trả lời bị thay thế. Không tạo nhánh hoặc thay đổi dữ liệu cũ chỉ để mở bảng nguồn.
8. Frontend `api.ts` validate SSE; `sourceActivity.ts` validate/merge danh mục độc lập với `sourceData.ts` max 30.
   `App.tsx` lưu metadata vào câu trả lời, giữ nhóm đang mở khi stream, đóng bảng khi đổi chat/view hoặc sửa câu hỏi.
   `WorkTimeline.closeWork` giữ danh mục và dừng live call nếu luồng kết thúc không có bản chốt.
9. `WebSources.tsx`, `SourceIcon.tsx`, `SourcesPanel.tsx`, `sources.css`: pill, favicon, nhóm truy vấn, fallback,
   sidebar và sheet. Inline citation vẫn dùng renderer/mapping hiện có.

**Không đưa `work.web` vào model input.** Test gửi lượt thứ hai bằng mock provider xác minh display query/snippet
không có trong kwargs/context. Giới hạn nguồn model vẫn 30. Không ghi log nội dung query, User-Agent hoặc token.

## Giao diện và an toàn

| Trước | Sau | Lý do |
| --- | --- | --- |
| Danh sách bung ngay dưới câu trả lời | Pill favicon mở bảng bên phải, tối đa 480 px | Giữ chiều cao hội thoại và giống mẫu Grok đã quan sát. |
| Nguồn phẳng bị cắt theo giới hạn context | Danh mục UI độc lập, query group thu gọn | Xem nhiều nguồn mà không tăng context model. |
| Không có liên kết query → kết quả công khai | Nhóm theo native ID/query đã chứng minh | Có provenance để đối chiếu, không đoán từ nhãn. |
| Card nhiều nhãn và viền | Title, snippet tùy chọn, favicon/tên miền ở dưới | Gọn và cùng thứ tự thông tin như Grok. |
| Bảng hẹp có thể lấn ô soạn | Ở viewport ≤1.100 px dùng sheet tối đa 85dvh | Có nút đóng 44 px, safe area, cuộn riêng và focus trong sheet. |
| Dữ liệu cũ không có query | Nhóm citation/page/tool/search/legacy theo dữ kiện cũ | Vẫn xem được, không tạo lịch sử tìm kiếm giả. |

Chỉ một bảng nguồn/tài liệu/sơ đồ mở cùng lúc. Query có ellipsis và title đầy đủ; mở nhóm không phát request AI.
Nhóm lịch sử đã nêu mức bằng chứng thì card không lặp nhãn đó; citation/mức đọc một phần vẫn có nhãn cần thiết.
Lượt không có nguồn chỉ hiện “Đang tra cứu” khi còn call live; kết thúc dùng “Tra cứu”, không để trạng thái treo.
Escape đóng bảng; sheet dùng native dialog + focus wrap và trả focus về opener còn tồn tại. Button đóng tròn,
hover chỉ bật trên pointer fine; có focus-visible, touch-action, dark/light và overscroll containment.
Không thêm animation hoặc chỉ dẫn dài. Không sửa chuyển động/persona Companion.

URL chỉ HTTP(S), không credentials/control/backslash và được kiểm ở hai phía. Text render qua React escaping;
không raw HTML/eval. Link mở với `noopener noreferrer`. Favicon Google S2 nhận **hostname công khai**, không path,
query hoặc referrer chat (`referrerPolicy=no-referrer`); host private/local/IP dùng globe, YouTube/GitHub có SVG
cục bộ. Icon lỗi dùng globe. Không proxy/đọc trang để dò icon. Đây là external favicon request mới cho các site
công khai khác, không phải chứng minh favicon của mọi website luôn tải được.

## Kiểm chứng

Không có API LLM trả phí hoặc prompt Grok mới trong lần triển khai. Browser tests chặn network ngoài, favicon dùng
fixture và SSE streaming dùng server HTTP local. Số dưới đây là các lượt kiểm có phần chồng nhau, **không cộng thành
tổng test duy nhất**; không tuyên bố đã chạy toàn bộ test repository.

| Nhóm | Kết quả |
| --- | --- |
| Backend source activity + adapter + web search/Claude/citation hiện có | 108 passed; sau hardening Unicode/byte budget/bulk restore, 30 test sở hữu chạy lại đều qua. |
| Backend pipeline + WorkLog + chat turns + citation | 43 passed. Sau thêm case fork giữ danh mục, pipeline 5 passed. |
| Frontend WebSources/SourceActivity | Ban đầu 19 passed. Rà soát cuối WebSources/SourceActivity/API/chatStage4: 31 passed; sau thêm ba case kết thúc không nguồn, WebSources 13 passed. |
| Frontend API/Citations/chatStage4/App | 148 passed. API/closeWork chạy lại sau hardening: 3 passed. |
| Browser nguồn/citation/chat-stage4, desktop + mobile emulation | Lần cuối chạy cả ba file: **24 passed** (1,2 phút), gồm case sửa câu hỏi và ảnh query/nguồn/light. |
| Production build | `npm run build` passed; chỉ còn cảnh báo chunk lớn hiện có. |
| Whitespace | `git diff --check` sạch. |

Coverage: thiếu ID/query, multi-query, query trùng, URL trùng nhiều call, source annotation, metadata đến muộn,
payload OpenAI riêng, native Claude HTTP mock/pause/replay, byte-split Unicode SSE, 105/205 nguồn, query dài,
cap JSON, XSS/URL nguy hiểm, favicon lỗi, dark/light, tab/Escape, breakpoint, bảng tài liệu, đổi chat, F5,
owner scope, stop/restart, fork giữ prefix và catalogue không đi vào model context.

Một fixture cũ ở `test_chat_turns.py` cần nhận `**kwargs`: HEAD hiện có `quote_id` từ Companion; mock chỉ nhận
`*args` làm test lỗi trước khi tới đường nguồn. Chỉ sửa fixture, không sửa behavior Companion.
Case browser sửa câu hỏi đầu tiên dùng click trên action đang ẩn theo hover nên timeout; chuyển sang focus/Enter
theo hành vi bàn phím sản phẩm, cả desktop/mobile đều qua, không ép click hoặc bỏ kiểm tra.

Bulk normalize 200 nguồn/40 call, tám lần trên máy phát triển: trung bình 18,67 ms, lớn nhất 20,59 ms;
đã đối chiếu output như cũ sau tối ưu. Đây không phải benchmark VPS. Snapshot tối đa 256 KiB; nhóm thu gọn không
mount source cards, icon lazy. Chưa đo tải nhiều người dùng trên VPS 2 vCPU hoặc kiểm thiết bị điện thoại vật lý,
screen reader, payload live mới của cả ba nhà cung cấp.

## Deploy và nghiệm thu sau deploy

Chủ web commit/deploy sau khi xem. Cần **restart backend và build frontend**, rồi reload tab. Không đổi `.env`,
API key, model config, quyền connector hoặc schema DB.

1. Mở một hội thoại cũ có nguồn: thấy pill và fallback; nguồn không nhảy xuống dưới câu trả lời.
2. Mở bảng nguồn của nhiều câu khác nhau; đổi chat, sửa câu hỏi, mở tài liệu: không giữ nhầm bảng.
3. Kiểm điện thoại thực: mở/đóng sheet, chạm nguồn, cuộn danh mục và quay lại chat.
4. Nếu muốn nghiệm thu query group từ response mới, lượt tìm web thật có thể dùng quota. Chỉ hiển thị query/snippet
   khi payload thật có các trường đó. Thiếu thì dùng danh mục chung; lịch sử cũ không được tự khôi phục metadata mất.
