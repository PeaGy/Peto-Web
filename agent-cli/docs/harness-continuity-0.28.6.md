# Cải tiến sau bài thêm 5 bài GTA IV — CLI 0.28.6

Thực hiện 17–18/10/2026 theo yêu cầu của chủ dự án. Đây là thay đổi nguồn, chưa commit/deploy hay cập nhật Peto đã
cài. Máy chủ dùng trong bài thử vẫn quảng bá CLI 0.28.5. Ưu tiên CLI; không đổi desktop, không sửa game trong đợt này.

## Những điểm đã sửa

| Vấn đề quan sát được ở bài GTA | Thay đổi | Giới hạn |
| --- | --- | --- |
| Summary chỉ 57/99/234 ký tự hoặc chỉ hứa làm tiếp vẫn thay lịch sử | `continuation.py` yêu cầu sáu mục có nội dung, tối đa 8.000 ký tự; thử lại một lần từ low sang medium nếu sai mẫu | Kiểm định dạng và độ phủ các mục, không chứng minh nội dung model đúng về ngữ nghĩa; retry có tính bước |
| Kết quả lỗi/đường dẫn/kế hoạch dễ bị quên sau nén | Ghim riêng dữ kiện lấy từ tool result: 20 đường dẫn, 10 việc, 6 kết quả lệnh/lỗi gần nhất; giữ mã thoát và output rút gọn | Quan sát quá khứ, cần đọc lại tệp; output vẫn chịu giới hạn của producer. Không phải journal hay bộ nghiệm thu đầy đủ |
| Có thể thay ngữ cảnh trong RAM dù lưu phiên thất bại | Chỉ chấp nhận bàn giao sau khi archive và session đã lưu; save lỗi thì khôi phục items/context_tokens, giữ dấu đọc | Archive dư sau một lần save lỗi có thể còn tồn tại, giúp tra lại; không tự chạy lại công cụ |
| `*.{py,json,md}` trả 0 kết quả | `find_files` và `search_files` dùng chung bộ dịch glob có brace alternatives | Tối đa 64 lựa chọn/8 lần mở rộng; mẫu không hỗ trợ báo lỗi |
| Đọc 40 dòng cuối metadata 12 MB bị chặn vì giới hạn 1 MB; search bỏ tệp mà không báo | Quét UTF-8 theo dòng tới 64 MB, output có giới hạn; search báo lý do bỏ tệp/dòng | Sửa/undo tệp chữ vẫn 1 MB; dòng trên 1 triệu ký tự bị bỏ khỏi search và được báo rõ; giới hạn duyệt thư mục cũ vẫn còn |
| Peto lặp lỗi Python nhiều dòng trong cmd | Thêm khả năng thương lượng `python_exec`, công cụ `run_python`: truyền argv trực tiếp với `shell=False` | Cần deploy server và cập nhật CLI để model thấy tool mới; không tự chuyển đổi chuỗi shell thành Python |

`run_python` dùng chung chính sách quyền, snapshot thay đổi, timeout, output spool, Ctrl+C và kết quả lệnh. Có hiển thị
và replay/export tương ứng. Default dùng Python của Peto; tham số `python` chọn interpreter/venv khác. Mã tối đa
12.000 ký tự, timeout 600 giây. `cmd` nhiều dòng vẫn bị chặn. Eval policy kiểm argv thật, không phân tích lại chuỗi
hiển thị như lệnh shell; benchmark chỉ cho interpreter của chính bộ giám sát. Không thay mặc định allow của 0.28.5.

## Kiểm tra tự động

- Full CLI: **613 qua, 3 lỗi trong 616 case**. Fixture thống kê dùng summary một dòng đã được đổi sang mẫu bàn giao;
  một test mới gọi nhầm API replay được sửa. Test hộp chọn hội thoại còn phụ thuộc thời điểm chạy trong hai phút
  đầu ngày; đã cố định ngày/giờ của fixture để chạy ổn định qua nửa đêm.
- Chạy lại cả bốn module liên quan: **62 qua**, bao gồm cả ba case lỗi trong full run. Như vậy mọi case trong bộ
  616 đã được kiểm tra qua, nhưng không ghi nhận một lượt full duy nhất có 616 pass.
- Rà soát cuối thêm một regression về nén lặp: tail giữ nguyên không được làm bản sao kết quả lệnh đẩy mất lỗi cũ.
  Sau sửa loại trùng, **83 case ngữ cảnh/đọc/tìm/liên quan qua**, gồm case mới này; tổng 617 case CLI đã được phủ.
- Backend API, schema theo khả năng, prompt và wheel/installer: **74 qua**. Schema CLI cũ giữ nguyên; tool mới
  chỉ thêm khi có `python_exec`. Gói nguồn tăng đồng bộ hai số phiên bản thành 0.28.6.
- Test tiến trình thật kiểm Python Unicode/nhiều dòng/dấu nháy/ký tự shell, mã thoát lỗi, cwd, timeout, deny/ask,
  TerminalUI/replay và eval policy. Các bài này không dùng model trả phí.
- `git diff --check` qua. Các test socket/browser chạy với thư mục tạm riêng trong workspace ngoài sandbox test.

Log: `.runtime/peto-0286-cli-tests.txt`, `peto-0286-recheck.txt`, `peto-0286-final-tests.txt`, `peto-0286-backend-tests.txt`.

## Peto thật sau nén và mở lại phiên

Fixture riêng: `.runtime/peto-continuity-20261017/`. Đây là định dạng nhị phân giả **LCPK**, không phải định dạng GTA,
không phải audio thật và không phải đối chứng có độ khó bằng bài GTA. Mục đích là kiểm ranh giới harness:

1. Metadata JSONL **2.300.472 byte**, 12.506 dòng; năm nguồn mới nằm cuối tệp, lẫn một ID cũ trùng.
2. Gói gốc có 20 payload; script lỗi chỉ nối bytes, in `Build finished` và thoát 0, còn consumer độc lập thoát lỗi.
3. Bộ giám sát dựng lịch sử bằng tool result thật trên fixture và ghim điều chỉnh “ID 3 giữ payload gốc”. Các lời
   gọi chuẩn bị được ghi rõ là của bộ giám sát, không nhận là công việc Peto tự làm.
4. Gọi compaction thật rồi đọc lại session từ đĩa; kiểm checkpoint giữ exit code lỗi, kế hoạch đang làm và điều chỉnh
   người dùng. Model tiếp tục sửa builder từ bản bàn giao, không cung cấp đáp án mã cho Peto.
5. Chạy consumer trong fixture và kiểm riêng ngoài fixture: bảng offset/length liên tục, count, CRC, toàn bộ SHA-256
   payload, thứ tự 20 ID cũ, năm ID mới, không trùng ID/thừa bytes, manifest và checksum catalog gốc.

**Kết quả đạt:** 25 bản ghi, 20 payload cũ giữ nguyên, thêm đúng ID 101–105; ID 3 không bị ghi đè; kết quả 7.512 byte.
Peto sửa `append.py`, build và consumer đều thoát 0. Bộ kiểm riêng xác nhận đầu ra, không chỉ tin lời trả lời của model.
Đối chiếu sau chạy còn xác nhận metadata và cả năm nguồn giữ nguyên (`input-audit.json`).

**Chi phí:** 13 bước tính trên máy chủ, gồm một compaction và 12 lượt làm việc. Giai đoạn tiếp tục mất 86,65 giây,
18 tool call, **0 lần duyệt thủ công**. Bốn quyết định quyền trong giai đoạn này do PolicyUI xử lý tự động; thời gian
permission tổng 0,48 giây. Đây là luật riêng cho fixture chạy code trên máy thật; test mặc định allow có kiểm riêng.
Không so trực tiếp tốc độ bài nhỏ này với bài GTA mất hàng giờ.

Bộ giám sát có hai lỗi chuẩn bị được ghi trong `events.jsonl`: ban đầu policy chặn đường dẫn Python tuyệt đối
(chưa gọi model); sau đó một assertion nhầm rằng lần ghi bị từ chối phải được tính là tệp đã hoàn tất. Bản bàn giao
thật vẫn hợp lệ và ghi đúng lần ghi bị từ chối. Đã sửa bộ giám sát rồi tiếp tục chính session đã lưu, không chạy lại
compaction hay sửa đáp án cho Peto. Tổng 13 bước đã bao gồm lượt compaction đó.

## Những điểm chưa được chứng minh hoặc còn cần làm

- Máy chủ 0.28.5 chưa có `python_exec`. Peto vẫn thử Python nhiều dòng sai hai lần và một lệnh PowerShell bị policy
  của bài thi từ chối, rồi tự chuyển sang sửa/chạy script. Đường Python mới đã kiểm bằng tiến trình thật và schema
  giả, **chưa có bằng chứng model thật chọn đúng tool mới**. Cần deploy rồi thử tiếp phần này.
- CLI nhắc kiểm tra lại dù consumer đã qua, khiến Peto tốn thêm hai lượt để tìm cấu hình test. Không sửa bằng cách
  coi mọi exit code 0 hoặc mọi script tên consumer là nghiệm thu. Cần hợp đồng kết quả kiểm chứng/tiêu chí nghiệm thu
  rõ, rồi đo bằng bài khác để tránh chỉnh harness chỉ nhằm qua fixture này.
- Checkpoint hiện có giới hạn và là dữ liệu trong session, chưa thay thế durable inbox/journal, kho artifact có
  trạng thái nghiệm thu, hay tách hoàn toàn Presenter khỏi ToolRuntime/SessionCoordinator.
- Bài thử nén có lịch sử dựng có kiểm soát; không chứng minh mọi phiên dài tự nhiên đều giữ đủ ý. Test malformed
  summary, retry, lỗi lưu và nén nhiều lần dùng model giả để kiểm chính xác từng nhánh.
- Không chạy lại GTA IV. Xác nhận game ở bài trước vẫn chỉ ở mức người dùng đã nghe nhạc cũ và mới; không suy ra
  đã kiểm mọi đài, chế độ chơi hay DLC.

Sau commit/deploy, `/update` lấy CLI 0.28.6. Nên kiểm tiếp `run_python` với model thật trước khi quay lại bài game lớn.
