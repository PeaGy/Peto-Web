# Companion điều khiển Player — nghiệm thu giai đoạn 4 (23/10/2026)

## Phạm vi

Bản đối chiếu `9869571`, sau ba giai đoạn điều khiển, thư viện và tìm/chọn nhạc, cùng hai lần sửa xác nhận.
Đợt này nghiệm thu luồng đã có, bổ sung kiểm tra hủy lệnh và sửa phân loại số liệu vận hành. Chưa commit/deploy.
Không đổi persona, câu chữ xác nhận, UI Player, bridge hoặc cách lưu hàng đợi/yêu thích.

## Bổ sung và sửa lỗi phát hiện

- Thống kê đã cộng token/chi phí của `player_check` và `player_rephrase` vào tổng, nhưng chưa cộng chúng vào
  `side_calls`. Bổ sung hai nhãn vào nhóm lần gọi phụ; cập nhật chú thích trên trang quản trị. Không đếm chúng
  thành tin nhắn/lượt người dùng, không thay cách tính đơn giá hoặc phạm vi billing BYO.
- Lần gọi chính của Companion thiếu nhãn surface trong `_stream_reply`; nay gắn `companion` khi `spoken=True`.
  Các bước kiểm chứng tiếp tục mang nhãn riêng và effort low. Chat thường giữ phạm vi cũ.
- Kiểm tra tích hợp recorder → DB → thống kê với một lượt chat: hai lần gọi chính + kiểm tra/sửa/kiểm lại
  thành năm calls, ba side calls, đúng một turn; tổng token/chi phí vẫn gồm cả năm calls. Số token/tiền trong
  bài kiểm tra là fixture tự tạo, không phải số đo production hoặc dự báo hóa đơn.
- Kiểm tra stream backend: dù browser đã báo thành công, không chuyển bản nháp thành text cho UI/đọc giọng
  trước khi kiểm chứng xong. Hủy trong lúc kiểm chứng không phát câu chưa duyệt, không replay lệnh, dọn context.
- Browser mới: bấm X giữa lúc đổi bài chưa được xác nhận → kết quả lỗi, iframe bị gỡ, không tự mở lại;
  yêu cầu mới dùng revision mới phát được. Bấm Dừng chat lúc chờ → không gửi ack cho lệnh đã hủy, không tự thử
  lại; yêu cầu mới vẫn hoạt động. Hủy chat không phải undo một thao tác media đã gửi; không biết kết quả thì
  giữ trạng thái chưa xác nhận.

## Kết quả tự động

| Phần | Kết quả | Chứng cứ/phạm vi |
| --- | --- | --- |
| Backend | 249 đạt | 10 tệp Player, discovery, queue readback, catalogue, favorites, BYO, clock, prompt routing, admin. |
| Frontend | 197 đạt / 10 tệp | 191 ca Player/Companion/Hearing/API và 6 ca AdminDashboard. |
| Chrome cài trên máy | 38 đạt, 4 bỏ qua theo thiết bị | Desktop và mobile cảm ứng mô phỏng, một worker, không retry, không flaky. |
| Edge cài trên máy | 38 đạt, 4 bỏ qua theo thiết bị | Cùng bộ nghiệm thu và dữ liệu giả, không retry, không flaky. |
| TypeScript browser tests | Đạt | Kiểm tra cấu hình/bài browser, gồm hai ca mới. |
| Build frontend | Đạt | TypeScript + Vite; còn cảnh báo kích thước một số chunk lớn, không lỗi build. |

Backend dùng DB/tài khoản/provider/network giả. Browser chạy React/Player thật với backend và YouTube giả;
không gửi chat AI/TTS hoặc catalogue/YouTube production. Ca giọng đọc chạy Audio với PCM tổng hợp; micro là thiết
bị Chromium giả. Ca Live2D chạy renderer thật. Kết quả mock kiểm đường xử lý, không chấm chất lượng ngôn ngữ của AI.

Hồi quy gồm: v1/v2/v3, owner/expiry/dedup, dữ liệu giả/ID sai, cold start, đổi video một iframe, loop/shuffle/Next,
queue 200 mục, favorites 500 mục và sức chứa, giữ nguồn khi append playlist, video+list chỉ thêm riêng video,
readback sau move, lỗi quota/150/autoplay, `_`/mũi tên/X, desktop phát nền, mobile ẩn trang/rời Companion,
resize, phím Space/micro và phối hợp giọng đọc/renderer. Bốn ca bỏ qua theo thiết bị thuộc các hành vi desktop/mobile
khác nhau, không phải ca lỗi bị bỏ qua.

Bộ chạy: `frontend/playwright.player.config.ts`. Dữ liệu raw, ảnh và trace cục bộ được Git bỏ qua tại
`.runtime/player-control-stage4/`; báo cáo JSON riêng `chrome-results.json` và `msedge-results.json`.
Chrome 155.0.8059.86, Edge 155.0.4283.62; dùng channel của bản cài trên máy, không dùng Chromium bundled thay thế.

Tái hiện từ `backend/`:

```powershell
../.venv/Scripts/python.exe -m pytest tests/test_player_reply.py tests/test_player_tools.py tests/test_player_queue_readback.py tests/test_player_discovery_tools.py tests/test_byok.py tests/test_clock_tools.py tests/test_prompt_routing.py tests/test_player.py tests/test_player_catalog.py tests/test_admin.py -q
```

Từ `frontend/`:

```powershell
npx.cmd vitest run tests/playerInput.test.ts tests/playerControl.test.ts tests/player-queue.test.ts tests/player-library-playback.test.ts tests/usePlayerLibrary.test.tsx tests/useYouTubePlayer.test.tsx tests/api.test.ts tests/Companion.test.tsx tests/Hearing.test.tsx tests/AdminDashboard.test.tsx
npx.cmd tsc -p browser-tests/tsconfig.json
$env:PETO_PLAYER_BROWSER = 'chrome' # hoặc msedge; chạy tuần tự vì cùng cổng 5179
npx.cmd playwright test --config playwright.player.config.ts --workers=1
npm.cmd run build
```

## Android/Chrome và AI thật

Trong lượt này chủ web báo đổi bài, sửa vị trí hàng đợi, ẩn Player, mở lại và dừng đều ổn; đã xác nhận thực hiện
**bằng cách nhắn Peto trong chat**, không chỉ bấm controls. Đây là báo cáo máy thật của chủ web, agent không điều
khiển điện thoại. Cấu hình đã khai báo trước: Xiaomi, Android 13, Chrome 155.0.8059.87; không đo lại phiên bản
hoặc xác minh hash deploy trong đợt này. Không coi bài kiểm tra Android của thư viện cũ là bằng chứng chat mới.

“Lời xác nhận” là câu Peto trả lời sau yêu cầu điều khiển, không phải popup/nút xác nhận mới. Chủ web chưa báo
sai lệch thao tác trong các bước vừa thử; chưa có trích dẫn cặp yêu cầu/lời đáp mới để chấm độ tự nhiên. Không
suy rộng thành bảo đảm không bịa hoặc chứng nhận mọi câu/ngôn ngữ/model.

Các trường hợp còn dùng để thử AI thật theo nhu cầu, không cần F5 hoặc xóa phiên đang nghe:

| Tình huống | Đối chiếu thực tế |
| --- | --- |
| “What are we listening to?” | Title/kênh/trạng thái từ status mới, không nhớ tên từ lời cũ. |
| “Có bao nhiêu bài yêu thích?” | Tổng khớp tài khoản; lỗi đọc không biến thành 0. |
| “Thêm hết yêu thích vào queue.” | Giữ bài đang nghe; báo số thêm/bỏ trùng/thiếu sức chứa đúng. |
| “Chuyển bài thứ hai lên đầu” / “xóa bài thứ ba” | Chỉ phần Tiếp theo, đúng entry/revision; tên và vị trí khớp UI. |
| “Bài tiếp theo là gì?” | Phân biệt auto với explicit Next, nhất là loop one/shuffle. |
| “Mở Player và bật một bài Peto thích.” | Chọn từ metadata thật, không giả vờ đã nghe nội dung video. |
| “I'm tired.” → lời đề nghị → “Sure.” | Chỉ đề nghị chưa phát; sau đồng ý mới chọn và chờ phát thật. |
| Thêm URL video có `list` / nhập playlist riêng | Một video hoặc playlist đúng ý; append không đổi bài; báo partial/truncated đúng. |
| Đổi bài lỗi/blocked/timeout, rồi yêu cầu mới | Không nhận thành công hay tự lặp lệnh trong cùng turn; lượt mới được thử lại. |
| Đóng X/dừng chat trong lúc đang tìm/đổi bài | Phản hồi muộn không tự mở lại hoặc phát lại; không bịa nguyên nhân. |

Đối chiếu câu chat với video/hàng đợi thật, không bắt Peto lặp một mẫu câu hoặc bắt mỗi câu phải nhắc title.
Khi cần điều tra, `player_trace.reply_guard` phân biệt `natural_verified`, `natural_rewritten` và `receipt_fallback_*`;
commands cho biết action/sent/ok/error và trạng thái. Không dùng lời “done” thay bằng chứng thực thi.
Các bước checker/rephrase có tăng token/độ trễ; chưa đo latency/chi phí AI thật trong đợt này.

## Bàn giao

Các mục tự động đã đạt; bộ nghiệm thu và sửa thống kê sẵn sàng commit. Deploy restart backend khi không có
lượt chat đang chạy để nhận cách phân loại; rebuild frontend để nhận chú thích quản trị. Không migration/key/dependency mới, không cần F5 tab
Companion đang nghe. Không cần thay iframe, làm mất queue RAM hoặc thử lại video production chỉ vì đổi thống kê.

Không tự commit/deploy. Giới hạn còn lại: Gemini BYO chưa hỗ trợ function calling; ý định/ngôn ngữ và semantic
checker vẫn phụ thuộc model; trạng thái IFrame API không chứng minh loa đã phát tiếng. Đóng hẳn trang/browser
hủy iframe; desktop phát nền chỉ khi trang còn hoạt động. Không thêm tính năng mới ngoài kế hoạch trong đợt nghiệm thu.
