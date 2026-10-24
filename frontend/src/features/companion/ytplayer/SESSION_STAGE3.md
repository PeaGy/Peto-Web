# Player — lịch sử nghe và Previous, giai đoạn 3 (24/10/2026)

## Phạm vi

Bản đối chiếu `f6c1601`. Owner đã commit/deploy sửa resume và xác nhận F5 phát tiếp đúng mốc; yêu cầu giai đoạn 3.
Đợt này thêm lịch sử nghe và Previous thực tế, dùng chung UI/chat Peto. Chưa commit/deploy. Chưa triển giai đoạn 4
giảm âm lượng khi voicechat hoặc giai đoạn 5 nghiệm thu tích hợp. Nghe/xem video cùng Peto vẫn tạm gác.

## Giao diện và hành vi

- File → **Lịch sử nghe**; mobile mở từ menu ba chấm hiện có. Dùng panel danh sách đã có: title/kênh, giờ/ngày,
  bấm bài để phát lại hoặc dấu cộng để thêm vào queue. Có nút thùng rác **Xóa lịch sử nghe** riêng ở đầu panel.
- Nút trước nút Phát trở thành **Bài trước**. **Phát lại từ đầu** vẫn trong menu Play, giữ đúng ý nghĩa restart.
  Previous đi theo đường nghe thực tế, không theo vị trí ngẫu nhiên trong queue. Ví dụ A → B → C, Previous hai lần
  quay B rồi A; Next đi B rồi C. Bài rời được đặt đầu queue; giữ nguyên phần đuôi, loop và shuffle.
- Với loop All, một mục phù hợp trong queue được chuyển thành current, không nhân đôi mục đó. Các mục trùng khác
  vẫn giữ. Nếu queue đã đủ 200 và không có mục phù hợp để chuyển ra, Previous báo cần chừa một chỗ; không âm thầm
  bỏ bài hoặc vượt sức chứa để thêm bài hiện tại vào queue.
- Lịch sử tối đa **100 lượt gần nhất**, mới nhất trước. Chỉ ghi sau khi source/request khớp và native YouTube báo
  đúng video/state=1. Chọn link nhưng chưa phát, lỗi nhúng, autoplay bị chặn, response/event cũ không tạo lượt nghe.
- Pause/resume cùng nguồn không tạo lượt mới. Các lần phát liên tiếp cùng video/điểm bắt đầu gộp thành một mục và
  cập nhật thời điểm gần nhất; loop one/restart không làm đầy danh sách bằng bản sao. A → B → A vẫn có hai lượt A.
- Lịch sử phản ánh **bắt đầu phát**, không chứng minh đã nghe trọn bài, có tiếng ra loa hay AI đã hiểu nội dung.
  Previous có đường điều hướng riêng tối đa 100 mục để quay nhiều lần không mắc vòng B ↔ C do log mới nhất thay đổi.
- F5 giữ lịch sử và đường Previous, vẫn khôi phục stopped; đọc lịch sử không mở cửa sổ/tải iframe. Khi current là
  một bài vừa chọn chưa nghe, Previous có thể trả về bài đã xác nhận gần nhất. Khi current trống, chọn bài từ lịch sử.
- Clear Queue/Clear All giữ lịch sử. Xóa lịch sử chỉ xóa log và đường Previous, không đổi source, queue, yêu thích,
  chế độ hoặc giọng nói. Không lập tức ghi lại bài đang chạy; lần phát nguồn mới sau đó có thể tạo lịch sử mới.
  Không đưa thao tác xóa lịch sử vào Undo của hàng đợi.

## Cách lưu và kiểm soát kết quả

`playerHistory.ts` tách khỏi `playerSession.ts`, dùng khóa localStorage có phiên bản riêng
`peto-player-history-v1:<account-id>`. Giữ ID công khai đã băm của tài khoản như phiên nghe, không owner secret/token.
Clear All và bundle cũ chỉ dọn key phiên nghe, không xóa key lịch sử. Tài khoản khác không đọc lịch sử này; chưa
đồng bộ qua máy/trình duyệt. Storage event và đọc lại trước thao tác nhận thay đổi từ tab khác, tránh ghi trả các
mục vừa bị xóa. Đường Previous đồng bộ theo lịch sử đó; không điều khiển media của tab khác.

Codec kiểm phiên bản/kích thước, 100 mục log + 100 mục điều hướng, ID, timestamp hợp lệ và metadata Unicode;
URL dựng lại từ video ID. Không lưu lệnh/nonce, autoplay, request/revision runtime hoặc ý định Previous đang chờ.
Storage lỗi được báo bằng vùng lỗi hiện có. Tool không xác nhận xóa lịch sử đã lưu nếu browser chưa ghi thành công;
lỗi đọc không được biến thành danh sách rỗng đã xác nhận.

Chỉ bắt đầu ghi từ các lần phát được bundle mới xác nhận. Không dựng lại lịch sử từ queue, order loop nội bộ,
lời Peto trong hội thoại hoặc các phiên cũ chưa ghi. Sửa resume trước vẫn giữ: start nguyên + API cue rõ mốc,
không autoplay sau F5. Không đổi renderer hoặc mạch giọng nói.

Client quảng bá **player_control: 5**. Backend chỉ cấp v5 các action `previous`, `list_history`, `play_history_entry`,
`clear_history`; tab v1–v4 tiếp tục schema/prompt cũ. Chọn một mục lịch sử phải có entry_id/history_revision từ
list_history trong cùng turn; cũ/sai bị chặn. Phân trang tối đa 50 mục/lần, limit=0 đọc tổng. `played_at` dùng Unix
milliseconds. History và queue có revision riêng, nên ghi lịch sử không làm stale ID của queue.

Mutation phát chờ state React **và** native playing/history đã ghi nhận request đó trước receipt. Backend đối chiếu
video đích và native ID/state; stale ID, lỗi/chưa xác nhận không được báo thành công hoặc retry mutation ngầm. Giữ
checker lời đáp tự nhiên hiện có, không đóng cứng câu Peto. Prompt khả năng tách riêng; không đổi persona/examples,
billing/provider, DB, API key hoặc dependency. Trace vẫn gọn, không lưu toàn bộ danh sách/nonce trong hội thoại.

## Kiểm chứng

| Phần | Kết quả |
| --- | --- |
| Backend | 291 ca đạt / 12 tệp Player/BYO/clock/prompt/admin, gồm 25 ca history/v5 mới. |
| Frontend | 234 ca đạt / 12 tệp Player/Companion/Hearing/API. |
| Chrome desktop/mobile mô phỏng | Lượt đầy đủ: 50 đạt, 2 lỗi selector menu, 4 skip theo thiết bị. Sau sửa: 6/6 ca history/Yêu thích đạt, gồm hai ca trước lỗi. |
| Edge desktop/mobile mô phỏng | 6/6 ca history/Previous/Yêu thích đạt. Không chạy lại toàn bộ Edge. |
| Build frontend, browser TypeScript | Đạt; còn cảnh báo chunk lớn đã có. |

Ca mới phủ: proof request/video đúng, event cũ/nguồn chưa phát, giữ source khi xóa, nhiều lần Previous + Next,
loop/shuffle, video trùng, queue đủ 200 không mất dữ liệu, giới hạn 100, cập nhật metadata/thời điểm, F5, Clear All,
queue Undo, xóa từ tab khác, storage lỗi, codec hỏng và tách tài khoản. Native v5 kiểm schema cũ, đọc cùng turn,
revision/ID sai, page hỏng, native state mâu thuẫn và provider → tool → lời đáp tự nhiên.

Browser chạy UI thật với API/backend/YouTube giả; desktop và touch/mobile mô phỏng. Ca voice dùng PCM tổng hợp,
micro giả; Live2D renderer thật trong hồi quy cũ. Đợt này **không gọi AI/TTS/catalogue/YouTube production**, chưa
test Android/Chrome thật hoặc chấm câu trả lời của model production. Xác nhận resume thật của owner thuộc bản
trước, không dùng thay nghiệm thu history mới. Đã xem ảnh panel desktop/mobile, giữ palette và bố cục đã duyệt.

Bằng chứng cục bộ Git-ignored: `.runtime/player-session-stage3/`, JSON riêng theo browser, ảnh
`listening-history.png`. Hồi quy bắt ca Yêu thích dùng selector class cũ bị trùng với mục history mới; sửa tách
class cho menu history và kiểm lại, không coi lỗi selector là mất dữ liệu yêu thích. Tổng cộng 52 ca Chrome khác
nhau đã đạt qua hồi quy + kiểm lại; không gắn nhãn lượt đầu là hoàn toàn xanh. JSON `chrome-results.json` giữ lần
hồi quy đó; `chrome-verified-results.json` và `msedge-verified-results.json` giữ nhóm kiểm lại sau sửa. Không retry
ngầm hoặc flaky. Sau khi làm rõ mô tả field ID/revision của schema v5, đã kiểm lại 25/25 ca backend history đạt.

Từ `backend/`:

```powershell
../.venv/Scripts/python.exe -m pytest tests/test_player_history_tools.py tests/test_player_session_tools.py tests/test_player_reply.py tests/test_player_tools.py tests/test_player_queue_readback.py tests/test_player_discovery_tools.py tests/test_byok.py tests/test_clock_tools.py tests/test_prompt_routing.py tests/test_player.py tests/test_player_catalog.py tests/test_admin.py -q
```

Từ `frontend/`:

```powershell
npx.cmd vitest run tests/playerInput.test.ts tests/playerControl.test.ts tests/player-queue.test.ts tests/player-session.test.ts tests/playerSession.test.ts tests/playerHistory.test.ts tests/player-library-playback.test.ts tests/usePlayerLibrary.test.tsx tests/useYouTubePlayer.test.tsx tests/api.test.ts tests/Companion.test.tsx tests/Hearing.test.tsx --maxWorkers=2
npx.cmd tsc -p browser-tests/tsconfig.json
$env:PETO_PLAYER_BROWSER = 'chrome'
npx.cmd playwright test --config playwright.player.config.ts --workers=1
$env:PETO_PLAYER_BROWSER = 'msedge'
npx.cmd playwright test --config playwright.player.config.ts --workers=1 --grep 'listening history records|unplayed and failed replacements|yêu thích thật'
npm.cmd run build
```

## Deploy và thử thật

Rebuild frontend + restart backend. Backend lên trước/cùng bundle v5 để nhận chat client mới; server vẫn hỗ trợ
tab v1–v4 đang chạy. Bundle cũ không có history/Previous mới; tải lại sau phiên nghe để nhận bản mới. Session cũ
vẫn đọc được và resume stopped như trước. Không migration hoặc cấu hình/key mới. Chưa tự commit/deploy.

Checklist desktop rồi Xiaomi/Android 13/Chrome mà owner dùng:

1. Phát A → B → C. Previous → B → A rồi Next → B → C, kể cả shuffle/loop đang bật. Queue không mất bài/nhân iframe.
2. File/menu ba chấm → Lịch sử nghe: giờ/tên đúng, thêm vào queue không đổi current; bấm bài phát lại được.
3. Chỉ nhập/chọn chưa phát hoặc video lỗi không được ghi là đã nghe. Pause/resume không thêm bản sao; loop one
   cập nhật mục gần nhất thay vì tạo hàng loạt dòng. F5 giữ history/queue/mốc/chế độ và chưa tự phát.
4. Nhắn Peto “quay lại bài trước”, “liệt kê các bài vừa nghe”, “phát lại mục thứ hai trong lịch sử”, “xóa lịch sử”.
   Đối chiếu hành động và lời đáp; không bắt Peto dùng một mẫu câu. Lỗi/ID cũ không nhận đã làm xong.
5. Xóa lịch sử khi đang nghe: nhạc/queue/yêu thích giữ nguyên, F5 không làm history cũ xuất hiện lại. Clear All dọn
   phiên nhưng vẫn mở được history. `_`/mũi tên/X, mobile rời/ẩn Companion và logout vẫn theo hành vi cũ.

Sau nghiệm thu mới chuyển giai đoạn 4 giảm âm lượng nhạc khi trò chuyện bằng giọng nói.
