# Player — lưu/khôi phục phiên nghe, giai đoạn 2 (24/10/2026)

## Phạm vi

Bản đối chiếu `7811606`. Owner đã commit/deploy giai đoạn 1 và báo Clear Queue, Clear All, Hoàn tác đều thử thành
công; đợt này triển khai bước lưu/khôi phục sau F5. Chưa commit/deploy. Chỉ sửa frontend, không đổi backend,
persona/examples, tool schema v4, DB, API key hoặc dependency. Không thêm lịch sử/Previous, giảm âm lượng voicechat,
playlist cá nhân hoặc khả năng Peto nghe/xem video.

## Hành vi

- Lưu bài hiện tại, vị trí nghe, phần Tiếp theo (tối đa 200 mục, giữ mục trùng và thứ tự), âm lượng/mute,
  loop/shuffle và thứ tự vòng loop nội bộ. Không coi thứ tự vòng loop là tính năng lịch sử nghe.
- Sau F5 hoặc mở lại trang trong cùng trình duyệt/tài khoản: phục hồi dữ liệu trong bộ điều khiển kín, cửa sổ vẫn
  đóng và không tải IFrame API/video. Người dùng mở Player thì cue ở vị trí đã lưu, trạng thái dừng; bấm Phát
  hoặc yêu cầu Peto phát mới bắt đầu. Nếu chỉ có queue thì giữ queue, chưa tự chọn bài làm current.
- Peto đọc status/list_queue/next_track được ngay sau F5 khi cửa sổ chưa mở. Native bridge chờ bộ điều khiển lazy
  thay vì báo trống tạm thời. Metadata có thể được làm mới bằng API hiện có, không phát video để đọc metadata.
- Restart/loop dùng điểm bắt đầu gốc của bài, không dùng vị trí phục hồi làm điểm bắt đầu vòng mới.
- Clear Queue cập nhật bản lưu ngay, vẫn giữ current. Clear All xóa bản lưu ngay; F5 không phục hồi danh sách vừa
  dọn. Hoàn tác Clear All trong phiên hiện tại có thể lưu lại danh sách, vẫn dừng. Undo không tồn tại qua F5.
- `_`/mũi tên tiếp tục ẩn phát nền; X vẫn dừng/giải phóng iframe và giữ danh sách. Ẩn/rời Companion trên mobile,
  pagehide hoặc logout vẫn dừng theo vòng đời cũ. Đóng hẳn trang/browser không thể giữ iframe phát nhạc.

## Lưu trữ và giới hạn

`playerSession.ts` giữ một snapshot có phiên bản trong localStorage, khóa `peto-player-session-v1:<account-id>`.
App truyền ID công khai đã băm từ phiên đăng nhập qua Companion; cây Companion được key theo tài khoản, không dùng
owner secret hoặc token làm khóa lưu. Không có ID tài khoản thì không lưu/khôi phục. Tài khoản khác không dùng
snapshot này; đăng nhập lại cùng tài khoản trên cùng trình duyệt có thể khôi phục ở trạng thái dừng.

Đây là dữ liệu cục bộ của trình duyệt/origin, chưa đồng bộ qua máy hay trình duyệt khác. Xóa dữ liệu website sẽ
mất phiên cục bộ; yêu thích vẫn theo tài khoản/backend. Các tab có UI độc lập, chưa đồng bộ phát nhạc trực tiếp.
Đối chiếu snapshot trước khi tự lưu ngăn timer/pagehide của tab cũ ghi đè thay đổi mới hoặc Clear All từ tab khác;
một thao tác chỉnh queue/nguồn mới do người dùng chủ động có thể ghi snapshot của tab đó.

Queue/nguồn/chế độ/dọn được ghi đồng bộ khi chỉnh. Tiến trình phát được nhớ trong RAM từ poll, ghi xuống tối đa
mỗi 5 giây; pause, X, visibilitychange, pagehide và unmount flush lại. Capture lifecycle đọc native trước khi
YouTube bị giải phóng. Âm lượng cuối giữ trong ref để sự kiện ẩn trang tới sau pagehide không ghi đè bằng snapshot
React cũ. Khi browser/thiết bị bị đóng đột ngột không có lifecycle, vị trí có thể lùi khoảng một chu kỳ lưu.

Codec giới hạn kích thước đọc/ghi, số mục, loại dữ liệu, thời gian, âm lượng và độ dài metadata Unicode. Snapshot
sau serialize vượt giới hạn bị từ chối ghi, giữ bản lưu hợp lệ trước đó và báo lỗi. URL dựng lại từ
video ID hợp lệ; không tin URL trong storage. Dữ liệu hỏng/phiên bản lạ bị bỏ an toàn. Entry key được tạo lại,
revision/token bắt đầu mới, autoplay luôn false; không lưu source intent, command, nonce, chat receipt hay Undo.
Không replay lệnh hoặc tự thử lại khi phục hồi. Nếu lưu bị chặn/hết chỗ, Player tiếp tục dùng trong RAM và báo
lỗi bằng vùng lỗi sẵn có; khi đó không bảo đảm thay đổi mới tồn tại sau F5. Lỗi chưa lưu được giữ qua các nhịp
throttle, chỉ xóa sau lần ghi thực sự thành công. Không gửi phiên nghe lên backend.

## Kiểm chứng

| Phần | Kết quả |
| --- | --- |
| Frontend | 217 ca đạt / 11 tệp Player/Companion/Hearing/API. |
| Chrome desktop/mobile mô phỏng | Hồi quy 48 ca đạt, 4 bỏ qua theo thiết bị; hai ca F5 kiểm lại sau chốt biên cuối đều đạt. Không retry/flaky. |
| Edge desktop/mobile mô phỏng | Cả 8 ca lưu/khôi phục và yêu thích sau F5 đạt; không retry/flaky. Không chạy lại toàn bộ Edge. |
| Build frontend | Đạt; cảnh báo chunk lớn đã có. |
| TypeScript browser tests | Đạt. |

Ca mới: F5 thật với 200 mục và bản trùng; thứ tự shuffle/loop; chỉnh native time/volume ngay trước pagehide,
chưa chờ poll; mute=0; cue chưa phát báo time=0 vẫn giữ điểm phục hồi, seek/pause thực tế về 0 vẫn được nhận;
phục hồi dừng/không iframe trước khi mở; native chat đọc/phát/restart/Next sau phục hồi;
Clear Queue/Clear All rồi F5; Undo không qua F5; queue-only; đổi tài khoản; không trùng entry key sau thêm mới;
quota/storage bị chặn; snapshot hỏng/quá cỡ/sai ID; Unicode; tab cũ không hồi sinh snapshot đã dọn.
Các ca kiểm codec/storage/tab cũ thuộc unit test; không gắn nhãn tất cả là browser test. Hai chốt cuối thêm kiểm
ghi snapshot quá cỡ và cue chưa phát báo time=0; kiểm lại nhóm F5 Chrome và nhóm lưu/khôi phục Edge sau sửa này.

Browser chạy React/Player thật với API/backend và YouTube giả, mobile là viewport/touch mô phỏng. Fake YouTube
được sửa để thực hiện `playerVars.start` như constructor thật, không bỏ qua điểm phục hồi. Ca renderer/voice
hồi quy dùng Live2D thật, PCM tổng hợp và micro giả. Không gọi AI/TTS/catalogue/YouTube production; không đo tiếng
ra loa, latency hay quota thật. Chưa kiểm thử đợt này trên Android/Chrome thật. Backend không thay đổi nên không
chạy lại bộ 266 ca backend từ giai đoạn 1 và không trình bày con số đó như kết quả mới.

Bằng chứng Git-ignored tại `.runtime/player-session-stage2/`: JSON riêng theo browser và ảnh
`restored-player-stopped.png`. Kết quả ban đầu đã bắt lỗi âm lượng native vừa chỉnh bị snapshot cũ ghi đè trong
chuỗi pagehide → visibilitychange; đã thêm ca riêng cho việc giữ native state cuối và chạy lại sau sửa.
Đã xem ảnh phục hồi stopped trên desktop Chrome và mobile Edge, bố cục/controls giữ giao diện đã duyệt.

Từ `frontend/`:

```powershell
npx.cmd vitest run tests/playerInput.test.ts tests/playerControl.test.ts tests/player-queue.test.ts tests/player-session.test.ts tests/playerSession.test.ts tests/player-library-playback.test.ts tests/usePlayerLibrary.test.tsx tests/useYouTubePlayer.test.tsx tests/api.test.ts tests/Companion.test.tsx tests/Hearing.test.tsx
npx.cmd tsc -p browser-tests/tsconfig.json
$env:PETO_PLAYER_BROWSER = 'chrome'
npx.cmd playwright test --config playwright.player.config.ts --workers=1
$env:PETO_PLAYER_BROWSER = 'msedge'
npx.cmd playwright test --config playwright.player.config.ts --workers=1 --grep 'F5 restores|saved Clear Queue|listening snapshots|yêu thích thật'
npm.cmd run build
```

## Bàn giao và thử thật

Chỉ cần rebuild/deploy frontend, không cần restart backend hay cấu hình mới. Các tab đang chạy bundle giai đoạn 1
vẫn chỉ có queue trong RAM: tải lại sau khi kết thúc phiên nghe để nhận bundle mới. Không có cách lấy lại queue
chưa được bản cũ lưu trước lần tải lại đầu tiên. Từ bundle mới trở đi, cùng tài khoản/trình duyệt sẽ có phục hồi.
Không tự commit/deploy.

Sau deploy thử trên desktop rồi Xiaomi/Android 13/Chrome mà owner dùng:

1. Phát một bài, tua tới giữa, chỉnh âm lượng; thêm vài bài có mục trùng, bật loop/shuffle. F5: chưa có tiếng,
   chưa có cửa sổ; mở Player thấy đúng bài/vị trí/queue/chế độ, bấm Phát mới chạy. Thử cả mute.
2. Nhắn Peto hỏi bài/queue ngay sau F5, chưa mở Player; tên/số lượng phải khớp bản lưu. Nhờ phát rồi restart/Next.
3. Clear Queue → F5 giữ current nhưng queue trống. Clear All → F5 trống hoàn toàn. Không còn Hoàn tác sau F5;
   Hoàn tác trước F5 thì danh sách khôi phục được lưu lại ở trạng thái dừng.
4. Ẩn mobile để chat không có khung phụ; mở lại/dừng/X như trước. Rời Companion/ẩn tab mobile/logout vẫn dừng.
5. Tài khoản khác không thấy phiên của tài khoản trước. Cùng tài khoản ở trình duyệt/máy khác chưa đồng bộ phiên.

Sau khi nghiệm thu mới chuyển giai đoạn 3 (lịch sử nghe và Previous thực tế). Nghe/xem video cùng Peto vẫn tạm gác.
