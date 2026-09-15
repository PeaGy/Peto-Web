# Nhân vật Companion

Bản đầu: Hiyori Momose chính thức, PixiJS 6 + pixi-live2d-display/Cubism 4.
Không nạp renderer khi chưa mở Companion, tháo renderer khi rời tab, dừng ticker khi trang bị ẩn.
Giới hạn 30 FPS và độ phân giải 1,5 lần để giảm tải điện thoại.

## Thư viện nhân vật

Mở nút **Nhân vật** trên sân khấu Companion, hoặc **Cài đặt → Giao diện → Chọn nhân vật**.
Nút **Thêm model** hỗ trợ:

- Live2D: ZIP hoặc toàn bộ thư mục chứa đúng một `.model3.json`, `.moc3`, texture và các tệp motion/pose liên quan.
- VRM: một tệp `.vrm` tự chứa texture và buffer; dùng Three.js + `@pixiv/three-vrm` để hiển thị VRM 0/1.

Thư viện có chọn, đổi tên, xóa và ảnh xem trước tạo sau lần hiển thị đầu. Hiyori đi kèm luôn được giữ
để quay về khi xóa model đang dùng. Xóa chỉ bỏ bản lưu trong trình duyệt, không đụng tệp gốc trên máy.
Thay nhân vật không đổi hai giọng TTS, nội dung trò chuyện hay relay.

Model lưu trong IndexedDB `peto-characters` của **trình duyệt và địa chỉ web hiện tại**. Lựa chọn lưu ở
`peto-selected-character`. Đây là tùy chọn thiết bị, dùng chung giữa các tài khoản Peto trên cùng hồ sơ
trình duyệt; chưa đồng bộ tài khoản/VPS. Máy hoặc trình duyệt khác cần nhập lại. Xóa dữ liệu trang web,
hoặc trình duyệt thu hồi bộ nhớ, có thể làm mất thư viện; giữ tệp gốc để nhập lại.

Tối đa 20 model riêng, 80 MB/lần nhập, 512 tệp; ZIP giải nén tối đa 160 MB, 64 MB/tệp. Giới hạn kiểm tra
cả số byte thực sau giải nén. Peto kiểm tra entry, moc header, JSON, tham chiếu thiếu và đường dẫn thoát gói;
không chạy script hoặc tải tài nguyên mạng do model cung cấp. Bỏ âm thanh đi kèm motion để không chồng lên TTS.
VRM phải là GLB có phần mở rộng VRM và tài nguyên nhúng. Thư viện không tải model của người dùng lên VPS.

VRM có tư thế nghỉ, chớp mắt, nhìn theo con trỏ và biểu cảm miệng `aa` theo WAV đang phát. Model cần có
các biểu cảm tương ứng. Tư thế tay được tính theo hướng xương thực trong `src/vrmPose.ts`, tránh xoay
ngược thành chữ V trên VRM 0 khi áp dụng góc dành cho VRM 1. Không cần nhập lại model sau bản sửa.
Trên máy tính: cuộn để phóng, chuột giữa để dời, chuột phải để xoay, bấm đúp để
về khung ban đầu. Bản đầu chưa nhập animation VRMA hay lưu góc nhìn VRM. Live2D giữ góc nhìn riêng theo
ID model, dùng nhóm `LipSync` nếu có, nếu không thì thử `ParamMouthOpenY`.

Phần quản lý tham khảo AIRI, viết riêng cho React:
https://github.com/moeru-ai/airi/blob/main/packages/stage-ui/src/stores/display-models.ts
và https://github.com/moeru-ai/airi/tree/main/packages/stage-ui/src/components/scenarios/dialogs/model-selector .
API VRM: https://github.com/pixiv/three-vrm/tree/dev/packages/three-vrm .

`src/characterConfig.ts` giữ cấu hình model mặc định. Model riêng nhập qua thư viện được đọc từ
bộ nhớ trình duyệt mà không thay hệ thống chat/TTS. Tài nguyên đi kèm được phục vụ từ chính Peto,
không gọi CDN hoặc AIRI khi người dùng mở trang.

Model tải nguyên trạng từ Live2D/CubismWebSamples, revision
`b1de66b0b1f1cb881d95fb6158622aeb6a2827bd`, thư mục Samples/Resources/Hiyori.
Core tải từ https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js,
giữ nguyên header giấy phép. Hash file có trong `public/characters/assets-manifest.json`.

Hiyori không thuộc MIT của AIRI. Không sửa thiết kế; giữ thông báo ghi công và liên kết giấy phép
ở `public/characters/NOTICE.html`. Điều kiện SDK và từng model áp dụng riêng.
Tính năng nhập Live2D làm thay đổi phạm vi so với bản model cố định: trước khi mở công khai trên VPS,
cần đối chiếu/trao đổi với Live2D về mục **Expandable Applications**. Live2D nêu nhóm này cần xét duyệt
và thỏa thuận phát hành riêng, kể cả khi ngoại lệ miễn phí cho cá nhân/doanh nghiệp nhỏ có thể áp dụng
cho loại ứng dụng khác. Việc phát triển/thử nghiệm và việc phát hành được phân biệt tại:
https://www.live2d.com/en/sdk/license/ . Không có hợp đồng hay thanh toán nào được thực hiện trong lần sửa này.

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
Model Hiyori và Core đi kèm thư mục public (~5 MB); các thư viện được cài qua lockfile.
Không cần cài model AI hay đổi relay. Model VRM mẫu dùng kiểm thử không được đóng kèm bản phát hành.

Dependency `gh-pages` đi kèm pixi-live2d-display 0.4.0 là công cụ xuất bản không dùng trong ứng dụng.
Override lên bản 6 để tránh lỗ hổng prototype pollution của bản 4; không chạy script xuất bản này.

Kiểm thử: 148 kiểm thử frontend đạt, build thành công. ZIP Hiyori chính thức và VRM1_Constraint_Twist_Sample từ kho `pixiv/three-vrm`
được nhập qua giao diện bản xem thử riêng. Kiểm tra đổi tên, lựa chọn sau tải lại, xóa model đang dùng,
giao diện máy tính/điện thoại; kiểm thử tự động bao gồm file sai, lưu/xóa tài nguyên, miệng VRM và cleanup.
Giọng Qwen thật trên VPS chưa được kiểm thử lại cùng thay đổi này.
Bản sửa tư thế tay: 5 kiểm thử VRM đạt, build thành công; kiểm thử dùng bộ xương chuẩn hóa thật của
three-vrm cho cả VRM 0/1, kiểm tra khuỷu/bàn tay nằm dưới vai và độ dài tay không đổi. Đã kiểm tra
hiển thị trên model VRM 0 gặp lỗi của người dùng trong bản xem thử tại máy.
`local-tts/speak_server.py` hiện trả WAV PCM16 đúng định dạng được hỗ trợ.
