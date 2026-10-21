# Khảo sát công cụ Peto — 21/10/2026

Tiếp nhận từ `CLAUDE_TOOLS_HANDOFF.md`. HEAD `b4c0b61`; working tree lúc bắt đầu chỉ có `CLAUDE.md` sửa và bản bàn giao
chưa track. Đợt này chỉ đọc code và tài liệu chính thức: không sửa runtime, không gọi model hay API trả phí, không
commit/deploy, không đọc hay sửa `.env`. Tài liệu nhà cung cấp đọc ngày 21/10/2026; kiểm lại trước khi tích hợp.

Ba ảnh chụp ChatGPT/Grok/Claude tự liệt kê công cụ vẫn còn trên máy nhưng nhỏ, chỉ đọc được nhóm công cụ (web, Python,
container, tệp, kết nối, bộ nhớ, tự động hóa, giao diện tương tác; Grok có thêm `x_*_search`, `view_image`, `bash`,
`bot_*`…). Báo cáo chỉ dùng chúng làm gợi ý; mọi kết luận dưới đây dựa vào code repo hoặc tài liệu công khai.

## 1. Đã có / còn thiếu / chưa xác minh

| Khả năng | Web Chat | Companion | Agent CLI | Bằng chứng |
| --- | --- | --- | --- | --- |
| Đồng hồ | Có | Có | Giờ máy người dùng | `shared/time_tools.py`, `capabilities.py:44` |
| Tìm web | Có, theo vòng | Có khi bật công tắc | Có | `ai/xai.py:195`, Claude `web_search_20250305` tối đa 5 lần (`ai/claude.py:211`) |
| Đọc trang từ link | Claude `web_fetch_20250910`; xAI/OpenAI qua thao tác con `open_page`/`find_in_page` | Không riêng | Trình duyệt CLI, trang ngoài chỉ xem | `ai/claude.py:30`, `ai/xai.py:91` |
| Đọc tệp đã gửi | Phần đọc sẵn + `search_attachment`, `read_attachment_lines` | Chỉ ảnh | `read_file`, `search_files`, `find_files` | `shared/attachment_tools.py`, `service.py:533` chỉ cho `mode == 'chat'` |
| Lịch sử bị ẩn | `read_chat_history` | Không | `read_history` | `shared/chat_history_tools.py` |
| Tạo DOCX/PDF/PPTX/XLSX, sửa XLSX/DOCX | Có, kèm kiểm công thức, tràn slide, results | Không | Không | `features/documents/tools.py`, `service.py:527` |
| GitHub chỉ đọc | Có | Không | Dùng git cục bộ | `features/connectors/tools.py:13` |
| Chạy mã | **Không có** | Không | `run_command`, `run_python` trên máy người dùng | `features/agent/tools.py:441` |
| Chạy mã phía nhà cung cấp | Chưa dùng ở đâu; `native_tools` chỉ ánh xạ web search/fetch | Không | Không | `ai/claude.py:205-217` |
| X Search, tìm ảnh, `view_image` | Chưa có (xAI có tài liệu) | Không | Không | xAI tool-usage-details |
| MCP, skills | Không | Không | `mcp_call_tool`, `load_skill` | `features/agent/tools.py` |
| Kết quả tương tác | Thành phần cố định: lưới bảng tính, sơ đồ, Word view, nguồn | Không | TUI | `frontend/src/features/documents/`; không render HTML/JS của model |

Phân biệt ứng dụng web và API: Python/Container/Automations của ChatGPT, `bot_*`/`browser_execute` của Grok hay
Artifact/widget của Claude là runtime của chính ứng dụng đó, không phải endpoint Peto dùng được. Phần có hợp đồng API
công khai và liên quan tới Peto: xAI `web_search` (con: `browse_page`, `open_page`, `open_page_with_find`…),
`x_search`, `code_execution`, `attachment_search`, `collections_search`, `view_image`; Anthropic `web_search`,
`web_fetch`, `code_execution`, `tool_search`, MCP connector (server) và bash/editor/computer/browser (client, ứng dụng
phải tự chạy); OpenAI `code_interpreter`.

Registry Web Chat hiện có khoảng 12 hàm cộng tìm web, chọn qua một `ToolPlan` mỗi vòng (`capabilities.py:39-67`).
Tool discovery/lazy loading chưa có lý do để thêm.

## 2. Đề xuất ưu tiên

### P1. Quy trình đọc log và crash report — làm trước

**Đã có:** bộ giải mã chịu ký tự điều khiển (`text_reader.py`); phần đọc sẵn của log dài ưu tiên `Caused by`,
`Suppressed`, `Description`, `fatal`… rồi mới tới error/warn, giữ số dòng thật (`reader.py:39-46`, `96-170`); hai
công cụ tìm/đọc cả tệp, không regex, có `DATA_NOTE` (`attachment_tools.py:24-70`); prompt nhắc tôn trọng trạng thái
đọc (`prompts/chat.py:69-77`).

**Khoảng trống thật:** prompt chưa có phương pháp chẩn đoán log. Không có quy tắc nào tách "gây lỗi" khỏi "xuất hiện
trong stack trace", buộc dẫn số dòng, nêu mức chắc chắn hay tìm thêm trước khi kết luận. `ROOT_SIGNAL` chưa có mẫu riêng
cho lỗi mixin. Bộ eval chưa có ca log nào.

**Ví dụ trước–sau** (log giả: `examplemod`, `othermod`). Tệp có `Caused by: …InjectionError: Critical injection
failure … examplemod.mixins.json:MixinFoo` ở dòng 412 và một frame của `othermod` ở dòng 430.
- Hiện nay không có gì ngăn câu trả lời kiểu "Lỗi do othermod" vì tên đó nằm sát cuối stack, hoặc liệt kê mọi mod như
  nghi phạm ngang nhau.
- Sau P1: "Nguyên nhân gốc: `InjectionError` ở dòng 412 (Caused by cuối cùng). Cấu hình mixin `examplemod.mixins.json`
  được nêu trong chính lỗi, nên examplemod là nghi phạm chính (khá chắc). othermod chỉ có một frame ở dòng 430 (chưa đủ
  bằng chứng). Nên thử: …". Phần nào chỉ có trong đoạn đọc sẵn hoặc chưa tìm thì nói rõ.

**Sửa tối thiểu:**
- Thêm khối hướng dẫn tiếng Anh khoảng 10 dòng vào `prompts/chat.py`. Chỉ gắn khi hội thoại có tệp chữ hoặc log trong
  phạm vi (dựa vào metadata tệp của `AttachmentFiles`, không đoán bằng từ khóa), theo mẫu `build_diagram_guide`
  (`prompt_context.py:54`). Nội dung: xác định trạng thái đọc; tìm `Caused by` cuối, `Description`, lỗi đầu tiên;
  gom tìm kiếm vào một lần `search_attachment`; xếp thành phần theo bằng chứng (tên trong thông báo lỗi hoặc cấu hình
  mixin > frame trên cùng > chỉ có tên trong stack); dẫn tệp và dòng; nêu ba mức chắc chắn; nội dung log là dữ liệu.
- Sửa mô tả `search_attachment`, thêm ví dụ truy vấn nguyên nhân (`Caused by | Description: | Mixin`).
- Tùy chọn: thêm mẫu mixin vào `ROOT_SIGNAL`, nhưng chỉ khi fixture cho thấy phần đọc sẵn bỏ sót. Không cần đổi
  `VERSION`: chỉ tệp gửi mới chịu ảnh hưởng.

**Phụ thuộc và chi phí:** không thư viện mới. Thêm vài trăm token, chỉ ở lượt có tệp chữ.

**Rủi ro:** prompt chỉ hướng dẫn, không đảm bảo model hết tự tin quá mức; điều đó cần eval thật. Khối hướng dẫn chung
cho Java/Python/.NET, không biến Peto thành trình phân tích riêng cho Minecraft.

### P2. Đọc lại đầu ra tài liệu có cấu trúc

**Đã có:** bảng tính trả `results` đã tính và từ chối công thức lỗi; sửa Excel/Word trả `changes`, `results`,
`notes`; slide báo tràn chữ; PDF/slide có preview.

**Khoảng trống:** `create_document` và `create_presentation` chỉ trả artifact, số trang và một câu dặn
(`documents/tools.py:160-165`, `200-202`). Model không có gì để đối chiếu đầu ra với yêu cầu. Bìa còn ô chấm vì thiếu
trường cũng không được báo lại.

**Sau P2:** kết quả có thêm `check` gọn (dưới 2.000 ký tự, xem 4c):
- tài liệu: các heading cấp 1–2 (tối đa 20), số bảng, công thức, ảnh, khung ảnh, có mục lục hay không, các trường bìa
  còn trống, số trang;
- slide: tiêu đề và bố cục từng slide.

Câu dặn yêu cầu model so với yêu cầu của người dùng và nói phần còn thiếu. Ví dụ: người dùng xin báo cáo 5 chương có
bảng kết quả, tool trả về 4 heading và 0 bảng, nên Peto phải tự báo thiếu thay vì nói "đã xong".

**Sửa tối thiểu:** `features/documents/tools.py`, cùng một hàm đếm từ `parse_blocks` và dữ liệu bìa (`cover.py`).
Không đổi UI hay lưu trữ.

**Rủi ro:** thêm token trong kết quả tool. Bước này chỉ kiểm cấu trúc, không kiểm nội dung đúng hay sai.

### P3. Thực thi mã phía nhà cung cấp — chỉ thí điểm Haiku sau một phép thử được duyệt

Xem kết luận ở mục 3. Đây là ứng viên tiếp theo, không phải việc làm ngay.

## 3. Kết luận về code execution

| Câu hỏi | Anthropic (Haiku 5.5) | xAI (Peto) | OpenAI (Luna) |
| --- | --- | --- | --- |
| Model/đường kết nối | `claude-haiku-5-5` có trong danh sách hỗ trợ (GA, không cần beta header). Repo dùng Messages API với khóa máy chủ (`claude.py:196`), đúng đường. Quyền của workspace/khóa chưa thử. | Ví dụ dùng `grok-4.7` với **API key**. Peto mặc định `XAI_MODEL=grok-4.7` (giá trị production nằm trong `.env`, chưa đọc), nhưng xác thực bằng **OAuth client của Grok CLI** (`xai_auth.py:44-52`); tài liệu không nói gì về OAuth. Tìm web chạy được qua OAuth chưa chứng minh `code_interpreter` cũng chạy được. | Trang code interpreter không liệt kê `gpt-6-luna`; chưa xác minh. |
| Schema và sự kiện | Tool `{"type":"code_execution_20250825"\|"…20260521","name":"code_execution"}`. Block `server_tool_use` (`bash_code_execution`, `text_editor_code_execution`). Kết quả `bash_code_execution_tool_result` gồm `stdout`, `stderr`, `return_code` và `content` chứa `file_id`. Kết quả về nguyên khối trong `content_block_start`. Có thể gặp `pause_turn`. Phản hồi có `container{id, expires_at}`. | Responses `{"type":"code_interpreter"}`, output item `code_interpreter_call`, tính tiền theo `server_side_tool_usage`. Tên sự kiện stream và các trường không có trong tài liệu. | `code_interpreter`, file ra qua `container_file_citation`. |
| Tệp vào/ra | Files API GA; `container_upload` theo `file_id`. Tệp tải lên không tải về được; tệp tạo ra tải về được. Chỉ lấy được tệp ở cấp đầu `$OUTPUT_DIR`. Tối đa 500 MB/tệp. Tệp còn cho tới khi xóa hoặc hết `expires_in_seconds` (3.600–7.776.000). **Phạm vi là cả workspace**: không được nhận `file_id` từ client, nên tách workspace riêng. ZDR: không đủ điều kiện. | Files API `POST /v1/files`, `input_file`/`file_id`, 512 MB; không ghi thời hạn lưu. Gắn tệp tự kích hoạt `attachment_search`. Trang code execution ghi "file I/O hạn chế"; **không có hợp đồng tệp đầu ra.** | Container files; container hết hạn sau 20 phút không dùng. |
| Trạng thái | Mỗi request một container mới nếu không truyền `container`. Checkpoint sau khoảng 5 phút rảnh, hết hạn sau 30 ngày. Giữ REPL từ bản `20260120`. | Không giữ trạng thái giữa các request. | Container "auto" dùng lại trong hội thoại. |
| Chi phí và giới hạn | Tính theo thời gian chạy, **tối thiểu 5 phút**. Mỗi tổ chức có 1.550 giờ miễn phí/tháng, sau đó $0,05/giờ/container. Request có tệp thì tính cả khi không gọi tool. Miễn phí khi cùng request có `web_search_20260209`/`web_fetch_20260209` trở lên; Peto đang dùng `20250305`/`20250910` nên không được miễn. Giới hạn: 5 GiB RAM, 5 GiB đĩa, 1 CPU, không có internet. Usage ở `usage.server_tool_use.code_execution_requests`. | $5 cho 1.000 lượt gọi cộng token (theo bảng giá). Lưu tệp $0,025/GiB/ngày. **Tính tiền khi dùng OAuth/gói thuê bao: không có tài liệu**; trang Quản trị cũng để Grok "chưa có giá". Không có số liệu timeout. | Theo bảng giá built-in tools; chưa đọc số. |

**Khoảng trống trong adapter hiện tại** (cần sửa nếu thí điểm):
- `native_tools` không ánh xạ code execution.
- `NATIVE_BLOCK_TYPES` thiếu các block mới (`claude.py:26`). Vì vậy `build_messages` sẽ không phát lại nhóm block gốc
  (`89-99`), và `_portable_output` bỏ chúng: sang vòng sau của cùng lượt, kết quả chạy mã biến mất. `container` cũng chưa
  được truyền tiếp khi `pause_turn` hay giữa các vòng function call.
- Với xAI, `observe_item` bỏ qua item lạ, và các item output được gửi lại khi `store:false` (`xai.py:284`, `495`). Chưa
  biết xAI có nhận `code_interpreter_call` làm input hay không.
- Lịch sử chỉ lưu chữ, nên stdout cũng mất sau lượt.
- Phải giữ cách xử lý chữ ký thinking của Haiku và điểm cache hiện có.

**Áp vào Peto:**
- Container gắn với `request_id` của lượt: dùng chung giữa các vòng và `pause_turn`, không dùng lại giữa các lượt hay
  thiết bị.
- Stop đóng stream, nhưng tài liệu không nói việc chạy phía server có dừng không, nên coi như vẫn có thể bị tính tối
  thiểu 5 phút. Retry là lần thử mới với container mới. Hai chat song song dùng container riêng.
- Tệp ra phải tải về ngay trong lượt, lưu vào kho artifact của Peto theo owner/hội thoại/tin, rồi
  `DELETE /v1/files/{id}`. Model dẫn ID artifact của Peto, không dẫn link của nhà cung cấp. Tải lỗi thì không báo thành công.
- Stdout là bằng chứng trong nhật ký "Đang làm", không phải thẻ nguồn.
- Model không hỗ trợ: manifest ghi `run_code` ở trạng thái `unavailable` kèm lý do. Peto tự tính và ghi rõ "chưa chạy
  để kiểm"; không tự đổi model và không gọi thêm lượt trả phí.

**Kết luận:**
- Haiku: khả thi trên giấy tờ (model, đường API, tệp, sự kiện và giá đều có tài liệu). Trước khi làm cần quyết định về
  quyền riêng tư (tệp người dùng nằm ở Anthropic tới 30 ngày, không có ZDR, workspace dùng chung) và một phép thử thật.
- Peto/xAI: chưa đủ bằng chứng. Còn thiếu OAuth, tên sự kiện và cách tính tiền theo gói. Kể cả chạy được, tài liệu chỉ
  cho thấy stdout, không có tệp đầu ra.
- Luna: chưa xác minh, để sau.

**Phép thử trả phí đề xuất** (chưa chạy; chủ web quyết định). Chạy bằng script riêng ngoài runtime, kết quả ghi vào
`.runtime/`, không ghi key hay nội dung riêng:
- **A — Haiku.** Một request stream, `code_execution_20260521`, CSV giả 20 dòng gửi thẳng trong tin, nhờ tính trung bình
  và ghi `chart.png` vào `$OUTPUT_DIR`. Giới hạn effort low, `max_tokens` 2048, tối đa một lần tiếp `pause_turn`. Ghi lại
  loại block/sự kiện, `usage.server_tool_use`, `container`. Tải tệp, xóa tệp, kiểm list. Chi phí: token Haiku cộng tối
  thiểu 5 phút chạy, nằm trong 1.550 giờ miễn phí nếu tổ chức chưa dùng hết (vượt thì khoảng $0,004).
- **B — xAI qua OAuth hiện tại.** Một request Responses `store:false` với `{"type":"code_interpreter"}` và dữ liệu
  gửi thẳng; ghi mọi loại sự kiện và item, `server_side_tool_usage`. Request thứ hai gửi lại các item đó làm input
  để xem xAI có nhận không. Chi phí: theo API key là $0,005/lượt cộng token; theo OAuth thì chưa rõ.

## 4. Kế hoạch từng phần

| Phần | Nội dung | Nghiệm thu | Rollback |
| --- | --- | --- | --- |
| 0 | Báo cáo này | Chủ web đọc và chọn | — |
| 1 (P1) | Khối log có điều kiện, mô tả `search_attachment`, (tùy chọn) `ROOT_SIGNAL`; fixture crash log giả; 2–3 ca eval có tệp đính kèm | Test định tuyến prompt (có log thì có khối; Companion/không tệp thì không), fixture phần đọc sẵn giữ `Caused by` cuối và dòng mixin, test công cụ tìm; harness eval mock đạt. Eval thật chỉ khi duyệt `--allow-paid` | Revert commit; không migration; cache cũ không đổi |
| 2 (P2) | `check` trong kết quả `create_document`/`create_presentation` | `test_document_artifacts`, `test_presentations`, `test_document_themes`; giới hạn kích thước; không lộ đường dẫn | Revert; artifact đã lưu không đổi |
| 3a | Phép thử A/B | Biên bản dạng block/sự kiện, usage, chi phí thực | Không có thay đổi runtime |
| 3b | Thí điểm Haiku sau tắt-mở `PETO_CLAUDE_CODE_EXECUTION=false` mặc định: capability `run_code`, ánh xạ tool/block, container theo lượt, bước nhật ký, lưu tệp ra thành artifact, dọn Files API, ghi usage và chi phí | SDK/HTTP giả cho thành công, `return_code≠0`, `execution_time_exceeded`, thiếu usage, tải tệp lỗi, Stop/retry, owner khác; chữ ký thinking Haiku không vỡ; UI với API giả; một lượt thật của chủ web | Tắt cờ; lưu trữ chỉ thêm, không phá dữ liệu cũ |
| 3c | xAI/Luna | Chỉ khi phép thử B (hoặc một phép thử Luna) đạt | — |

Để sau, chỉ làm khi có nhu cầu cụ thể: bảng/biểu đồ tương tác theo schema hữu hạn, tool discovery, X Search, kết nối
Drive/mail/lịch. Có một ghi chú riêng: Anthropic `web_search_20260209+` có lọc động (tự dùng code execution, miễn phí
phần chạy mã), nhưng đổi phiên bản sẽ đổi hành vi và cách tính phí tìm web của Haiku, nên là quyết định riêng.

## 4b. P1 đã làm (21/10/2026, chủ web duyệt; chưa commit/deploy)

- `prompts/chat.py` có `LOG_PROMPT` tiếng Anh, khoảng 1.900 ký tự. `prompt_context.has_text_files` chỉ xét tệp đã lưu
  của hội thoại: `kind='file'` và MIME nằm trong `TEXT_MIMES` (log, txt, code, csv, md…), không xét lời người dùng.
  Tài liệu Peto tự tạo, PDF, Word, Excel và ảnh không tính. `service.py` lấy `file_index` trước khi dựng prompt rồi
  truyền `text_files`. Khối chỉ có ở Chat, không có ở Companion, và đứng trước hồ sơ/trí nhớ nên không phá tiền tố
  cache khi hội thoại còn tệp chữ. Lượt tiếp theo trong cùng hội thoại vẫn kèm khối này.
- Mô tả `search_attachment` có thêm ví dụ tìm chuỗi nguyên nhân (`Caused by | Description: | Exception | FATAL`).
- `ROOT_SIGNAL` thêm `mixin apply` và `(?:mixin|injection)\w*(?:error|exception)`. Phép thử với log modpack giả:
  khi có 100–400 lỗi texture/recipe khác dạng đứng trước, dòng `Mixin apply for mod … failed` (dòng duy nhất nêu tên
  mod) bị loại khỏi phần đọc sẵn ở giới hạn 20.000 và 80.000 ký tự. Sau khi thêm mẫu thì giữ được. Không đổi
  `TEXT_FORMAT`: phần đọc sẵn đã lưu của tệp cũ giữ nguyên, chỉ tệp gửi mới theo cách chọn mới.
- Kiểm thử: `tests/test_log_workflow.py` (6 ca) gồm log giả, kiểm mẫu không bắt nhầm tên tệp cấu hình hay cảnh báo
  khác, quy tắc chọn khối, lượt chat thật qua API với provider giả (có tệp chữ thì kèm khối, cả ở lượt sau; hội thoại
  không có tệp thì không), tìm/đọc theo đúng số dòng. Đã kiểm ca phần đọc sẵn thất bại với mẫu cũ. Nhóm liên quan
  264 đạt; toàn bộ backend 1.578 đạt, 1 bỏ qua (348,63 giây); `git diff --check` đạt.
- Eval: `evals/chat-log-cases.json` có 3 tình huống (mod gây lỗi theo bằng chứng, đoạn stack thiếu, chỉ dẫn trong log).
  Bộ dựng prompt eval nhận `text_files` giống app. Đã chạy mock với Peto/Luna/Haiku, 9 lượt, đủ lượt, prompt có khối
  log. Mock trả câu mẫu nên trượt các phép `match` là bình thường; chưa chạy LIVE.
- Giới hạn: khối hướng dẫn không bảo đảm model hết tự tin quá mức; điều đó cần eval LIVE hoặc thử thật. Log dán thẳng
  vào ô chat (không đính kèm) và log nằm trong PDF/Word không kích hoạt khối này.

## 4c. P2 đã làm (21/10/2026, sau khi P1 được deploy; chưa commit)

- `features/documents/readback.py` dựng trường `check` từ chính nội dung đã render:
  - Tài liệu: tên in ở đầu (sau `body_blocks`, nên đề mục trùng tên không tính là chương), đề mục cấp 1–2 (tối đa 20,
    mỗi đề mục 60 ký tự, kèm `headings_omitted`), số chữ đếm theo khoảng trắng như Word, số bảng, công thức (trong
    dòng, trong ô và dòng riêng), ảnh, khung ảnh, mục lục, số trang. Khi có khối bìa thì kèm `cover.blank`: các dòng in
    chấm vì thiếu (trường, khoa, giảng viên, thành viên).
  - Slide: từng slide `[số, bố cục, tiêu đề ≤ 40 ký tự]`, `without_notes`, số ảnh, bảng, biểu đồ.
  - Cả hai dưới 2.000 ký tự ở trường hợp lớn nhất (đã có test).
- `create_document` và `create_presentation` trả thêm `check` và câu dặn đối chiếu với yêu cầu, nói rõ phần thiếu,
  nhắc điền dòng bìa còn trống. Câu dặn slide cũ luôn bảo Peto nói "mỗi slide có ghi chú", kể cả khi có slide trống ghi
  chú; giờ câu dặn nêu đúng slide chưa có ghi chú. Đọc lại lỗi thì chỉ bỏ `check`, tệp đã dựng vẫn lưu và báo thành công.
  Kết quả lặp lại (cùng tham số trong lượt) vẫn trả đúng kết quả cũ.
- Không đổi UI, lưu trữ, schema công cụ hay prompt hệ thống; `create_spreadsheet` và hai công cụ sửa tệp giữ nguyên vì
  đã trả `results`/`changes`/`notes`.
- Kiểm thử: `tests/test_document_readback.py` (7 ca), gồm cấu trúc, giới hạn kích thước, kết quả công cụ, lỗi đọc lại,
  ghi chú slide và vòng công cụ thật với client giả (model nhận `check` trong `function_call_output`). Nhóm test tài
  liệu 252 đạt; toàn bộ backend 1.585 đạt, 1 bỏ qua (381,64 giây); `git diff --check` đạt.
- Giới hạn: chỉ kiểm cấu trúc, không kiểm nội dung đúng hay sai. Model có thực sự đối chiếu và báo phần thiếu hay không
  cần thử với model thật.

## 5. Mức kiểm chứng

- **Đợt khảo sát này:** chỉ đọc code (có một lệnh Python cục bộ, không gọi mạng, để liệt kê tên tool của Agent) và
  tài liệu. Không chạy test, không gọi model.
- **Mock/unit sau này:** chứng minh cấu trúc, phạm vi, giao thức; không chứng minh chất lượng chẩn đoán.
- **UI với API giả:** chứng minh hiển thị và luồng; không chứng minh nhà cung cấp chấp nhận request.
- **Model thật/production:** chưa có gì cho các đề xuất này. Cần phép thử 3a, eval thật hoặc kiểm tra của chủ web.

## Nguồn

- xAI: [tool usage details](https://docs.x.ai/developers/tools/tool-usage-details),
  [code execution](https://docs.x.ai/developers/tools/code-execution), [files](https://docs.x.ai/developers/files),
  [pricing](https://docs.x.ai/developers/pricing).
- Anthropic: [tool reference](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference),
  [code execution](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool),
  [Files API](https://platform.claude.com/docs/en/build-with-claude/files).
- OpenAI: [tool design](https://developers.openai.com/plugins/plan/tools),
  [code interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter).
