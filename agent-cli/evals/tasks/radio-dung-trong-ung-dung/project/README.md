# Bộ radio mẫu

`python build.py` tạo `radio.bank`; `python -m unittest` kiểm công cụ đóng gói.
`python player.py` là ứng dụng tiêu thụ thật của mẫu này, đọc cả bank và `stations.json`.

Định dạng MUS1: magic 4 byte, số mục uint32 little-endian; mỗi mục gồm tên ASCII 16 byte,
offset uint32 và kích thước uint32. Payload của mỗi mục phải bắt đầu ở bội số 16 và nằm
sau bảng mục. Các byte giữa những vùng là padding 0. Danh sách đài trỏ tới tên mục trong bank.
Không đổi quy tắc bộ đọc để làm tệp sai được chấp nhận.
