# Player — dọn phiên nghe và hoàn tác, giai đoạn 1 (24/10/2026)

## Phạm vi và kế hoạch đã chốt

Bản đối chiếu `b3b7fa8`. Owner đã commit/deploy đợt điều khiển Player trước và yêu cầu triển khai giai đoạn 1
của kế hoạch cải tiến tiếp theo. Đợt này chưa commit/deploy.

1. Clear Queue, Clear All và hoàn tác một bước, dùng được từ UI lẫn chat Peto — đợt này.
2. Lưu/khôi phục phiên nghe sau F5, khôi phục ở trạng thái dừng.
3. Lịch sử nghe và Previous theo lịch sử thực tế.
4. Giảm âm lượng nhạc trong lúc trò chuyện bằng giọng nói.
5. Nghiệm thu tích hợp, hồi quy và bàn giao.

Các giai đoạn sau chưa triển khai. Playlist cá nhân để sau. Ý tưởng Peto nghe/xem video được tạm gác, không bỏ;
không đưa thu âm, chụp video hoặc suy đoán nội dung video vào đợt này.

## Hành vi

| Thao tác | Kết quả |
| --- | --- |
| `_` / mũi tên xuống | Ẩn UI, tiếp tục phát theo cơ chế desktop/mobile hiện có. |
| X | Dừng và giải phóng iframe, giữ danh sách để mở lại. |
| File → Clear Queue | Xóa toàn bộ phần Tiếp theo; giữ bài hiện tại và trạng thái phát. |
| File → Clear All | Dừng và giải phóng iframe; xóa bài hiện tại và phần Tiếp theo, giữ cửa sổ ở trạng thái trống. |
| File → Hoàn tác | Hoàn tác lần thêm/xóa/di chuyển/dọn gần nhất, đúng một bước. |

Mobile dùng menu ba chấm sẵn có, cùng ba lệnh. Không thêm khung nhỏ, popup xác nhận hoặc lời hướng dẫn thường trực.
Clear Queue/Clear All không xóa yêu thích. Clear All chưa liên quan dữ liệu lịch sử nghe vì tính năng này chưa có.
Hoàn tác Clear All khôi phục bài và thứ tự nhưng **không tự phát**. Hoàn tác sửa phần Tiếp theo không đổi iframe
hoặc tua lại bài hiện tại. Snapshot chỉ giữ một bản trong RAM, tối đa một bài hiện tại và 200 mục Tiếp theo;
không giữ chuỗi snapshot lồng nhau. Hoàn tác không tồn tại qua F5.

Next, chọn nguồn mới, restart, đổi shuffle/repeat hoặc chuyển bài tự động làm mất bản hoàn tác cũ, tránh khôi phục
một lịch phát đã lỗi thời. Metadata và thao tác dọn khi đã trống không ghi đè bản hoàn tác hữu ích. Có thể bấm dọn
lặp lại an toàn. Dọn cũng xóa lịch vòng loop nội bộ để bật loop All sau đó không làm các mục đã dọn xuất hiện lại.

## UI, chat và kết quả thực thi

- Client quảng bá `player_control: 4`; backend chỉ cấp `clear_queue`, `clear_all`, `undo_queue` và prompt tương ứng
  cho client v4. Các tab v1/v2/v3 tiếp tục dùng schema/prompt cũ, không bị ép nâng cấp giữa phiên nghe.
- Chat dùng một lệnh dọn nguyên khối, không lặp xóa từng mục. Undo cần đọc `list_queue` trong cùng lượt rồi gửi
  đúng `queue_revision`; revision tăng sau hoàn tác, không quay lại revision cũ.
- UI và chat gọi cùng đường xử lý. Kết quả có revision, số mục xóa/khôi phục, loại thao tác đã hoàn tác và trạng thái
  `can_undo`. Frontend chờ state React đã commit; Clear All chờ không còn track/queue hoặc native player trước khi
  xác nhận. Backend kiểm kết quả dọn/hoàn tác và giữ nguyên guard lời đáp tự nhiên theo receipt.
- Clear/Undo tăng thế hệ phiên, hủy tìm kiếm/import/đổi nguồn cũ, kể cả lệnh SSE từ lượt chat bắt đầu trước thao tác
  nhưng chưa đến browser. Lệnh dọn do chính Peto đang thực hiện được miễn hủy để nhận receipt; các lệnh cũ khác bị hủy.
  Import playlist kiểm lại thế hệ kể cả khi promise cũ đã resolve. Không tự retry hay replay.
- Token phát vẫn tăng sau Clear All dù không còn source; phát bài mới sau dọn/hoàn tác không thể nhầm với token cũ.
  Event ENDED cũ không làm nhảy bài. Successful clear/undo xóa cache discovery trong lượt backend để đọc lại đúng.
- Không đổi persona/examples, cách chọn model/billing, DB, API key hoặc dependency. Lượt chat có mutation vẫn dùng
  cơ chế kiểm chứng câu trả lời hiện có; không thêm một lần gọi AI riêng chỉ vì bổ sung ba action này.

## Kiểm chứng tự động

| Phần | Kết quả |
| --- | --- |
| Backend | 266 ca đạt trong 11 tệp Player/BYO/clock/prompt/admin. |
| Frontend | 200 ca đạt trong 10 tệp Player/Companion/Hearing/API. |
| Chrome desktop/mobile mô phỏng | 42 ca đạt, 4 bỏ qua theo thiết bị; hồi quy toàn bộ, không retry/flaky. |
| Edge desktop/mobile mô phỏng | Cả 4 ca mới đạt, không retry/flaky; không chạy lại toàn bộ hồi quy Edge. |
| TypeScript browser tests | Đạt. |
| Build frontend | Đạt; còn cảnh báo chunk lớn đã có. |

Ca mới phủ: 200 mục trùng video nhưng khác entry; Clear Queue giữ nguồn; Clear All/Undo không tự phát;
dọn lặp; favorites giữ nguyên; undo chỉ một bước; loop All không hồi sinh mục đã xóa; revision/ENDED cũ;
playlist trả muộn; lệnh chat bắt đầu trước thao tác dọn; dedup; lỗi YouTube 150 rồi dọn/phát mới;
v1/v2/v3 không được cấp lệnh mới; backend từ chối receipt Clear/Undo mâu thuẫn; vòng provider → tool → câu trả lời.

Backend dùng provider/network/DB giả. Browser chạy UI thật với API/backend và YouTube giả, mobile là viewport/touch
mô phỏng. Hồi quy renderer chạy Live2D thật; giọng đọc dùng Audio với PCM tổng hợp, micro Chromium giả.
Không gọi AI/TTS/catalogue/YouTube production; không suy kết quả mock thành chứng nhận lời AI hay phát tiếng thật.
Ảnh File menu desktop/mobile đã xem, bố cục nằm trong màn hình và giữ palette hiện có.

Bằng chứng cục bộ được Git bỏ qua: `.runtime/player-session-stage1/`, gồm JSON riêng theo browser và ảnh
`session-file-menu.png`, `session-after-clear-undo.png`. Bộ browser: `frontend/playwright.player.config.ts`.

Từ `backend/`:

```powershell
../.venv/Scripts/python.exe -m pytest tests/test_player_session_tools.py tests/test_player_reply.py tests/test_player_tools.py tests/test_player_queue_readback.py tests/test_player_discovery_tools.py tests/test_byok.py tests/test_clock_tools.py tests/test_prompt_routing.py tests/test_player.py tests/test_player_catalog.py tests/test_admin.py -q
```

Từ `frontend/`:

```powershell
npx.cmd vitest run tests/playerInput.test.ts tests/playerControl.test.ts tests/player-queue.test.ts tests/player-session.test.ts tests/player-library-playback.test.ts tests/usePlayerLibrary.test.tsx tests/useYouTubePlayer.test.tsx tests/api.test.ts tests/Companion.test.tsx tests/Hearing.test.tsx
npx.cmd tsc -p browser-tests/tsconfig.json
$env:PETO_PLAYER_BROWSER = 'chrome'
npx.cmd playwright test --config playwright.player.config.ts --workers=1
$env:PETO_PLAYER_BROWSER = 'msedge'
npx.cmd playwright test --config playwright.player.config.ts --workers=1 --grep 'bulk clear and|manual clear-all'
npm.cmd run build
```

## Deploy và thử thật

Rebuild frontend + restart backend; backend có thể lên trước hoặc cùng bundle v4. Tab đang mở giữ chức năng cũ và
queue RAM. Nhận ba lệnh mới cần bundle mới: tải lại sau khi kết thúc phiên nghe, vì giai đoạn 2 chưa có và F5 vẫn
xóa phiên nghe. Không migration, không cần cấu hình/key mới. Agent không tự commit/deploy.

Sau deploy, kiểm tra bằng UI và nhắn Peto trên desktop, rồi Android/Chrome:

1. Phát một bài, thêm vài mục (gồm video trùng). Clear Queue giữ bài hiện tại, Undo trả đủ thứ tự/mục trùng.
2. Clear All dừng tiếng, bài và queue trống; yêu thích giữ nguyên. Undo khôi phục nhưng đứng yên; bấm Phát mới chạy.
3. Thêm/xóa/di chuyển một mục rồi Undo. Bấm Undo lần hai không được; chuyển bài/đổi chế độ làm mất Undo cũ.
4. Nhắn “xóa hết cả bài đang phát và hàng đợi”, “xóa phần tiếp theo thôi”, “hoàn tác” và đối chiếu lời Peto với UI.
   Không ép model một mẫu câu; nếu lỗi/không còn bản Undo thì không được nhận đã làm xong.
5. Khi playlist/đổi bài đang chờ, dọn thủ công; kết quả muộn không được tự thêm/phát lại. Ẩn/mở/X vẫn giữ hành vi cũ.

Chưa kiểm thử tính năng mới trên điện thoại thật hoặc bằng AI production. Báo cáo Android trước của owner thuộc
luồng điều khiển cũ, không dùng thay nghiệm thu mới. Gemini BYO vẫn chưa có function calling. Đóng hẳn trang/browser
hủy iframe; desktop phát nền chỉ tồn tại khi trang vẫn hoạt động.
