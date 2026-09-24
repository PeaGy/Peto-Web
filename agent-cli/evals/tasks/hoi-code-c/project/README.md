# sas-net

Đồng bộ file save lên máy chủ bảng xếp hạng. Viết bằng C, build bằng `make` (gcc) hoặc `build.bat` (MSVC).

    sas-net sync game.sav                   # gửi save, nhận lại hạng hiện tại
    sas-net upload game.sav --timeout 20    # chỉ tải lên, đặt thời gian chờ (giây)

Cấu trúc:

- `include/config.h`: địa chỉ máy chủ và các giá trị mặc định.
- `src/http.c`: gửi request HTTP.
- `src/net.c`: socket, TLS, thời gian chờ.
- `src/sync.c`: đóng gói save và đọc kết quả.
- `src/main.c`: đọc tham số dòng lệnh.
