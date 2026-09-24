# save-tool

Công cụ nhỏ đọc và sửa file save của game (định dạng SAV1).

## Định dạng SAV1

| Phần | Kích thước | Nội dung |
|---|---|---|
| magic | 4 byte | `SAV1` |
| độ dài | 4 byte, little-endian | số byte của phần dữ liệu |
| dữ liệu | N byte | JSON UTF-8 |
| checksum | 4 byte, little-endian | xem dưới |

Checksum = (tổng mọi byte của magic + độ dài + dữ liệu) mod 2^32, rồi XOR với `0x5A5A5A5A`.

## Dùng

    python -m savetool show game.sav
    python -m savetool set-gold game.sav 9999

## Chạy test

    python -m unittest
