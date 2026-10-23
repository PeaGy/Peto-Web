# Thư viện Player — giai đoạn 2 (23/10/2026)

Đã ghép giao diện được duyệt ở `/prototypes/player-library/` vào Companion thật. Chưa commit/deploy.
Prototype vẫn là bản duyệt độc lập, không phải màn hình để thử API thật.

## Hành vi

- Tim lưu/bỏ lưu theo tài khoản ở SQLite. File → Yêu thích, hoặc menu ba chấm trên mobile, mở danh sách.
  F5/đăng nhập lại vẫn có yêu thích; API dùng chủ tài khoản từ session, không nhận owner do trình duyệt gửi.
  Trạng thái tim chỉ đổi sau khi máy chủ xác nhận; lỗi lưu cho phép thử lại và không giả báo thành công.
- File có ô link và hai thao tác: mở video ở trạng thái dừng hoặc thêm vào cuối hàng đợi.
  Chọn bài trong Yêu thích/Hàng đợi là yêu cầu phát của người dùng. Thêm bài không ngắt bài đang nghe, không tự mở
  hàng đợi; icon hiện chấm báo. Danh sách chờ hỗ trợ chọn bài, kéo/đổi thứ tự bằng phím hoặc menu và xóa.
- Hàng đợi, vị trí, loop/shuffle chỉ giữ trong phiên đăng nhập hiện tại, không ghi localStorage/backend.
  F5 bắt đầu phiên phát trống, không tự phát. Đóng X giữ lựa chọn/hàng đợi nhưng hủy iframe; mở lại chuẩn bị ở trạng thái dừng.
- Shuffle/Loop có trên hàng năm nút chính và trong hàng đợi, dùng chung trạng thái. Mặc định tắt.
  Loop: tắt → hàng đợi → một bài → tắt. Một bài chỉ lặp khi hết; Tiếp theo vẫn bỏ qua.
  Lặp cả hàng đợi giữ trọn vòng, phục hồi bài đã nghe khi bật muộn và không phục hồi mục đã xóa.
  Shuffle giữ bài hiện tại, trộn phần chờ, trộn lại mỗi vòng khi kết hợp loop all; không lặp ngay mục vừa hết
  ở ranh giới vòng nếu có mục khác. Tắt shuffle khôi phục thứ tự thường còn chờ. Sắp xếp bằng tay tắt shuffle.
- Tiêu đề/kênh lấy từ oEmbed qua máy chủ, tái sử dụng `shared.youtube.lookup`; không đoán tên từ ID.
  Nếu thiếu metadata vẫn phát/lưu được, hiển thị “Video YouTube” và ID. Thumbnail chỉ dựng từ mã video hợp lệ.
- Video lỗi nhúng, bị xóa, API lỗi hoặc autoplay bị chặn giữ nguyên lỗi và cách mở YouTube/thử lại;
  không tự chạy vòng bỏ qua lỗi. Người dùng có thể chọn bài kế tiếp. Giới hạn: 200 mục chờ, 500 yêu thích/tài khoản.
- Desktop: `_` và icon ẩn/hiện vẫn phát; X dừng/hủy. Mobile: mũi tên xuống ẩn cả UI và giữ phát trong cùng tab,
  không có mini player. Rời Companion/ẩn trang trên mobile hủy phiên; desktop giữ phát theo khả năng con trỏ.
  Pagehide, logout, unmount luôn dừng. Quyền Space, micro, giọng đọc và renderer giữ hành vi trước.

## Mã và vòng đời

- `PlayerLibraryShell.tsx`, `PlayerLibraryPanel.tsx`, `PlaybackModeButtons.tsx`, `LibraryIcon.tsx`, `playerLibrary.css`:
  UI được chuyển từ bản đã duyệt, không import prototype/catalogue. Shell cũ giữ cho các prototype kiểm tra riêng.
- `usePlayerLibrary.ts`/`playerQueue.ts`: điều khiển thư viện và reducer thuần. Metadata đến muộn chỉ cập nhật đúng ID,
  không thay yêu cầu phát. Mỗi mục hàng đợi có key riêng, kể cả hai mục cùng video. Yêu cầu kết thúc cũ không được
  đẩy qua bài mới hoặc xử lý hai lần.
- `useYouTubePlayer.ts`: URL nhập chỉ cue. Các yêu cầu chọn/phát tiếp có token riêng và dùng `loadVideoById` trên
  iframe hiện có. Loop cùng ID cũng tạo token mới. Token autoplay đã dùng/bị hủy không phát lại khi đóng, suspend
  hoặc quay lại từ pagehide. Chờ xác nhận nguồn mới rồi bật controls; xử lý blocked hữu hạn.
- Dựa trên [YouTube IFrame Player API chính thức](https://developers.google.com/youtube/iframe_api_reference)
  cho cue/load và sự kiện kết thúc; không dùng clock của bản mẫu để quyết định hết bài thật.
- API: GET `/api/companion/player/videos/{video_id}`, GET `/favorites`, POST/DELETE `/favorites/{video_id}`
  (hai đường dẫn cuối cùng dưới `/api/companion/player`). Chỉ nhận ID 11 ký tự hợp lệ, không proxy URL tùy ý.
- Backend: `features/companion/player_api.py`, `storage/player.py`. `storage.schema.init_db` tạo bảng/index
  `player_favorites` theo cách bổ sung, idempotent. Không thay bảng dữ liệu trước. Yêu cầu mạng oEmbed cố định,
  có timeout/cache như tính năng YouTube trong chat hiện tại; không có Data API key mới.

## Kiểm chứng

- Backend: 65 ca trong nhóm player/YouTube/profile/auth đạt, DB tạm và metadata giả.
- Frontend: 291 ca trong nhóm App/Companion/Hearing, queue, lưu tim/hủy request, hook YouTube, URL và loader đạt.
  Hook kiểm tra vòng đời/blocked và không phát lại yêu cầu đã bị hủy; build frontend đạt.
- Browser ứng dụng thật với backend/YouTube giả: 4 ca thư viện (desktop/mobile) đạt. Kiểm tra tim sau F5,
  chọn bài, queue reorder, auto-next, loop one/all, shuffle, lỗi 150, ẩn UI và giữ đúng một iframe.
- Hồi quy browser Player cũ/Companion: 23 ca đạt, 7 ca bỏ qua theo loại thiết bị. Bao gồm Space/micro,
  Live2D/giọng đọc, chuyển bố cục, ẩn/phát nền, pagehide và logout.
- Các ca trên không phải nghiệm thu quảng cáo, tài nguyên khi phát YouTube thật hoặc Android/Chrome thật.
  Phần trình duyệt/thiết bị thật thuộc vòng nghiệm thu sau; không gọi AI/TTS trả phí.
- Lúc bàn giao chưa kết nối được backend local ở cổng 8000, nên chưa thử bằng phiên đăng nhập thật trên máy chủ web.

## Triển khai và bước sau

Khi chủ web quyết định deploy: build frontend và khởi động lại backend theo quy trình hiện có. Bảng yêu thích
được tạo tự động lúc khởi động; không cần chạy SQL tay, đổi `.env` hoặc xóa dữ liệu.

Giai đoạn 3 mới thêm tìm theo tên và nhập playlist công khai với YouTube Data API. Giai đoạn 4 nghiệm thu
browser/thiết bị/tài nguyên. Chưa thêm lệnh chat/voice hoặc tiến trình phát sau khi thoát hẳn trình duyệt.
