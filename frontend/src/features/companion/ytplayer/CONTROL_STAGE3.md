# Peto điều khiển Player — giai đoạn 3 (23/10/2026)

Bản đối chiếu `7b912f4`. Chủ web đã deploy bản kiểm chứng queue, xác nhận Peto chuyển đúng vị trí mà không cần
F5, rồi yêu cầu giai đoạn tiếp theo. Đợt này thêm tìm/chọn nhạc, video URL, nhập playlist và hội thoại gợi ý → đồng ý.
Đã commit ở `8ed3642`, sau đó sửa xác nhận ở `f3e8c3b` và `9869571`; các nội dung dưới ghi lần bàn giao ban đầu.
Nghiệm thu tiếp theo: [CONTROL_STAGE4.md](./CONTROL_STAGE4.md). Không gửi chat AI/TTS có phí hoặc gọi YouTube
production để kiểm tra trong đợt triển khai này.

## Hành vi

| Bạn nhắn | Kết quả mong muốn |
| --- | --- |
| “Tìm Tetris của Teto.” | Tra YouTube, trả lựa chọn từ kết quả thật; chưa tự phát. |
| “Mở Tetris của Teto.” | Tra nếu cần, chọn kết quả khớp tên/kênh, yêu cầu Player phát rồi chờ xác nhận. |
| “Thêm bài này …watch?v=…&list=…&index=8” | Thêm riêng video vào queue; giữ bài đang nghe. |
| “Thêm playlist này …playlist?list=…” | Thêm cuối, giữ thứ tự và bản trùng như nhập thủ công; không bắt đầu phát. |
| “Mở Player và bật một bài Peto thích.” | Chọn theo nhân vật, hội thoại và dữ liệu yêu thích hoặc kết quả tìm kiếm, rồi phát. |
| “I'm tired, Peto.” → Peto đề nghị nhạc → “Sure.” | Lời mệt tự nó chưa chạy Player. Sau đồng ý rõ ràng, có thể chọn/phát nhạc theo đề nghị. |

Ý định và lựa chọn do model xử lý bằng tool native, không regex câu người dùng. Nếu chưa rõ bài/bản cover,
Peto được hỏi ngắn để chọn; không mặc định mọi lượt tìm đều phát kết quả đầu. Model chỉ đọc metadata và trạng thái,
không nghe trực tiếp video. Không thêm bộ nhớ/playlist “gu nhạc” riêng, không đổi persona/examples hoặc bố cục UI.

## Mã và giao thức

- Client gửi `player_control: 3`. Backend chỉ cấp 4 action mới cho v3: `search_videos`, `play_video`, `enqueue_video`,
  `enqueue_playlist`. Schema v1/v2 giữ phạm vi cũ; Gemini BYO vẫn không có function calling.
- `player_discovery_tools.py` tách khỏi phần bridge/queue. Search/playlist dùng lại `youtube_catalog.py`: cùng key,
  cache, rate/concurrency, giới hạn trang và lỗi được làm sạch. Link video dùng oEmbed đã có, không cần key Data API.
  Chỉ nhận hostname/path YouTube hợp lệ; không dùng URL nhập vào làm địa chỉ fetch/iframe.
- Model truyền query, video ID đã đọc trong turn hoặc URL do người dùng cung cấp trong phần lịch sử hiện còn ngữ cảnh.
  Server giữ các ID/metadata đã quan sát trong turn; không nhận title/artist/danh sách tracks do model tự viết.
  Với URL video, giữ timestamp từ link người dùng (giới hạn 7 ngày), bỏ index và không tự nhập list đi kèm.
- Server chụp trạng thái trước tra cứu, rồi gửi metadata đã kiểm tra qua SSE đến đúng browser. Search chỉ trả dữ liệu,
  không mở iframe. `playerDiscoveryControl.ts` kiểm payload và thực hiện bằng library/YouTube hook hiện có.
- `play_video` chờ host mount trước khi tạo autoplay intent, chờ đúng source/token phát thật; giữ một iframe khi đổi bài.
  Bị chặn autoplay, lỗi 150, sai video hoặc chưa playing đều không được coi là phát thành công.
- `enqueue_video`/`enqueue_playlist` dùng append theo entry key, chờ các key xuất hiện, không autoplay hoặc đổi nguồn.
  Dùng sức chứa thực tế lúc commit, tối đa 200 chờ; giữ bản trùng. Server trả số thêm, bỏ qua không khả dụng,
  thiếu sức chứa và cờ playlist còn bị cắt. Queue đầy từ đầu thì không gọi catalogue playlist.
- `window_revision` tăng khi X đóng phiên. Đóng trong lúc tra cứu hoặc đợi phát làm payload cũ hết hiệu lực, kể cả
  đã mở lại. Không tự mở lại sau X. Hủy chat/unmount và ID/expiry/dedup/owner vẫn dùng cơ chế bridge cũ.
- Không thêm key, DB migration, dependency, mini player, queue persistence hoặc audio analyzer.

## Kiểm chứng

- Backend **171 ca đạt**: discovery, player tools/readback, catalogue, favorites, BYO, clock và prompt routing.
  Có native provider giả search → play và link trong lịch sử user → enqueue; ID/URL giả, lỗi quota/timeout,
  metadata sai/rỗng, video+list, timestamp, giới hạn 200, bản trùng, sai video/chưa playing và X sau search.
- Frontend: nhóm Player/queue/library/YouTube/API/Companion/Hearing **169 ca đạt / 9 tệp**, gồm gửi đúng phiên bản
  v1/v2/v3 và append playlist áp sức chứa thực tế, giữ bản trùng/nguồn đang nghe.
- Chrome cài trên máy, desktop và màn hình mobile mô phỏng: **32 đạt, 4 skip theo thiết bị**, toàn bộ
  `playwright.player.config.ts`. Ca discovery mới đi qua chat/Player thật với SSE/YouTube/network giả: append kín,
  dedup sự kiện, giữ nguồn khi append, phát lần đầu/sau X, stale generation, payload lỗi và autoplay bị chặn.
  Các ca cũ giữ một iframe, micro/giọng đọc/Live2D, phát nền và 200 mục vẫn đạt. Build frontend đạt.

Các ca sử dụng provider/catalogue/YouTube giả, không chứng minh model thật luôn nhận đúng ý định, chọn bản thu
hợp ý hoặc xử lý “Sure” chính xác. Phần đó cần nghiệm thu sau deploy, cùng Android/Chrome thật.

## Deploy và thử thật

Cập nhật backend trước hoặc cùng frontend, rebuild frontend và restart backend; không migration/key mới.
Tab cũ v1/v2 tiếp tục dùng bộ công cụ cũ, giữ phiên đang nghe. Giai đoạn này cần bundle frontend v3 để nhận action
mới: tải trang mới vào lúc phù hợp khi kết thúc phiên nghe. F5 hiện vẫn làm trống queue trong RAM; không yêu cầu
tải lại giữa bài. Favorites theo tài khoản vẫn giữ.

Sau deploy thử các câu ở bảng bằng bộ não Peto, so tên bài/kênh và queue với UI. Thử thêm:

1. Hỏi tìm bài, rồi yêu cầu chọn một kết quả; tìm kiếm tự nó không phát.
2. Thêm link video kèm list, chỉ tăng queue một mục. Yêu cầu playlist riêng giữ bài đang nghe và báo đúng counts.
3. Khi Peto đang tìm, bấm X: phản hồi về muộn không bật lại nhạc. Thử lại bằng yêu cầu mới thì phát bình thường.
4. Video lỗi nhúng/autoplay bị chặn: báo đúng lỗi, không tự chuyển bài khác và nhận là thành công.
5. Android/Chrome: ẩn Player vẫn phát trong Companion; mở lại điều khiển và X dừng, không thêm khung phụ.

Không tính nghiệm thu Xiaomi của thư viện cũ là nghiệm thu điều khiển nhạc qua chat mới.
