"""Sửa thẳng tệp Excel (.xlsx, .xlsm) người dùng gửi lên mà giữ nguyên mọi phần khác của tệp.

Không mở rồi lưu lại cả tệp bằng thư viện (openpyxl bỏ kết quả công thức đã lưu, sparkline, định dạng mở rộng và hình
vẽ lạ). Ở đây chỉ viết lại đúng những phần XML bị đổi: các hàng ô được sửa, bảng kiểu ô khi cần kiểu mới, và khi chèn
hoặc xóa hàng/cột thì mọi chỗ trỏ tới ô (công thức, vùng gộp, định dạng có điều kiện, Bảng, biểu đồ, bảng tổng hợp,
ghi chú, hình). Phần còn lại, kể cả macro VBA, chép nguyên từng byte nội dung.

Công thức mới và công thức phụ thuộc ô vừa sửa được tính lại bằng bộ tính của create_spreadsheet (sheets/engine.py);
công thức dùng hàm bộ tính chưa có thì bỏ kết quả cũ và để Excel tính khi mở tệp (fullCalcOnLoad).
"""
