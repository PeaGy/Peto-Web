# Peto Brain Benchmark v1

Công cụ nội bộ so sánh phản hồi Chat, Companion và nhập vai bằng dữ liệu giả. Không đổi model, prompt, routing hoặc
database đang dùng; không có dashboard Web. Bản đầu có **30 tình huống, 37 lượt người dùng**. Một lượt có thể phát sinh
nhiều request nếu Claude yêu cầu tiếp tục; giới hạn tính từng request đó.

## Phạm vi và cách đọc kết quả

- Chat: danh tính trợ lý, trò chuyện, đọc tệp có căn cứ, code, suy luận, trí nhớ và trung thực về khả năng.
- Companion: tính cách, giọng nói tiếng Anh, cảm xúc, ghi chú riêng và tính liên tục giữa các lượt.
- Nhập vai: cách xưng hô, quyền quyết định của người dùng và thoát vai khi được hỏi khả năng thật.
- Agent: tiếp tục dùng [bộ đánh giá CLI hiện có](../../agent-cli/evals/README.md); không gộp điểm Agent với Companion.

Tái sử dụng `ai/models.py`, provider trong `ai/`, cách ghép prompt trong `features/chat/prompt_context.py`, lịch sử tệp
trong `features/chat/history.py` và bộ lọc Companion hiện có. Hồ sơ/trí nhớ được thay bằng fixture trong tiến trình
CLI. Không mở database thật, gọi memory gateway, tạo tiêu đề, chạy ghi nhớ nền, công cụ, tìm web hoặc TTS.
Tệp chỉ có tên/chữ/trạng thái giả; không đọc file người dùng từ đường dẫn.

Đây là bài đo **prompt và hội thoại không có công cụ**, chưa đo toàn bộ Peto Web. Quyền tài khoản, trích/tóm tắt/lưu
trí nhớ, thao tác Web, giọng nói và ảnh cần bài đo riêng. Chat trong app thường cho phép đầu ra dài hơn; v1 giới hạn
128–1024 token mỗi request vì dùng nhánh provider hiện có với `tools_enabled=False`. Mức suy nghĩ cao có thể hết
ngân sách trước khi trả lời. Kết quả chỉ áp dụng cấu hình đã lưu, không đại diện chất lượng tối đa của model.

`mock` chỉ xác nhận công cụ chạy được, **không đánh giá hay xếp hạng model**. Provider mock trả câu mẫu, nên không
đạt nhiều tiêu chí nội dung/cảm xúc là bình thường. LIVE vẫn cần người chấm; regex chỉ kiểm tra dấu hiệu hẹp, không
chứng minh câu trả lời đúng. Chưa thêm LLM-as-judge hoặc tự chọn model production.

## Chạy không cần khóa API

Cài thư viện backend theo `requirements.txt` trong venv hiện có. Chạy từ `backend/`; Windows dùng:

```powershell
../.venv/Scripts/python.exe -X utf8 -m evals list
../.venv/Scripts/python.exe -X utf8 -m evals plan --models peto luna haiku --max-calls 150
../.venv/Scripts/python.exe -X utf8 -m evals run --models peto luna haiku --max-calls 150 --concurrency 3
../.venv/Scripts/python.exe -X utf8 -m pytest tests/test_brain_evals.py
```

Trên VPS/Linux thay `../.venv/Scripts/python.exe -X utf8` bằng `../.venv/bin/python`. Mock bỏ qua `.env` và khóa API
của tiến trình. Không cần khởi động backend hoặc mở trình duyệt. `plan` chỉ in kế hoạch, không gọi API ở cả hai chế độ.

Model và effort lấy trực tiếp từ registry đang cài. V1 nhận các model Web `peto`, `luna`, `haiku`; model chỉ dành cho
Agent bị từ chối. Tên effort phải được mọi model đã chọn hỗ trợ. Muốn so sánh các effort khác nhau, chạy riêng rồi
dùng `compare`. Cùng tên effort giữa hai hãng không có nghĩa cùng lượng tính toán.

## Chạy thật sau khi chủ máy quyết định dùng billing

LIVE đọc `.env` ở gốc repo hoặc biến môi trường của **máy đang chạy lệnh**, giống backend. Cần `OPENAI_API_KEY` cho
Luna, `ANTHROPIC_API_KEY` cho Haiku; Peto dùng `XAI_API_KEY` hoặc token xAI riêng của repo. Thiếu credential thì dừng
trước request đầu tiên. Không gửi khóa trong chat, dataset hoặc tham số lệnh. Nếu môi trường đặt
`PYTHON_DOTENV_DISABLED=1`, `.env` không được đọc, cần cấp biến môi trường hoặc chạy ở shell thông thường.

Ví dụ dưới đây **sẽ gọi API trả phí khi thực thi**, chỉ chọn một bài trước:

```powershell
../.venv/Scripts/python.exe -X utf8 -m evals plan --mode live --models haiku --cases companion-private-game --max-calls 3
../.venv/Scripts/python.exe -X utf8 -m evals run --mode live --allow-paid --models haiku --cases companion-private-game --max-calls 3 --max-output-tokens 512 --timeout 90 --concurrency 1
```

`run` thật luôn cần cả `--mode live --allow-paid`. Không retry SDK, không tự chuyển model hoặc chạy lại lỗi. CI mặc
định chỉ chạy mock/test với HTTP giả. Các giới hạn:

| Tham số | Mặc định | Khoảng nhận |
|---|---:|---:|
| `--repeat` | 1 | 1–5 |
| `--concurrency` | 1 | 1–4 |
| `--timeout` (giây/lượt) | 90 | lớn hơn 0, tối đa 600 |
| `--max-calls` (request toàn lần chạy) | 60 | 1–500 |
| `--max-output-tokens` (mỗi request) | 1024 | 128–1024 |
| `--max-input-chars` (mỗi request) | 60000 | 1000–120000 |

Kế hoạch vượt số request bị từ chối trước khi chạy. Mỗi request SDK kiểm lại số lượt, ký tự payload và token đầu ra,
kể cả request tiếp tục của Claude. Lịch sử tăng qua các lượt cũng được kiểm lại. Timeout/hủy không bảo đảm nhà cung
cấp ngừng tính phí ngay. Đây là giới hạn request/token/ký tự, **không phải trần USD tuyệt đối**. Giá và cách mã hóa
token tùy nhà cung cấp; dùng bài nhỏ để kiểm tra trước. `Ctrl+C` giữ kết quả những lượt đã xong, `finished=false`.

Chọn bài bằng `--cases ID ...`, `--persona chat|companion|roleplay`, `--group identity|conversation|memory|reasoning|truth|protocol`.
Chọn dataset bằng `--dataset PATH`. Mã bài sai hoặc lựa chọn không còn bài nào bị từ chối. Mã thoát: 0 hoàn thành CLI;
LIVE trả 1 nếu có lỗi lượt hoặc phép kiểm tra critical không đạt; 2 lỗi cấu hình; 130 bị người chạy ngắt. Mock trả 0
khi công cụ hoàn thành, không dùng các phép kiểm tra nội dung mock làm tiêu chí chất lượng.

## Tệp đầu ra và chấm thủ công

Mỗi lần chạy có thư mục mới dưới `benchmark-output/` ở gốc repo, đã được Git bỏ qua. `--output PATH` chọn thư mục mới;
nếu đã tồn tại thì không ghi đè.

| Tệp | Nội dung |
|---|---|
| `results.json` | Prompt đầy đủ, hash, cấu hình, câu trả lời raw/hiển thị, từng request và usage |
| `summary.json` | Số liệu theo model/persona/nhóm, độ phủ usage và các tiêu chí đã chấm |
| `report.md` | Bảng kết quả, lỗi, giới hạn và điểm thủ công |
| `review.json` | Phiếu chấm trộn thứ tự, ẩn tên model, có lịch sử và ngữ cảnh giả |

Phiếu chỉ có các lượt hoàn tất. Điền `scores` bằng số nguyên 1–5 hoặc `null` nếu chưa chấm; `comment` ghi lý do.
Không đổi `sample_id`, `case_id`, tiêu chí hoặc `run_id`. Mỗi tiêu chí có mô tả trong `rubric` và thang điểm trong
`scale`; `expectation` nói điều cần kiểm trong tình huống cụ thể. Chấm đúng vai: Chat không bị trừ điểm vì không đóng
vai nhân vật. Ngôn ngữ, sự tự nhiên, chủ động vừa phải, sự dài thừa và disclaimer không cần thiết do người chấm đọc,
không dùng đếm từ để giả lập đánh giá chất lượng. Nên chấm trước khi mở `results.json` để giảm thiên kiến theo hãng.

`reference_private_notes` chỉ chứa ghi chú của **lượt trước trong cuộc hội thoại giả**, giúp đối chiếu trò đoán số.
`response` và `history` vẫn chỉ là nội dung hiển thị sau bộ lọc. Raw ghi chú được giữ riêng trong `results.json` để
model nhận ở lượt sau, giống luồng Companion hiện có. Kết quả là dữ liệu kiểm thử cục bộ, không có endpoint công khai.
Chỉ dùng dữ liệu tự tạo; không chép hội thoại thật/khóa API vào fixture. CLI ẩn khóa môi trường đã biết và không in
body lỗi SDK; điều đó không thay thế việc chọn dữ liệu giả.

```powershell
../.venv/Scripts/python.exe -X utf8 -m evals report ../benchmark-output/TEN-LAN-CHAY --ratings ../benchmark-output/TEN-LAN-CHAY/review.json
../.venv/Scripts/python.exe -X utf8 -m evals compare ../benchmark-output/LAN-A ../benchmark-output/LAN-B --output ../benchmark-output/so-sanh.md
```

`report` giữ nguyên phiếu đã chấm; `compare` dùng `summary.json` hiện có để giữ điểm thủ công/chi phí, kiểm `run_id`.
Không có một điểm “bộ não” tổng: xem lỗi nghiêm trọng riêng, điểm theo tiêu chí và số mẫu đã/chưa chấm. Phiếu ẩn nhãn
model, nhưng giọng trả lời vẫn có thể gợi ý model; chưa phải thí nghiệm mù tuyệt đối.

## Token, cache, độ trễ và giá

Capture bọc lời gọi SDK trên **instance riêng** của provider, không đổi instance của backend. OpenAI/xAI đọc usage
từ sự kiện response cuối; Claude đọc usage gốc của từng message, tránh đếm cache hai lần khi có continuation.
Thiếu số liệu được ghi `null`/“chưa có dữ liệu”, không suy token từ số chữ. Model trả về và slug yêu cầu được lưu
riêng; hãng không báo model thì `actual_model=null`. Mock không có usage API, request_count ở cấp run chỉ là lượt giả.

`first_text_ms` đo mảnh chữ đầu (chưa lọc); `first_visible_ms` đo chữ hiện đầu sau bộ lọc; `elapsed_ms` đo tổng lượt.
Đây là thời gian stream nhìn từ CLI, không phải TTFT mức token nội bộ của nhà cung cấp. Bảng p50/p95 chỉ lấy lượt
hoàn tất; lỗi/timeout/bỏ qua được đếm riêng. `summary.json` giữ số mẫu và độ phủ; từng request giữ cache/suy nghĩ nếu
SDK báo. Đầu ra bị ngắt vẫn có phần đã nhận, nhưng không được tự coi là câu trả lời thành công.

Giá do người chạy cấp bằng `--rates PATH`, USD trên một triệu token. Cấu trúc ví dụ bên dưới **không phải giá thật**:

```json
{
  "slug-model-tu-registry-hoac-sdk": {
    "input": 1,
    "output": 5,
    "cached_input": 0.1,
    "cache_write": 1.25
  }
}
```

Tra giá theo `actual_model`, rồi slug yêu cầu nếu chưa có dòng cho actual. `cache_write` cần khi có token tạo cache;
nếu thiếu usage/cache/đơn giá, chi phí cả nhóm là chưa biết, không ghi phần đã biết như tổng. `priced_calls` và
`usage_reported_calls` cho biết độ phủ. Giá ước tính chỉ tính token, không phải hóa đơn hay ngân sách chặn chi tiêu.
Có thể bổ sung giá sau bằng `report --rates PATH` rồi `compare` lại.

## Thêm bài, model và đối chiếu prompt

`cases.json` có `version=1`, danh sách `cases`. Mỗi bài có `id` duy nhất, `title`, `persona`, `group`, `context`
(profile/memory/summary giả), từ 1–6 `turns`. Mỗi lượt có `user`, `expectation`, `rubric`, `checks` tùy chọn và
`attachments` tùy chọn (`name`, `text`, `status`: ready/partial/missing). Không có đường dẫn file hoặc vai system
tùy ý. Tiêu chí chấm không được gửi cho model; lượt tương lai cũng không vào lịch sử/prompt của lượt hiện tại.

Phép kiểm tra có `kind`, `label`, `critical` và `value` khi cần. Hỗ trợ `match`/`avoid` (regex dấu hiệu hẹp),
`max_chars` khi tình huống cần ngắn; `emotion`/`private_hidden`/`spoken_plain` chỉ dùng cho Companion. Không biến
văn phong đẹp hoặc một từ khóa xuất hiện thành bằng chứng về độ đúng. Bộ fixture nhỏ này cần mở rộng theo lỗi thật
đã khử thông tin người dùng, gồm cả tình huống ngoài bộ bài, trước khi chọn cấu hình production.

Model mới đi qua registry/provider hiện có, không tạo đường gọi API riêng trong benchmark. Dùng model Web; với model
Agent hãy mở rộng bộ CLI. Không truyền prompt thay thế vào benchmark v1: muốn so sánh phiên bản prompt, chạy từ
checkout/commit của phiên bản đó. Lưu `--clock 2026-10-09T00:00:00+00:00` giống nhau để đồng hồ không làm khác hash.

Manifest ghi commit, trạng thái chưa commit, hash dataset/code/prompt, clock và phiên bản SDK. Khi so sánh cần cùng
dataset, persona, prompt, giới hạn, effort và môi trường tương đương. Lặp vài lần để quan sát biến động; 30 bài
không đủ chứng minh model tốt hơn trong mọi việc. Mock/test không chứng minh chất lượng câu trả lời hoặc token tính
phí. Hướng tiếp cận task-specific và đối chiếu điểm máy với người chấm tham khảo
[hướng dẫn đánh giá của OpenAI](https://developers.openai.com/api/docs/guides/evaluation-best-practices);
v1 chạy cục bộ, không dùng dịch vụ Hosted Evals.
