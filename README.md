# Peto Web

Giao diện chat riêng cho Peto: **chat chữ, xem ảnh và đọc tệp chữ**.

Bot Discord (`Tracen Jukebox`) vẫn phát triển độc lập. Web có database riêng;
có thể bật đọc bản tóm tắt trí nhớ từ bot qua Memory Gateway, không ghi ngược
vào bot. `PETO_WEB_HANDOFF.md` là bối cảnh ban đầu; README này mô tả code hiện tại.

## Chạy

Cần Python 3.12+ và Node 20+.

```bash
# 1. Cài đặt
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 2. Cấu hình
cp .env.example .env      # rồi điền phần Discord, xem bên dưới

# 3. Đăng nhập xAI một lần trên máy chạy server
cd backend
../.venv/Scripts/python.exe -m xai_auth login
../.venv/Scripts/python.exe -m xai_auth status

# 4. Chạy — hai terminal
cd backend && ../.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

Mở http://localhost:5173. Dev server của Vite tự proxy `/api` sang backend nên
không cần cấu hình CORS khi chạy local.

### Cấu hình đăng nhập Discord

1. Vào https://discord.com/developers/applications, tạo application (hoặc dùng
   application sẵn có của bot).
2. Tab **OAuth2**: copy `CLIENT ID` và `CLIENT SECRET` vào `.env`.
3. Vẫn tab đó, thêm **Redirect**:
   `http://localhost:5173/api/auth/discord/callback`
4. Điền `PETO_ALLOWED_DISCORD_IDS` bằng Discord ID của từng người trong nhóm,
   cách nhau bằng dấu phẩy. **Rỗng nghĩa là không ai vào được.**
5. Sinh `PETO_SESSION_SECRET`:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`

Chưa biết Discord ID? Cứ đăng nhập thử — nếu chưa được cho phép, trang sẽ hiện
đúng ID của tài khoản đó để bạn thêm vào danh sách.

Sau khi sửa `PETO_ALLOWED_DISCORD_IDS`, **khởi động lại dịch vụ web** để nạp
cấu hình mới. Quyền được kiểm tra ở mỗi yêu cầu API, nên phiên cũ của tài khoản
đã bị xóa khỏi danh sách cũng bị chặn. Không cần đổi khóa ký để thu hồi một người.

## Đưa lên VPS

Xem [DEPLOY.md](DEPLOY.md) — từng bước cho VPS đang chạy bot, kèm cách bật
trí nhớ từ Discord và bảng tra khi hỏng.

Ở production, backend phục vụ luôn giao diện đã build (`frontend/dist`), nên
chỉ cần một tiến trình và một cổng cho Cloudflare Tunnel trỏ vào — không cần
nginx. Lúc dev không có `dist` nên Vite vẫn lo phần giao diện như cũ.

## Kiểm thử

```bash
cd backend
../.venv/Scripts/python.exe -m pytest
```

Toàn bộ test chạy bằng nhà cung cấp giả và database tạm — không chạm dữ liệu thật.

Kiểm thử giao diện và build:

```bash
cd frontend
npm test
npm run build
```

Sau đợt cải tiến 10/09/2026: **169 test backend, 23 test frontend đạt**;
TypeScript và Vite build đạt. Các test bao gồm thu hồi quyền, chuyển hội thoại
với kết quả tải về không đúng thứ tự, giữ bản nháp, dừng phản hồi, lưu câu trả lời
dở dang, nâng cấp schema, ẩn danh, phân trang, bảng Markdown, ngày giờ/múi giờ,
vòng gọi công cụ, tin nhắn dài, tạo ảnh, đổi tab khi đang tạo, xác nhận xóa ảnh,
giữ mô tả khi lỗi, thời hạn tạo ảnh và phản hồi ảnh không hợp lệ.

Khi cập nhật bản này, cài lại dependencies, build frontend rồi khởi động lại web.
Backend tự bổ sung cột trạng thái tin nhắn khi khởi động; giữ nguyên dữ liệu cũ.

## Kiến trúc

```
backend/
  main.py        FastAPI: /api/chat (SSE), /api/conversations, /api/health
  auth.py        Đăng nhập Discord OAuth2, cookie phiên có chữ ký
  persona.py     Tính cách Peto, đã tách khỏi Discord
  db.py          SQLite riêng; mọi truy vấn lọc theo owner
  rate_limit.py  Cooldown + đồng thời + hàng chờ có timeout
  xai_auth.py    OAuth xAI riêng của web + CLI login/status/logout
  config.py      Đọc biến môi trường
  chat_tools.py  Đồng hồ máy chủ, múi giờ IANA và bộ chạy công cụ đã đăng ký
  imagine_api.py API Peto tạo ảnh: tạo, liệt kê, tải và xóa ảnh theo tài khoản
  ai/
    base.py      Interface ChatProvider — phần còn lại chỉ nói chuyện qua đây
    xai.py       Grok Responses API: stream và vòng gọi công cụ có giới hạn
    mock.py      Trả lời giả, không gọi mạng
    routing.py   Chọn mức suy luận low/medium/high
    imagine.py   Kết nối dịch vụ tạo ảnh; kiểm tra dữ liệu ảnh trả về
frontend/
  src/api.ts     Đọc SSE bằng fetch (endpoint là POST nên không dùng EventSource)
  src/App.tsx    Màn hình đăng nhập + giao diện chat
  src/Imagine.tsx Peto tạo ảnh: gợi ý, tiến trình, bộ ảnh và khung xem ảnh
```

### Đổi nhà cung cấp AI

Thêm một file trong `backend/ai/` cài đặt `ChatProvider`, đăng ký vào
`_PROVIDERS` trong `backend/ai/__init__.py`, rồi đặt `PETO_AI_PROVIDER`. Không
phải sửa route, database hay giới hạn tải.

Đặt `PETO_AI_PROVIDER=mock` bất cứ lúc nào để làm việc trên giao diện mà không
tốn hạn mức xAI.

## Peto tạo ảnh

Mở tab **Tạo ảnh**, nhập mô tả hoặc chọn một gợi ý rồi bấm **Tạo ảnh**.
Giao diện có hai chế độ **Nhanh / Chi tiết**, độ phân giải **1K / 2K**, tỉ lệ
khung hình và số ảnh. Chọn gợi ý hoặc **Dùng lại mô tả** chỉ điền nội dung;
yêu cầu tạo ảnh chỉ gửi khi người dùng bấm tạo hoặc nhấn Enter.

- Có thể chuyển sang Trò chuyện trong lúc chờ rồi quay lại: mô tả, yêu cầu
  đang chạy và kết quả được giữ trong phiên trang hiện tại. Tải lại cả trang
  trong lúc đang tạo chưa có cơ chế theo dõi tiến trình nền.
- Nhấp ảnh để xem toàn bộ khung hình, chuyển giữa các ảnh trong lượt và tải
  xuống với tên `peto-…`. Escape đóng khung xem; hộp thoại hỗ trợ bàn phím.
- **Sửa ảnh:** bấm **Thêm ảnh**, chọn PNG/JPEG/WebP (tối đa 8 MB), nhập yêu cầu
  rồi bấm **Sửa ảnh**. Có xem trước, đổi/gỡ ảnh, kéo thả và dán ảnh vào ô nhập.
  Khi mở một ảnh trong bộ ảnh, bấm **Sửa ảnh này** để tiếp tục chỉnh sửa ảnh đó.
- Mỗi lượt sửa dùng một ảnh gốc và lưu kết quả thành lượt mới. **Xem ảnh gốc**
  mở bản gốc được lưu riêng; **Dùng lại mô tả** nạp cả ảnh gốc lẫn yêu cầu sửa.
  Xóa lượt cũ không làm mất bản gốc của lượt sửa mới. Nếu lỗi, ảnh đã chọn và
  yêu cầu vẫn được giữ; chuyển sang chat rồi quay lại cũng không mất bản nháp.
- Xóa yêu cầu xác nhận và cho biết số ảnh sẽ mất. Nếu tạo hoặc xóa lỗi,
  mô tả/ảnh hiện có vẫn được giữ để thử lại.
- Giao diện dùng **Peto tạo ảnh**, **Tạo ảnh** và thông báo của Peto. Các tên
  model, biến môi trường, đường dẫn `/api/imagine` và bảng dữ liệu được giữ
  tương thích. Không đổi slug model thành tên thương hiệu vì API cần tên thật.
- API lọc ảnh theo tài khoản đăng nhập. Thời hạn gọi dịch vụ áp dụng cho toàn
  bộ lượt tạo và tải ảnh, thay vì chỉ cho từng lần đọc dữ liệu. Phản hồi JSON
  và chữ ký định dạng ảnh được kiểm tra trước khi lưu.

Các tùy chọn kết nối vẫn theo [tài liệu tạo ảnh của xAI](https://docs.x.ai/developers/model-capabilities/images/generation).
Khi có ảnh gốc, backend dùng `/images/edits` với ảnh dạng data URI theo
[tài liệu sửa ảnh](https://docs.x.ai/developers/model-capabilities/images/editing).
Trình duyệt chỉ gửi nội dung ảnh hoặc ID ảnh thuộc tài khoản đang đăng nhập;
không nhận URL ảnh tùy ý. Bảng ảnh cũ được bổ sung cột `kind` khi khởi động,
mặc định các ảnh cũ là kết quả tạo ảnh. Ảnh gốc dùng cùng quyền truy cập riêng tư.
Mặc định `PETO_IMAGINE_MODEL=grok-imagine-image-2.0`,
`PETO_IMAGINE_TIMEOUT_SECONDS=90`, `PETO_MAX_IMAGINE_N=4`,
`PETO_MAX_IMAGINE_PROMPT_CHARS=2000`, `PETO_MAX_IMAGINE_SOURCE_BYTES=8388608`.
Giới hạn chọn tệp ở giao diện là 8 MB; máy chủ có thể đặt mức thấp hơn qua biến
môi trường trên. Xem `.env.example` để cấu hình.

Đợt sửa này đã thử giao diện tối/sáng ở máy tính và điện thoại, tạo/xem ảnh
và sửa ảnh với nhà cung cấp giả, kiểm thử lỗi dịch vụ và quyền truy cập. Ảnh giả chỉ là
PNG một điểm ảnh để kiểm tra đường đi dữ liệu; chưa đánh giá chất lượng ảnh
hay chỉnh sửa thật, hoặc xác minh xác thực với dịch vụ xAI thật. Chưa triển khai lên VPS.

## Ngày giờ và độ dài dành cho web

- Mỗi lượt gửi kèm múi giờ IANA từ trình duyệt, ví dụ `Asia/Barnaul`.
  **Ngày giờ lấy từ đồng hồ máy chủ**, không lấy giờ do trình duyệt tự khai.
  Khi trình duyệt không cung cấp múi giờ, dùng `PETO_DEFAULT_TIMEZONE`, mặc định
  `Asia/Ho_Chi_Minh`. Múi giờ không hợp lệ bị từ chối, không âm thầm đoán.
- Mốc thời gian mới được đưa vào ngữ cảnh ngay trước mỗi lượt gọi AI, kể cả
  khi hội thoại cũ được mở lại hoặc đã chờ trong hàng đợi. Peto có thể dùng mốc
  đó để hiểu hôm nay/hôm qua/ngày mai; không mặc định biết vị trí của người dùng.
- Công cụ `get_current_datetime` cho phép AI tra lại giờ hiện tại ở múi giờ
  khác. Python `zoneinfo` và dependency `tzdata` xử lý ngày đổi theo múi giờ và
  giờ mùa hè trên cả Windows và Linux. Đây chưa phải công cụ lịch, nhắc việc
  hay tra lịch âm.
- xAI nhận schema công cụ, backend kiểm tra và chạy công cụ rồi gửi kết quả
  trở lại AI. Giao diện chỉ nhận phần văn bản trả lời. Tối đa 3 vòng thực thi,
  8 lời gọi công cụ trong một lượt; kết thúc bằng thông báo rõ nếu vượt giới hạn.
  Luồng giữ ngữ cảnh công cụ trong lượt với `store=false`, theo
  [tài liệu function calling](https://docs.x.ai/developers/tools/function-calling)
  và [hướng dẫn giữ trạng thái trong input](https://docs.x.ai/developers/tools/advanced-usage).
- Không còn chốt 4.000 ký tự ở giao diện hoặc luật ép 1–3 câu. Mặc định web
  nhận **32.000 ký tự/tin**, AI có ngân sách **8.192 token/phản hồi** (token không
  tương đương ký tự, còn phụ thuộc model và phần suy luận). Có thể chỉnh qua
  `PETO_MAX_INPUT_CHARS` và `XAI_MAX_OUTPUT_TOKENS`; cấu hình rõ trong `.env`
  được ưu tiên. Không tự cắt hoặc chia tin theo giới hạn của Discord.
- Timeout mặc định thấp/trung bình/cao là 180/300/480 giây để đủ thời gian
  stream nội dung dài. Khi AI chạm giới hạn hoặc kết nối dừng giữa chừng, giữ
  phần đã viết và đánh dấu chưa hoàn tất, không giả vờ trả lời xong.

Thử: “Bây giờ mấy giờ?”, “Hôm nay thứ mấy?”, “Ở New York hiện tại là mấy giờ?”.
Provider `mock` trả lời các câu hỏi ngày giờ đơn giản bằng đồng hồ thật để thử
luồng web; khả năng hiểu câu hỏi linh hoạt và chọn múi giờ khác cần provider AI.
Chưa gọi xAI thật trong đợt kiểm thử này. Khi cập nhật VPS, cài lại requirements
(có `tzdata`), build frontend rồi khởi động lại web.

## Danh tính

Đăng nhập bằng Discord OAuth2 với scope `identify`. Máy chủ tự đổi code lấy
token rồi tự hỏi Discord "người này là ai" — **không bao giờ** nhận Discord ID
do trình duyệt gửi lên. Phiên nằm trong cookie `HttpOnly` có chữ ký.

Discord ID đã xác minh được lưu ở bảng `users` và dùng làm `owner` của mọi hội
thoại (`discord:<id>`).

## Trí nhớ từ Discord (một chiều, chỉ đọc)

Peto trên web có thể đọc trí nhớ dài hạn mà bot Discord đã tích lũy về đúng
người đang đăng nhập, để giữ tính liên tục giữa hai nơi.

**Bật ở cả hai phía** (chỉ dùng được khi web và bot chạy **cùng máy**):

```bash
# Sinh một token dùng chung
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- Repo bot, trong `.env`: `MEMORY_GATEWAY_TOKEN=<token>`
- Peto Web, trong `.env`:
  `PETO_MEMORY_GATEWAY_URL=http://127.0.0.1:8766` và
  `PETO_MEMORY_GATEWAY_TOKEN=<cùng token>`

Rồi khởi động lại cả hai. Để trống token là tắt — web vẫn chat bình thường,
chỉ là Peto không nhớ gì từ Discord.

Giới hạn cố ý của phần này:

- **Một chiều.** Chuyện nói trên web không chảy ngược về trí nhớ Discord.
- **Chỉ bản tóm tắt** và ghi chú đã ghim; không lấy lịch sử chat thô, để không
  mang nguyên văn tin nhắn riêng ở DM sang một bề mặt khác.
- **Chỉ đọc.** Web không có đường nào ghi vào `bot_memory.db`.
- **Loopback.** Cổng của bot chỉ nghe `127.0.0.1`, không bao giờ đặt sau
  Cloudflare Tunnel.
- **Tôn trọng chế độ ẩn danh.** Mỗi lượt chat hỏi lại gateway để xác minh trạng
  thái mới; không dùng cache trí nhớ từ lượt trước. Biến `PETO_MEMORY_CACHE_TTL`
  cũ không còn có tác dụng. Việc bật ẩn danh không xóa câu trả lời web đã lưu.
- **Hỏng thì bỏ qua.** Bot tắt hay token sai thì chat vẫn chạy, chỉ mất trí nhớ.

## Ranh giới đang được giữ

- Prompt của web không chứa tên thật hay Discord ID của thành viên. Có test
  chặn (`tests/test_persona.py`).
- Peto xem được ảnh đính kèm trong chat, tạo/sửa ảnh trong tab Tạo ảnh; chưa có
  nhạc, tìm kiếm hay giọng nói.
- Database riêng và **file token xAI riêng**; không dùng chung file nào với
  production Discord.
- Không có credential AI nào xuống trình duyệt. Discord access token chỉ dùng
  một lần để đọc hồ sơ rồi bỏ, không lưu.
- Chỉ Discord ID trong `PETO_ALLOWED_DISCORD_IDS` mới vào được — chưa mở đăng ký
  công khai.
- Mọi truy vấn hội thoại lọc theo `owner` ở backend; biết ID của người khác cũng
  không đọc được.
- Có hướng dẫn triển khai và unit dịch vụ mẫu. Trạng thái VPS thực tế không
  được xác nhận chỉ bằng việc đọc repository hoặc chạy test local.

## Trải nghiệm chat hiện có

- Chuyển hội thoại có trạng thái tải và bỏ qua kết quả cũ; chưa gửi được khi
  nội dung hội thoại chưa tải xong.
- Bản nháp và tệp được giữ lại nếu yêu cầu chưa được máy chủ xác nhận. Khi đã
  nhận tin, UI dùng đường dẫn tệp thật từ backend. Nếu mất kết nối trước xác
  nhận, hãy kiểm tra lịch sử trước khi gửi lại để tránh gửi trùng.
- Dừng/lỗi/timeout giữ phần trả lời đã nhận và đánh dấu chưa hoàn tất. Dừng
  trước khi có chữ không để lại dấu đang trả lời chạy mãi.
- Xóa hội thoại có xác nhận; danh sách có nút tải thêm các hội thoại cũ hơn 50.
- Bảng Markdown và khối mã cuộn ngang; đọc tin cũ không bị kéo xuống mỗi đoạn
  trả lời mới. Giữ tông tím tối, thu gọn cột chat trên màn hình rộng.
- Tối đa 4 tệp/tin, 8 MB/tệp, tổng 16 MB theo cấu hình mặc định. Ảnh và tệp chữ
  được chuyển vào ngữ cảnh AI. **PDF chỉ được lưu để tải lại, chưa trích nội dung**;
  giao diện nhắc rõ giới hạn này. Tệp được kiểm tra và chỉ chủ sở hữu đọc được.

## Chưa có ở bước này

Đọc nội dung PDF, gọi công cụ, giọng nói, nhân vật 3D, ghi hoặc đồng bộ trí nhớ
hai chiều với Discord. Chưa kiểm chứng chất lượng AI thật và hoạt động VPS trong
đợt kiểm thử local nêu trên.
