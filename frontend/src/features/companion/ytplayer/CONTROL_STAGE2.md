# Peto điều khiển Player — giai đoạn 2 (23/10/2026)

Giai đoạn 1 đã được chủ web commit/deploy ở `0602baf`. Chủ web xác nhận AI thật mở được Player và đọc đúng title.
Đợt này ghép quản lý hàng đợi/yêu thích vào Companion thật; chủ web đã commit/deploy ở `19706c2`.
Nội dung nghiệm thu ban đầu dưới đây dùng mock, không gọi AI/TTS trả phí.

## Bổ sung sau báo lỗi tên bài khi di chuyển (23/10/2026)

Chủ web báo yêu cầu đưa bài thứ hai trong phần Tiếp theo lên đầu; Peto nói đã chuyển và nêu “Stay With Me”,
nhưng UI không có bài này. Đọc lịch sử trên production thấy đúng câu trả lời đó. Không có trace tool lưu từ lượt
cũ nên chưa biết lệnh thực sự đã chạy hay model chỉ nói đã chạy; không quy nguyên nhân cho người dùng/tab cũ.
Không gửi chat/gọi AI hoặc sửa hàng đợi/yêu thích production để điều tra. Không yêu cầu F5 khi đang nghe vì
queue chỉ tồn tại trong RAM; tải lại mất phiên nghe, favorites vẫn lưu.

Bản sửa đã được chủ web commit/deploy ở `7b912f4`, xác nhận chuyển queue đúng mà không cần F5. Chỉ thay backend và prompt khả năng:

- Remove/move/play phải dùng entry ID + revision đã đọc trong chính turn đó; ID đoán hoặc từ turn trước bị từ chối
  trước khi gửi lệnh xuống browser. Client vẫn kiểm revision lúc reducer thực thi.
- Target trong phản hồi mutation phải khớp video ID đã chọn. Sau move, server tự gửi `list_queue` đọc lại tối đa
  5 mục quanh đích. Chỉ xác nhận khi entry ID, video ID, vị trí và revision đều khớp. Trả `change` gồm vị trí
  trước/sau cùng target và các mục xung quanh vừa đọc để AI có dữ liệu cụ thể khi trả lời.
- Sai/lỗi đọc lại hoặc queue đã đổi tiếp thì báo chưa xác minh; không chạy lại mutation tự động. Khi hết kết nối/
  hủy lượt, cả lệnh đọc lại cũng được dọn. Không thêm lượt gọi model chỉ để xác minh.
- Prompt dùng tên từ kết quả tool, yêu cầu thực thi trước khi nói đã làm và không coi lời xác nhận cũ là bằng chứng.
  Tab v1 được nói rõ không có quyền đọc/sửa queue. Không thay persona/examples, UI hoặc cách lưu queue.

Kiểm chứng: **118 ca backend đạt**, gồm nhóm `test_player_tools`, `test_player_queue_readback`, `test_player`,
`test_byok`, `test_clock_tools`, `test_prompt_routing`. Có provider giả đọc → move → server tự readback → final,
ID lịch sử/giả, sai target/order/revision, phản hồi thiếu dữ liệu, trang cuối queue 200 và hủy đang chờ readback.
Đây là AI/browser giả, chưa phải nghiệm thu AI thật; không bảo đảm model tuyệt đối không trả lời sai khi bỏ qua tool.

Deploy chỉ cần restart backend sau khi commit, lúc không có lượt chat đang xử lý. Không cần rebuild frontend hoặc
F5 tab **v2** đang phát: đọc lại dùng giao thức v2 sẵn có. Backend restart không tự xóa queue/iframe trong tab.
Sau deploy có thể thử “move the second upcoming song to first”, so UI và tên Peto nói; không phải tắt nhạc để thử.

## Cách dùng sau khi cập nhật

| Bạn nhắn | Kết quả mong muốn |
| --- | --- |
| “Có bao nhiêu bài yêu thích của tôi?” | Đọc mới từ tài khoản và trả tổng số chính xác. |
| “Liệt kê yêu thích của tôi.” | Tên/kênh từ dữ liệu thật, có phân trang; không tự điền những bài chưa đọc. |
| “Thêm hết bài yêu thích vào hàng đợi.” | Thêm cuối, giữ nguyên bài đang nghe; báo số thêm, số trùng và số chưa thêm do đầy. |
| “Lưu bài này vào yêu thích.” / “Bỏ yêu thích bài này.” | Đặt trạng thái mong muốn, chỉ báo xong sau phản hồi máy chủ. |
| “Thêm bài X trong yêu thích vào hàng đợi.” | Đọc danh sách, chọn ID của bài đã lưu rồi thêm riêng; không tìm video mới. |
| “Có những bài nào trong hàng đợi?” | Đánh số phần Tiếp theo từ 1, không tính bài đang nghe. |
| “Xóa bài thứ ba khỏi hàng đợi.” | Đọc danh sách rồi xóa đúng entry ID của mục số 3. |
| “Đưa bài cuối lên đầu.” | Di chuyển đúng entry; tắt shuffle giống thao tác tay trong UI. |
| “Phát bài thứ hai trong hàng đợi.” | Chọn đúng mục và chờ YouTube xác nhận; không tự phát nguồn cũ khi mở cửa sổ. |
| “Bài tiếp theo là gì?” | Báo bài tự phát kế tiếp; nếu loop one thì nói bài hiện tại sẽ lặp. Có thêm dữ liệu bài khi bấm Next. |

## Quyết định hành vi

- Đếm/liệt kê yêu thích luôn dùng GET tài khoản mới, không lấy danh sách cache cũ hoặc coi lỗi tải là 0 bài.
  Đọc hoặc thêm hàng loạt khi chưa mở Player chỉ mount bộ điều khiển kín, không mở cửa sổ, iframe hoặc mini player.
- Bulk bỏ qua video đã là bài hiện tại hoặc có trong queue, so theo video ID. Giữ thứ tự yêu thích mới nhất trước
  như UI hiện có, thêm cuối, tối đa 200 bài chờ. Ví dụ 500 yêu thích khi queue trống: thêm 200, báo 300 chưa thêm.
  Gọi lại báo 200 trùng và 300 chưa thêm, không tự tạo bản trùng. UI thêm link/playlist thủ công vẫn cho bản trùng
  và mỗi bản có entry ID riêng. Bulk không gọi oEmbed cho từng bài, kể cả metadata trống.
- `set_favorite` nhận giá trị đích, không toggle. Có thể áp dụng cho bài hiện tại hoặc ID đã đọc từ favorites/queue.
  UI tim và tool dùng chung writer với khóa chống ghi đồng thời, phản hồi máy chủ và hủy request khi hết phiên.
  Read cũ về muộn không ghi đè kết quả mới. Đọc thất bại giữ cache để UI còn hiển thị, nhưng tool trả thất bại.
- Mutations theo entry ID cần `queue_revision` từ lần đọc. Sửa thứ tự, tự sang bài, đổi mode hoặc sửa queue làm
  đổi revision; metadata cập nhật tên/thời lượng không làm đổi revision. Sai revision thì không sửa; Peto cần đọc lại
  và đánh giá yêu cầu, không âm thầm lấy mục khác cùng vị trí. Reducer kiểm lại revision lúc thực thi để xử lý cả
  thao tác tay đang chờ React commit. Các mục trùng video vẫn phân biệt bằng ID.
- Bài kế tiếp luôn khớp mục đầu đang hiển thị. Khi All + shuffle gần hết vòng, thứ tự vòng sau được chuẩn bị trong
  lúc bài cuối còn phát, không trộn bất ngờ khi nhận ENDED. Loop one chỉ ảnh hưởng tự hết bài; Next vẫn bỏ qua.
  Một bài duy nhất + All tự lặp, nhưng không có mục để bấm Next. Không có nguồn đang phát thì chỉ thêm queue,
  không suy rằng một bài chờ đã bắt đầu phát.
- Lịch sử nội bộ để khôi phục vòng All được giữ tối đa 201 mục gồm hiện tại + 200 mục còn lại. Phiên nghe dài
  rồi bật All không làm queue phình vượt 200. Các mục đang chờ luôn được ưu tiên giữ; không cắt queue đang nghe.
- Metadata gửi công cụ giới hạn 300/200 ký tự Unicode cho title/kênh, giữ nguyên emoji, không cắt đôi surrogate.
  Dữ liệu trả mỗi trang tối đa 50 mục (mặc định 20), `limit: 0` chỉ đếm. Model vẫn có ngân sách tool của lượt cũ;
  danh sách lớn có thể cần nhiều lượt để liệt kê, không được khẳng định đã đọc hết khi còn trang.

## Giao thức và phạm vi

Client mới gửi `player_control: 2`. `control_player` thêm 9 action: `list_queue`, `list_favorites`, `next_track`,
`remove_queue_entry`, `move_queue_entry`, `play_queue_entry`, `set_favorite`, `enqueue_favorite`, `enqueue_favorites`.
Kết quả gồm snapshot cũ và `data` có kiểu/giới hạn: danh sách, tổng, phân trang, revision, bài kế hoặc số đã thêm.

Backend tiếp tục nhận version 1 và chỉ cấp schema/hướng dẫn giai đoạn 1 cho tab cũ, không gửi action mới xuống
trình duyệt chưa biết xử lý. Client không có protocol vẫn không được cấp tool. Cơ chế ID chống trùng, owner,
timeout 12 giây, dọn pending và không replay khi khôi phục của giai đoạn 1 giữ nguyên.

`playerLibraryControl.ts` xử lý thư viện riêng, `usePlayerControl` nối media/window. Prompt khả năng vẫn tách khỏi
persona/examples. Khi phát từ queue lần đầu, controller chờ vùng iframe mount rồi mới tạo ý định autoplay, tránh
ý định bị stop trước khi mount tiêu thụ. X trong lúc media command đang chờ làm lệnh đó hết hiệu lực; không phát
muộn khi mở lại. Thao tác thư viện không cần giữ cửa sổ mở.

Chưa thêm tìm video ngoài thư viện, nhập link/playlist qua chat, gu nhạc của Peto hay hội thoại gợi ý nhạc → đồng ý.
Đó là giai đoạn 3. Gemini khóa riêng vẫn chưa có vòng function calling nên không cấp khả năng này. Các adapter khác
cần model hỗ trợ công cụ. Không key mới, dependency mới hoặc thay schema database. Không thay bố cục/controls UI.

## Kiểm chứng

- Backend: `test_player_tools`, `test_player`, `test_byok`, `test_clock_tools`, `test_prompt_routing`: **104 đạt**.
  Có vòng native AI giả đọc queue rồi sửa theo ID/revision, schema strict/null, kết quả tối đa 50, v1/v2, owner/lifecycle
  và các bộ não. Một mã video dùng làm đầu vào sai trong test hóa ra dài đúng 11 ký tự; đổi dữ liệu test, không nới validator.
- Frontend: `playerControl`, `player-queue`, `usePlayerLibrary`, `useYouTubePlayer`, `api.test`, `Companion.test`,
  `Hearing.test`: **166 đạt / 9 tệp**. Có 100 lần chuyển vòng so preview với nguồn thật, guard revision/entry trùng,
  phiên nghe dài, bulk/cap/metadata, idempotent favorite, lỗi tải/hủy và metadata emoji.
- Chrome cài trên máy, desktop/mobile mô phỏng: toàn bộ `playwright.player.config.ts` **30 đạt / 4 skip theo thiết bị**.
  Sau kiểm tra cuối về ID mục phát và hủy lệnh, chạy lại riêng bốn ca thư viện mới: **4 đạt**.
  Các ca mới dùng UI chat và Player thật, provider/YouTube/network giả. Có phân trang, 500 yêu thích, 200 chờ,
  chống bulk trùng, thay đổi DB yêu thích, stale mutation, move/play và loop/shuffle qua ENDED.
- Build frontend đạt. Không coi kết quả mock là AI thật, YouTube thật hoặc nghiệm thu Android mới.
  Lượt đầu đã tìm ra lỗi phát queue khi chưa từng mở Player (ý định phát bị tiêu thụ trước host mount); đã sửa
  và chạy lại ca desktop/mobile đạt. Không gọi dịch vụ có phí hoặc thay dữ liệu production.
- Lỗi fixture trí nhớ khi chạy `test_chat_stage4` trước BYO đã được đối chiếu mã cũ trong giai đoạn 1; không sửa
  luồng trí nhớ trong đợt này. Không chạy lại nhóm đó hoặc toàn bộ backend.

## Commit/deploy và nghiệm thu thật

Commit rồi rebuild frontend + restart backend. Có thể cập nhật backend trước để phục vụ cả tab v1 đang mở;
người dùng cần tải trang mới để nhận công cụ thư viện v2. Không cần thêm key hoặc migration.

Sau deploy trên Peto mặc định, thử các câu trong bảng bằng dữ liệu yêu thích của chính bạn. Kiểm tra tên/tổng
khớp UI, bulk giữ bài đang phát, xóa đúng phần Tiếp theo và câu trả lời bài kế đúng thực tế. Thử cả Player đóng/
thu gọn và Android/Chrome. Nếu sửa queue bằng tay lúc Peto xử lý, lệnh cũ phải bị từ chối hoặc đọc lại, không xóa nhầm.
Khi trình duyệt chặn autoplay hoặc video không nhúng được, Peto phải báo chưa phát được thay vì xác nhận thành công.
