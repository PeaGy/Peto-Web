# Companion Player notes

Scope: The YouTube Player inside Companion: library, queue, favorites, session restore, history, ducking, and Companion controlling the Player. Per-stage hand-over files live in `frontend/src/features/companion/ytplayer/`.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Dated log (newest first)

## Player — giảm nhạc khi trò chuyện, giai đoạn 4 (2026-10-24)

Owner đã kiểm chứng và commit/deploy giai đoạn 3 ở `ed499ba`, yêu cầu bước tiếp. Thêm ducking 20% mức chọn khi
Companion foreground và TTS playing / giữ để nói / hearing speaking. Chờ 350ms sau hết tiếng; buffer dài trở về
thường, không giảm chỉ vì gõ, chờ AI, tải tiếng hoặc bật mic chờ. Loại giọng/mic test Cài đặt. Rời/ẩn Companion
release, desktop giữ playback, mobile lifecycle cũ. X/Clear All/unmount hủy, tín hiệu muộn không tạo/phát lại iframe.
Tách `usePlayerDucking` (tín hiệu) và `PlayerVolume` (mức chọn/native). UI/session giữ mức chọn; thay volume/mute
qua UI/native/chat khi đang nói vẫn nhận, trả mức mới và không tự unmute. Iframe mới áp mức hạ trước autoplay.
Pending native ack cũ không ghi ngược lựa chọn. IFrame thật tạm trả undefined isMuted/getVolume khi cue dù đã
onReady: coi unknown, không ép0/mute hoặc cấp native proof; đã thêm kiểm kiểu và ca regression. F5 giữ mức chọn,
không lưu ducking, restore stopped. Không đổi renderer/ASR/TTS/Space/UI, không analyser/nghe/xem video.
Receipt v5 thêm optional effective_volume (native thật) và ducked; volume là mức chọn. Backend nhận optional và
tab cũ vẫn hợp lệ; prompt khả năng giải thích hai mức, không đổi persona/examples/guard câu tự nhiên. set_volume/
mute/unmute chờ mức chọn và native phù hợp hệ số, không coi gọi hàm là thành công. Không DB/key/dependency mới.
276 frontend/14 tệp và 296 backend/12 tệp đạt, build và browser TypeScript đạt (chunk warning cũ). Chrome hồi quy
đầy đủ 53 đạt/1 test chờ release sai/4 skip; sửa và nhóm voice kiểm lại 5 đạt/1 skip. Có một lượt kiểm lại khác
timeout tải lạnh 8s, chỉnh phần tải lên30s và chạy tuần tự đạt; không giấu lượt lỗi. Edge nhóm voice 5 đạt/1 skip.
Iframe YouTube thật Chrome/Tetris đạt30→6, native chỉnh50→10, release50 và F5 cue stopped50. Profile riêng, browser
tắt tiếng đầu ra, account/backend/ASR giả; không dùng AI/TTS/Data API tính phí hoặc account production. Không lấy
đây làm bằng chứng nghe tại loa/Android hoặc AI hiểu nhạc. Unit mới giữ tình huống cache thiếu thật; mock cũ bỏ sót.
Chi tiết/checklist và mức phủ sau sửa: `frontend/src/features/companion/ytplayer/SESSION_STAGE4.md`; raw ignored
`.runtime/player-session-stage4/`. committed `6bcee93`; chưa deploy. Rebuild frontend + restart backend, backend trước/cùng
frontend vì receipt mới. Owner cần thử micro/loa/Xiaomi Android13 Chrome sau deploy. Giai đoạn5 nghiệm thu tích
hợp vẫn là bước tiếp theo; Peto nghe/xem video vẫn tạm gác.

## Player — lịch sử nghe và Previous, giai đoạn 3 (2026-10-24)

Owner đã commit/deploy `f6c1601`, xác nhận F5 phát đúng mốc, yêu cầu bước tiếp. Thêm File/menu mobile → Lịch sử nghe,
panel cũ với replay/append/giờ-ngày và nút xóa riêng. Back thành Bài trước; restart vẫn trong Play. Chỉ ghi sau proof
source/request/native ID/state1 đúng; chưa phát/lỗi/event cũ không ghi. Max100 log +100 đường Previous, liên tiếp
cùng nguồn gộp và cập nhật giờ; pause/resume không spam. Previous theo thực nghe, đẩy current đầu queue, giữ tail/
loop/shuffle. Queue đủ200 không có mục phù hợp thì báo cần chừa1chỗ, không bỏ bài. F5 giữ history/Previous stopped.
History key riêng `peto-player-history-v1:<public-account-id>`; Clear All/queue Undo giữ history, xóa history giữ media/
queue/favorites và không lập tức re-add current. Storage event/read-before-write tránh hồi sinh log đã xóa từ tab khác.
Chưa sync máy/trình duyệt; không dựng lịch sử cũ từ order/queue/chat. Chỉ ghi các lần phát từ bundle mới.
Client v5/native previous/list_history/play_history_entry/clear_history; v1–v4 schema/prompt giữ nguyên. Play entry
cần ID/history_revision đọc cùng turn; proof playing chờ cả React/history commit, backend kiểm native ID/state.
Giữ guard lời tự nhiên, không đổi persona/examples/billing/provider/DB/key/dependency. Không AI/TTS/Data API/YouTube
production đợt này, chưa Android thật. 291 backend/12 tệp, 234 frontend/12 tệp, build + browser TypeScript đạt.
Chrome lượt đầy đủ 50 đạt/2 lỗi selector menu/4 skip; đã tách class history khỏi favorites, kiểm lại 6/6 ca liên quan
trên Chrome và 6/6 Edge đạt. Không gọi lượt đầu là hoàn toàn xanh; 52 ca Chrome khác nhau đạt qua hồi quy + kiểm lại.
25/25 backend history kiểm lại sau chỉnh mô tả schema cũng đạt. Chi tiết `frontend/src/features/companion/ytplayer/SESSION_STAGE3.md`. Raw ignored
`.runtime/player-session-stage3/`. committed `ed499ba`; chưa deploy; backend trước/cùng frontend v5, rebuild frontend + restart backend.
Chưa triển giai đoạn 4 giảm nhạc khi voicechat hoặc 5 nghiệm thu; nghe/xem video cùng Peto vẫn tạm gác.

## Player — sửa phát tiếp sau F5 (2026-10-24)

Owner đã commit/deploy giai đoạn 2 ở `03a184f`, báo thanh thời lượng đúng nhưng Phát vẫn chạy từ đầu. Đã tìm
`playerVars.start` nhận số nguyên mà code truyền vị trí thập phân; mock cũ cũng nhận float nên bỏ sót. Sửa constructor
floor start và cueVideoById(startSeconds float) rõ mốc khi nguồn dừng có start>0, không autoplay/seek hoặc tạo iframe
thêm. Nguồn autoplay không đổi; seek 0/pause/play sau đó không bị kéo lại mốc cũ. Mock chỉ nhận embed start nguyên,
ca F5 kiểm actual playing position qua cả nút native và Peto. Không chuyển giai đoạn 3 trong đợt sửa này.
Đã kiểm iframe/video YouTube thật trên Chrome desktop, account/backend Peto giả/profile riêng/volume0. Đối chứng
cách gọi cũ với mốc45.75 chạy từ0; bản sửa nút Peto và nút YouTube đều chạy quanh46 (slider bước1s), ba phép kiểm đạt.
Không AI/TTS/Data API, chưa Android thật; không suy mọi video đều đạt. Unit57/3tệp, Chrome/Edge mỗi loại2caF5
desktop/mobile mô phỏng, build và TypeScript browser tests đều đạt, không retry/flaky. Chi tiết ở
`frontend/src/features/companion/ytplayer/SESSION_RESUME_FIX.md`. Raw ignored `.runtime/player-resume-*`.
Chỉ frontend, không đổi session schema/backend/DB/key/dependency/persona. committed `f6c1601`; chưa deploy; chỉ build/deploy frontend,
tải lại bundle để nhận sửa. Session cũ đọc được; mốc đã bị bản cũ ghi gần0 sau khi phát lại không tự lấy lại mốc xa cũ.

## Player — lưu/khôi phục phiên nghe, giai đoạn 2 (2026-10-24)

Owner đã commit/deploy giai đoạn 1 ở `7811606`, báo Clear Queue/Clear All/Hoàn tác thử thành công, yêu cầu bước tiếp.
Đợt này lưu phiên theo ID tài khoản công khai trong localStorage của trình duyệt/origin: current, position, queue
tối đa 200 (giữ trùng/thứ tự), volume/mute, loop/shuffle/thứ tự vòng. F5 phục hồi stopped, cửa sổ đóng, không iframe/
IFrame API trước khi mở; Peto đọc được trạng thái/queue mà không mở cửa sổ. Mở thì cue ở vị trí đã lưu, Phát mới chạy.
Restart/loop dùng start gốc. Clear Queue ghi ngay; Clear All xóa snapshot ngay; Undo trong RAM có thể lưu lại phiên
stopped, không giữ Undo qua F5. X/minimize/mobile visibility/logout vẫn theo lifecycle cũ. Không phát khi đóng hẳn browser.
Codec kiểm kích thước/kiểu/ID, giới hạn Unicode, dựng URL từ ID, tái tạo entry key/revision và bỏ autoplay/intent/
command/receipt/Undo. Queue chỉnh ghi đồng bộ, progress throttle 5s + flush pause/X/ẩn trang/pagehide/unmount. Native
time/volume được đọc trước dispose; volume ref tránh snapshot React cũ ghi đè khi visibility tới sau pagehide.
Tab cũ không tự lưu đè snapshot mới hoặc Clear All của tab khác; chỉnh queue/nguồn chủ động mới có thể ghi lại.
Các tab chưa sync UI; snapshot chưa sync qua máy/trình duyệt. Storage lỗi thì dùng RAM và báo lỗi sẵn có.
Chỉ frontend, giữ protocol v4/backend/persona/DB/key/dependency. committed `03a184f`; chưa deploy. 217 ca frontend/11 tệp đạt;
Chrome hồi quy desktop/mobile mô phỏng 48 đạt/4 skip theo thiết bị, Edge 8 ca lưu/khôi phục mới đạt, không retry/flaky.
Hai ca F5 Chrome kiểm lại, build/TypeScript đều đạt sau chốt biên cuối; lỗi ghi storage giữ tới lần ghi thành công.
Chi tiết kết quả trong
`frontend/src/features/companion/ytplayer/SESSION_STAGE2.md`.
Không gọi AI/TTS/catalogue/YouTube production; chưa test Android thật đợt mới. Backend không đổi, không chạy lại 266 ca
cũ. Chỉ build/deploy frontend. Tab bundle cũ vẫn RAM, tải lại sau phiên nghe để nhận bundle mới; bản cũ chưa lưu thì
không cứu được queue ở lần F5 đầu. Chi tiết/bằng chứng/checklist trong SESSION_STAGE2.md; raw ignored
`.runtime/player-session-stage2/`. Kế tiếp giai đoạn 3 lịch sử/Previous, chưa triển. Nghe/xem video vẫn tạm gác.

## Player — dọn phiên nghe và hoàn tác, giai đoạn 1 (2026-10-24)

Owner đã commit/deploy đợt điều khiển trước, yêu cầu giai đoạn 1 của kế hoạch mới. Bản đối chiếu `b3b7fa8`.
Đã thêm File → Hoàn tác / Clear Queue / Clear All; mobile dùng menu ba chấm. Clear Queue xóa Tiếp theo, giữ
bài đang nghe; Clear All dừng/giải phóng iframe và xóa current/queue, giữ yêu thích. `_`/mũi tên vẫn ẩn phát nền,
X vẫn dừng giữ queue. Undo một bước cho append/remove/move/clear; Undo Clear All khôi phục stopped, không autoplay.
Next/nguồn/chế độ mới làm mất Undo cũ; metadata/no-op không ghi đè. Snapshot bounded trong RAM, chưa lưu phiên qua F5.
Client quảng bá v4; backend cấp ba action clear_queue/clear_all/undo_queue chỉ cho v4, giữ v1/v2/v3 cho tab cũ.
Undo cần revision từ list_queue trong cùng turn. Clear/Undo tăng thế hệ, hủy discovery/import/native command cũ,
kể cả SSE chưa đến từ lượt chat bắt đầu trước thao tác; lượt dọn của chính Peto vẫn nhận receipt. Backend kiểm
receipt rồi giữ lời đáp tự nhiên qua guard đã có. Không đổi persona/examples, billing, DB, key hoặc dependency.
266 ca backend, 200 ca frontend và build/browser TypeScript đạt. Chrome desktop/mobile mô phỏng hồi quy 42 đạt/4
skip theo thiết bị; Edge chạy 4 ca mới đều đạt, không chạy lại toàn bộ Edge. Không retry/flaky.
Không gọi AI/TTS/YouTube production, chưa kiểm thử thay đổi mới trên Android thật. committed `7811606`; chưa deploy.
Deploy rebuild frontend + restart backend (backend lên trước/cùng bundle); tab cũ giữ phiên và bộ lệnh cũ.
Nhận lệnh mới cần bundle v4, tải lại sau phiên nghe vì F5 vẫn mất queue RAM. Bàn giao/checklist/bằng chứng:
`frontend/src/features/companion/ytplayer/SESSION_STAGE1.md`; raw Git-ignored `.runtime/player-session-stage1/`.
Kế hoạch tiếp: (2) lưu/khôi phục phiên stopped sau F5; (3) lịch sử/Previous thật; (4) giảm âm nhạc khi voicechat;
(5) nghiệm thu tích hợp. Chưa triển các bước này, playlist cá nhân để sau. Nghe/xem video cùng Peto tạm gác,
không bỏ, không tự triển vì chủ đề nghe/xem xuất hiện trong lịch sử.

## Companion điều khiển Player — nghiệm thu giai đoạn 4 (2026-10-23)

Owner đã commit sửa lời đáp tự nhiên ở `9869571`, yêu cầu giai đoạn tiếp theo. Đợt này nghiệm thu cuối luồng đã có,
không thêm tính năng Player/persona. Đã phát hiện và sửa hai nhãn thống kê: player_check/player_rephrase được tính
vào side_calls (token/chi phí trước đó đã có trong tổng), và lời gọi chính spoken=True gắn surface companion.
Chú thích quản trị kể cả kiểm chứng Player. Không đổi billing/routing/model, DB, key hoặc dependency.
Thêm ca backend chặn text/đầu vào giọng đọc cho tới khi checker hoàn tất, kể cả ack đã thành công; hủy không phát
bản nháp hoặc replay. Ca browser mới: X giữa swap chưa xác nhận dọn iframe/không mở lại, yêu cầu mới được phát;
Dừng chat không gửi ack cho lệnh hủy, không retry ngầm. Không coi cancel là undo media đã gửi.

Backend Player/BYO/clock/prompt/admin **249 ca đạt**, frontend **197 ca/10 tệp đạt**, build và browser TypeScript đạt.
Chrome và Edge desktop/mobile mô phỏng **mỗi loại 38 đạt/4 skip theo thiết bị, không flaky**. Network/provider/
YouTube giả, Audio dùng PCM tổng hợp; không gọi AI/TTS/catalogue/YouTube production, không đo latency/chi phí AI thật.
Owner báo thử **bằng chat Peto trên Android/Chrome**: đổi bài, sửa queue, ẩn/mở Player và dừng đều ổn. Đây là báo cáo
máy thật của owner, không phải agent điều khiển USB; chưa chấm câu trả lời tự nhiên trên nhiều trường hợp/model.
Không suy mọi câu đều đúng từ test mock. Bộ Brain Benchmark cũ chưa phải eval Player native.

committed `b3b7fa8`; chưa deploy. Deploy restart backend khi không có chat đang chạy; rebuild frontend cho chú thích quản trị.
Không F5 tab đang nghe, queue RAM vẫn ở browser. Chi tiết/checklist/bằng chứng:
`frontend/src/features/companion/ytplayer/CONTROL_STAGE4.md`; raw Git-ignored `.runtime/player-control-stage4/`.

## Player — lời đáp tự nhiên, đối chiếu biên nhận (2026-10-23)

Owner đã deploy bản sửa `f3e8c3b`, xác nhận swap hoạt động nhưng không muốn câu “Playing…” bị cố định.
Yêu cầu giữ giọng Peto tự nhiên, không máy móc và không xác nhận sai. Bản sửa backend đã commit ở `9869571`.
Sau mutation, giữ nguyên lời model/cảm xúc nếu bước đối chiếu chỉ đọc xác nhận các thông tin Player khớp receipt.
Prompt khả năng Player bỏ yêu cầu xác nhận ngắn/nhắc tên bắt buộc, không sửa persona/examples. Không ép độ dài,
tên bài hay cách xưng hô. Sai thì viết lại đúng một lần bằng cùng persona/ngôn ngữ rồi kiểm lại;
không chạy lại thao tác. Chỉ khi kiểm tra lỗi/timeout/JSON sai hoặc câu sửa vẫn không được xác nhận mới dùng câu
fallback từ receipt. Guard thiếu thực thi, chặn mutation lặp sau lỗi và native video ID/state vẫn giữ nguyên.

Bước phụ dùng đúng provider/account của lượt chính, effort low, web off, tools disabled và Player ContextVar=None;
không phát draft/JSON cho UI/TTS. Mỗi bước tối đa 15s/16.000 ký tự đầu ra; hủy stream khôi phục context. Lượt có
mutation thêm một lần gọi AI; khi cần sửa thêm một lần viết lại + một lần kiểm lại, tối đa ba lần gọi phụ. Có tăng
độ trễ/token; hội thoại thường và lượt chỉ đọc trạng thái không thêm lần gọi. Usage ghi purpose player_check và
player_rephrase. Đây là đối chiếu ngữ nghĩa bằng model, không phải chứng minh tuyệt đối; chưa eval AI thật.
Trace ghi natural_verified/natural_rewritten hoặc receipt_fallback_* để phân biệt lời giữ nguyên/sửa/fallback.
Checker dùng kết quả tool đầy đủ đã có giới hạn (gồm lists/counts); trace lưu DB vẫn gọn như trước.

Backend nhóm Player/BYO/clock/prompt **219 ca đạt** bằng provider/browser giả; không gọi AI/TTS/YouTube production.
Không đổi frontend/DB/key/dependency. Deploy restart backend là đủ, không cần F5 và mất queue đang nghe.
Chi tiết/cách thử thật trong `frontend/src/features/companion/ytplayer/CONTROL_CONFIRMATION_FIX.md`.

## Player — chặn xác nhận “Swapped” sai (2026-10-23)

Owner đã commit giai đoạn 3 ở `8ed3642`, báo model nói đổi bài nhưng video cũ còn phát, nhắc lại mới đổi; yêu cầu
sửa. Chưa có trace production cũ để chốt root cause. Đợt này committed `f3e8c3b`; chưa deploy. PlayerSession ghi receipt có
sent/result; guard ở _stream_reply dùng chung providers giữ draft khỏi chữ/TTS và dựng xác nhận mutation từ receipt,
không lấy lời AI làm success. Nhánh không mutation nhưng nói đã làm (mẫu Anh/Việt) sửa tối đa một lần; không phải
router ý định và không bảo đảm phủ mọi cách nói. Mutation sent bị lỗi/unknown chặn mutation tiếp trong cùng turn,
vẫn cho status; turn mới từ user được thử lại. Câu trả lời Player gọn theo mẫu; giữ emote, không đổi persona/examples/UI.
Native proof đọc getVideoUrl/getPlayerState; đổi bài cần ID đúng + state 1, bỏ event cũ/thiếu ID, poll nhận cache muộn.
Snapshot native fields optional cho tab cũ; backend từ chối success playing nếu bằng chứng đã cung cấp mâu thuẫn.
Trace checkpoint/chốt vào work JSON sẵn có, /api/companion trả player_trace cùng owner, không thêm UI. Giữ action,
sent/error/state/target/counts, không ID lệnh thực thi/URL/key/full lists. Lịch sử 3 turn trace gần nhất kèm cho AI
giải thích, không replay. Không gọi AI/TTS/YouTube production. Frontend 170 ca đạt, Chrome desktop/mobile mô phỏng
34 đạt/4 skip, build đạt. Backend nhóm Player/BYO/clock/prompt **203 ca đạt**.
Deploy rebuild frontend + restart backend. Guard backend có hiệu lực cho tab cũ; native proof cần bundle mới,
tải lại sau phiên nghe vì F5 vẫn xóa queue RAM. Không DB migration/key/dependency mới. Chi tiết và giới hạn:
`frontend/src/features/companion/ytplayer/CONTROL_CONFIRMATION_FIX.md`.

## Companion điều khiển Player — giai đoạn 3 (2026-10-23)

Owner đã deploy `7b912f4`, xác nhận queue đổi đúng không cần F5 rồi yêu cầu bước tiếp. Đã ghép native action v3
search_videos/play_video/enqueue_video/enqueue_playlist; committed `8ed3642`; chưa deploy. Discovery tách file, dùng lại catalogue
với key/cache/admission cũ, link video dùng oEmbed. Search không tự phát; chọn ID đã quan sát trong turn hoặc URL
người dùng đưa trong ngữ cảnh. Metadata/danh sách tracks do server tạo, model không tự điền title/artist.
Video có list vẫn là riêng video; playlist chỉ nhập khi yêu cầu, append giữ nguồn/thứ tự/trùng và báo counts/cắt.
Client kiểm source playing và entry keys sau append; window_revision bảo vệ X trong lúc tra cứu/chờ phát, không
mở lại muộn. Prompt khả năng riêng có chọn theo nhân vật/hội thoại/favorites/search và đề nghị nhạc → đồng ý;
không regex ý định, không đổi persona/examples/UI. Backend cấp đúng v1/v2/v3, Gemini BYO vẫn không function calling.
Không DB/key/dependency/persistence mới. Deploy backend trước/cùng frontend, rebuild frontend + restart backend.
Tab v2 cũ vẫn giữ phiên và chức năng cũ; nhận discovery cần bundle v3, tải lại sau khi kết thúc phiên nghe vì F5
vẫn mất queue RAM. Không tự gửi chat/gọi AI/TTS hoặc catalogue production. Backend 171 ca đạt; frontend 169 ca,
Chrome desktop/mobile mô phỏng 32 đạt/4 skip; build đạt. Kiểm chứng/tiêu chí thử thật
trong `frontend/src/features/companion/ytplayer/CONTROL_STAGE3.md`.

## Player — kiểm chứng đổi thứ tự sau báo lỗi (2026-10-23)

Owner đã commit/deploy giai đoạn 2 ở `19706c2`. Báo Peto nhận chuyển bài thứ hai lên đầu nhưng nêu “Stay With Me”
không có trong queue. Đã đọc lịch sử production bằng IAB có sẵn; không gửi chat/gọi AI/TTS hoặc sửa dữ liệu. Lịch sử
không lưu trace tool nên chưa xác định lệnh trước có chạy hay không; không kết luận do cache hoặc lỗi người dùng.
Không yêu cầu F5 trong phiên đang nghe: queue hiện chỉ ở RAM, F5 dừng nhạc/làm trống queue (favorites vẫn lưu).
Đợt sửa chỉ backend: bắt buộc entry ID/revision từ list_queue trong cùng turn trước remove/move/play; xác nhận
target phải khớp video ID đã đọc. Sau move tự đọc lại tối đa 5 mục quanh vị trí đích và so entry ID, video ID,
position, revision; gửi tên/vị trí thực tế cho AI. Không khớp/timeout là chưa xác nhận, không tự lặp mutation.
Dùng action list_queue sẵn của client v2, không cần F5/rebuild frontend; deploy restart backend khi không có lượt
chat đang chạy. Tab v1 vẫn chỉ có playback. Prompt khả năng ngắn yêu cầu dùng kết quả tool, không coi lời “done”
hoặc tên từ lịch sử là bằng chứng. Không thay persona/examples/UI/persistence/DB/key/dependency.
Backend 118 ca đạt (AI/browser giả), bao gồm native provider → move → readback trước final, sai target/revision/order,
phân trang và hủy readback. Không thêm lượt gọi model cho readback. Owner đã commit/deploy `7b912f4` và xác nhận
Peto đổi vị trí đúng mà không cần F5. Agent không tự gửi thêm chat AI thật.
Chi tiết thêm trong `frontend/src/features/companion/ytplayer/CONTROL_STAGE2.md`.

## Companion điều khiển Player — giai đoạn 2 (2026-10-23)

Owner đã deploy `0602baf` và xác nhận mở Player/đọc title với AI thật, yêu cầu bước tiếp theo. Đã ghép đọc/paginate
yêu thích, thêm tất cả/riêng bài yêu thích, set tim idempotent, đọc queue, remove/move/play theo entry ID + revision,
và báo next thực tế (tách auto với skip). Owner đã commit/deploy ở `19706c2`; nội dung dưới ghi lần bàn giao. Client protocol v2; backend tiếp tục cấp schema/prompt
v1 cho tab cũ. Đọc/append khi Player chưa mở mount controller kín, không iframe/UI; bulk bỏ trùng current/queue,
điền tối đa 200 và trả counts rõ ràng; không oEmbed từng bài. Favorite read mới từ DB, lỗi không thành 0, chống read
cũ ghi đè/write trùng. Shuffle + All chuẩn bị vòng kế sớm để queue[0]/preview khớp ENDED; lịch sử vòng tối đa 201
để All không khôi phục quá 200. Sửa lần play từ queue chưa từng mở: chờ host rồi tạo intent; đóng X hủy media đang
chờ. Không thay bố cục, DB/key/dependency. Backend 104, frontend 166 ca đạt; build đạt. Chrome desktop/mobile 30 đạt,
4 skip theo thiết bị; chi tiết trong
`frontend/src/features/companion/ytplayer/CONTROL_STAGE2.md`. Tìm tên/link/playlist qua chat, tự chọn gu nhạc và hội thoại
gợi ý nhạc ở giai đoạn 3. Gemini BYO chưa có function calling. Không gọi AI/TTS có phí, chưa test thật Android cho
thay đổi mới. Deploy rebuild frontend + restart backend; backend có thể lên trước để hỗ trợ tab v1 đang mở.

## Companion điều khiển Player — giai đoạn 1 (2026-10-23)

Owner đã commit/deploy giai đoạn này ở `0602baf` và xác nhận mở/đọc title bằng AI thật. Các dòng sau ghi lần bàn giao
giai đoạn 1: đã ghép tool `control_player` vào Companion thật.
Đọc trạng thái, mở/ẩn/đóng, play/pause/seek/volume/mute, Next/restart, đặt shuffle/repeat. Không dò từ khóa, không thay
persona/examples. Prompt khả năng tách riêng. Client gửi phiên bản, server chỉ cấp tool cho Companion; SSE command ID
ngẫu nhiên → browser thực thi cùng player → POST owner-scoped/one-use → provider nhận kết quả rồi trả lời. Timeout 12s,
chống lệnh trùng/hết hạn/hủy, không replay khi hồi phục lịch sử. Hỗ trợ vòng Responses/Claude và CC/Ollama; Gemini BYO
chưa có function calling nên không cấp khả năng. Backend 93 ca trực tiếp và frontend 159 ca đạt; build đạt. Chrome
desktop/mobile mô phỏng 26 đạt, 4 skip. Một lỗi thứ tự fixture trí nhớ ở nhóm mở rộng cũng tái hiện tại HEAD chưa sửa;
ghi chi tiết trong báo cáo. Không gọi AI/TTS có phí, không coi Android nghiệm thu bản cũ là nghiệm thu thay đổi mới.
Deploy cần rebuild frontend + restart backend; không migration/key/dependency mới. Tìm/chọn nhạc, yêu thích, thao tác
chi tiết hàng đợi và hội thoại gợi ý nhạc là các bước sau. Chi tiết: `frontend/src/features/companion/ytplayer/CONTROL_STAGE1.md`.

## Player library — nghiệm thu giai đoạn 4 (2026-10-23)

Chủ web đã deploy `645fe3b`, thêm key máy chủ và xác nhận tìm/chọn/playlist hoạt động. Yêu cầu làm nốt giai đoạn cuối.
Đã nghiệm thu bản deploy bằng phiên sẵn có: 20 kết quả Tetris, phát/auto-next, nhập 10 bài playlist 3Blue1Brown,
ẩn UI vẫn phát và gõ nháp, X gỡ iframe; không gửi chat/gọi AI/TTS/đổi cài đặt hoặc sửa yêu thích production.
Backend 83 ca, frontend 318 ca đạt; browser Chrome và Edge cài trên máy mỗi loại 22 đạt, 4 skip theo thiết bị.
Thêm `playwright.player.config.ts` và `player-library-acceptance.spec.ts`: 200 mục, từ chối 201, resize,
10 vòng tạo/hủy player, loader một lần và tim ở giữa hit area. Không thay mã sản phẩm.
`ops/youtubePlayerCheck.mjs` cập nhật tên controls/metadata/favorites giả cho bản thư viện. Hai lượt headless mạng thật
đều exit 0: bốn video phát, Rick/Shape 150. Đo CPU/private RAM 5 giây từng trạng thái; không coi headless là ca OS hidden.
Chủ web báo Xiaomi/Android 13/Chrome 155.0.8059.87 làm checklist chức năng đều ổn. Đây là nghiệm thu thủ công của
chủ web, không phải agent truy cập điện thoại; chưa đo nhiệt/pin dài hạn hoặc micro loa thật.
Chi tiết/số đo/cách chạy: `frontend/src/features/companion/ytplayer/LIBRARY_STAGE4.md`. Raw/ảnh ignored ở
`.runtime/player-library-stage4/`. Tệp nghiệm thu committed `218c686`; chưa deploy; không cần deploy tính năng mới từ đợt này.

## Player library — giai đoạn 3 (2026-10-23)

Chủ web đã commit/deploy giai đoạn 2 và hai chỉnh sửa tim desktop/hover (HEAD trước lượt này: e347bb9).
Giai đoạn 3 đã được chủ web commit/deploy ở `645fe3b`; các nội dung sau mô tả lần bàn giao giai đoạn 3.
File và ô mở đầu dùng chung phân loại link/tên; tìm khi submit, không autocomplete hoặc tự phát kết quả đầu.
Panel kết quả dùng lại vị trí queue/yêu thích, có chọn phát, dấu cộng và tải thêm. Link video kèm list vẫn mở
riêng video, có nút Nhập playlist trong File. Playlist thêm cuối queue, không đổi bài đang nghe, giữ thứ tự/bản trùng;
bỏ video riêng tư/xóa/không nhúng được, thông báo khi bị cắt theo sức chứa 200 bài. X/hủy/unmount vô hiệu hóa request cũ.
Máy chủ dùng YouTube Data API v3 qua `youtube_catalog.py`; key `PETO_YOUTUBE_API_KEY` chỉ ở backend, gửi trong header,
không vào URL/frontend/log lỗi. Auth, cache 5 phút có giới hạn, rate/concurrency riêng không giữ slot chat.
Không đổi DB/dependency. Link video/tim vẫn chạy nếu chưa có key. `.env` local chưa có key, chưa thử Data API thật.
Kiểm chứng và cách bật: `frontend/src/features/companion/ytplayer/LIBRARY_STAGE3.md`.
Giai đoạn 4 mới nghiệm thu YouTube thật/tài nguyên/Android Chrome thật. Không tự commit/deploy hoặc gọi AI/TTS trả phí.

## Player library — giai đoạn 2 (2026-10-23)

Chủ web đã commit/deploy giai đoạn này (d898696); các nội dung sau mô tả lần bàn giao giai đoạn 2:
PlayerLibraryShell/Panel + CSS và icon riêng chuyển từ bản duyệt, không import prototype/catalogue vào app.
Tim lưu ở SQLite theo session owner qua `/api/companion/player/favorites` (GET, POST/DELETE theo video ID),
metadata qua `/videos/{id}` dùng oEmbed cũ. Bảng/index `player_favorites` được tạo bổ sung lúc init_db; không SQL tay.
Hàng đợi và loop/shuffle chỉ trong phiên tài khoản; F5 trống, yêu thích vẫn còn. File nhận link video, mở ở trạng thái dừng
hoặc thêm vào queue; chọn từ danh sách mới yêu cầu phát. UI giữ tất cả lựa chọn bố cục/heart và hai nơi bấm mode đã duyệt.
playerQueue reducer độc lập media; ENDED của iframe mới đẩy bài, token chống sự kiện cũ/nhân đôi và lặp cùng ID.
useYouTubePlayer hỗ trợ loadVideoById cho yêu cầu phát, không cue lại nguồn ban đầu và không phát lại token đã hủy sau X/suspend/pagehide.
Giữ portal, phát nền desktop, ẩn mobile không mini, X/logout dừng và quyền Space/micro/giọng đọc/renderer.
Chi tiết kiểm chứng, deploy và giới hạn: `frontend/src/features/companion/ytplayer/LIBRARY_STAGE2.md`.
Tìm tên/playlist vẫn giai đoạn 3; nghiệm thu thật giai đoạn 4. Không tự commit/deploy hoặc chạy AI/TTS trả phí.

## Player: mở rộng yêu thích và hàng đợi — giai đoạn 1 (2026-10-23)

Chủ web đã commit/deploy vòng Player trước và duyệt kế hoạch mở rộng bốn giai đoạn. Đã yêu cầu triển giai đoạn 1:
bản duyệt UI tương tác riêng tại `/prototypes/player-library/`, chưa ghép vào app, committed `d898696`; chưa deploy.
Tim desktop ở hàng điều khiển phụ; mobile ở mép phải khối tên bài/người trình bày dưới video, canh giữa hai dòng, trên timeline,
thẳng cột với tổng thời lượng
(chủ web sửa lại hướng trái thành phải ngày 23/10).
File → Yêu thích (mobile menu ba chấm); hàng đợi bên phải khi frame đủ rộng, dưới khi hẹp/mobile,
mặc định đóng. Dấu cộng giữ danh sách hiện tại và hiện chấm báo ở icon hàng đợi. Một vùng danh sách dùng chung cho
hàng đợi/yêu thích/kết quả, không thêm tab cố định. Ô link/tên và playlist dùng dữ liệu mẫu; tìm tên không tự phát bài đầu.
Chỉ state trong phiên, không persistence/API/iframe/audio thật. Production Player và backend chưa thay đổi.
Bổ sung theo yêu cầu trước giai đoạn 2: hàng điều khiển chính desktop/mobile có Shuffle · Phát lại từ đầu · Phát/Tạm dừng
· Bài tiếp theo · Loop canh giữa theo ảnh chủ web. Hai icon cạnh “Tiếp theo” trong hàng đợi dùng chung trạng thái;
không cần mở hàng đợi để đổi mode. Âm lượng/tim desktop/icon hàng đợi ở hàng phụ; mode mặc định tắt.
Loop chu kỳ off → all → one → off; lặp một bài chỉ khi hết bài, nút Tiếp theo vẫn bỏ qua. Shuffle giữ bài hiện tại,
trộn bài chờ, tắt thì khôi phục thứ tự thường còn lại; đổi thứ tự bằng tay tắt shuffle. All giữ cả vòng phát, kể cả bài
đã nghe trước lúc bật, bỏ hẳn mục đã xóa; all + shuffle trộn mỗi vòng, tránh lặp ngay tại ranh giới vòng.
Các chế độ vẫn chỉ mô phỏng trong phiên. `queuePlayback.ts` reducer thuần dùng seed trong action để Strict Mode chạy lại ổn định.
Chi tiết, đường dẫn mở và bước tiếp: `frontend/src/prototypes/player-library/README.md`.
Giai đoạn 2 mới ghép yêu thích theo tài khoản, hàng đợi thật và loop/shuffle; giai đoạn 3 playlist công khai/tìm tên với Data API;
giai đoạn 4 nghiệm thu browser/thiết bị/tài nguyên. Lệnh chat/voice để sau.

## Player YouTube trong Companion (2026-10-22)

Giai đoạn 3 đã ghép Player vào Companion và chủ web đã deploy. Nút icon desktop cạnh Bối cảnh/Nhân vật và mục Player trong
menu mobile; giữ giao diện retro đã được chủ web duyệt. Mũi tên mobile ẩn toàn bộ giao diện và tiếp tục phát trong
cùng tab, không thêm mini player. Sau góp ý bản deploy: nút _ và icon desktop chỉ ẩn/hiện, giữ video đang phát; X đóng
hẳn. Bỏ chữ trên nút icon và dải chừa 76 px dưới vùng kéo; cửa sổ chạm được đáy Companion, vẫn chừa cột chat.
Theo yêu cầu mới ở giai đoạn 4: desktop (`hover: hover` + `pointer: fine`, độc lập chiều rộng UI) giữ cùng iframe
và phát khi đổi tab trình duyệt, thu nhỏ hoặc rời Companion sang Trò chuyện/Cài đặt; cửa sổ được ẩn, trả quyền phím.
Mobile chỉ giữ phát khi ẩn UI trong cùng tab Companion; rời Companion/ẩn trang vẫn hủy phiên. X, hết phiên, unmount
và pagehide luôn hủy iframe; sau khi hủy quay lại không tự phát. Không thể phát sau khi đóng tab/thoát hẳn trình duyệt.
Đã bỏ dòng idle “Trả lời ngắn bằng tiếng Anh” cũ; giữ trạng thái đang xử lý và tên provider BYO.
Chỉ nạp API sau link hợp lệ. Module tải riêng, không import prototype/sáu mẫu vào app. Không cue thừa nguồn ban đầu
ngay onReady để tránh ghi đè lần bấm Phát đầu.
Đổi nguồn chờ sự kiện cued/playing rồi mới bật Phát/seek, không báo sẵn sàng ngay khi gửi cue; timeout 20 giây.

Chi tiết vòng đời, portal, Space/micro, bố cục hẹp và kiểm chứng: `frontend/src/features/companion/ytplayer/README.md`.
Giọng đọc, renderer và Nhún theo nhạc giữ cơ chế hiện có; không lấy audio iframe.
Báo cáo giai đoạn 4: `frontend/src/features/companion/ytplayer/STAGE4_REPORT.md`. Thiết bị điện thoại chủ web chọn:
Android/Chrome; phần máy thật còn chờ xác nhận, không đánh đồng với mô phỏng. Ca thu nhỏ cửa sổ Edge qua CDP chưa
xác nhận được trạng thái minimized, cần thao tác bằng tay; chuyển tab Edge thật và thu nhỏ Chrome thật đã kiểm tra.
Không tự commit/deploy hoặc chạy AI/TTS trả phí.
