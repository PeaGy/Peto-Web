# Lỗi terminal khi đọc đầu ra build, 17/10/2026

Ảnh người dùng cung cấp và phiên Peto gần nhất cho cùng nguyên nhân: **TerminalUI.tool_started thiếu nhãn
`read_output`**, gây KeyError trước khi công cụ được thực thi. Đây là lỗi CLI 0.28.0 đang cài trên máy.

## Bằng chứng từ phiên

Yêu cầu: “Code đỏ khá nhiều, bạn sửa giúp tôi chạy lại được nhé. Cố đừng thay đổi logic”.
Phiên `20261017-103459-2fcead`, nhật ký `124001764_NguyenTrieuAn_Api-20261017-103415.jsonl`.
Peto đã đọc mã và chạy chẩn đoán build, chưa gọi công cụ sửa mã nguồn. Đầu ra của lệnh msbuild dài **860 dòng**
được lưu thành `out_cba52bcff9cf`. Model chọn read_output để tìm trong đó, một thao tác phù hợp với output dài.

`tui/view.py` có read_output và read_history trong EXPLORE, nhưng tool_started lấy nhãn từ một dict khác chỉ có
read_file/list_files/search_files/find_files. Truy cập dict bằng tên read_output gây đúng traceback trong ảnh.
read_history cũng có thể gây cùng lỗi; ba test mới (đọc output, tìm trong output, tra lịch sử) đều tái hiện lỗi
trên mã cũ trước khi sửa.

Vòng `_run` chỉ bắt WorkspaceError và KeyboardInterrupt. KeyError thoát ra ngoài, nhưng finally vẫn ghi outcome
mặc định “done” và lưu đè bản tiến độ tốt bằng hội thoại còn một lời gọi thiếu kết quả. Vì vậy cần sửa cả giao diện
lẫn trạng thái phiên, không chỉ đổi nhãn lỗi trên màn hình.

## Bản sửa 0.28.2

- Gộp danh sách công cụ đọc/tìm và hàm dựng nhãn trạng thái vào cùng bảng EXPLORE, đủ cả read_output/read_history.
- Với ngoại lệ bất ngờ trong `_run`, ghi outcome error, lưu interrupted với INTERRUPTED_RESULT cho những lời gọi
  chưa trả về. Giữ traceback để chẩn đoán, không tự phát lại công cụ hoặc báo đã xong.
- Test qua đúng Tools → TerminalUI, cả đọc thường/tìm regex của output và read_history. Kiểm việc lỗi ở lúc bắt đầu
  hoặc kết thúc hiển thị công cụ đều lưu phiên hợp lệ, đánh dấu dang dở và không chạy công cụ tiếp theo.
- Tăng đồng thời phiên bản pyproject và __init__ lên 0.28.2. Gói gồm cả bản sửa cmd nhiều dòng của 0.28.1.

Bài radio trước dùng PolicyUI, nên không đi qua nhánh TerminalUI gây lỗi này. Việc bài đó đạt không chứng minh
toàn bộ giao diện tương tác đã được kiểm. Những test mới bổ sung trực tiếp phần còn thiếu này.

## Khôi phục trên máy người dùng

Hồ sơ tại `.runtime/peto-ui-crash-20261017/`: wheel và checksum, repair-manifest.json, bản sao package 0.28.0 cùng
session gốc, nhật ký cài đặt, repair-result.json và smoke-result.json sau khi thực hiện.
Khôi phục chỉ thêm kết quả “bị ngắt” cho read_output còn thiếu và đặt cờ interrupted; giữ nguyên các mục chat cũ.
Không tự chạy lại build, sửa bài tập, gọi model hoặc thay cấu hình đăng nhập. Có kiểm checksum để không ghi đè
nếu phiên đã bị một tiến trình khác thay đổi trong lúc chuẩn bị sửa.

Sau bản vá, trong thư mục bài tập: mở `peto`, gõ `/resume 1`, rồi yêu cầu “Làm tiếp việc sửa lỗi biên dịch,
giữ nguyên logic”. Những lỗi C# mà Peto đang chẩn đoán vẫn cần được xử lý trong phiên tiếp theo.

Bản vá cục bộ không cập nhật máy chủ hoặc máy khác; cần phát hành nguồn 0.28.2 riêng khi muốn phân phối.

## Kết quả thực hiện trên máy

- 543 test CLI qua trong 236,81 giây; 5 test gói cài qua.
- Đã cài wheel 0.28.2 ngoại tuyến vào Peto đang dùng. Launcher thật trả `peto 0.28.2`.
- Sao lưu trước sửa: `.runtime/peto-ui-crash-20261017/backup-20261017-104907/`.
- Chỉ thêm một kết quả bị ngắt cho lời gọi read_output còn thiếu trong phiên gốc và đặt interrupted=true.
- Smoke test bằng Python/gói đã cài đọc lại đúng output 860 dòng qua Tools/TerminalUI, kiểm đủ cặp lời gọi/kết quả
  và vẽ lại toàn bộ phiên qua TerminalUI.replay; đều qua. Không gọi model.
