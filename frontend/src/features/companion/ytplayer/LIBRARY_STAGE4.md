# Nghiệm thu thư viện Player — giai đoạn 4, 23/10/2026

## Phạm vi và trạng thái

Nghiệm thu trên commit `645fe3b` mà chủ web đã deploy; chủ web đã cấu hình key trên máy chủ và xác nhận tìm/chọn
video, nhập playlist hoạt động. Đợt này bổ sung bộ kiểm tra và cập nhật công cụ đo cho giao diện hiện tại,
không thay mã sản phẩm, database, model, prompt hoặc cấu hình triển khai. Chưa commit/deploy các tệp nghiệm thu.

Ba loại chứng cứ được tách riêng:

- **Bản deploy thật**: `https://peto.pearto.shop/companion`, phiên đăng nhập có sẵn, YouTube/Data API thật.
  Chỉ thao tác Player; không gửi chat, gọi AI/TTS, bật micro, đổi cài đặt hay ghi/xóa yêu thích của chủ web.
  Một lượt tìm tên và một lượt nhập playlist; không tìm tự động theo từng phím. Đã dừng Player bằng X khi kết thúc,
  trả viewport về mặc định và khôi phục bản nháp chat.
- **Kiểm tra tự động local**: mã Companion thật, backend/YouTube giả; gồm nhóm riêng chạy Chrome và Edge cài trên máy,
  desktop và mobile cảm ứng mô phỏng. Một ca chạy Live2D và Audio thật với PCM tổng hợp, không gọi TTS.
- **Ma trận phát/tài nguyên**: bản build loopback, profile Chrome/Edge tạm, Live2D Hiyori và YouTube thật;
  backend/tài khoản/metadata giả, không dùng key Data API hoặc profile cá nhân. Chạy tuần tự từng trình duyệt.

**Android/Chrome thật: chủ web đã nghiệm thu thủ công** trên điện thoại Xiaomi, Android 13, Chrome 155.0.8059.87,
báo các bước đã gửi đều ổn, chưa thấy vấn đề. Agent không điều khiển điện thoại qua USB debugging;
thu hẹp viewport trên desktop vẫn được ghi riêng, không thay cho báo cáo máy thật này.

## Kết quả trên bản deploy

- Tìm `Tetris Kasane Teto` trả 20 kết quả có tiêu đề, kênh và thời lượng thật; mở kết quả đầu
  `テトリス / 重音テトSV` phát được. UI báo playing, tiến độ quan sát 53 → 106 giây, một iframe.
- Dấu cộng thêm bản ENG Cover của Moonlit Star, giữ video đầu đang phát. Khi video đầu kết thúc,
  Player tự chuyển sang bản cover; quan sát cover đến 2:17/2:21 rồi ended.
- Đã bật loop một bài, chọn lại Tetris và tua End; sau đó quan sát cùng video ở trạng thái playing,
  một iframe `widget4`. Kiểm chứng sự kiện ENDED/loop có thêm ca tự động ở bộ hook/queue và browser.
- Nhập playlist [Neural Networks của 3Blue1Brown](https://www.youtube.com/playlist?list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi)
  thêm 10 video, giữ mục hiện tại và các mục đã có trong hàng đợi.
- Bố cục responsive ở 390×844 có iframe khoảng 335×200 và không tràn ngang. Đây là desktop thu hẹp viewport,
  không phải điện thoại thật hoặc bằng chứng trình duyệt Android xử lý bàn phím/visibility.
- Mũi tên xuống ẩn toàn bộ UI, iframe `widget4` vẫn còn một; tiến độ 66 → 97 giây khi nhập nháp chat.
  Mở lại ở bố cục desktop vẫn cùng iframe. X đưa tổng iframe về 0; mở lại chuẩn bị nguồn với `autoplay=0`.
- Lần mở lại cuối đã xác nhận danh sách chờ giữ đủ chín chương sau chương Neural Network đầu tiên;
  đã đóng X sau khi chụp minh chứng. Không gửi hoặc thay nội dung cuộc trò chuyện.

Ảnh/ghi nhận cục bộ (ignored): `.runtime/player-library-stage4/production/desktop-playlist.png`,
`mobile-playlist.png`, `summary.json`. Ảnh chỉ chứa Player, không chụp nội dung chat của chủ web.

## Kiểm tra tự động

- Backend **83 ca đạt**: player/catalog/YouTube/auth/profile, DB và mạng giả. Bao gồm cách ly tài khoản,
  key thiếu/sai, quota/rate limit, cache, batch dữ liệu, giới hạn playlist, lỗi giữa chừng và đầu vào sai.
- Frontend **318 ca đạt** trong 9 file: input/URL, thư viện, queue, API loader, hook YouTube, App, Companion và Hearing.
- Chrome cài trên máy: **22 ca đạt**, 4 bỏ qua theo thiết bị. Hai ca danh sách 200 mục được chạy lại riêng
  sau khi sửa selector `summary` trong bộ test; 20 ca còn lại đã đạt ở lượt trước.
- Edge cài trên máy: **22 ca đạt**, 4 bỏ qua theo thiết bị, trong một lượt chạy cuối.
- Hai ca nghiệm thu mới mỗi thiết bị: nhập 200 mục, cuộn đến cuối/xóa/thêm, từ chối mục 201;
  resize 320×640, 390×844, 844×390 hoặc desktop không tràn, iframe tối thiểu 200×200;
  đóng/mở 10 lần tạo/hủy đúng 10 player, IFrame API chỉ nạp một lần; tâm tim trùng tâm vùng bấm.
- Hồi quy cũ: favorites sau reload, chọn từ kết quả, queue/reorder/next, loop/shuffle hai nơi cùng trạng thái,
  lỗi 150/blocked, `_`/mũi tên/X, pagehide/logout, Space/PTT, Live2D và tiếng đọc.
- Build TypeScript/Vite đạt. Không thấy import catalogue/prototype vào các thay đổi này.

Ca micro dùng thiết bị Chromium giả; ca tiếng đọc dùng PCM tổng hợp. Chúng kiểm tra vòng đời/phối hợp của ứng dụng,
không chứng minh khử vọng hoặc chất lượng loa/micro thật.

## Video thật và tài nguyên

Chi tiết của hai lượt đo nằm trong `.runtime/player-library-stage4/live/chrome.json` và `msedge.json`.
Mỗi video được quan sát khoảng 5 giây; tiến độ/kích thước video/paused và trạng thái quảng cáo đọc từ iframe thật.
Số CPU/RAM lấy mẫu 5 giây ở mỗi trạng thái, trên i5-10300H, 8 CPU logic, Windows 10.0.26300.
CPU 100% tương đương một CPU logic; private MiB là bộ nhớ commit, không gồm VRAM. Tổng working set có thể tính
trùng trang dùng chung. Không dùng các mẫu ngắn để xếp hạng Chrome/Edge, kết luận rò bộ nhớ hoặc dự đoán pin Android.

Chrome **155.0.8059.86**, Edge **155.0.4283.62**; hai lệnh mạng thật kết thúc mã 0, không có lỗi JavaScript.
Bốn video phát được đều được đối chiếu video ID trong iframe; không cần dùng nút native để cứu lượt phát.

| Video | Chrome | Edge |
|---|---|---|
| Miku concert (`HDz9dSuAI4s`) | Phát, +4,54 giây | Phát, +4,53 giây |
| Vampire (`e1xCOsgWG0M`) | Phát, +4,55 giây | Phát, +4,53 giây |
| Tetris (`Soy4jGPHr3g`) | Phát, +4,55 giây | Phát, +4,86 giây |
| Rick Astley (`dQw4w9WgXcQ`) | YouTube trả lỗi 150 | YouTube trả lỗi 150 |
| Shape of You (`JGwWNGJdvx8`) | YouTube trả lỗi 150 | YouTube trả lỗi 150 |
| 3Blue1Brown (`aircAruvnKk`) | Phát, +4,55 giây | Phát, +4,53 giây |

150 là lỗi chủ video không cho phát nhúng, UI giữ thông báo/mở trên YouTube; không đổi nguồn phát để lách.
Không thấy quảng cáo trong các mẫu nhúng 5 giây. Đối chứng trực tiếp 3Blue1Brown trên Chrome có quảng cáo khoảng
15,02 giây (4/4 mẫu quan sát là quảng cáo); trên Edge chưa thấy trong cửa sổ 5 giây. Không cam kết không quảng cáo.

| Mốc (ms) | Chrome | Edge |
|---|---:|---:|
| Mở shell | 428 | 463 |
| URL đầu → sẵn sàng | 1.163 | 1.591 |
| Click trong trang → playing, Tetris | 2.215 | 1.536 |
| Đổi URL → sẵn sàng, các video phát được | 522–538 | 241–528 |
| Click trong trang → playing, các lượt đổi video phát được | 686–2.153 | 563–1.146 |

Mốc sẵn sàng gồm thao tác công cụ/polling; mốc click→playing lấy timestamp trong trang. Không phải phép đo khung
hình đầu tiên. Bốn cửa sổ CPU/RAM dưới đây lấy trong cùng profile, không cộng trình duyệt cá nhân.

| Trạng thái | Chrome CPU (% một CPU logic) | Chrome private MiB | Edge CPU (% một CPU logic) | Edge private MiB | iframe |
|---|---:|---:|---:|---:|---:|
| Companion, chưa mở TV | 42,1 | 401 | 43,5 | 404 | 0 |
| Tetris đang phát + Hiyori | 89,4 | 655 | 74,6 | 634 | 1 |
| Phát nền trong Trò chuyện | 21,9 | 501 | 19,2 | 462 | 1 |
| Đóng X, quay về Companion | 43,0 | 608 | 33,7 | 572 | 0 |

Phát Tetris tăng private khoảng 254 MiB trên Chrome, 230 MiB trên Edge trong các mẫu này. Sau X, iframe/timer đã
được dọn nhưng browser còn cache/tiến trình nên RAM không về ngay baseline. Không suy ra rò bộ nhớ từ số RAM này;
các ca đóng/mở xác nhận tạo/hủy từng player, chưa phải một phép đo heap kéo dài hàng giờ.

Chrome với mobile cảm ứng mô phỏng giữ một iframe qua 390×844, 320×640, 844×390; vùng iframe lần lượt
342×342, 272×200, khoảng 406×200. Khi ẩn UI và gõ nháp, tiến độ 4 → 8 giây; X gỡ iframe. Controls thật
pause/play, seek ~61 giây, volume 100→0→100 và Space trong iframe đạt trên cả Chrome/Edge.

Lượt headless không xác nhận được `document.hidden` tự nhiên nên **không tính đạt** đổi tab/thu nhỏ cửa sổ hệ điều hành.
Nút `_`, chuyển sang Trò chuyện trong Peto, controls và X được kiểm tra riêng. Chứng cứ cửa sổ thật của vòng trước
còn ở [báo cáo Player trước](./STAGE4_REPORT.md); không gộp các số cũ thành số mới của thư viện.

## Chạy lại

Từ thư mục `frontend`:

```powershell
# Chọn Chrome hoặc Edge thật; không dùng API/AI/TTS thật trong bộ browser.
$env:PETO_PLAYER_BROWSER = 'chrome' # hoặc msedge
npm run test:browser -- --config playwright.player.config.ts

# Bản build + server preview; phép đo mạng thật chỉ bật khi thêm --live.
npm run build
npm run preview -- --host 127.0.0.1 --port 5188 --strictPort
# Ở cửa sổ khác, chạy tuần tự:
node ops/youtubePlayerCheck.mjs --live --browser chrome --observe 5 --sample 5 --output ../.runtime/player-library-stage4/live
node ops/youtubePlayerCheck.mjs --live --browser msedge --observe 5 --sample 5 --output ../.runtime/player-library-stage4/live
```

Script chỉ nhận loopback, dùng profile riêng và backend giả; việc phát video iframe thật không dùng key tìm kiếm.
Trong môi trường sandbox, server preview và tiến trình trình duyệt phải cùng môi trường truy cập loopback.

## Android/Chrome — nghiệm thu thủ công của chủ web

Thiết bị được báo: **Xiaomi, Android 13, Chrome 155.0.8059.87**; chưa có mã model chi tiết.
Chủ web đã làm các bước 1–5 bên dưới và báo “vẫn thấy ổn, chưa thấy vấn đề gì”. Đây là kết quả người dùng báo,
không phải agent đo hoặc điều khiển điện thoại:

1. Tìm một bài, chọn phát; thêm một bài, thử Next, shuffle, loop tắt → hàng đợi → một bài → tắt.
2. Nhập playlist có sẵn: bài hiện tại tiếp tục, danh sách đủ/đúng thứ tự và cuộn được.
3. Mũi tên xuống: vẫn nghe, không có mini frame; gõ nháp chat. Mở lại để pause; X dừng hẳn.
4. Xoay dọc/ngang, mở bàn phím nhập tên/link/chat: player/controls đủ lớn, không bị cắt/tràn ngang.
5. Rời Companion hoặc ẩn tab: điện thoại phải dừng theo vòng đời đã chốt. Quay lại không tự phát sau khi bị hủy.
6. Chưa có số đo nhiệt/pin hoặc thử loa/micro thật kéo dài. Theo dõi trong phiên dùng bình thường;
   không cần gọi AI/TTS trả phí chỉ để hoàn thành danh sách này.

Giai đoạn nghiệm thu chức năng hoàn tất trong phạm vi trên, không còn lỗi chặn đã ghi nhận. Nhiệt/pin dài hạn và
thao tác thu nhỏ cửa sổ OS mới không được đánh dấu là đã đo; đây không phải cam kết tài nguyên trên mọi máy.
