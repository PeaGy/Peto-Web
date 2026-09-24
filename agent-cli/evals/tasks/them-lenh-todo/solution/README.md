# todo-cli

Danh sách việc cần làm trên dòng lệnh, lưu trong một file JSON.

## Dùng

    python todo.py add "Mua sữa"       # thêm việc
    python todo.py list                # xem danh sách
    python todo.py list --chua-xong    # chỉ việc chưa xong
    python todo.py done 1              # đánh dấu việc số 1 đã xong (không có số đó thì báo lỗi, mã thoát 1)

Mặc định lưu vào `todo.json` ở thư mục đang đứng; đổi bằng `--file`, ví dụ `python todo.py --file viec.json list`.

## Chạy test

    python -m unittest
