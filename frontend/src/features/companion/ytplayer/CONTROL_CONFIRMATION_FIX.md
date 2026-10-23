# Sửa xác nhận Player sai (23/10/2026)

## Cập nhật: giữ lời đáp tự nhiên sau xác nhận (23/10/2026)

Chủ web đã commit/deploy bản sửa bên dưới ở `f3e8c3b` và xác nhận swap được, nhưng không muốn lời đáp luôn là
“Playing…”. Đợt cập nhật này chỉ sửa backend, chưa commit/deploy. Phần mô tả dựng câu cố định và không thêm lần
gọi AI ở mục “Thay đổi” bên dưới ghi lại bản trước; hành vi hiện tại được thay thế như sau:

- Peto vẫn tự viết lời đáp theo persona và hội thoại. Sau mutation, một bước chỉ đọc đối chiếu các thông tin Player
  với kết quả thực thi: đúng thì giữ nguyên câu chữ/cảm xúc, không ép nhắc tên bài hay giới hạn độ dài.
  Prompt khả năng Player cũng bỏ yêu cầu báo kết quả ngắn/luôn nhắc tên; persona và examples không sửa.
- Nếu sai tên bài, vị trí, số lượng, bỏ qua lỗi đáng kể hoặc nói thành công khi thất bại, cho viết lại một lần trong
  giọng Peto rồi kiểm lại. Không tự chạy lại lệnh để biến câu sai thành đúng. Lỗi/unknown vẫn là lỗi/chưa xác nhận;
  không bịa nguyên nhân hoặc nói đã xem/nghe nội dung video.
- Chỉ dùng câu từ receipt làm phương án cuối khi bước kiểm tra không khả dụng/timeout/JSON sai hoặc câu sửa vẫn
  không được xác nhận. Guard thiếu lệnh, chặn mutation lặp sau lỗi, native video ID/state và history trace giữ nguyên.
- Bước phụ dùng cùng provider/account đã chọn, effort low, web off, tools disabled và không có Player context.
  Kết quả phụ không gửi ra UI/giọng đọc, không có quyền thực thi Player. Mỗi bước tối đa 15 giây/16.000 ký tự đầu ra;
  cancellation đóng stream/khôi phục context, không chuyển thành retry.

Chi phí: thêm **một lần gọi AI** mỗi lượt có mutation; nếu cần sửa thì thêm một lần viết lại và một lần kiểm lại
(tối đa ba lần gọi phụ). Có tăng token/độ trễ; lượt chỉ đọc trạng thái và hội thoại thường không thêm bước này.
Usage phân biệt `player_check` / `player_rephrase`. Trace lưu `natural_verified`, `natural_rewritten`,
`receipt_fallback_unsupported` hoặc `receipt_fallback_check_unavailable`; không thêm UI/log nội dung công khai.
Kết quả tool đầy đủ có giới hạn được gửi cho checker, gồm số bỏ trùng và các trang danh sách đã đọc; trace DB vẫn
giữ giới hạn cũ. Đây là kiểm tra ngữ nghĩa bằng model, **không bảo đảm loại bỏ mọi hallucination**.

Kiểm chứng đợt này: **219 ca backend đạt**, cùng nhóm chín tệp liệt kê bên dưới. Ca mới kiểm lời tự nhiên Anh/Việt,
không bắt nhắc title, giữ cảm xúc, sửa tên sai, lỗi thật/unknown, thành công một phần, checker phê duyệt nhầm câu
“Swapped” khi lệnh lỗi, JSON sai, timeout, mất kết nối, lệnh bất thường và hủy stream. Responses và adapter BYO
đều qua guard; không lộ bản nháp sai và không replay mutation. Dữ liệu giả kiểm đường xử lý, chưa đo chất lượng
câu chữ của model thật; không gọi AI/TTS/YouTube production. Không đổi frontend nên không chạy lại browser/build.

Deploy **chỉ restart backend**, không F5 tab đang nghe; không migration/key/dependency mới. Sau deploy thử các
yêu cầu đổi bài/mở Player bằng cách nói khác nhau và cả lỗi video: lời đáp có thể tự nhiên, ngắn/dài theo ngữ cảnh,
nhưng title/trạng thái/kết quả phải khớp Player. Nếu thường xuyên ra câu mẫu, xem `reply_guard` để phân biệt checker
không khả dụng với bản nháp không được xác nhận; không giảm bằng chứng thực thi hoặc bỏ guard để che lỗi.

## Bản sửa nền tảng đã deploy ở f3e8c3b

Bản đối chiếu `8ed3642`. Chủ web thử đổi bài qua chat: Peto nói “Swapped” nhưng video cũ vẫn phát; sau nhắc lại
mới đổi được. Không có trace của lượt production cũ để xác định lần đầu đã gọi công cụ hay chưa. Đợt này sửa cả
lỗi xác nhận bằng lời và lỗ hổng dùng trạng thái playing của nguồn cũ. Chưa commit/deploy; không gọi AI/TTS có phí,
catalogue hoặc YouTube production để kiểm chứng.

## Thay đổi

- `PlayerSession.run` ghi biên nhận riêng cho từng lời gọi: action, có gửi xuống browser không, kết quả, lỗi,
  trạng thái, target/counts/revision/đổi vị trí. Không coi lời assistant là bằng chứng. Hủy khi đang chờ để lại
  biên nhận chưa xác nhận, không biến thành thành công.
- `player_reply.guarded_reply` dùng chung cho các provider qua `_stream_reply`. Giữ bản nháp, không gửi ra chữ/
  giọng đọc trước khi kiểm tra. Sau thao tác Player, câu xác nhận ngắn được dựng từ biên nhận thay cho câu AI tự viết;
  tên bài lấy từ snapshot/target, lỗi lấy từ kết quả thật. Giữ thẻ cảm xúc đầu tiên, không đổi persona/examples.
  Đây là thay đổi có chủ ý: lời xác nhận thao tác sẽ gọn và ít biến thể hơn; phần hội thoại thường vẫn do model viết.
- Nếu chưa có mutation nhưng đầu ra khẳng định đã thao tác (“Swapped”, “đã đổi bài”…), cho model một lần sửa để
  thực hiện yêu cầu thật. Vẫn không thực hiện thì trả chưa xác nhận; không phát bản nháp. Đây là bộ phát hiện
  câu xác nhận tiếng Anh/Việt, **không phải bộ hiểu ý định người dùng bằng regex** hoặc bộ chứng minh ngữ nghĩa
  cho mọi cách diễn đạt/ngôn ngữ. Các cách diễn đạt ngoài mẫu còn cần theo dõi bằng trace và eval AI thật.
- Một mutation đã được gửi mà lỗi/chưa xác nhận sẽ chặn các mutation tiếp theo trong cùng turn ở backend,
  kể cả model cố gọi lại. Vẫn cho đọc status; yêu cầu mới từ người dùng mở turn mới. Tránh tự lặp skip, append,
  restart hoặc tự đổi sang video khác khi không biết kết quả lần trước.
- Câu trả lời trạng thái như “Paused.” có status đọc thật phù hợp thì không bị coi là thiếu thao tác.
- Không thêm lượt AI cho hội thoại thông thường hoặc một mutation đã có kết quả. Chỉ nhánh thiếu thực thi có
  tối đa một lượt sửa bổ sung (bên trong vẫn dùng vòng tool cũ). Do giữ bản nháp, chữ/giọng đọc Companion bắt đầu
  khi câu trả lời chốt đã sẵn sàng; không đọc từng token chưa kiểm tra.

## Bằng chứng nguồn phát

- `observe()` đọc thêm video ID từ `getVideoUrl()` và trạng thái từ `getPlayerState()`. Khi xác nhận phát/Next/
  restart/chọn từ queue, phải có đúng video ID và trạng thái native `1` cùng source/token dự kiến.
- Khi cue nguồn mới, không coi event playing/cued thiếu ID hoặc còn ID cũ là hoàn tất. Poll có thể nhận nguồn
  đúng khi cache API tới muộn, không phải chờ một event mới hoặc tạo iframe mới.
- Snapshot gửi `native_video_id`/`native_state`. Backend từ chối `ok: true` + playing nếu bằng chứng native đã
  cung cấp mâu thuẫn với bài được chọn. Trường này optional để phục vụ tab cũ; kiểm native đầy đủ cần frontend mới.
- Đây là các getter của IFrame Player API, không phải tìm kiếm/Data API hoặc bộ nghe âm thanh. Tài liệu:
  [YouTube IFrame API — trạng thái và thông tin video](https://developers.google.com/youtube/iframe_api_reference#Playback_status).

## Trace và giải thích lượt trước

Trace được checkpoint/chốt cùng câu trả lời trong trường JSON `messages.work` đã có, không migration. Chỉ cùng
owner đọc được qua lịch sử; `/api/companion` trả riêng `player_trace`, không dựng thêm bảng, nút hay hướng dẫn UI.
Không lưu command ID để thực thi lại, URL, key hoặc toàn bộ danh sách tìm kiếm/yêu thích/queue. Tối đa 24 lời gọi
mỗi turn; title/error và các payload đã có giới hạn. Không gửi trace vào console/analytics công khai.

Ba lượt có trace gần nhất (tối đa 8 lệnh/lượt trong ngữ cảnh giải thích) được kèm làm dữ liệu lịch sử cho AI;
không phải trạng thái live và không chạy lại. Nếu lỗi gốc không có mã/nguyên nhân, Peto được hướng dẫn nói đúng
phần chưa biết. Lịch sử trước bản sửa không tự có thêm trace, không thể suy ngược chắc chắn từ lời “Swapped”.

## Kiểm chứng

- Backend: **203 ca đạt**: `test_player_reply`, `test_player_tools`, `test_player_queue_readback`, `test_player_discovery_tools`,
  `test_byok`, `test_clock_tools`, `test_prompt_routing`, `test_player`, `test_player_catalog`. Có model giả khăng khăng
  nói thành công khi không gọi lệnh/khi lệnh thất bại, nhánh sửa đúng một lần, target bị bịa, native ID sai,
  mutation lặp bị chặn, adapter khóa riêng, trace lưu rồi đọc lại, trạng thái đọc hợp lệ và hội thoại thường.
- Frontend: **170 ca / 9 tệp đạt** (Player/queue/library/YouTube/API/Companion/Hearing).
- Chrome cài trên máy: **34 đạt, 4 skip theo thiết bị**, desktop và màn hình mobile mô phỏng. Ca mới giữ native
  video cũ trong lúc yêu cầu đổi: không xác nhận, không tự gửi load lại; yêu cầu mới sau đó phát đúng và giữ một
  iframe. Các ca thư viện, loop/shuffle, mic/giọng đọc/Live2D và phát nền cũ vẫn đạt. Build frontend đạt.

Các kết quả là provider/YouTube giả, không phải phát nhạc/AI thật hoặc Android thật. Không khẳng định đã xác định
đúng nguyên nhân lịch sử production.

## Deploy và thử lại

Cập nhật backend + frontend, rebuild frontend rồi restart backend, không key/dependency/migration mới.
Guard câu xác nhận/trace hoạt động từ backend với các tab hỗ trợ control hiện có. Nhận đầy đủ native proof cần
frontend mới; tải lại khi kết thúc phiên nghe, vì F5 vẫn dừng iframe và xóa queue RAM.

Sau deploy thử đổi giữa hai video cho phép nhúng, cả lúc Player đang hiện và thu gọn. So title/âm thanh thực với
câu xác nhận. Thử video lỗi: chỉ báo lỗi/chưa xác nhận, không tự đổi bài khác. Sau đó yêu cầu thử lại rõ ràng;
lượt mới được phép thực hiện. Hỏi “what actually happened?” và đối chiếu `player_trace` trong lịch sử nếu có lỗi.
