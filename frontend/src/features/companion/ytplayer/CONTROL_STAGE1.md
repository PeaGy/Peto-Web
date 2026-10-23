# Peto điều khiển Player — giai đoạn 1 (23/10/2026)

Đã được chủ web commit/deploy ở `0602baf`; chủ web xác nhận mở Player và đọc title với AI thật. Các phần dưới ghi
lần bàn giao giai đoạn 1; bước tiếp theo ở [CONTROL_STAGE2.md](./CONTROL_STAGE2.md). Bản đối chiếu lúc bắt đầu: `218c686`.

## Phạm vi đã làm

- Một công cụ native `control_player`: `status`, `open`, `hide`, `close`, `play`, `pause`, `next`, `restart`,
  `seek`, `set_volume`, `mute`, `unmute`, `set_shuffle`, `set_repeat` (`off`/`all`/`one`).
- Peto đọc tên video/kênh, trạng thái phát, tiến độ/thời lượng, âm lượng, mode và số bài chờ qua kết quả thật của
  browser. Không nhét toàn bộ hàng đợi/yêu thích vào mỗi tin nhắn và không suy trạng thái hiện tại từ lịch sử chat.
- Điều khiển player đang có, kể cả khi thu gọn; không tạo iframe phụ. `open` luôn mở, không toggle. `hide` giữ phát,
  `close` dùng đúng luồng X để hủy iframe; mở lại sau X vẫn chuẩn bị ở trạng thái dừng. `play` có thể mở lại nguồn
  cũ sau X. Nếu chưa chọn video thì Peto nhận lỗi rõ ràng, không tự chọn bài.
- Next dùng thứ tự queue hiện tại, bỏ qua loop một bài; không còn bài thì báo hết. Restart phát lại nguồn hiện tại
  từ điểm bắt đầu của nguồn, giống nút UI hiện có; không phải bài trước trong lịch sử. Có thể Next qua lỗi 150.
- Shuffle/loop nhận giá trị đích, tránh lời gọi lặp làm đổi mode lần nữa. Đặt loop one trực tiếp không đi ngang
  qua loop all và không khôi phục các bài đã phát một cách ngoài ý muốn.
- Giữ prompt persona/examples; hướng dẫn Player ngắn nằm riêng tại `backend/prompts/companion_player.py`.
  Một tâm trạng hoặc lời đề nghị tự nó chưa yêu cầu bật nhạc. Tìm tên/link/playlist qua chat, chọn nhạc cho nhân vật,
  hỏi bài tiếp theo và đọc/sửa hàng đợi/yêu thích vẫn thuộc các giai đoạn sau.

## Luồng lệnh và vòng đời

1. Client Companion mới gửi `player_control: 1`. Client cũ, Chat thường và các lượt phụ không được cấp công cụ.
2. Provider gọi tool; server kiểm action/args, tạo ID ngẫu nhiên cho đúng owner/lượt, stream sự kiện `player_command`
   đến đúng request đang nhắn. Không broadcast tới các tab khác.
3. Browser thực hiện qua controller đang dùng cho UI. Phát/dừng chờ sự kiện trạng thái YouTube; âm lượng/tua đọc lại
   API. Mode và cửa sổ chờ React cập nhật. Đổi bài có kiểm token để không nhận thành công nhầm một nguồn khác.
4. Client POST `/api/companion/player/commands/{id}/result`. Server chỉ nhận đúng owner và lệnh còn chờ, một lần;
   `ok: true` không có state được chuyển thành chưa xác nhận. Kết quả được đưa lại provider rồi mới viết bản chốt.
   Bản nháp trước tool được xóa khỏi câu trả lời như trước khi tra web; nếu đã bật đọc streaming, một phần câu dẫn
   có thể đã được đọc trước khi provider quyết định gọi tool. Prompt yêu cầu không xác nhận trước kết quả.

Server chờ tối đa 12 giây; browser chờ mỗi bước tối đa 8 giây, đồng thời kiểm hạn lệnh. Kết quả không về thì nói
chưa xác nhận, không tự lặp lại Next/restart. Client gộp sự kiện trùng ID (cache tối đa 100 kết quả trong phiên).
Hết lượt/dừng/mất kết nối thì pending được dọn; phục hồi lịch sử không chạy lại lệnh. Browser từ chối lệnh đã hết
hạn, request đã hủy hoặc Companion không ở phía trước. Không khôi phục phát nền mới sau khi rời trang/mobile ẩn tab.

Đây là trạng thái browser tự báo, không chứng minh âm thanh thực tế đã ra loa. Video có thể bị chặn autoplay hoặc
không cho nhúng; kết quả lỗi không được coi là đã phát. Hạn lệnh dùng đồng hồ client nên thiết bị cần có giờ đúng.
Broker nằm trong RAM cùng tiến trình chat: phù hợp service uvicorn một worker đang có; nhiều worker/instance cần
broker dùng chung hoặc định tuyến gắn phiên trước khi đổi mô hình triển khai.

## Các bộ não

- Peto mặc định và các adapter kế thừa vòng Responses (OpenAI/Claude), Chat Completions/Ollama được nối qua công cụ
  chuẩn, không dò từ khóa trong câu người dùng. Các model tự chọn bởi người dùng vẫn cần hỗ trợ function calling.
- Gemini dùng khóa riêng hiện chỉ có native Google Search, chưa có vòng function calling; không cấp Player tool,
  và prompt báo đúng khả năng thiếu này. Không giả lập thành công bằng câu chữ.
- Chưa gọi AI có phí hoặc YouTube thật cho tính năng chat mới. Các kết quả dưới đây dùng fake provider/network;
  khả năng model thật lựa chọn đúng tool, diễn đạt tiếng Việt/Anh và độ trễ cần thử sau deploy.

## Kiểm chứng

- Backend: nhóm `test_player_tools`, `test_byok`, `test_clock_tools`, `test_prompt_routing`, `test_player`: **93 đạt**.
  Riêng `test_player_tools`: **21 đạt**, bao gồm hai vòng native provider chờ kết quả thật/giả lỗi, schema strict/null,
  owner/401/404/422, timeout/hủy, không cấp quyền cho Chat/client cũ/Gemini và adapter BYO.
- Frontend: `playerControl`, `player-queue`, `usePlayerLibrary`, `useYouTubePlayer`, `api.test`, `Companion.test`,
  `Hearing.test`: **159 đạt / 9 tệp**. Nạp lazy, trạng thái rỗng không tải API, chống trùng, hủy/ẩn/hết hạn, ack trước
  final text và đặt repeat trực tiếp.
- Chrome cài trên máy, desktop + mobile mô phỏng: bộ `playwright.player.config.ts` **26 đạt / 4 skip theo thiết bị**.
  Bốn ca mới đi qua UI chat thật với SSE/API/YouTube giả: đọc trạng thái, mở/ẩn/đóng, phát/pause/volume/mute/unmute/
  seek/Next/restart/shuffle/loop, một iframe, Next gửi hai sự kiện chỉ chạy một lần, blocked/150/hết hạn/skip qua lỗi.
  Các ca cũ kiểm hàng đợi/tim/playlist, 200 bài, 10 vòng mount/destroy, Space/micro/renderer và PCM tổng hợp vẫn đạt.
- Build frontend đạt. Không đổi schema DB, dependency hoặc cấu hình key.
- Đã gặp lỗi sandbox Windows không chia sẻ được tệp tạm của Vitest; chạy ngoài sandbox đạt các con số trên.
  Lần browser đầu có điều kiện chờ sai (nút gửi bị disable vì ô nhập rỗng) và tải lazy quá giới hạn 8 giây; đã sửa
  bài kiểm thử, rồi chạy toàn bộ suite một worker đạt. Không sửa giao diện để chiều test.

Nhóm backend mở rộng có một lỗi sẵn có: `test_companion_turn_uses_own_key_without_memory` thất bại nếu chạy sau
`test_chat_stage4`, khi bộ lọc trí nhớ không trả lại hội thoại mới. Đối chiếu archive **HEAD chưa sửa** bằng cùng
hai module tái hiện đúng IndexError (15 đạt, 1 lỗi); nhóm trực tiếp ở trên chạy với DB mới đạt. Không sửa luồng trí
nhớ ngoài phạm vi giai đoạn này. Hai lượt rộng lần lượt 154/125 đạt cùng lỗi đó; chưa chạy toàn bộ backend.

## Commit/deploy và thử thật

Commit các thay đổi, build frontend rồi restart backend như quy trình đang dùng. Không cần key mới hoặc migration.
Cần cập nhật cả hai phía: backend cũ không hiểu sự kiện mới, frontend cũ không có cầu nối xác nhận.

Chọn sẵn một bài và thêm một bài chờ trong Player, thu gọn, rồi thử trên bộ não Peto:

1. “What are we listening to?” → đúng tên/kênh/trạng thái.
2. “Nhỏ xuống 30%”, “tắt tiếng”, “bật tiếng lại” → UI và tiếng thực tế đổi tương ứng.
3. “Tạm dừng”, “phát tiếp”, “tua tới giây 40” → đúng trạng thái/tiến độ.
4. “Bật shuffle”, “lặp bài này”, “tắt loop”, “bài tiếp theo” → đúng UI và nguồn phát.
5. “Mở Player”, “thu gọn Player”, “dừng và đóng Player” → phân biệt giữ phát với X.
6. Thử khi chưa có nguồn, hết bài chờ và video lỗi; Peto phải báo đúng phần chưa làm được.

Mobile thực chưa nghiệm thu thay đổi chat này. Kết quả Xiaomi trước đó chỉ thuộc thư viện Player cũ, không được
tính lại như đã thử tính năng mới. Không deploy hay gửi chat có phí tự động trong đợt triển khai này.
