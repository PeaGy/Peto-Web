# Player trong Companion — giai đoạn 3

Đã ghép vào Companion và được chủ web triển khai. Dùng player YouTube chính thức; không thêm thư viện,
backend, Data API key, tìm kiếm, playlist hoặc xử lý âm thanh iframe.

## Cách mở

- Desktop: nút icon cạnh Bối cảnh/Nhân vật ẩn/hiện cửa sổ; không có chữ Player trên nút. Nút **_** ẩn cửa sổ và tiếp tục
  phát, **X** dừng/hủy player. Mở lại sau khi ẩn giữ iframe, tiến độ và trạng thái đang phát.
  Kéo, resize, phóng lớn và menu giữ giao diện đã duyệt. Cửa sổ giới hạn bên trái cột chat và xuống được sát đáy Companion;
  không dành dải 76 px bên dưới. Các nút công cụ nằm bên phải nên vẫn bấm được.
- Mobile: menu → **Player**. Mũi tên xuống ẩn toàn bộ Player nhưng giữ iframe/phát trong cùng tab, không có khung
  hay controls phụ. Mở lại bằng menu để tạm dừng hoặc nhấn X để dừng hẳn. Ẩn giao diện không đồng nghĩa ẩn tab trình duyệt.
- Companion còn thanh bên và cột chat nên cửa sổ hẹp (viewport ≤900 px) cũng dùng màn hình Player riêng; màn hình
  cảm ứng thấp dùng bố cục ngang. Đổi bố cục giữ nguyên iframe; vùng xem tối thiểu 200×200 khi hiển thị.
- Lần đầu có ô **Link YouTube**; chỉ nạp API sau khi nhập link hợp lệ. Không tự chọn mẫu, tự phát hoặc lưu URL vào
  localStorage. Đóng bằng X rồi mở lại giữ link trong lần đăng nhập hiện tại và chỉ chuẩn bị video ở trạng thái dừng.
- Metadata nằm trong iframe chính thức, không bịa tên/kênh từ mã video. Không import sáu mẫu của prototype vào app.
  Chỉ hiện lỗi và hướng xử lý khi cần; link mở YouTube bên ngoài chỉ xuất hiện lúc có lỗi.

## Các điểm gắn

- `Companion.tsx`: nút desktop, trạng thái mở/ẩn, ref quyền phím và focus, biên vùng cửa sổ. Tải riêng
  `CompanionPlayer.tsx` sau lần mở đầu. `active=false` đóng phiên Player, kể cả vào Cài đặt Companion.
- `App.tsx` và `Sidebar.tsx`: mục mobile phát yêu cầu mở Player; xóa yêu cầu khi hết phiên đăng nhập. Companion có
  key theo tài khoản và bị gỡ khi đăng xuất, nên nguồn/iframe không theo sang tài khoản khác.
- `CompanionPlayer.tsx`: giữ link và nối `useYouTubePlayer`; portal ổn định ngoài container sân khấu để mobile
  thực sự phủ viewport khi xoay ngang. Biên desktop theo vị trí/kích thước sân khấu, có dọn observer/listener.
- `PlayerShell.tsx` và `playerLayout.ts`: giao diện/vòng focus dùng chung với prototype, iframe không bị chuyển
  sang cây khác khi resize. Mobile đang mở làm sân khấu/chat inert; ẩn/đóng trả lại tương tác và focus.
- `useYouTubePlayer.ts`: chưa có nguồn không tải API; đổi video chỉ cue. Đóng, rời Companion, unmount, đăng xuất,
  `document.hidden` và `pagehide` dừng/hủy player, gỡ iframe và dọn timer. Quay lại không tự phát.

## Phím, micro, giọng đọc và nhân vật

Chọn Player để nhận Space; bấm ra ngoài trả phím cho Companion. Khi iframe focus, YouTube nhận phím gốc, trang cha
không bắt phím xuyên nguồn. Bộ nghe kiểm tra cả quyền phím, `defaultPrevented` và vùng Player, không phụ thuộc thứ tự
đăng ký listener. Chọn Player lúc đang giữ để nói hủy lần thu đó, không gửi lời nghe dở.

Mở/đóng/ẩn Player không dừng tiếng đọc và không gỡ renderer nhân vật. Nhún theo nhạc vẫn dùng chia sẻ âm thanh hiện
có; không nối iframe vào bộ phân tích nhịp. Chưa tự giảm âm lượng video hay lọc tiếng nhạc lọt qua micro.

## Kiểm chứng và giới hạn

- `companion-player.spec.ts`: ứng dụng thật với tài khoản/backend/YouTube giả; kiểm tra link và nạp API muộn, một iframe,
  đổi nguồn/bố cục, ẩn mobile trả đủ diện tích chat, rời tab/Cài đặt/đăng xuất và quyền Space của bộ nghe thật. Micro
  dùng thiết bị giả của Chromium, không thu âm người dùng.
- Cùng bộ đó có ca dùng renderer Live2D và Audio thật với PCM tổng hợp từ phản hồi TTS giả: mở/đóng Player không dựng
  lại canvas, không dừng tiếng đọc. Không gọi dịch vụ AI/TTS trả phí.
- `youtube-player-api.spec.ts`, `youtube-player-preview.spec.ts`: hồi quy module dùng chung, lỗi 101/150/153, retry,
  autoplay bị chặn, vòng đời, keyboard, menu, volume, kéo và resize. API giả chia sẻ ở `youtubeFixture.ts`.
- Unit: App, Companion, Hearing, URL, loader và hook. Build frontend kiểm tra TypeScript và tạo chunk Player tải riêng.
- Giai đoạn 4 còn ma trận sáu video trên Chrome/Edge, quảng cáo, CPU/RAM, lần mở đầu/đổi bài và điện thoại thật.
  Mô phỏng mobile không thay thế thiết bị thật; không cam kết không quảng cáo hay hỗ trợ khóa màn hình.

Kết quả ngày 22/10/2026: 270 unit test đạt; 34 ca trình duyệt đạt, 10 tổ hợp bỏ qua vì dành cho bố cục còn lại;
build và diff check đạt. Build có chunk `CompanionPlayer` tải riêng, không chứa trang prototype, API giả hay ID video mẫu.

Kiểm tra bổ sung bằng Chromium, API/iframe YouTube và Live2D thật trong ứng dụng: Tetris phát, tạm dừng và đóng gỡ
iframe trên desktop 1440×900 và mobile mô phỏng 390×844. Khi ẩn Player mobile rồi nhập chat, thời gian tăng từ 2 lên
4 giây; diện tích chat trước khi nhập không đổi, mở lại giữ đúng iframe, mỗi màn hình vẫn có một canvas và không lỗi
JavaScript. Tài khoản/backend của lượt này được giả lập, không gọi AI/TTS thật. Đây là smoke test ngắn, không thay
thế ma trận sáu video, đo tài nguyên hoặc nghiệm thu điện thoại thật.

Sau góp ý bản deploy: 35 ca trình duyệt đạt, 11 tổ hợp bỏ qua theo bố cục; build đạt. Ca desktop mới kiểm tra nút
icon không còn chữ, thu nhỏ/ẩn bằng icon giữ cùng iframe và tiến độ, X hủy player, kéo/phóng lớn chạm đúng đáy
Companion và khôi phục đúng vị trí. YouTube thật trên Chromium: cả nút _ desktop và mũi tên mobile giữ phát khi ẩn,
tiến độ tăng từ 2 lên 4 giây; mở lại cùng iframe và X gỡ iframe. Bản sửa này chưa deploy lại.
