# Nhân vật Companion

Bản đầu: Hiyori Momose chính thức, PixiJS 6 + pixi-live2d-display/Cubism 4.
Không nạp renderer khi chưa mở Companion, tháo renderer khi rời tab, dừng ticker khi trang bị ẩn.
Giới hạn 30 FPS và độ phân giải 1,5 lần để giảm tải điện thoại. Không hỗ trợ import model tùy ý ở bản này.

`src/characterConfig.ts` giữ đường dẫn model và tên tham số miệng. Có thể thay bằng model riêng
đã có quyền sử dụng mà không thay hệ thống chat/TTS. Tài nguyên được phục vụ từ chính Peto,
không gọi CDN hoặc AIRI khi người dùng mở trang.

Model tải nguyên trạng từ Live2D/CubismWebSamples, revision
`b1de66b0b1f1cb881d95fb6158622aeb6a2827bd`, thư mục Samples/Resources/Hiyori.
Core tải từ https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js,
giữ nguyên header giấy phép. Hash file có trong `public/characters/assets-manifest.json`.

Hiyori không thuộc MIT của AIRI. Không sửa thiết kế; giữ thông báo ghi công và liên kết giấy phép
ở `public/characters/NOTICE.html`. Điều kiện SDK và model áp dụng riêng. Bản phát triển hiện tại
dùng model mẫu cố định; nếu sau này thêm nhập model của người dùng hoặc phát hành thương mại,
cần đối chiếu điều khoản SDK hiện hành, đặc biệt mục Expandable Applications:
https://www.live2d.com/en/sdk/license/ .

Đồng bộ miệng: `voiceActivity.ts` đọc độ lớn từng cửa sổ 20 ms của WAV PCM16 do máy tạo giọng trả về,
tra mức mở miệng theo `HTMLAudioElement.currentTime`. Không dùng thời gian nhận request hay timer
giả, không thay đường phát âm thanh. Tạm dừng, kết thúc, hủy và khoảng lặng trả miệng về đóng.
Đây là mở miệng theo cường độ, chưa phân loại nguyên âm như wLipSync của AIRI.
WAV không hỗ trợ vẫn phát bình thường, chỉ không điều khiển miệng.

Tương tác: cuộn chuột hoặc chụm hai ngón để phóng quanh chỗ đang chỉ, giữ chuột giữa (hoặc một ngón tay)
kéo để dời, bấm đúp để về cỡ
vừa khung; góc nhìn lưu ở `peto-character-view`. Khi được cử động, nhân vật chạy motion nhóm Idle,
thở, chớp mắt và nhìn theo con trỏ trên cả trang. Trên máy tính, chạm màn hình dùng để kéo nên không
tính. Trên điện thoại (dưới 720px) khung khóa cứng, không phóng hay kéo, và ngón tay đang giữ trên màn
hình đóng vai con trỏ.
Phần tính toán nằm ở `src/characterView.ts`. `headHeight` trong `characterConfig.ts` là vị trí đầu
tính từ chân lên theo chiều cao model; thay model có tỉ lệ khác thì chỉnh lại số này.

Không hỗ trợ WebGL hoặc tải model lỗi: dùng ảnh đại diện dự phòng, chat và giọng vẫn hoạt động.
Cử động do người dùng chọn ở Cài đặt → Giao diện → Nhân vật cử động, lưu ở `peto-character-motion`.
"Theo máy" (mặc định) tôn trọng giảm chuyển động: nhân vật đứng yên, miệng vẫn theo âm thanh.
"Luôn cử động" bỏ qua cài đặt đó. Windows tắt Animation effects được trình duyệt báo là giảm chuyển động.

Sau khi cập nhật VPS: `npm ci` và `npm run build` trong frontend như thường lệ.
Model và Core đi kèm thư mục public (~5 MB); không cần cài model AI hay đổi relay.

Dependency `gh-pages` đi kèm pixi-live2d-display 0.4.0 là công cụ xuất bản không dùng trong ứng dụng.
Override lên bản 6 để tránh lỗ hổng prototype pollution của bản 4; không chạy script xuất bản này.

Kiểm thử bản đầu: 110 kiểm thử frontend đạt, build thành công; kiểm tra giao diện desktop
và viewport điện thoại 390 × 844, phát/dừng WAV thử nghiệm và tháo canvas khi rời Companion.
Kiểm tra âm thanh dùng WAV tổng hợp trong máy phát triển, chưa thử lại giọng Qwen thật trên VPS
với phần nhân vật này. `local-tts/speak_server.py` hiện trả WAV PCM16 đúng định dạng được hỗ trợ.
