# Bảy cải tiến UI/UX Trò chuyện theo Grok

Triển khai và kiểm tra ngày 27/10/2026; khảo sát Grok ngày 26/10. Chủ web đã cho phép triển khai toàn bộ;
bắt đầu từ worktree sạch tại `3695600`.
Đây là bốn giai đoạn mới, không mở lại bốn giai đoạn bảng nguồn đã hoàn thành. Chưa commit/deploy.

## Phạm vi và tham chiếu

Web Chat: Peto, Luna, Haiku cùng dùng UI. Giữ riêng Companion/AIRI và Imagine. Không thêm public sharing,
đọc audio, code execution/HTML preview, Segments, dependency AI hoặc tự động gọi lại model.
Tiêu chí: gần hành vi Grok đã khảo sát, màu/điều khiển nhất quán với Peto, icon gọn, keyboard/touch và dark/light.

Khảo sát Grok đã kiểm trực tiếp: bảng có Copy/Save, chọn đoạn → Add to chat → quote trong composer, Search có
preview khi ArrowDown, code Collapse/Expand, menu response và Regenerate. Không bấm tạo lại hay gửi prompt mới.
Đọc byte handler của bundle công khai đã tải từ URL thực tế; không đưa bundle Grok vào repo/sản phẩm.
Chi tiết bằng chứng nằm ngoài repo tại artifact `grok-ux-research-20261026/research.md` của cuộc chat triển khai.

- Quote: `3g6pmqu1mzq8v.js`, Selection/Range → popup → setQuotedSource(text, sourceResponseId).
- Bảng: `3g_9xf_1y55rd.js`, CSV Blob/download và clipboard text + HTML; không phải XLSX.
- Code: `29--105p2mzz0.js`, collapse >5 dòng, wrap khi dòng dài >90 desktop/>50 mobile. Không gán Expand là fullscreen.
- Phiên bản: `346k4xi92crzj.js`, PivotNavigation đổi response theo family; `055ot0d1wf4t9.js` tải nhánh.
- Paste: `2wx5sic4o0ltl.js`, đường mặc định >50.000 ký tự thành pasted-text.txt. Mới có bằng chứng static cho mục này.
- REA parent mới: `ev_c277db1bcfb0f716e0eef5ae08f5d96f1a0d5631c26179fc58b8e41ebcb645be`, artifact SHA256
  `0c78b30728e922a9a6f89edcf2c81a92df2234747abf3c7e7345321e25fee0d7`. Bốn file parse thành công,
  semantic/application coverage một phần; không tuyên bố biết backend Grok hoặc mọi account/A-B.

## Giai đoạn 1 — Tiện ích đầu ra: điểm 1, 4, 6

- Bảng có hai icon copy/tải CSV. Copy có HTML và plain text; CSV xử lý Unicode, dấu phẩy/xuống dòng/quote,
  ô có thể bị ứng dụng bảng tính hiểu là công thức. Không gọi AI tạo bảng lần nữa.
- Code dài có thu gọn/mở; dòng dài có Wrap/Unwrap; copy luôn lấy đủ code gốc. Không chạy code.
- Thanh thao tác assistant icon-only, nút hình dáng thống nhất, hover/focus/touch rõ, ít chữ. Menu `…` chứa
  xuất Markdown và **In / lưu PDF** qua trình duyệt. Không giả vờ đã tải PDF khi chỉ mở hộp thoại in.
- Giữ inline citation, nguồn bên phải, Mermaid và tài liệu hiện có. Chức năng mới chỉ nối vào Web Chat.

Đạt khi: unit conversion/safety/copy/menu/code state qua; nhìn lại desktop/mobile/sáng/tối; print không kéo
sidebar/composer/action controls vào trang in; không làm source marker hoặc code nguyên bản biến đổi.

## Giai đoạn 2 — Ngữ cảnh và điều hướng: điểm 2, 3

- Chọn đoạn trong đúng một câu trả lời đã lưu → thêm vào câu hỏi; quote strip xóa được, bấm về tin gốc.
  Selection không tự gửi, không ghi đè chữ đang soạn; có xử lý keyboard/touch/viewport và đoạn quá dài.
- Request `quoted_source: {message_id,text}` giới hạn 2.000 ký tự, kiểm nguồn assistant trong đúng owned chat.
  Lưu quote riêng với raw user content, dùng như dữ liệu người dùng trong history; không biến thành chỉ dẫn system.
  Quote nháp giữ đúng scope tài khoản/chat; lưu qua reload; chỉ xóa khi server nhận đúng snapshot đã gửi.
- Quote cũ giữ qua retry/fork, remap source ID khi copy nhánh; nguồn mất thì giữ excerpt nhưng không bấm nhầm.
  Companion `quote_id` không đổi.
- Search desktop list + preview, ↑/↓ chọn, Enter mở, Escape đóng, mobile dùng view preview/back phù hợp.
  Có abort/stale guard/cache nhỏ trong dialog, remount theo user. GET preview chỉ last12 tin/tổng24k ký tự;
  không tải toàn bộ chat/work/tài liệu hoặc gọi LLM để tạo preview.

Đạt khi: quote từ UI → mock request → model context → SQLite/history/fork khớp, raw content không đổi,
cross-owner/source sai bị chặn trước provider; search không hiện kết quả cũ khi query/account thay đổi.

## Giai đoạn 3 — Tạo lại và các phiên bản: điểm 5

- Câu trả lời hoàn tất có Regenerate; chỉ chạy khi chủ động bấm và không có lượt đang chạy.
- Giữ nhánh cũ; dùng question/response lineage thật để tạo family, không gom mọi chat trong branch_group thành
  các bản trả lời ngang hàng. Copy prefix không nhân đôi variant. Lịch sử cũ thiếu lineage không đoán từ nội dung.
- Điều khiển nhỏ index/count; chuyển bản mở đúng conversation và trỏ đúng message. Không chạy lại model.
  Giữ content/source/work/artifact/provider/quote cùng model/effort của bản đó.
- Tắt thao tác trong lúc đang stream/load/read-only; không làm mất draft riêng của chat khác.

Đạt khi: mock complete regenerate tạo nhánh mới, reload còn cả hai; siblings đúng câu hỏi; owner/archived/legacy,
fork prefix, lỗi/dừng/retry và nguồn/tệp được kiểm. Không gọi paid provider để kiểm nút.

## Giai đoạn 4 — Paste dài và nghiệm thu: điểm 7

- Đoạn plain text dán >50.000 ký tự thành tệp text có tên, kích thước, mở xem trước và gỡ được; không tự gửi.
  Không cắt im lặng hay mất nội dung nếu giới hạn tệp/đang stream/đọc clipboard lỗi. Giữ chữ và caret đang soạn.
- Thông báo gọn kèm Undo để trở lại văn bản; bảo vệ trường hợp người dùng đã sửa nháp sau khi chuyển đổi.
  Dùng cùng luồng giới hạn 16 tệp/8MiB mỗi tệp/16MiB tổng; tệp mới chỉ ở bộ nhớ tab như mọi draft attachment.
- Kiểm thử cả 7 điểm bằng API/SSE/provider giả; browser desktop + mobile emulation, dark/light, dài/trống/lỗi,
  lịch sử/owner/reload/branch và keyboard/touch. Không có lượt LLM trả phí.
- Build/diff check, tài liệu và ảnh bằng chứng. Chủ web commit/deploy sau khi xem. Cần build frontend + restart
  backend; migration chỉ additive. Điện thoại vật lý/live provider acceptance ghi riêng nếu chưa có.

## Trạng thái

| Giai đoạn | Trạng thái | Bằng chứng |
| --- | --- | --- |
| 1 | Hoàn tất trên bản local | Bảng CSV/HTML copy, code state, Markdown/print và icon actions qua unit + browser desktop/mobile |
| 2 | Hoàn tất trên bản local | Quote → request → context → history/fork; search preview/keyboard/mobile/back qua test |
| 3 | Hoàn tất trên bản local | Tạo lại tạo nhánh, đổi bản/F5 giữ cả hai; explicit lineage và phạm vi quyền qua test |
| 4 | Hoàn tất trên bản local | Paste/Undo/preview và kiểm hồi quy hoàn tất; build thành công |

## Kiểm thử và giới hạn xác nhận

Tất cả provider/API trong test là giả; không gửi prompt tới Grok, OpenAI hay Anthropic và không dùng quota.
Những lần chạy cuối sau sửa lỗi (các nhóm bên dưới không trùng file trong cùng tầng):

- Backend: `tests/test_chat_quoted_variants.py` **26 passed**; nhóm hồi quy **165 passed** gồm
  `test_conversation_actions`, `test_chat_turns`, `test_chat_recovery`, `test_chat_context`, `test_chat_selection`,
  `test_chat_stage4`, `test_source_activity_pipeline`, `test_companion_messages`, `test_chat`, `test_archive`.
  Có test migration DB cũ đã có dữ liệu chạy hai lần rồi fork, và di chuyển project không lộ family khác phạm vi.
- Frontend: `tests/App.test.tsx` **131 passed**; nhóm **218 passed / 13 files** gồm `messageUtilities`,
  `HistorySearch`, `Citations`, `MessageAttachments`, `chatStage4`, `WebSources`, `longPaste`, `quotedFollowup`,
  `chatDrafts`, `chatUxApi`, `api`, `companionChat`, `Companion` (đuôi `.test.ts` hoặc `.test.tsx`).
- Browser: **44 passed**, Chromium desktop 1440×900 và mobile emulation 390×844, trong `grok-chat-ux`,
  `source-activity`, `citations`, `chat-stage4`, `compose-during-reply`, `chat-selection`, `chat-attachments`,
  `chat-stop`. Chặn mạng ngoài, kiểm nguồn/F5/IME/focus/overflow, sáng/tối, giả lập đúng một lần bấm tạo lại.
  Suite mới cũng kiểm không có JavaScript/React console error. Ảnh đã được xem lại bằng mắt.
- `npm run build` (gồm TypeScript) thành công; `git diff --check` không có lỗi khoảng trắng.
  Cảnh báo kích thước chunk lớn có sẵn từ các thư viện đồ họa vẫn còn.

Không tuyên bố đã chạy toàn bộ repository, thử trên điện thoại vật lý, VoiceOver/NVDA, Safari hay provider/VPS thật.
Các ảnh kiểm tra cuối nằm ở artifact `grok-chat-ux-implementation/` ngoài repo của cuộc chat.

### Rà soát giao diện

| Before | After | Why |
| --- | --- | --- |
| Copy câu trả lời có chữ; bảng chưa có thao tác riêng | Một bộ nút icon tròn cho câu trả lời, code, bảng; nhãn ẩn cho trợ năng | Gọn và đồng bộ với nút sửa/copy tin người dùng |
| Code luôn mở và cuộn ngang | Thu gọn/mở, bật ngắt dòng; copy luôn đủ code | Giảm chiều dài lịch sử mà không mất dữ liệu |
| Search chỉ là danh sách | Hai cột trên desktop, preview/back trên mobile | Đọc thử trước khi rời chat hiện tại |
| Focus menu khi portal còn ẩn; mobile ẩn kết quả đang focus | Focus sau đo/hiện menu; mobile sang Open và Back về kết quả | Giữ thao tác bàn phím khi bố cục thay đổi |
| Ô Search có viền focus trắng dày vuông | Viền mỏng bo góc, cùng tông muted | Focus vẫn nhận ra và bớt chói |
| Export bảng xóa regex marker ở mọi ô | Chỉ bỏ badge citation đã render | Không xóa `[web:n]` viết như code/link hay dữ liệu người dùng |

## Hợp đồng và triển khai

- `quoted_source` độc lập với `quote_id` của Companion. Trường quote có `message_id: null` khi source cũ mất;
  vẫn hiển thị excerpt nhưng không nhảy nhầm. Draft quote dùng sessionStorage cùng scope hiện có, file chỉ trong RAM.
- GET `/api/conversations/{id}/preview`: chỉ Web Chat của owner, last 12 tin/tổng 24.000 ký tự,
  `{messages:[{id,role,content,status}], truncated}`; không dùng endpoint tải đầy đủ hoặc tạo bản tóm tắt bằng AI.
- `reply_variants: {index, choices:[{conversation_id,message_id,model?,effort?}]}` chỉ trang trí public history.
  Không thêm danh mục này vào ngữ cảnh model. Giới hạn latest 200 câu hỏi, 20 response origins/family; giữ bản hiện tại.
  Nhánh cũ không có lineage không bị đoán thành siblings chỉ vì nội dung giống nhau.
- Migration additive khi khởi động: `messages.quoted_source`, `chat_message_lineage`, `chat_turns.model/effort`;
  trigger vô hiệu hóa summary nếu quote thay đổi. Không xóa chat hay sửa nội dung gốc của nhánh đã hoàn tất.
- Deploy: cập nhật backend + build frontend rồi restart backend; không cần thêm `.env` hay thư viện mới.
  Chưa commit/deploy trong phiên này. Chỉ bấm Tạo lại sau deploy khi muốn phát sinh một lượt model mới thật.
