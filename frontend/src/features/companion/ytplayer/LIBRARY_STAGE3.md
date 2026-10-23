# Thư viện Player — giai đoạn 3 (23/10/2026)

Đã ghép tìm theo tên và nhập playlist vào Companion thật; chủ web đã commit/deploy `645fe3b` và cấu hình key máy chủ.
Phần dưới ghi lại bàn giao giai đoạn 3; nghiệm thu cuối xem [LIBRARY_STAGE4.md](./LIBRARY_STAGE4.md).
Giữ giao diện, vị trí tim và hành vi phát của giai đoạn 2; prototype vẫn là dữ liệu mẫu độc lập.

## Sử dụng

- Ô **Link hoặc tên video** có ở màn hình mở đầu và File/menu ba chấm trên mobile.
  Tên video chỉ tìm khi gửi form, không tìm theo từng phím và không tự phát kết quả đầu.
- Kết quả dùng cùng panel với hàng đợi/yêu thích: bên phải khi frame đủ rộng, bên dưới trên mobile/frame hẹp.
  Chọn một bài để phát, dấu cộng thêm vào cuối hàng đợi và giữ nguyên kết quả/bài đang nghe.
  **Xem thêm** tải trang tiếp theo, loại kết quả trùng; tối đa 100 kết quả trong một lượt tìm.
- Link video vẫn mở ở trạng thái dừng, giữ mốc thời gian trong link. File có **Thêm vào hàng đợi** cho link video.
- Link `/playlist?list=…` nhập các bài vào cuối hàng đợi, mở hàng đợi và giữ nguyên bài đang phát.
  Không tự phát playlist khi chưa có bài hiện tại; chọn một mục trong hàng đợi để bắt đầu.
  Link video kèm `list=…` vẫn mở riêng video; File có thêm **Nhập playlist** để chọn nhập cả danh sách.
- Giữ thứ tự và các mục video trùng trong playlist. Video đã xóa/riêng tư/không cho nhúng bị bỏ qua.
  Máy chủ đọc tối đa 200 mục (4 trang), chỉ thêm trong sức chứa còn lại của hàng đợi (200 bài).
  Có thông báo số bài thêm/bỏ qua và khi còn mục chưa nhập; không âm thầm cắt danh sách.
  Nếu lỗi giữa chừng thì không thêm từng phần; hàng đợi cũ được giữ.
- Lỗi mạng, playlist không truy cập được, thiếu key hoặc hết quota có trạng thái lỗi và cách thử lại.
  Kết quả đến muộn của lượt đã hủy không thay nguồn hoặc thêm bài. Đóng X hủy khám phá đang chờ;
  `_`/mũi tên xuống vẫn chỉ ẩn giao diện và giữ phát theo vòng đời đã chốt.

## Bật trên máy chủ

1. Tạo/chọn project trong Google Cloud, bật **YouTube Data API v3**, tạo API key.
   [Hướng dẫn chính thức](https://developers.google.com/youtube/v3/getting-started).
2. Giới hạn key cho YouTube Data API v3; giới hạn IP máy chủ nếu máy có IP cố định.
3. Thêm `PETO_YOUTUBE_API_KEY=...` vào `.env` riêng của Peto Web trên máy chủ, rồi khởi động lại backend.
   Build frontend theo quy trình deploy đang dùng. Không đổi schema, chạy SQL tay hoặc cài dependency mới.
4. Không dùng biến `VITE_*`, không đưa key vào repo/chat/trình duyệt. Máy chủ gửi key trong header
   `X-Goog-Api-Key`, tránh ghi key vào URL của request/log HTTP.
   [Cách gửi API key của Google](https://docs.cloud.google.com/docs/authentication/api-keys-use).

Thiếu key chỉ tắt tìm tên/đọc playlist; mở link video, yêu thích và hàng đợi đã có vẫn dùng được.
Đây là key của ứng dụng, không phải đăng nhập Google của người nghe. Không truy cập playlist riêng tư,
Watch Later, Liked Videos hay các mix động không được Data API hỗ trợ.

## API và giới hạn

- GET `/api/companion/player/search?q=…&page_token=…`: 20 kết quả mỗi trang, `tracks` và `next_page_token`.
- GET `/api/companion/player/playlists/{id}?limit=…`: `tracks`, `skipped`, `truncated`; limit từ 1 đến 200.
- Cả hai yêu cầu session. Đầu vào chỉ query/ID/token có giới hạn; chỉ gọi các resource cố định ở Google,
  không tải URL người dùng cung cấp. Timeout từng HTTP 8 giây, toàn lượt 30 giây, phản hồi tối đa 512 KB.
- Tìm dùng [search.list](https://developers.google.com/youtube/v3/docs/search/list) với `type=video`,
  `videoEmbeddable=true`, `videoSyndicated=true`; phân trang qua token chính thức.
  Playlist dùng [playlistItems.list](https://developers.google.com/youtube/v3/docs/playlistItems/list).
  [videos.list](https://developers.google.com/youtube/v3/docs/videos/list) lấy title/kênh/thời lượng và lọc trạng thái.
- Cache tối đa 128 kết quả/trang trong 5 phút, không ghi DB. Slot khám phá riêng: 3 lượt đồng thời, 4 lượt chờ,
  khoảng nghỉ tài khoản 1,5 giây cho cache miss; không chiếm slot AI, không gọi oEmbed từng mục đã có metadata.
  Không tự retry hoặc tự chuyển trang. Quota thật xem trong Google Cloud của project;
  [bảng quota chính thức](https://developers.google.com/youtube/v3/determine_quota_cost).
- `embeddable` không bảo đảm phát trên mọi vùng/thiết bị. Lỗi iframe 101/150 và cách mở YouTube vẫn giữ nguyên.
  Không thay hoặc bỏ quảng cáo YouTube.

## Kiểm chứng

- Build frontend đạt. Backend: 47 ca đạt, kiểm tra auth, ID/query/token, key thiếu/sai, cache, quota/rate limit, batch metadata,
  thứ tự/bản trùng, video không khả dụng, playlist cắt giới hạn và lỗi giữa chừng không trả danh sách một phần.
- Frontend: 318 ca đạt trong hai lượt nhóm liên quan; phân loại input/hostname giả, tìm tên không autoplay, phân trang/loại trùng,
  abort/phản hồi cũ, nhập playlist giữ bài hiện tại, đổi sức chứa khi request còn chờ; hồi quy queue/YouTube/Companion/voice.
- Browser: 6 ca mới desktop/mobile mô phỏng qua API/YouTube giả đạt; 14 ca cũ Companion/library đạt,
  4 ca bỏ qua theo thiết bị. Đã xem ảnh kết quả tìm kiếm và playlist trên desktop/mobile.
- `.env` local chưa có key; chưa gọi Data API thật. Kết quả giả không thay cho nghiệm thu YouTube thật,
  quảng cáo, quota project, CPU/RAM hoặc Android/Chrome thật. Các phần đó tiếp tục ở giai đoạn 4.

Không tự commit/deploy. Không chạy AI/TTS trả phí trong kiểm chứng này.
