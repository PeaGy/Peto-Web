# Bàn giao ngữ cảnh — Peto Web và hướng phát triển chatbot 3D

Cập nhật: 09/09/2026.

Tài liệu này giúp tiếp tục thảo luận trong một project/cuộc chat mới mà không
phải kể lại từ đầu. Đây là bản tóm tắt có chọn lọc, không phải toàn bộ lịch sử
cuộc trò chuyện hay bộ nhớ của Peto. Không có token, cookie hoặc dữ liệu người dùng.

## 1. Đọc trước khi bắt đầu

- Người dùng vẫn tiếp tục phát triển bot Discord ở dự án cũ. Peto Web là hướng
  phát triển riêng, không thay thế hoặc bỏ bot Discord.
- Việc hiện được yêu cầu là chuẩn bị bản bàn giao. Chưa có yêu cầu tạo giao diện,
  triển khai máy chủ web, chuyển dữ liệu, hay thay đổi bot để phục vụ web.
- “Nhánh riêng” trong trao đổi là một hướng dự án; không tự suy ra tên Git branch
  hoặc yêu cầu fork/chuyển repository.
- Phân biệt quyết định của người dùng với đề xuất của trợ lý ở các mục dưới.
  Không coi toàn bộ đề xuất là đã được phê duyệt để triển khai.
- Nếu code thực tế mới hơn tài liệu, kiểm tra lại rồi báo khác biệt. Không giả vờ
  nhớ những cuộc trò chuyện hoặc dữ liệu không được cung cấp.

## 2. Mục tiêu và mong muốn đã được người dùng nêu

- Đây là dự án sinh viên, quy mô nhỏ, dùng chơi và trò chuyện trong nhóm bạn.
- Muốn đưa AI Peto ra ngoài Discord, trước hết để chat được trên một giao diện riêng.
- Về sau có dự định nâng cấp thành **3D AI chatbot**.
- Muốn tiếp tục làm việc lâu dài, giữ ngữ cảnh và những quyết định quan trọng giữa
  dự án Discord và dự án mới.
- Ưu tiên cách làm vừa sức, dễ hiểu, phát triển từng bước; chưa có yêu cầu xây một
  dịch vụ công khai quy mô lớn.

## 3. Hướng đã được đề xuất trong cuộc trao đổi

Đây là phương án làm việc để tiếp tục bàn, chưa phải danh sách tính năng đã chốt:

1. **Web chat trước:** chat chữ, giữ tính cách Peto, lịch sử riêng từng người;
   cân nhắc gửi ảnh sau khi luồng cơ bản ổn định.
2. **Giọng nói sau:** micro, nhận dạng giọng nói, Peto trả lời bằng âm thanh;
   có bật/tắt micro và ngắt lời rõ ràng.
3. **Nhân vật 3D sau nữa:** chuyển động khi nghỉ, chớp mắt, biểu cảm, nhép miệng.
   Phần nhân vật là lớp giao diện, không phải một bộ AI mới phải viết lại từ đầu.

Trợ lý đề xuất tạo **project/repository Peto Web riêng**, dùng lại phần AI có
chọn lọc. Không chép nguyên `features/ai_chat.py` thành một bản sao thứ hai.
Từng bước tách phần dùng chung nếu thật sự cần; không bắt buộc dựng ngay một hệ
thống nhiều dịch vụ hay repository thứ ba cho thư viện.

Có thể cân nhắc chạy hai ứng dụng riêng trên cùng VPS nếu đủ tài nguyên, nhưng
chưa đo tải cho ứng dụng web, chưa chọn cổng/domain hoặc duyệt triển khai.
Chưa có lý do để mua GPU chỉ nhằm gọi dịch vụ AI từ xa. Lựa chọn mô hình chạy
cục bộ, giọng nói và yêu cầu phần cứng vẫn để ngỏ.

## 4. Những việc chưa chốt — không tự quyết thay người dùng

- Tên chính thức, thư mục và repository của web; `Peto-Web` hiện chỉ là tên gợi ý.
- Giao diện, công nghệ frontend/backend, cách cập nhật câu trả lời theo luồng.
- Nhà cung cấp AI, phương thức xác thực, model, hạn mức và ngân sách cho web.
- Đăng nhập Discord, tài khoản được duyệt, hay cơ chế đăng nhập nhỏ gọn khác.
- Chia sẻ trí nhớ với Discord hay tách riêng. Phương án thận trọng đã đề xuất:
  lịch sử web riêng trước, liên kết tài khoản và đồng bộ sau nếu được duyệt.
- Phạm vi upload ảnh/tệp, lưu giữ/xóa dữ liệu và quyền của quản trị viên.
- Giọng nói, nhân vật 3D, phong cách/model nhân vật và giấy phép tài sản.

Không cần hỏi tất cả cùng lúc. Bước tiếp theo nên chốt phạm vi chat chữ và cách
giới hạn người truy cập trước, rồi mới chọn thiết kế triển khai phù hợp.

## 5. Dự án Discord hiện có

Tên sản phẩm thường dùng: **Peto**, tài khoản bot còn được gọi là **Pearto**.
Repository được mô tả trong README/AGENTS là **Tracen Jukebox**.

Nguồn tham khảo cục bộ tại thời điểm bàn giao:

`C:/Users/binhb/Downloads/Discord-Bot-Music-main/Discord-Bot-Music-main`

Đây là đường dẫn để tìm code nguồn nếu môi trường mới được phép truy cập;
không phải dependency phải hard-code vào ứng dụng mới. Nếu không truy cập được,
hãy yêu cầu cung cấp những file nguồn cần thiết, không yêu cầu gửi dữ liệu riêng.

- Python và `discord.py`; bot chạy local trên Windows và production trên Ubuntu.
- Production cũ: `/home/ubuntu/peto`, dịch vụ `peto.service`.
- Có nhạc/voice, tải media, AI chat và trí nhớ, ảnh, Study Mode, kiến thức Limbus,
  gacha nhiều game, Peto Points, mã quà tặng và thông báo game.
- Những tính năng Discord đó không mặc nhiên thuộc phạm vi web.
- File `AGENTS.md` của repository cũ quy định cách sửa và bảo vệ hệ thống cũ.
  Phải đọc lại trước khi thay đổi code ở đó.

## 6. Bản đồ phần AI cần tham khảo

Các đường dẫn sau tương đối so với repository Discord, không phải file đã có
trong project web mới:

| File | Nội dung đáng tham khảo | Lưu ý khi tái sử dụng |
| --- | --- | --- |
| `features/ai_chat.py` | `GrokChat`, các phần prompt/tính cách, `_create_response`, `_ask_grok`, media, công cụ và định tuyến | Gắn chặt với Discord, quyền server, vòng đời bot và trí nhớ; không import nguyên module vào web như một API độc lập |
| `user_memory.py` | Hội thoại, trí nhớ cá nhân, chế độ ẩn danh | Tham khảo logic/schema; không sao chép database thật hoặc tin rằng ID do trình duyệt gửi là danh tính đã xác thực |
| `guild_ai_settings.py` | Chính sách AI, quyền, cooldown, hàng chờ và giới hạn đồng thời | Có thể học cách giới hạn tải; chính sách web cần mô hình tài khoản riêng |
| `xai_oauth.py` | Cơ chế gọi/xác thực nhà cung cấp hiện có | Chỉ xem code, không chuyển file token; xác minh phương thức được hỗ trợ và quyền sử dụng trước khi áp dụng cho web |
| `study_mode.py` | Cách xử lý và trình bày bài học | Các nút/view Discord cần giao diện thay thế nếu bổ sung Study Mode cho web |
| `peto_help.py` | Nhận diện câu hỏi hướng dẫn Peto, chọn ngữ cảnh công khai, kiểm tra tên lệnh | Đang dựa vào cây slash-command Discord; web phải mô tả đúng khả năng của web, không giả vờ có voice/server |
| `peto_help_catalog.py` | Tài liệu tính năng dùng chung với `/help` | Là nội dung công khai, nhưng mô tả Discord; cần phân biệt nền tảng khi sử dụng |
| `commands/help.py` | Bảng trợ giúp Discord | Không cần chuyển UI này nguyên xi |
| `.env.example`, `README.md` | Tài liệu cấu hình và tổng quan | Chỉ là ví dụ/mô tả; không chứng minh cấu hình production hiện tại |

README hiện mô tả Grok/xAI, OAuth và API key dự phòng. Đó là hiện trạng code
Discord, **không phải xác nhận có thể dùng nguyên tài khoản/gói đó cho một ứng dụng
web nhiều người dùng**. Trước khi tích hợp cần kiểm tra tài liệu, quyền sử dụng và
chi phí hiện hành của nhà cung cấp. Không mặc định người dùng muốn đổi sang OpenAI.

Giữ tính cách Peto bằng cách đọc các phần prompt liên quan rồi tách nội dung trung
lập với nền tảng. Rà soát các phần có tên người, quan hệ hoặc ngữ cảnh riêng;
không mang chúng sang web như thông tin chung cho mọi tài khoản.

## 7. Những đặc tính cần giữ khi thiết kế web

- Giao tiếp tự nhiên bằng tiếng Việt, không biến Peto thành bảng lệnh khô cứng.
- Câu hỏi “làm sao…” khác yêu cầu thực hiện; không tự phát nhạc, tạo ảnh hoặc gọi
  công cụ chỉ vì câu hỏi có từ khóa liên quan.
- Tạo/sửa/tìm ảnh cần ý định rõ ràng. Viết lại, dịch hoặc giải thích văn bản không
  được kích hoạt công cụ ảnh.
- Có timeout, retry hữu hạn, giới hạn đồng thời và chống spam. Một yêu cầu chậm
  không giữ toàn bộ nhóm bạn chờ.
- Không đưa payload công cụ/JSON thô cho người dùng; phân biệt dữ kiện đã kiểm tra
  với điều chưa biết.
- Giữ định tuyến mức suy luận phù hợp nếu nhà cung cấp hỗ trợ: nhẹ cho chat thường,
  cao hơn cho bài toán hoặc công việc thật sự cần suy luận.
- Ngữ cảnh và quyền của Discord không tự có trên web. Không tuyên bố “đã phát nhạc”
  hoặc “đã thay đổi server” khi web chưa có tích hợp tương ứng.

## 8. Danh tính, trí nhớ và bảo mật

Bot cũ gắn trí nhớ dài hạn với Discord `user_id`, dùng được giữa DM/server nhưng
không chia sẻ cho người khác. Chế độ ẩn danh không đọc/ghi trí nhớ dài hạn.

Nếu web liên kết Discord trong tương lai, chỉ ánh xạ danh tính sau khi đăng nhập
đã được máy chủ xác minh. Không cho nhập tùy ý một Discord ID để đọc trí nhớ.
Mọi thao tác xem/sửa/xóa hội thoại phải kiểm tra chủ sở hữu ở backend.

- Không sao chép `.env`, `.xai_tokens.json`, cookie, token, database production,
  lịch sử chat, file tải riêng hoặc ảnh đính kèm của thành viên vào dự án mới.
- Không đưa thông tin xác thực AI xuống trình duyệt hoặc nhúng vào mã frontend.
- Không dùng chung trực tiếp file SQLite production giữa hai ứng dụng chỉ để
  “đồng bộ nhanh”. Thiết kế giao diện truy cập và quyền trước nếu cần liên thông.
- Chỉ dùng dữ liệu giả cho kiểm thử. Không log toàn bộ nội dung riêng hoặc thông
  tin xác thực; không coi yêu cầu lấy trí nhớ của người khác là hợp lệ.
- Không mở đăng ký công khai hoặc triển khai public khi chưa được người dùng duyệt.

## 9. Trạng thái gần nhất cần biết

Trong cuộc chat cũ, phần Peto tự hướng dẫn cách dùng đã được triển khai:

- Nhánh chat chữ chỉ đọc tài liệu công khai và metadata lệnh đang đăng ký.
- Dùng chung nội dung với `/help`; kiểm tra lệnh trong câu trả lời và dùng hướng
  dẫn cục bộ nếu AI trả công cụ/lệnh chưa xác nhận hoặc gặp lỗi.
- Không đi vào luồng xử lý ảnh/link, công cụ hoặc trí nhớ cá nhân khi nhận diện
  câu hỏi hướng dẫn. Vẫn giữ quyền/kênh và giới hạn Chat AI.
- Các bài kiểm thử liên quan: `tests/test_ai_self_help.py`,
  `tests/test_peto_help.py`, `tests/test_help.py`, `tests/test_image_intent.py`.
- Lần chạy toàn bộ kiểm thử được ghi nhận trong cuộc chat: **289 tests, OK**.
  Đây là kết quả lịch sử của thay đổi đó, không phải một lần chạy mới cho Peto Web.

Khi chuẩn bị tài liệu này, HEAD local là `39d86e1`, và worktree sạch trước khi
thêm tài liệu. Những file self-help ở trên đang có trong repository. Không suy
ra từ đó rằng VPS đã cập nhật, remote đã đồng bộ, hoặc web đã được tạo.

Phần nhạc đã được đo hiệu năng và người dùng chọn giữ nguyên pipeline hiện tại.
Không quay lại tối ưu nhạc hay thay proxy/FFmpeg trong công việc Peto Web.

## 10. Cách bắt đầu trong project mới

1. Đặt bản sao tài liệu này vào thư mục project web.
2. Đọc tài liệu, xác nhận mục tiêu và chỉ hỏi những lựa chọn đang thật sự chặn
   bước kế tiếp. Không yêu cầu người dùng kể lại toàn bộ lịch sử bot.
3. Đề xuất phạm vi chat chữ nhỏ, độc lập với production Discord; chốt cách truy
   cập cho nhóm bạn và cách gọi AI trước khi triển khai.
4. Khi được duyệt, xây một luồng chat hoạt động từ giao diện đến backend, có lỗi
   rõ ràng và giới hạn yêu cầu; kiểm thử bằng dữ liệu giả.
5. Chỉ tách phần AI dùng chung khi đã đọc code và có kiểm thử bảo vệ bot cũ.
   Không refactor toàn bộ bot hoặc bật thêm giọng nói/3D ngay trong bước chat chữ.

Sau mỗi quyết định quan trọng, cập nhật tài liệu của project mới để cuộc chat
sau có nguồn ngữ cảnh bền vững. Duy trì danh sách “đã chốt / còn mở / đã kiểm thử”.

## 11. Lời nhắn mở đầu có thể dùng trong project mới

> Đọc PETO_WEB_HANDOFF.md trước khi bắt đầu. Đây là hướng phát triển Peto Web cho
> nhóm bạn, còn bot Discord vẫn được phát triển độc lập. Hãy tóm tắt ngắn những gì
> đã hiểu, phân biệt quyết định đã chốt với đề xuất, rồi cùng tôi chốt phạm vi chat
> chữ trước. Chưa thay đổi bot Discord, dùng dữ liệu production hay triển khai
> public. Mục tiêu lâu dài là thêm giọng nói và nhân vật 3D, không cần làm ngay.

## 12. Nhật ký quyết định — Peto Web (09/09/2026)

### Đã chốt
- **Stack:** backend Python + FastAPI, database SQLite riêng, frontend Vite +
  React + TypeScript. Chọn React vì bước nhân vật 3D sau này sẽ dùng
  `three.js` / VRM, không phải viết lại giao diện.
- **Không clone project chat mã nguồn mở làm nền.** Tự viết phần lõi nhỏ, chỉ
  dùng lại thư viện. Lý do: Peto có tính cách, trí nhớ và luật định tuyến riêng.
- **Phạm vi bước 1:** chat chữ, lịch sử lưu lại, stream câu trả lời, báo lỗi rõ,
  timeout + giới hạn đồng thời. Chưa đăng nhập, chưa ảnh, chưa công cụ, chưa deploy.
- **Nhà cung cấp AI:** chạy bằng adapter giả (`mock`) trước; provider thật chỉ
  thêm một file khi đã duyệt.

### Đã làm và đã kiểm thử
- Khung `backend/` + `frontend/` chạy được đầu-cuối tại `localhost:5173`.
- Tính cách Peto đã port từ `features/ai_chat.py` (dòng 455-817) sang
  `backend/persona.py`, **bỏ** `KNOWN_PEOPLE_PROMPT`, `SPECIAL_USERS`,
  `SPECIAL_USER_REFERENCE_NOTES` (tên thật + Discord ID), các luật công cụ,
  luật toán riêng của Discord và Study Mode.
- Thêm `WEB_PLATFORM_PROMPT`: Peto ở web nói rõ chưa có nhạc/ảnh/tìm kiếm.
- Giới hạn tải rút gọn từ `guild_ai_settings.py`: cooldown theo người,
  `max_concurrent`, hàng chờ có giới hạn và timeout.
- Định tuyến mức suy luận rút gọn từ `_reasoning_effort_for_request`.
- **22 test, OK** (`cd backend && ../.venv/Scripts/python.exe -m pytest`).
  Gồm test chặn tên thật/Discord ID lọt vào prompt web. Chạy bằng dữ liệu giả.

### Còn mở
- Nhà cung cấp AI cho web: model, quyền sử dụng, hạn mức, chi phí. Chưa kiểm tra
  liệu tài khoản xAI của bot Discord có được dùng cho web nhiều người hay không.
- Cách giới hạn người truy cập cho nhóm bạn (mã mời, đăng nhập Discord, hay khác).
- Chia sẻ trí nhớ với Discord hay tách riêng. Hiện đang tách riêng hoàn toàn.
- Deploy: cổng, domain, VPS chung hay riêng. Chưa đo tải.
- Giọng nói, nhân vật 3D, model và giấy phép tài sản.

## 13. Cập nhật — AI thật và đăng nhập Discord (09/09/2026)

### Người dùng đã chốt
- **Giữ xAI `grok-4.6` qua OAuth** cho web, giống bot Discord đang chạy tốt.
- **Thêm đăng nhập Discord**, hướng tới việc Peto biết người chat trên web và
  trên Discord là cùng một người.

### Đã làm
- `backend/xai_auth.py` — luồng PKCE riêng của web, **file token riêng**
  (`backend/data/xai_tokens.json`). Không đọc và không ghi `.xai_tokens.json`
  của bot. CLI: `python -m xai_auth login | status | logout`.
- `backend/ai/xai.py` — gọi xAI Responses API có `stream=True`, giữ
  `reasoning.effort`, không khai báo tool nào. Lỗi xác thực/rate limit/mạng
  được diễn đạt thành câu người dùng đọc được.
- `backend/auth.py` — Discord OAuth2 scope `identify`, chống CSRF bằng state
  cookie, phiên là cookie `HttpOnly` có chữ ký (`itsdangerous`).
- Bảng `users`: ánh xạ `discord:<id>` ⇄ hồ sơ Discord đã xác minh. Đây là nền
  cho việc liên kết trí nhớ sau này.
- Mọi endpoint hội thoại nay yêu cầu đăng nhập và lọc theo `owner`.

### Quyết định bảo mật đã áp dụng
- **Allowlist `PETO_ALLOWED_DISCORD_IDS`** — rỗng thì không ai vào được. Đây là
  cách thực thi "không mở đăng ký công khai" ở mục 8.
- Discord ID chỉ đến từ máy chủ tự hỏi Discord, không nhận từ trình duyệt.
- Discord access token dùng một lần để đọc hồ sơ rồi bỏ; không lưu, không có
  credential nào xuống frontend.
- Trang đăng nhập chỉ xin `identify` — không xin email, không xin danh sách server.

### Đã kiểm thử
**43 test, OK** (`cd backend && ../.venv/Scripts/python.exe -m pytest`), gồm:
- Mọi endpoint trả 401 khi chưa đăng nhập.
- Người dùng khác không đọc/xóa/chen được vào hội thoại của mình dù biết đúng ID.
- Cookie phiên bị sửa một ký tự là hỏng; state không khớp thì từ chối callback.
- `/api/auth/me` không lộ token, secret hay email.
- File token của web không trùng file của bot Discord.
- Prompt web vẫn không chứa tên thật hay Discord ID.

Không test nào gọi ra xAI hoặc Discord thật.

### Còn mở
- **Chia sẻ trí nhớ với bot Discord vẫn CHƯA được duyệt.** Đăng nhập mới chỉ
  cho biết "ai đang chat"; lịch sử web vẫn tách riêng. Muốn đồng bộ thì phải
  thiết kế giao diện truy cập và quyền trước, không dùng chung file SQLite.
- Chi phí và hạn mức khi nhiều người cùng dùng token xAI của người vận hành.
- Deploy: domain, HTTPS, `PETO_COOKIE_SECURE=true`, đổi `DISCORD_REDIRECT_URI`.
- Giọng nói, nhân vật 3D.

### Lưu ý khi chạy lại
Các hội thoại tạo ở bước 1 thuộc owner `local` (chưa có đăng nhập) nên sẽ không
hiện sau khi thêm đăng nhập. Đó là dữ liệu thử, xóa `backend/data/peto_web.db`
là sạch.

## 14. Đã chạy được đầu-cuối (09/09/2026)

Peto Web đã hoạt động thật: đăng nhập Discord thành công, chat nhận được câu
trả lời từ Grok qua OAuth. Đây là lần đầu toàn bộ chuỗi chạy với dịch vụ thật,
không phải provider giả.

Cấu hình đang chạy: `PETO_AI_PROVIDER=xai`, application Discord dùng chung với
bot, allowlist 4 Discord ID.

### Ba lỗi đã gặp khi dựng, và cách sửa

Ghi lại để lần sau không mất thời gian dò lại:

1. **`UnicodeEncodeError` khi chạy `python -m xai_auth login`.** Console Windows
   dùng cp1258, in tiếng Việt là vỡ ngay dòng đầu — chết trước cả khi kịp mở
   trình duyệt. Sửa: `_force_utf8_output()` ép stdout/stderr sang UTF-8.
   Test chặn: `test_cli_prints_vietnamese_on_legacy_console`.
2. **`xai_auth login` treo tới khi bấm Ctrl+C.** Server nhận callback dùng
   `handle_request` (một-shot); trình duyệt xin `/favicon.ico` trước là tiêu mất
   lượt phục vụ duy nhất, callback thật bị từ chối kết nối. Sửa: đổi sang
   `serve_forever` + `Event`, request lạ trả 404 rồi tiếp tục đợi. Có thêm
   đường thoát dán URL thủ công khi loopback bị chặn.
   Test chặn: `tests/test_callback_server.py`.
3. **Discord báo invalid khi đăng nhập.** URL authorize có `prompt=none`, tham
   số này chỉ đúng với người ĐÃ từng cấp quyền cho application — lần đầu thì
   chưa ai cấp. Sửa: bỏ hẳn `prompt`, dùng mặc định `consent`.

Ngoài ra: `uvicorn --reload` chỉ theo dõi file `.py`, **không** theo dõi `.env`.
Sửa `.env` xong phải khởi động lại backend bằng tay.

### Trạng thái kiểm thử
**51 test, OK** (`cd backend && ../.venv/Scripts/python.exe -m pytest`).
Không test nào gọi ra xAI hoặc Discord thật.

### Việc tiếp theo nên cân nhắc
- Chưa đo chi phí/hạn mức khi 4 người cùng dùng token xAI của người vận hành.
  Bot Discord và web dùng chung tài khoản nên ăn chung hạn mức.
- Trí nhớ vẫn tách riêng. Muốn Peto nhớ xuyên web ↔ Discord thì đó là bước
  thiết kế riêng, chưa được duyệt.
- Chưa deploy. Khi deploy cần: HTTPS, `PETO_COOKIE_SECURE=true`, đổi
  `DISCORD_REDIRECT_URI` sang domain thật và đăng ký lại trong Developer Portal.

## 15. Nối trí nhớ web ← Discord (09/09/2026)

Người dùng đã duyệt: **một chiều**, **chỉ bản tóm tắt**, và cho phép sửa repo
bot sau khi được báo trước chính xác những gì sẽ thay đổi.

### Phát hiện quan trọng khi khảo sát
`user_memory.get_summary()` **bỏ qua tham số `scope`** và luôn dùng
`GLOBAL_MEMORY_SCOPE`. Trí nhớ dài hạn vốn đã là MỘT bản cho mỗi người, dùng
chung giữa DM và mọi server — đúng như `AGENTS.md` mô tả. Nên web không phải
chọn "lấy trí nhớ ở server nào"; nó chỉ là một cửa sổ nữa nhìn vào cùng bản đó.

### Thay đổi ở repo bot (Tracen Jukebox)
Worktree sạch trước khi sửa, HEAD `39d86e1`, branch `main`.

| File | Thao tác |
| --- | --- |
| `features/memory_gateway.py` | Mới — cog aiohttp chỉ-đọc, loopback, mặc định tắt |
| `tests/test_memory_gateway.py` | Mới — 14 test offline |
| `.env.example` | Sửa — thêm khối `MEMORY_GATEWAY_*`, tất cả để trống |

**Không đụng** `user_memory.py`, `features/ai_chat.py`, `bot.py`, hay bất kỳ
database nào. **Chưa commit, chưa push.**

Endpoint: `GET /internal/memory/{user_id}` + header `X-Peto-Token`.

Bất biến đã cài vào code và có test chặn:
- Trống `MEMORY_GATEWAY_TOKEN` = không mở cổng nào.
- Từ chối khởi động nếu host không phải loopback.
- Chỉ đọc — test quét source cấm `add_post`/`set_summary`/`add_message`.
- Không trả lịch sử thô — test cấm `get_history`/`chat_history`.
- Ẩn danh thì không đọc trí nhớ (dùng scope riêng `"web"`).
- Token so bằng `compare_digest`; lỗi 401 không nói rõ thiếu hay sai token.
- Lỗi database không lộ chi tiết ra response.

### Thay đổi ở Peto Web
- `backend/discord_memory.py` — client có cache 5 phút, timeout 3s, **fail-open**.
- `backend/persona.py` — `build_memory_context()`, luật đi kèm bám theo
  `MEMORY_PRIVACY_PROMPT` của bot.
- `backend/main.py` — `_build_system_prompt()` ghép trí nhớ vào prompt, tra bằng
  Discord ID lấy từ phiên đã xác minh.
- `backend/config.py`, `.env.example`, `README.md`.

### Kiểm thử
- Bot: **303 test, OK** (`python -m unittest discover -s tests`), tăng từ 289.
  `git diff --check` sạch.
- Web: **67 test, OK**, tăng từ 51. Gồm test "bot tắt thì chat vẫn chạy" và
  "web chỉ hỏi trí nhớ của chính người đang đăng nhập".
- Không test nào gọi ra mạng thật.

### Chưa làm — cần quyết sau
- **Chưa bật.** Cả hai phía vẫn để trống token. Muốn bật thì đặt cùng một token
  ở `.env` của bot và của web rồi khởi động lại (xem README).
- Web và bot phải **cùng máy**. Hiện bot ở VPS, web ở máy cá nhân, nên chỉ dùng
  được sau khi web dọn lên VPS.
- Ghi ngược từ web về trí nhớ Discord: chưa làm, chưa duyệt.
- Trên VPS, `.env` không đi theo `git pull` — phải thêm biến bằng tay rồi
  `sudo systemctl restart peto`.
