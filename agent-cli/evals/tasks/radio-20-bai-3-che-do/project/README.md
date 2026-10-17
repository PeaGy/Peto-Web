# Radio Lab

Ứng dụng giả lập đọc radio ngoại tuyến, chỉ dùng thư viện chuẩn Python. Tệp WAV là tín hiệu tổng hợp ngắn,
không phải bài hát thương mại. Đây là bài mô phỏng tích hợp, không phải bản GTA IV thật.

`python build.py` dựng dữ liệu; `python -m unittest discover -s tests -v` kiểm roundtrip của pack.py.
`python player.py --mode base --all` kiểm ứng dụng độc lập. Chế độ còn lại: lost, ballad.
`python player.py --mode lost --station station-06` kiểm một đài (có thể là đài nói chuyện).

Ứng dụng nạp các lớp trong loader.json từ trái sang phải. Đài trùng id ở lớp sau ghi đè đài ở lớp trước.
Đường dẫn audio của mỗi đài thuộc thư mục catalog của lớp đã cung cấp đài đó.
Không có cache cần xóa. Không được sửa loader hoặc chương trình player để né lỗi dữ liệu.

Định dạng RDX2 (little-endian), xem thêm vector nhỏ trong references/:

- Header `<4s7I>` dài 32 byte: magic RDX2, rate, channels, tổng frames, frames mỗi khối, số khối,
  offset tuyệt đối đầu vùng data, CRC32 của toàn bộ PCM signed 16-bit interleaved gốc.
- Ngay sau header: (số khối + 1) bản ghi `<II>` gồm frame đầu và offset tuyệt đối của khối.
  Bản ghi cuối là mốc tổng frames và độ dài tệp chính xác; không chứa audio.
- Đầu data và đầu mỗi khối căn lề 16 byte. Khoảng trống là zero.
- Trong một khối: lưu tất cả mẫu của kênh 0 trước, tiếp đến kênh 1 (nếu có).
  Mỗi mẫu signed 16-bit little-endian. Khối cuối giữ đủ phần dư, không thêm frame âm thanh.
- Mỗi clip có một tệp `.rdx`, clip id là tên tệp không có phần mở rộng.
- Playlist giữ duration_ms = ceil(frames * 1000 / rate). Không tự đổi rate hoặc số kênh.

`player.py` kiểm container rồi thử seek trực tiếp một số vị trí, không gọi pack.py.
Giá trị gain nằm ở cấp đài, không phải cấp bài. Các trường ngoài playlist cần được giữ nguyên.
