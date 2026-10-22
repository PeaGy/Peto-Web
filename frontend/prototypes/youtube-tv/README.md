# Player Companion — POC giai đoạn 1–2

Bản thử độc lập, đã nối player YouTube chính thức. Giai đoạn 3 đã ghép module dùng chung vào Companion thật;
trang prototype này vẫn chạy riêng để đối chiếu giao diện. Chưa deploy.
Không thêm backend, Data API key hoặc thư viện mới; không lấy âm thanh từ iframe hoặc thay đổi Nhún theo nhạc.

## Mở bản xem thử

Chạy frontend như bình thường, rồi mở `/prototypes/youtube-tv/`. Phiên xem thử ngày 22/10/2026 dùng
`http://127.0.0.1:5186/prototypes/youtube-tv/` cho YouTube thật; thêm `?mode=ui` để xem lại giao diện mô phỏng giai đoạn 1
không nạp iframe, API, video hoặc âm thanh bên ngoài.

- Trên desktop: kéo thanh tiêu đề để di chuyển; kéo bốn mép hoặc bốn góc để đổi kích thước. Cửa sổ giữ trong sân khấu,
  chừa chỗ bấm nút Player và giữ vùng xem ít nhất 200×200. Phóng lớn rồi khôi phục giữ lại vị trí và kích thước trước đó.
- File/View/Play/Tools/Help mở bảng nổi ngay dưới nút, không đẩy video xuống. Bấm ngoài hoặc Esc để đóng bảng.
- Rê chuột hoặc đưa focus vào loa để hiện thanh âm lượng trên cùng hàng, ngay bên phải loa. Bấm loa để tắt/bật tiếng
  và hiện thanh điều chỉnh; dùng một biểu tượng loa duy nhất, không có hộp nổi. Bấm ngoài hoặc Esc để thu thanh lại.
  Trên mobile dùng thao tác bấm; thanh vẫn nằm cùng hàng và vừa màn hình hẹp.
- Nút Player bật/tắt cửa sổ desktop, kể cả khi phóng lớn. Thu nhỏ hoặc đóng trên desktop dừng phát và hủy player.
- Bấm vào cửa sổ rồi nhấn Space để phát/tạm dừng. Khi focus nằm trong iframe, YouTube tự xử lý Space; trang cha
  không bắt được sự kiện phím khác nguồn. Bấm nền bên ngoài để thử giữ Space cho Companion: ở trang POC thao tác này
  chỉ đổi nhãn trạng thái, không mở micro. Các ô nhập vẫn nhận khoảng trắng.
- Trên mobile, theo yêu cầu chủ dự án: mũi tên xuống **Ẩn Player** ẩn toàn bộ giao diện Player, video vẫn phát trong
  cùng tab để trả toàn bộ diện tích cho chat. Không có khung video nhỏ, banner hoặc controls nổi. Menu Companion →
  Player mở lại đúng iframe và tiến độ đang phát; từ đó có thể tạm dừng hoặc nhấn **Dừng và đóng Player** (X).
  Chế độ `mode=ui` giữ thao tác đóng cũ.
- File hoặc nút tùy chọn trên mobile cho chọn sáu link thử của báo cáo hoặc nhập link YouTube khác. Chọn nguồn chỉ
  chuẩn bị video; nhấn Phát trong cửa sổ hoặc trong YouTube để phát. Không tự phát khi mở trang hoặc quay lại.
- Tiến độ, thời lượng, volume và trạng thái phát lấy từ API, đồng bộ cả khi dùng controls native. Có tải/buffering,
  lỗi tải API, hết giờ, video riêng tư/đã xóa, cấm nhúng (101/150), lỗi nguồn nhúng (153) và autoplay bị chặn.
  Chỉ hiện thông báo bổ sung khi có lỗi hoặc phát bị chặn; lỗi tải có nút thử lại. Dùng link mở YouTube có sẵn trong
  iframe, không thêm link trùng bên ngoài.
- Giao diện phát bình thường chỉ giữ video, tên/kênh, tiến độ và controls. Đã bỏ badge YOUTUBE, dòng sẵn sàng,
  dòng quảng cáo, link mở YouTube bên ngoài và footer nhắc Space. Trạng thái API giữ trong dữ liệu của cửa sổ để
  điều khiển/kiểm tra, không dựng nhãn hoặc hướng dẫn ẩn chỉ để phục vụ test.
- Thanh cuộn nội dung/menu Player mảnh 8 px, thumb bo tròn màu đỏ trầm trên desktop và hồng trầm trên mobile,
  track theo nền, bỏ nút mũi tên hệ điều hành. Kiểu cuộn chỉ áp dụng trong Player, không can thiệp iframe YouTube.
- Sáu tiêu đề/tên kênh trong danh sách là nhãn thử đã nhập sẵn; video khác hiện tên chung và mã video.
  Không gọi Data API hay suy đoán metadata. Chế độ `mode=ui` vẫn chỉ có sáu mẫu và đồng hồ giả.

## Kiến trúc và vòng đời

- `youtubeUrl.ts`: URL parser, hostname chính xác và mã video 11 ký tự. Nhận watch/youtu.be/shorts/live/embed/v,
  thời điểm bắt đầu `t`, `start`, `#t`; bỏ tracking/playlist, chỉ phát một video. Danh sách host/dạng link đối chiếu
  `backend/shared/youtube.py`. Frontend nhận một URL, từ chối credentials, cổng lạ và đường dẫn thừa; backend tìm
  tối đa ba link trong văn bản. Không thay backend. Đầu vào luôn chuyển thành video ID và link watch chuẩn hóa.
- `youtubeApi.ts`: chia sẻ một Promise/script IFrame API, giữ callback có trước, hạn tải 15 giây và cho retry.
- `useYouTubePlayer.ts`: giữ một iframe trong phiên hiển thị; đổi nguồn bằng `cueVideoById`. Tạo player không phụ
  thuộc nguồn/bố cục nên không nhân đôi trong Strict Mode, kéo/resize hay xoay màn hình. Giữ controls/keyboard gốc,
  `origin`, referrer, playsinline; player phải ready trong 20 giây. Đồng bộ trạng thái qua event và số liệu mỗi 500 ms.
- Đóng hẳn, thu nhỏ desktop, `enabled=false`, unmount, `document.hidden` hoặc `pagehide`: pause/stop/destroy, gỡ iframe và dọn
  timer ngay. Bỏ qua callback muộn khi đã đóng. Hiện lại trang chỉ tạo/cue player ở trạng thái dừng. API dùng chung
  được giữ trong trang để mở lại không tải script lần nữa.
- Ẩn giao diện mobile giữ nguyên `enabled`, source và cây chứa iframe; không restart video. `hidden`/`display:none`
  bỏ toàn bộ diện tích của Player, `inert` và `aria-hidden` bỏ controls khỏi focus/accessibility. Tắt quyền phím và
  vòng focus của Player ngay khi ẩn; mở lại mới nhận phím. Iframe tối thiểu 200×200 khi đang hiển thị. Ẩn tab/rời trang
  vẫn dừng như trước: đây là phát khi quay về chat trong cùng trang, không phải hỗ trợ khóa màn hình/đổi ứng dụng.
- `PlayerShell.tsx`: cửa sổ chung cho giao diện mẫu và YouTube thật. Trạng thái lưu ở `data-status`; chỉ thông báo lỗi
  mới hiện ngoài iframe, không có footer/trạng thái hướng dẫn lặp lại.

## Ranh giới với các giai đoạn sau

Trang xem thử và dữ liệu thử không được import vào ứng dụng chính. Build production chỉ đưa module player dùng
chung và phần ghép Companion vào chunk tải riêng, không đưa trang prototype hay sáu mẫu vào ứng dụng.

Giai đoạn 3 đã nối nút/menu thật, vòng đời và quyền phím: xem [phần ghép Companion](../../src/features/companion/ytplayer/README.md).
Giai đoạn 4 mới nghiệm thu sáu video trên Chrome/Edge,
quảng cáo, CPU/RAM, điện thoại và thiết bị mục tiêu. Queue, playlist, CSS3D và Tauri không thuộc POC này.

## Kiểm tra

- `npm test -- youtubeUrl.test.ts youtubeApi.test.ts useYouTubePlayer.test.tsx`: URL giả/sai, loader dùng chung và
  retry, Strict Mode, controls, nguồn/bố cục, `enabled`, ẩn/hiện trang, callback muộn, lỗi và autoplay bị chặn.
- `npm run test:browser -- youtube-player-preview.spec.ts youtube-player-api.spec.ts`: giao diện mẫu và giao diện
  với API giả, iframe khác nguồn, Space, resize, native controls, lỗi, đóng/ẩn trong lúc tải và mở lại.
- `npm run build`: kiểm tra TypeScript, bao gồm các tệp giao diện mới, và build ứng dụng.

Mô phỏng mobile không thay thế kiểm tra trên điện thoại thật; bước đó vẫn chờ thiết bị chuẩn.

Kết quả ngày 22/10/2026:

- 60 unit test cho URL/loader/hook đạt. Bộ trình duyệt sau cập nhật ẩn Player mobile: 27 đạt, 9 tổ hợp bỏ qua vì chỉ
  dành cho bố cục còn lại; API trong bộ này là giả. Kiểm tra chat giữ nguyên diện tích, Player ẩn không nhận phím/focus,
  ẩn trong lúc API tải, xoay màn hình, mở lại cùng iframe và đóng hẳn dọn player.
  Build frontend đạt.
- Sau dọn UI, bộ trình duyệt vẫn 27 đạt/9 tổ hợp bỏ qua và build đạt. Đã xem YouTube thật ở desktop/mobile và hai
  viewport thấp phải cuộn: nhãn/link/footer thừa không còn, thumb 8 px/bo tròn/màu đúng và không tràn ngang.
- Chromium thật, không chặn/mock request: Tetris `Soy4jGPHr3g` tải iframe chính thức, nhấn Phát có trạng thái playing,
  thời lượng API 143 giây, tiến độ tăng từ 0 lên 3 giây, pause chuyển trạng thái và đóng gỡ iframe (còn 0).
  Space khi iframe focus cũng chuyển sang paused. Đổi nguồn sang 3Blue1Brown `aircAruvnKk` vẫn giữ nguyên phần tử
  iframe và chỉ có một iframe trong trang; bước đó chỉ cue nguồn, không phải nghiệm thu phát toàn bộ video.
- Đã xem iframe YouTube thật ở 1440×900, 390×844, 320×640 và 844×390. Kích thước iframe tương ứng: 610×343,
  344×344, 274×200 và 387×218; không tràn ngang, không lỗi JavaScript.
- Chưa chạy ma trận phát cả sáu video/Chrome/Edge, đo tài nguyên hoặc nghiệm thu điện thoại thật. Không rút ra
  kết luận về quảng cáo từ lượt kiểm tra ngắn. Không cam kết không quảng cáo.

## Rà lỗi 150 và ẩn giao diện mobile (22/10/2026)

- Với API thật, Rick Astley `dQw4w9WgXcQ` và Shape of You `JGwWNGJdvx8` đều trả mã 150 ở desktop và mobile mô phỏng.
  Iframe gốc cũng hiện thông báo video không hoạt động và link xem trên YouTube; không có lỗi JavaScript của Peto.
- Đối chứng một trang HTML tạm chỉ có IFrame API, video ID, controls/origin và nút Phát, không dùng PlayerShell,
  hook hay API giả: hai video vẫn lỗi 150; Tetris phát được, thời gian tăng hơn 2 giây. Điều này cho thấy lỗi không
  phụ thuộc mã player Peto trong môi trường kiểm tra. Không suy diễn rằng hai video bị cấm nhúng ở mọi môi trường.
- Theo tài liệu API, 150 có cùng nghĩa với 101 (chủ video không cho phép nhúng). Không có thao tác play/seek/volume
  nào của Peto sửa được sự từ chối đó; giữ link mở YouTube. Dữ liệu mẫu và link video không bị thay sang bản khác.
- Test giả cho 150 chỉ nằm trong `tests/`/`browser-tests/`; mặc định trang POC dùng script và iframe YouTube thật.
- Chủ dự án đã làm rõ rằng mobile cần ẩn hẳn Player khi quay về chat, không muốn mini player chiếm chỗ. POC hiện
  dùng hành vi đó; quy tắc player nền của YouTube đã được thông tin trong trao đổi. Chưa triển khai production.
- Tetris thật tiếp tục chạy khi ẩn toàn bộ Player và nhập chat ở 390×844, 320×640, 844×390: iframe cũ còn kết nối,
  trạng thái playing và tiến độ tăng từ 2 lên 5 giây; vùng chat trước/sau có cùng tọa độ và kích thước. Mở lại vẫn
  cùng iframe/vị trí, tạm dừng được và X đóng hẳn thì iframe còn 0. Không tràn ngang hoặc lỗi JavaScript.

Tài liệu chính thức dùng khi triển khai: [IFrame API](https://developers.google.com/youtube/iframe_api_reference)
(events, lỗi, destroy) và [player parameters](https://developers.google.com/youtube/player_parameters)
(controls, origin, playsinline, keyboard, kích thước tối thiểu), cùng
[Developer Policies III.I.9](https://developers.google.com/youtube/terms/developer-policies#additional-prohibitions)
(player nền).
