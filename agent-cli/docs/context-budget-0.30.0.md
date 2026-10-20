# Context theo model và nâng 6 Sol lên 6.1 Sol — CLI 0.30.0

Ngày 20/10/2026. Chủ dự án yêu cầu đối chiếu OpenCode để cải tiến quản lý context/compact và nâng riêng lựa chọn Sol.
Đây là thay đổi nguồn; không commit, deploy, cập nhật CLI đã cài, sửa game hay chạy benchmark/API trả phí.

## Đối chiếu và phạm vi

Nguồn tham chiếu: OpenCode V2 **2.0.32**, MIT, checkout ngoại tuyến `.runtime/references/opencode`, commit
`22e771f5893e255ea78fc10557ed3fb98d3a1072`. Không chạy script hay cài dependencies của upstream.

| OpenCode | Thích nghi trong Peto |
| --- | --- |
| `schema/src/model.ts`: context/input/output theo provider/model | Server giữ catalog theo mã API thật; `/me` chỉ trả giới hạn của model tài khoản được dùng |
| `core/src/session/compaction.ts`: ceiling theo input/context, chừa 10% hoặc 16k | Backend và CLI có cùng công thức, kèm test hợp đồng; output còn chịu deployment cap |
| `estimatePrompt`: provider usage làm mốc, ước tính nội dung mới | CLI dùng tổng input/output đã chuẩn hóa làm mốc, cộng phần mới và thay đổi hướng dẫn; không cộng cache/reasoning thêm lần nữa |
| `model-request.ts`: chừa chỗ cho output, biên 15% với phần ước tính | Server dựng ngân sách từ instructions + schema tools + items thực tế, giảm max_output_tokens theo chỗ còn lại ước tính |
| `keep=15000`, ranh giới exchange, không tách tool call/result | Peto chọn tail theo token, tối đa khoảng 15k, giảm cho cửa sổ nhỏ, giữ nhóm tool/Claude có chữ ký; single-exchange có thể nén toàn bộ |
| Request quá dài: compact rồi phục hồi một lần | Chỉ mã `context_overflow` trước nội dung mới kích hoạt compact/retry một lần; lỗi sau nội dung không được hoàn bước hay tự phát lại |
| Bản summary quá lớn: thu nhỏ 70%/50%/35% sau provider rejection | Thu nhỏ bản nhìn của summarizer hữu hạn, cắt tool/assistant text có ghi chú; không cắt yêu cầu user hay canonical history |
| Lịch sử đầy đủ độc lập context gửi model | Giữ journal/JSON/archive hiện có và sáu mục bàn giao/TaskState của Peto |
| Native provider checkpoints tùy cấu hình | Đợt này vẫn dùng summary chữ; không bổ sung endpoint native compact hay checkpoint mã hóa |

Peto dùng ước tính UTF-8 bytes/4 thay vì chars/4 của checkout OpenCode, cộng 15% cho phần chưa đo. Đây là heuristic,
không phải tokenizer đúng của từng model; ảnh dùng ước tính cố định, opaque reasoning không giả làm văn bản. Sau
resume, chưa có mốc usage phù hợp thì ước tính lại; sau response mới dùng usage. Việc định dạng/truncate của adapter
provider có thể khác ước tính. Phục hồi overflow là cần thiết, không tuyên bố trước request nào cũng vừa tuyệt đối.

## Luồng và tương thích

`context_budget` được thương lượng qua `/me agent_features` và `context.features`. CLI cũ không khai báo thì giữ
payload, giới hạn output và lỗi cũ. CLI mới gặp máy chủ cũ vẫn dùng 180 mục/200.000 ký tự và tail 24 mục.
Không đổi schema hay thứ tự tools của các bộ feature đã phát hành.

Khi khai báo feature mới, `meta.context_budget` có danh tính model, context/input/output deployment limits,
ceiling, overhead/request estimate, output đã fit, số mục/dung lượng truyền và mục tiêu giữ tail. Không có API key,
raw credential hay quyền thực thi. Usage mốc chỉ tin event của request đang chạy, không nhận từ AGENTS.md/history.
Đổi model, reset, resume, hoặc compact thành công thì bỏ mốc usage. Identity đổi cùng alias cũng bỏ mốc.

Giới hạn giao thức vẫn là **300 items**, request theo `AGENT_MAX_REQUEST_BYTES` (mặc định 16 MB). CLI chủ động compact
ở 240 items hoặc 80% giới hạn byte, tách khỏi % ngân sách token trong footer. Vì vậy model cửa sổ lớn vẫn có thể
compact sớm khi có nhiều mục nhỏ. Sau compact chưa vừa giới hạn mục thì dừng trước bước tiếp theo.

Máy chủ chặn request vượt ngân sách ước tính trước khi gọi AI, hoặc phân loại lỗi context thật từ provider. Lượt chưa
có nội dung được hoàn bước theo cơ chế cũ; chỉ sau hoàn mới gửi mã phục hồi cho CLI. Nếu đã có delta/thinking/search,
không gắn mã cho phép phục hồi tự động. Retry có logical/physical request journal đầy đủ; không chạy lại tools cũ.

Compact vượt giới hạn chuyển transcript sang chữ, ghi rõ tool/assistant text đã cắt và có `read_history` để tra.
Trước khi retry tính kích thước mới từ request thực sự bị từ chối, không từ toàn bộ cửa sổ. Không tự bỏ user request
để làm vừa. Nếu user requests hoặc phần cố định quá lớn, hoặc ba mức thu gọn vẫn bị từ chối, giữ lịch sử và báo dừng.
Lỗi lưu vẫn giữ nguyên items/context/read state. Không thay đổi chính sách permission hay cô lập thực thi.

## Catalog và nguồn chính thức

Đã tra cứu ngày 20/10/2026:

| Mã API | Context | Max output của model | Output deployment Peto mặc định |
| --- | ---: | ---: | ---: |
| grok-4.7 | 500.000 | Không có trần text riêng được công bố | 8.192 |
| gpt-6-luna | 1.050.000 | 128.000 | 16.000 |
| gpt-5.6-terra | 1.050.000 | 128.000 | 16.000 |
| gpt-6.1-sol | 1.050.000 | 128.000 | 16.000 |
| claude-haiku-5-5 | 1.000.000 | 128.000 | 128.000 trong Agent |
| claude-sonnet-5-5 | 1.000.000 | 128.000 | 128.000 trong Agent |

Nguồn: [Grok 4.7](https://docs.x.ai/developers/grok-4-7),
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[Claude context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows).

Không có giới hạn input riêng được áp ở các mặc định này: dùng context làm cửa sổ đầu vào rồi chừa reserve.
Giới hạn deployment output đang có giữ nguyên, không tự nâng lên max output của nhà cung cấp. Mặc định ceiling
ước tính: Grok 450k, ba model GPT 945k, Claude 900k. Output thực gửi có thể giảm thêm theo room ước tính.
Những giá trị này không chứng minh account/deployment thực đã được cấp quyền model hay giới hạn đó.

`PETO_AGENT_CONTEXT_LIMITS` cho phép admin ánh xạ mã API tùy chỉnh sang context/input/output. Slug không biết dùng
ngân sách ứng dụng 200k, `known=false`. Không đoán model khác từ tiền tố thương hiệu. Catalog cần cập nhật khi nhà
cung cấp thay giới hạn; không gọi mạng để dò model mỗi lượt. Context không phải hạn mức bước tài khoản.

## Nâng Sol

Khóa lựa chọn **`sol` giữ nguyên**, label **6.1 Sol**, API ID **`gpt-6.1-sol`**. Giữ quyền owner-only, Agent-only,
step_cost=4 và các mức effort/giá bước đã được chủ dự án chốt. Không đổi Luna, Terra, Peto, Claude, provider keys,
prompt, endpoint Responses hay tier router. BYOK với mã model do người dùng tự chọn và báo cáo lịch sử không bị đổi.

6.1 Sol không hỗ trợ `none`/`minimal`; chỉ low/medium/high/xhigh/max. Server từ chối `none` trước khi tính bước;
CLI đọc supported efforts và chọn lại mức hợp lệ với cấu hình lưu cũ. GPTProvider cũng khai đúng capability.
Nguồn: [Model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[migration guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol).

Session/journal/JSON lưu thêm `model_identity` để phân biệt API model thật khi alias vẫn là sol. Resume có identity
khác hoặc phiên cũ chưa có identity thì dựng portable history, bỏ opaque reasoning/ID phụ thuộc model, giữ tin và
tool/result. Cùng identity thì giữ reasoning. Không tự chạy tiếp tác vụ khi resume. Journal/JSON schema version không
đổi vì trường metadata mới là tùy chọn. Nên cập nhật CLI sau khi deploy để phiên Sol cũ được chuyển đúng.

## Kiểm chứng

Test dùng tài khoản, provider, database và fixture giả; không gọi model trả phí và không đánh giá chất lượng suy luận.
Các tình huống mới gồm: cùng history trên model nhỏ/lớn, đổi model, usage/cache/reasoning không đếm đôi, guidance
thay đổi, byte/item limit riêng, metadata sai, signed tool group, archive nguyên vẹn khi thu nhỏ, context recovery
một lần, lỗi sau partial output, output budget và model identity của phiên Sol cũ.

- **Full CLI cuối: 673 pass**, 237,41 giây, gồm Ctrl+C và mọi test journal/history/permission/tool/UI trước đó.
  Lượt đầu có 667 pass và hai lỗi: fixture dùng tên `/model 6 sol` cũ, và kiểm thời gian Ctrl+C vượt 2 giây trong
  lượt chạy chung. Đã cập nhật fixture sang tên mới; không nới ngưỡng Ctrl+C hay sửa đường hủy lệnh. Lượt cuối qua.
- Sau điều chỉnh cuối phép đếm tính cả tên trường JSON, **17 test ngân sách CLI qua**; phép tính server/client có
  test đối chiếu trên Unicode, ảnh và opaque reasoning. Full CLI được khởi chạy trước điều chỉnh nhỏ này, vì vậy
  không mô tả nó là một lần full chạy trên từng byte cuối cùng của code; đường tính cuối đã được kiểm riêng.
- **Full backend: 1412 pass, 1 skip, 1 lỗi fixture**. Test mới đã giả định tài khoản luôn bắt đầu từ 0 bước, trong
  khi full suite có bước từ test trước. Đổi sang so sánh số dư trước/sau; không sửa logic hoàn bước để làm test qua.
- Chạy lại toàn bộ module liên quan API/budget/models/prompt/schema/installer: **140 pass**; mọi case lỗi của full
  backend được kiểm qua. Không chạy lại toàn bộ backend một lần nữa, không báo có một lượt full backend xanh.
- Kiểm cuối **7 test backend budget qua**, gồm số dư khi từ chối trước AI, không hoàn/thử lại khi đã có nội dung,
  route thật tới client giả `gpt-6.1-sol` và truyền max_output_tokens đã fit xuống provider.
- Changed Python modules compile; `git diff --check` qua. Không thêm dependency, không chạy frontend build vì
  không đổi frontend. Tất cả test model/provider dùng mock; chưa chứng minh quyền truy cập 6.1 Sol của billing account thật.

Log: `.runtime/peto-0300-cli-full.txt`, `peto-0300-cli-final.txt`, `peto-0300-budget-final.txt`,
`peto-0300-counting-tests.txt`, `peto-0300-backend-full.txt`, `peto-0300-api-final.txt`, `peto-0300-sol-final.txt`.
Sau commit/deploy cần `/update` CLI để bật context_budget và migration session theo model_identity.
