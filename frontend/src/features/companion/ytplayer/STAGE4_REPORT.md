# Nghiệm thu Player — giai đoạn 4, 22/10/2026

## Trạng thái

Bản sửa đang ở máy phát triển, trên nền commit `38239c8`, chưa commit/deploy. Phần điện thoại thật **chưa nghiệm thu**:
chủ web chọn Android/Chrome, hiện chưa có kênh điều khiển/ADB để truy cập máy thật. Không lấy mô phỏng làm kết quả máy thật.

## Thay đổi trong đợt này

- Bỏ dòng idle “Trả lời ngắn bằng tiếng Anh” đã cũ. Tên provider BYO và trạng thái đang xử lý vẫn hiển thị khi cần.
- Desktop giữ cùng player khi đổi tab trình duyệt, thu nhỏ cửa sổ hoặc chuyển sang Trò chuyện/Cài đặt trong Peto.
  Cửa sổ Player ẩn khi rời Companion, trả quyền phím và tương tác cho trang hiện tại. Đổi chiều rộng desktop không
  làm mất quyền phát nền: nhận diện bằng khả năng con trỏ, độc lập với bố cục.
- `_`/nút icon chỉ ẩn và giữ phát. X, đăng xuất, unmount và `pagehide` luôn giải phóng iframe/timer. Mobile giữ
  hành vi đã duyệt: mũi tên ẩn hết UI và phát trong cùng tab, không thêm mini player; rời Companion/ẩn trang thì dừng.
- Bỏ lần `cueVideoById` thừa ngay sau constructor. Trước sửa, đã gặp lần mở đầu Tetris đi qua buffering rồi trở
  về cued sau khi bấm Phát; sau sửa, các lượt cold start bên dưới phát bằng nút ngoài iframe. Có hồi quy cue phản hồi
  muộn và đổi nguồn trước `onReady`.
- Lượt Edge phát hiện cả lúc đổi bài cũng có thể bấm Phát trước khi cue hoàn tất. Đã chờ sự kiện cued/playing
  rồi mới bật Phát/seek, bỏ qua trạng thái nguồn cũ trong lúc chuyển. Có timeout 20 giây và hồi quy tương ứng;
  âm lượng vẫn điều chỉnh được. Không thêm retry tự phát hoặc lách lỗi của YouTube.

**Thoát hẳn trình duyệt/đóng tab Peto không thể giữ iframe phát.** Trang đã kết thúc thì không còn player chạy.
Đợt này hỗ trợ nền khi trang còn sống, không thêm cửa sổ phụ hay tiến trình desktop. Khi khôi phục sau `pagehide`
chỉ chuẩn bị nguồn, không tự phát. Tham khảo [vòng đời trang Chrome](https://developer.chrome.com/docs/web-platform/page-lifecycle-api).

## Môi trường và phương pháp

- Windows (kernel 10.0.26300), Intel Core i5-10300H 2.50 GHz, 8 CPU logic.
- Google Chrome 155.0.8059.86; Microsoft Edge 155.0.4283.62.
- Bản frontend build bằng Vite, phục vụ loopback `127.0.0.1:5188`; không thử trên production.
- Backend/tài khoản Peto giả, Live2D Hiyori thật, YouTube iframe/API thật. Không dùng profile cá nhân, khóa AI hoặc
  dịch vụ AI/TTS trả phí. Kết quả không chứng minh hoạt động của đăng nhập/backend production.
- Sáu video: mỗi video phát được lấy mẫu khoảng 15 giây, đọc thời gian/paused/kích thước video và trạng thái quảng
  cáo trong iframe. Xác nhận nội dung bằng link gốc, tiêu đề và duration; không tính “đã cue” là “đã phát”. Đổi bài
  giữ một iframe. Đây là mẫu ngắn, không kiểm tra hết video dài gần một giờ.
- Các lượt đầu có focus emulation của Playwright nên không thực sự đổi `document.hidden`, kể cả có cửa sổ. **Không
  tính chúng là đạt ca chuyển tab/thu nhỏ.** Lượt xác nhận riêng mở profile tạm, nối CDP với `noDefaults: true` ở
  context mặc định, không bật focus emulation/cờ chống throttling; kiểm tra `document.hidden` thật và tiến độ.
  [Tài liệu tùy chọn noDefaults](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp-option-no-defaults).

## Kiểm tra tự động

- Nhóm App, Companion, Hearing, Providers, URL, loader và hook: 278 ca đạt trước khi thêm bốn hồi quy cold start/cue;
  sau sửa hook, chạy lại toàn bộ file hook: **21/21 đạt**, gồm bốn ca mới. Tổng phạm vi nhóm hiện là 282 ca.
- Chạy lại bốn bộ browser sau sửa cuối: **37 đạt, 13 bỏ qua theo bố cục**, không có ca thất bại. YouTube/backend giả;
  có ca dùng renderer Live2D thật, micro Chromium giả và tiếng PCM tổng hợp qua Audio thật.
- Bao phủ parser hostname giả/URL sai; loader một lần; Strict Mode/một iframe; đổi nguồn; API lỗi/retry; lỗi 101/150/153;
  autoplay bị chặn; đóng khi đang tải; vòng đời desktop/mobile/pagehide/đăng xuất; Space/PTT; menu, kéo, resize và volume.
- Build TypeScript/Vite đạt. Không thay backend, model hoặc cơ chế Nhún theo nhạc.

## Sáu video thật

Lượt xác nhận cuối của ma trận/tài nguyên dùng Chrome và Edge không cửa sổ. Các ca chuyển tab/thu nhỏ tự nhiên
được tách sang cửa sổ thật như mô tả bên dưới. Hai lệnh ma trận cuối đều kết thúc với mã 0, không có lỗi JavaScript.

| Video | Chrome không cửa sổ | Edge không cửa sổ |
|---|---|---|
| [Miku concert](https://www.youtube.com/watch?v=HDz9dSuAI4s) | Phát, tiến độ +13,62 s | Phát, +13,58 s |
| [DECO*27 — Vampire](https://www.youtube.com/watch?v=e1xCOsgWG0M) | Phát, +13,60 s | Phát, +13,57 s |
| [Tetris](https://www.youtube.com/watch?v=Soy4jGPHr3g) | Phát, +13,57 s | Phát, +15,00 s |
| [Rick Astley](https://www.youtube.com/watch?v=dQw4w9WgXcQ) | Lỗi 150 từ YouTube | Lỗi 150 từ YouTube |
| [Shape of You](https://www.youtube.com/watch?v=JGwWNGJdvx8) | Lỗi 150 từ YouTube | Lỗi 150 từ YouTube |
| [3Blue1Brown](https://www.youtube.com/watch?v=aircAruvnKk) | Phát, +13,56 s | Phát, +13,59 s |

Mỗi nguồn vẫn một iframe. Lượt Edge sau sửa chờ cue không còn timeout Phát hoặc cần nút native để cứu như lượt
trước đó. Chrome cũng không cần nút native để cứu lần Phát ngoài iframe. Lỗi 150 là trường hợp không
cho phép nhúng theo [IFrame API](https://developers.google.com/youtube/iframe_api_reference?hl=en#onError);
giao diện báo lỗi và cho mở trên YouTube. Kết quả trước của TV trong game khác môi trường nhúng, không chứng minh
hai video đó phải phát trong Peto. Không coi lỗi nguồn nhúng là lý do để đổi sang luồng âm thanh/video khác.

Không thấy quảng cáo trong các mẫu bốn video phát được trên Chrome. Đối chứng trực tiếp 3Blue1Brown ở lượt cuối:
quảng cáo có duration khoảng 35,58 giây, 10/10 mẫu trong cửa sổ quan sát 15 giây là quảng cáo; không xem hết quảng
cáo. Một lượt Chrome có cửa sổ trước đó không thấy quảng cáo trong 15 giây. Chính sự khác nhau giữa các lượt là
lý do **không cam kết không quảng cáo**. Thương hiệu
Samsung thuộc báo cáo nghiên cứu trước của chủ web, không suy đoán thương hiệu của lượt mới chỉ từ duration.
Edge ở lượt xác nhận cuối không thấy quảng cáo trong mẫu bốn video nhúng, cũng không thấy trên đối chứng trực
tiếp 3Blue1Brown trong 15 giây. Không suy rộng các kết quả này sang lần phát/tài khoản/thiết bị khác.

## Hành vi thật và bố cục

- Chrome với focus tự nhiên: thu gọn Player +0→6 s; đổi tab trình duyệt, `document.hidden=true`, +6→12 s;
  thu nhỏ cửa sổ, `document.hidden=true`, +12→18 s; chuyển sang Trò chuyện +18→24 s. Giữ nguyên iframe.
- Edge với focus tự nhiên: đổi tab, `document.hidden=true`, +6→12 s, giữ iframe; `_` và chuyển sang Trò chuyện
  đều giữ phát. Ca thu nhỏ cửa sổ qua CDP trả windowState=normal nên **chưa tính đạt**, cần xác nhận thao tác
  thu nhỏ cửa sổ Edge bằng tay. Đây là kết quả tách riêng, không thay bằng sự kiện visibility giả.
- Controls thật trên Chrome/Edge: phát/tạm dừng, seek khoảng 60 s, volume 100→0→100, Space khi focus iframe đều đạt.
- Mobile mô phỏng trên Chrome desktop: 390×844, 320×640 và 844×390, vùng iframe lần lượt khoảng 342×342,
  272×200 và 385×216; không tràn ngang, resize không thay iframe. Ẩn Player rồi nhập chat tiến độ +4→8 s,
  mở lại cùng iframe, X gỡ iframe. Không có UI/mini player chiếm diện tích chat khi ẩn.
- Các ca micro/giọng đọc dùng fake YouTube và thiết bị/PCM tổng hợp; chưa có nghiệm thu micro loa thật trên điện
  thoại, chưa đo tiếng nhạc lọt micro hay khử vọng.

## Thời gian và tài nguyên

| Mốc (ms) | Chrome | Edge |
|---|---:|---:|
| Mở shell lần đầu | 372 | 360 |
| Gửi URL đầu → UI sẵn sàng | 1.079 | 1.666 |
| Click Phát thực nhận trong DOM → API playing, Tetris | 2.205 | 1.628 |
| Đổi nguồn khi API đã nạp → UI sẵn sàng, các video phát được | 456–531 | 197–529 |
| Click Phát trong DOM → API playing, các lượt đổi nguồn phát được | 697–4.278 | 599–1.023 |

Mốc UI đo từ yêu cầu click của công cụ, có chi phí thao tác và polling; sau sửa, đổi nguồn phải có xác nhận cue
mới bật Phát. Mốc click→playing lấy timestamp trong chính trang để tách thời gian công cụ chờ click. Không phải
phép đo first decoded frame hay SLA. Có lấy mẫu tiến độ/kích thước video sau đó để xác nhận nội dung thực sự chạy.
Lượt Vampire trên Chrome mất khoảng 4,3 giây sau click, nên không hứa đổi bài tức thì. Lượt Edge trước khi sửa có
chờ buffer/cue lâu và cần nút native cho Vampire; lưu ở `final/msedge.json`, không tính là lượt nghiệm thu đạt.

Mỗi mẫu CPU dài khoảng 8 giây, tổng các tiến trình của đúng profile trình duyệt kiểm thử qua CDP. CPU **100% là
một CPU logic**; trên máy 8 CPU logic, 61% tương đương khoảng 7,6% tổng máy. Private MiB là bộ nhớ commit;
working set cộng theo tiến trình có thể tính trùng trang dùng chung và không gồm VRAM. Chạy từng lượt tuần tự.
Mẫu có tiến trình kết thúc giữa hai thời điểm không tính được CPU cuối của tiến trình đó; các số là xấp xỉ, không
xếp hạng hai trình duyệt. YouTube tự chọn chất lượng; không ép cùng độ phân giải để làm benchmark codec/GPU.

| Trình duyệt / trạng thái | CPU (% một CPU logic) | Private MiB | Tổng working set MiB | iframe / canvas |
|---|---:|---:|---:|---|
| Chrome: Companion, TV chưa nạp API | 42,4 | 377,8 | 675,6 | 0 / 1 |
| Chrome: Tetris đang phát, Hiyori hiển thị | 61,1 | 603,3 | 1.012,2 | 1 / 1 |
| Chrome: phát nền trong Trò chuyện | 14,8 | 467,3 | 846,0 | 1 / 0 |
| Chrome: sau X, quay lại Companion | 32,8 | 455,7 | 810,1 | 0 / 1 |
| Edge: Companion, TV chưa nạp API | 24,4 | 365,8 | 659,6 | 0 / 1 |
| Edge: Tetris đang phát, Hiyori hiển thị | 60,6 | 574,4 | 947,7 | 1 / 1 |
| Edge: phát nền trong Trò chuyện | 16,4 | 458,1 | 814,4 | 1 / 0 |
| Edge: sau X, quay lại Companion | 36,0 | 437,3 | 761,2 | 0 / 1 |

Private tăng khoảng 226 MiB trên Chrome, 209 MiB trên Edge khi mở/phát; sau X iframe đã mất nhưng browser vẫn giữ cache/tiến trình.
CPU và RAM các mẫu ngắn dao động; không lấy một lần giảm CPU sau đóng để kết luận tiết kiệm tuyệt đối, cũng không
lấy RAM chưa về baseline để kết luận rò bộ nhớ. Chưa có thử mở/đóng lặp lâu, đo nhiệt/pin hay ngưỡng tài nguyên
trên điện thoại thật. Cần các mục đó trước khi tuyên bố chi phí tài nguyên đạt trên mọi thiết bị mục tiêu.

## Chạy lại và chứng cứ

Trong `frontend`, build rồi mở preview loopback port 5188. Công cụ chỉ chạy khi thêm `--live` và chỉ nhận base
loopback; tạo profile tạm riêng. Ví dụ:

```powershell
npm run build
npm run preview -- --host 127.0.0.1 --port 5188 --strictPort
# Ở cửa sổ khác:
node ops/youtubePlayerCheck.mjs --live --browser msedge
node ops/youtubePlayerCheck.mjs --live --browser chrome --headed --background-only --observe 5
```

Raw JSON và ảnh trong thư mục ignored `.runtime/youtube-tv-stage4/`: `verified/chrome.json` và
`verified/msedge.json` là hai ma trận cuối, có số đo click trong trang, tài nguyên và đối chứng quảng cáo;
`verified/chrome-mobile-emulated.png` là ảnh mobile mô phỏng. `visibility-native/chrome.json` xác nhận hidden
thật; `visibility-native/msedge.json` ghi cả ca tab đạt và ca windowState chưa xác nhận được. Các lượt trước trong
`gui/`, `final/` và `chrome.json` tại gốc là chứng cứ bổ sung/chẩn đoán, không thay kết quả cuối.
Kết quả browser mock ở `frontend/playwright-report/`. Báo cáo này lưu các số cần đọc, không phụ thuộc việc giữ cache.

## Phần còn lại để chốt nghiệm thu

1. Thao tác thu nhỏ cửa sổ Edge bằng tay: công cụ CDP chưa xác nhận được trạng thái minimized, không đánh dấu đạt.
2. Android/Chrome thật: ghi mẫu máy, phiên bản OS/Chrome; mở bốn video khả dụng và kiểm tra hai lỗi nhúng.
3. Kiểm tra xoay máy, bàn phím nhập URL/chat, safe area, controls, thanh cuộn, mũi tên ẩn toàn bộ UI và X dừng;
   thử rời Companion/ẩn tab theo vòng đời đã chốt.
4. Micro, giọng đọc và video cùng chạy trên loa/tai nghe thật; kiểm tra Space với bàn phím ngoài nếu dùng.
5. Đo tài nguyên/nhiệt/pin trong lượt dài trên điện thoại. Tauri/WebView, CSS3D, queue, tìm kiếm và playlist là phạm vi khác.

Không tự triển khai production trong đợt nghiệm thu này.
