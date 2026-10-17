# Giám sát Peto làm bài radio, 17/10/2026

Peto tự hoàn thành bài mô phỏng trong **314,1 giây**, dùng **23 lượt làm việc và một lượt nén ngữ cảnh**,
tổng **24 bước** tính trên máy chủ. Hai phép chấm bắt buộc và một phép phụ đều đạt. Đây là một lần chạy,
không phải tỷ lệ thành công ổn định hoặc bằng chứng giải được lại toàn bộ GTA IV.

## Cách chạy và điều kiện

Theo yêu cầu trực tiếp của chủ tài khoản, dùng máy bài thi đã đăng nhập với máy chủ thật, model `peto`, effort
`medium`, CLI nguồn **0.28.0**. Máy chủ báo CLI 0.28.0 và có `recall`, `wrapup` cùng các khả năng mới.
Không xác minh mã nguồn/prompt đang triển khai trên VPS bằng chỉ số phiên bản đó.

Dùng đúng `Session` và `Tools` của CLI qua bộ thi sẵn có mà CLAUDE.md mô tả. `PolicyUI` duyệt thao tác trên bản
sao theo luật bài thi. Người giám sát xem nhật ký khi chạy; không viết đáp án, sửa dự án hoặc đưa gợi ý cho Peto.
Peto không được thấy thư mục lời giải mẫu và test ẩn qua các công cụ dự án. Không chạy game hoặc đổi bản radio đã cài.

Bài `radio-20-bai-3-che-do`: 20 WAV tổng hợp, 23 đài gồm ba đài nói chuyện, ba chế độ base/lost/ballad.
Mỗi chế độ nạp catalog theo lớp; lớp mở rộng có thể ghi đè đài của lớp gốc. RDX2 dùng bảng seek có mốc cuối,
căn lề 16, PCM tách kênh trong từng khối, khối cuối không được mất mẫu. Phải sửa cả container, duration và playlist,
giữ nguyên nguồn/bộ đọc/loader cùng metadata quảng cáo, tin tức, nhiệm vụ, danh tính và gain của đài.

Giới hạn vòng làm việc 40 lượt, thời gian 1.200 giây. Giới hạn vòng chính không phải trần cứng của toàn bộ bước
bị tính: nén ngữ cảnh, tổng kết và agent con có thể tính thêm. Lượt này thực tế dùng 24 bước, không gọi agent con.

## Kết quả quan sát

| Mục | Kết quả |
|---|---|
| 23 đài ở mỗi chế độ | Đạt; tổng 69 lượt đọc đài |
| Dùng đủ 20 bài, mỗi đài đúng một bài | Đạt ở cả ba chế độ |
| PCM, rate, channels, frames | SHA-256/mẫu khớp WAV nguồn qua bộ đọc độc lập |
| Seek đầu, giữa và cuối | Đạt kiểm tra trong player độc lập |
| Giữ metadata và các tệp cấm sửa | Đạt |
| Build lặp lại | Tệp đầu ra không đổi |
| Bộ chấm ẩn | 4 test qua; không sửa bộ đọc để nới kiểm tra |
| Công cụ | 37 lần, gồm 10 lệnh; không bị từ chối, không lặp y hệt khi chưa có sửa tệp |
| Ngữ cảnh | Nén một lần; archive 50 mục, 100.008 byte, gồm 23 kết quả công cụ |
| Tra lịch sử/agent con | Không gọi read_history hoặc explore |

Peto nhận ra sai khác giữa encoder và consumer, kiểm vector chuẩn, sửa `pack.py` và `build.py`, tự kiểm PCM,
metadata và chạy player cho cả ba chế độ. Sau lần xóa script tạm, nó chạy kiểm tra lại rồi mới dừng.

Trước lượt chạy thật, selftest chứng minh bản lỗi trượt, lời giải mẫu qua. Kiểm thêm hai bản chỉ sửa container
hoặc chỉ sửa playlist: cả hai vẫn trượt ứng dụng, dù test roundtrip công khai đều qua. Hồ sơ kiểm bộ chấm ở
`.runtime/peto-live-eval-20261017/grader-audit/results.json`.

## Điểm harness phát hiện được và bản sửa sau bài thi

Hai lệnh `python -c` nhiều dòng chạy qua cmd đã trả `exit_code=0`, output rỗng, trong khi phần in dữ liệu không
thực hiện. Peto tự kiểm bằng lệnh một dòng rồi chuyển sang script `_inspect.py`, giải quyết được vướng mắc.

Tái hiện riêng bằng một lệnh có dòng sau in `123` rồi thoát lỗi: cmd trả 0 và không in gì; PowerShell in `123`
và trả mã khác 0. Bản ghi `.runtime/peto-live-eval-20261017/cmd-newline-repro.json`. Đây là lỗi thực thi/báo kết quả
đã quan sát được, không phải suy đoán model thiếu năng lực.

CLI **0.28.1** bổ sung chặn cmd nhiều dòng ở cả run_command/start_command, trước xin quyền và chạy tiến trình,
kèm hướng dẫn chọn PowerShell hoặc script. Không tự đổi shell vì sẽ đổi cú pháp và ý nghĩa lệnh đã duyệt.
Kiểm thử bao gồm LF/CRLF/CR, cmd mặc định/tường minh, lệnh thường/nền, và PowerShell thực thi đủ hai dòng.
Bản sửa này được làm **sau** lượt Peto đạt bài; không coi nó là nguyên nhân của kết quả đã ghi.

Trước bài thi còn sửa Recorder để chuyển tiếp `purpose="wrapup"`: nếu chạm trần bước, bộ ghi không còn làm lỗi
lượt tổng kết của CLI. Có test hồi quy riêng; lượt thật này không chạm trần nên không dùng nhánh đó.

59 test về shell/workflow/lệnh nền, 69 test bộ thi và 5 test gói cài qua (tổng 133).
Lần kiểm gói trong môi trường giới hạn bị treo trước thu thập test và được dừng; chạy lại với thư mục tạm riêng
và quyền phù hợp thì cả 5 test qua trong 3,34 giây. Mã 0.28.1 chưa được triển khai hoặc cài vào Peto hằng ngày
trong lượt công việc này.

## Giới hạn kết luận

Bài này cùng loại lỗi tích hợp với radio GTA IV nhưng **dễ hơn việc mod GTA IV thật**: có đặc tả đầy đủ, source
của consumer và vector chuẩn nhỏ; không cần tìm hiểu định dạng thương mại, codec nén, đóng gói archive hoặc hành vi
game. Tệp tổng hợp chỉ dài vài chục mili giây. Không kiểm hiệu năng với bài dài hoặc phát trực tiếp trong game.

Một lần đạt cho thấy Peto có thể tự sửa nhiều lớp và tự kiểm trong điều kiện này. Không đủ kết luận trần năng lực,
độ ổn định, hoặc rằng thay đổi prompt/recall đã cải thiện tỷ lệ đạt: chưa có lượt đối chứng dùng harness cũ trên
cùng bài. Archive thực sự được tạo, nhưng Peto không gọi read_history nên không đo khả năng tự dùng công cụ đó.

## Mở lại và chạy thêm

Kết quả gốc nằm ở `.runtime/peto-live-eval-20261017/results/20261017-091559-peto-medium/`:
`report.md`, `radio-20-bai-3-che-do/result.json`, `transcript.txt`, `diff.patch`, `log.jsonl`.
Bản Peto sửa còn ở `.runtime/peto-live-eval-20261017/work/20261017-091559/radio-20-bai-3-che-do/radio-lab/`.
Bản sao cấu hình đăng nhập tạm được gỡ sau khi chạy; máy bài thi đã đăng nhập trước đó vẫn giữ nguyên.

Từ gốc kho, dùng phiên bài thi mặc định đã đăng nhập:

```powershell
.venv\Scripts\python.exe agent-cli/evals/run.py run radio-20-bai-3-che-do --model peto --effort medium --timeout 1200 --keep
```

Mỗi lượt chạy tiếp vẫn dùng hạn mức thật. Có thể giao Peto một dự án khác bằng cách thêm task/fixture và bộ chấm
vào evals, kiểm selftest trước rồi dùng cùng cách giám sát. Nếu cần can thiệp, ghi riêng lượt có gợi ý để không
đánh đồng với lượt Peto tự làm.
