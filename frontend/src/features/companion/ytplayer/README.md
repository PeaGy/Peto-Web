# Player trong Companion

Bản Player trước đã được chủ web triển khai. Giai đoạn 2 của vòng mở rộng thư viện đã ghép vào Companion
(23/10/2026), chưa commit/deploy: tim/yêu thích theo tài khoản, hàng đợi/phát tiếp và loop/shuffle.
Xem [LIBRARY_STAGE2.md](./LIBRARY_STAGE2.md) cho API/lưu trữ và kiểm chứng. Dùng player YouTube chính thức,
không thêm dependency, Data API key, tìm kiếm, playlist hoặc xử lý âm thanh iframe.

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
  localStorage. Đóng bằng X rồi mở lại giữ link/hàng đợi trong lần đăng nhập hiện tại và chỉ chuẩn bị video ở trạng thái dừng.
- Tên/kênh ngoài iframe lấy qua oEmbed của máy chủ; thiếu metadata vẫn cho phát, không bịa tên từ mã video.
  Yêu thích lưu theo tài khoản; hàng đợi/loop/shuffle trong phiên. Không import catalogue mẫu của prototype vào app.
  Chỉ hiện lỗi và hướng xử lý khi cần; link mở YouTube bên ngoài chỉ xuất hiện lúc có lỗi.

## Các điểm gắn

- `Companion.tsx`: nút desktop, trạng thái mở/ẩn, ref quyền phím và focus, biên vùng cửa sổ. Tải riêng
  `CompanionPlayer.tsx` sau lần mở đầu. Desktop giữ phiên khi `active=false` (Trò chuyện/Cài đặt), đồng thời ẩn
  cửa sổ và trả quyền phím. Mobile rời Companion thì đóng phiên.
- `App.tsx` và `Sidebar.tsx`: mục mobile phát yêu cầu mở Player; xóa yêu cầu khi hết phiên đăng nhập. Companion có
  key theo tài khoản và bị gỡ khi đăng xuất, nên nguồn/iframe không theo sang tài khoản khác.
- `CompanionPlayer.tsx`: nối `usePlayerLibrary`/`useYouTubePlayer`; portal ổn định ngoài container sân khấu để mobile
  thực sự phủ viewport khi xoay ngang. Biên desktop theo vị trí/kích thước sân khấu, có dọn observer/listener.
- `PlayerLibraryShell.tsx`, `PlayerLibraryPanel.tsx` và `playerLayout.ts`: giao diện/vòng focus đã duyệt; iframe không bị chuyển
  sang cây khác khi resize. Mobile đang mở làm sân khấu/chat inert; ẩn/đóng trả lại tương tác và focus.
- `useYouTubePlayer.ts`: chưa có nguồn không tải API; nguồn ban đầu do constructor chuẩn bị, đổi video mới cue.
  Không cue lại ngay `onReady` để tránh ghi đè lần bấm Phát đầu. Đóng X, unmount, đăng xuất và `pagehide` luôn
  dừng/hủy player, gỡ iframe và dọn timer. Quay lại sau khi hủy không tự phát.
  Đổi nguồn chờ YouTube xác nhận cued/playing rồi mới bật Phát/seek; có timeout 20 giây. Âm lượng vẫn điều chỉnh được.
  Yêu cầu phát tiếp dùng loadVideoById; token autoplay chỉ dùng một lần, không phát lại sau khi phiên bị hủy.

## Phát nền

Theo yêu cầu mới của chủ web, desktop có chuột chính xác (`hover: hover` và `pointer: fine`) được phép tiếp tục
phát khi đổi tab trình duyệt, thu nhỏ hoặc chuyển sang Trò chuyện/Cài đặt trong Peto. Phân biệt thiết bị bằng khả
năng con trỏ, độc lập với bố cục: thu hẹp cửa sổ desktop không biến nó thành điện thoại. Không tạo phiên phát mới
khi đổi tab hoặc hiện lại cửa sổ; X và đăng xuất vẫn dừng hẳn.

Mobile chỉ giữ phát khi ẩn giao diện Player **trong cùng tab Companion**, không có mini player. Rời Companion hoặc
ẩn trang trình duyệt vẫn hủy phiên. Hành vi khóa màn hình/hệ điều hành chưa được cam kết.

Đóng tab Peto, rời trang bằng điều hướng toàn phần hoặc thoát hẳn trình duyệt kết thúc trang và player. Một web app
không thể giữ YouTube iframe chạy sau khi trình duyệt đã thoát. Không thêm service worker, tiến trình nền hoặc
cửa sổ phụ để giả lập khả năng này. Khi quay lại sau `pagehide` chỉ chuẩn bị nguồn, không tự phát.

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
- Ma trận sáu video trên Chrome/Edge, thời gian phản hồi, mẫu quảng cáo/tài nguyên và phạm vi nghiệm thu được ghi
  trong [STAGE4_REPORT.md](./STAGE4_REPORT.md). Mô phỏng mobile không thay thế Android/Chrome thật.

Bản Player trước đã được chủ web commit/deploy; bản mở rộng thư viện trong LIBRARY_STAGE2.md chưa commit/deploy.
Không cam kết không quảng cáo, phát sau khi thoát hẳn trình duyệt hoặc hỗ trợ khóa màn hình điện thoại.
