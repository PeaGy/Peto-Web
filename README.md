# Peto Web

Giao diện chat riêng cho Peto, **trợ lý AI** trả lời trung thực và đi thẳng vào việc: **chat chữ, xem ảnh, đọc
PDF, Word và tệp chữ; tạo tệp DOCX/PDF với thẻ xem trước ngay trong chat và bảng tài liệu bên phải**. Tên Peto lấy từ
bot Discord; khi muốn, người dùng bật [Chế độ nhập vai](#chế-độ-nhập-vai) để Peto trò chuyện bằng persona nhập vai của bot.

Nhắn “tạo file Word/PDF…” để Peto tạo tệp, xem trước, tải trực tiếp và mở
trong bảng tài liệu:
xem [hướng dẫn tài liệu](DOCUMENTS.md).

Bot Discord (`Tracen Jukebox`) vẫn phát triển độc lập. Web có database riêng;
có thể bật đọc bản tóm tắt trí nhớ từ bot qua Memory Gateway, không ghi ngược
vào bot. `PETO_WEB_HANDOFF.md` là bối cảnh ban đầu; README này mô tả code hiện tại.

## Chạy

Giọng nói dùng chung qua VPS: xem [hướng dẫn kết nối máy tạo giọng](voice-worker/README.md).
Model vẫn chạy trên Windows; người nghe không cần cài model.

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
4. Sinh `PETO_SESSION_SECRET`:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### Đăng nhập bằng Google (tùy chọn)

Tạo OAuth client loại **Web application** ở
[Google Cloud Console](https://console.cloud.google.com/apis/credentials), thêm
Authorized redirect URI khớp `GOOGLE_REDIRECT_URI`, rồi điền `GOOGLE_CLIENT_ID`
và `GOOGLE_CLIENT_SECRET`. Thiếu một trong hai thì nút Google tự ẩn, Discord và
Khách vẫn chạy bình thường.

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

Kiểm thử Peto Agent CLI (chỉ dùng thư viện chuẩn, chạy bằng pytest của venv):

```bash
.venv/Scripts/python.exe -m pytest agent-cli/tests
```

Sau đợt thêm tài liệu, tìm web và menu dấu +: **295 test backend, 164 test frontend đạt**;
TypeScript và Vite build đạt. Các test bao gồm thu hồi quyền, chuyển hội thoại
với kết quả tải về không đúng thứ tự, giữ bản nháp, dừng phản hồi, lưu câu trả lời
dở dang, nâng cấp schema, ẩn danh, phân trang, bảng Markdown, ngày giờ/múi giờ,
vòng gọi công cụ, tin nhắn dài, tạo ảnh, đổi tab khi đang tạo, xác nhận xóa ảnh,
giữ mô tả khi lỗi, thời hạn tạo ảnh, sửa ảnh, tìm web, nguồn trong lịch sử và
dừng tra cứu khi lỗi hoặc người dùng yêu cầu.

Khi cập nhật bản này, cài lại dependencies, build frontend rồi khởi động lại web.
Backend tự bổ sung cột trạng thái tin nhắn khi khởi động; giữ nguyên dữ liệu cũ.

## Kiến trúc

```
backend/
  main.py        FastAPI: /api/chat (SSE), /api/conversations, /api/health
  auth.py        Đăng nhập Discord OAuth2, cookie phiên có chữ ký
  persona.py     Lời nhắc hệ thống: Peto là trợ lý AI
  db.py          SQLite riêng; mọi truy vấn lọc theo owner
  rate_limit.py  Cooldown + đồng thời + hàng chờ có timeout
  xai_auth.py    OAuth xAI riêng của web + CLI login/status/logout
  config.py      Đọc biến môi trường
  chat_tools.py  Đồng hồ máy chủ, múi giờ IANA và bộ chạy công cụ đã đăng ký
  web_search.py  Quy tắc tra web, kiểm tra và chuẩn hóa nguồn tham khảo
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
  src/DocumentPanel.tsx Bảng tài liệu bên phải: danh sách, xem trước, phiên bản và tải tệp
  src/DocumentArtifactCard.tsx Thẻ tệp tạo trực tiếp trong tin nhắn
  src/WebSources.tsx Nguồn tham khảo có thể mở từ câu trả lời
  src/Imagine.tsx Peto tạo ảnh: gợi ý, tiến trình, bộ ảnh và khung xem ảnh
```

### Đổi nhà cung cấp AI

Thêm một file trong `backend/ai/` cài đặt `ChatProvider`, đăng ký vào
`_PROVIDERS` trong `backend/ai/__init__.py`, rồi đặt `PETO_AI_PROVIDER`. Không
phải sửa route, database hay giới hạn tải.

Đặt `PETO_AI_PROVIDER=mock` bất cứ lúc nào để làm việc trên giao diện mà không
tốn hạn mức xAI.

## Peto tạo ảnh

Mở tab **Tạo ảnh**, nhập mô tả hoặc chọn một gợi ý rồi bấm nút mũi tên để tạo.
Ô nhập theo kiểu Grok: hàng nút phía trên chọn **Nhanh / Chi tiết**, số ảnh và
tỉ lệ khung hình; trong khung có nút thêm ảnh để sửa và **1K / 2K**. Trên điện
thoại, ô nhập thu thành một thanh nổi ở đáy (nút trái mở thư viện ảnh, nút phải
mở tùy chọn) và chỉ mở đủ khi bấm vào; máy tính luôn hiện đủ. Chọn gợi ý
hoặc **Dùng lại mô tả** chỉ điền nội dung; yêu cầu tạo ảnh chỉ gửi khi người
dùng bấm tạo hoặc nhấn Enter.

- Trên điện thoại, nút Thư viện (hiện ảnh mới nhất) mở lưới mọi ảnh của 40 lượt
  gần nhất: tìm theo mô tả, chọn bố cục 2 hoặc 3 cột, lọc ảnh đã thích. Bấm
  **Chọn** hoặc giữ lâu một ảnh để chia sẻ, tải xuống hay xóa từng ảnh; lượt nào
  hết ảnh thì bị xóa theo. Nút **Thích** trong khung xem ảnh lưu trên máy chủ.

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

## Tìm kiếm web trong chat

Peto **tự động tìm web** khi câu hỏi cần thông tin mới, khi bạn yêu cầu
tìm/kiểm chứng hoặc đưa một URL cần đọc. Khung chat không còn ô chọn tìm web.

Nút **+** cạnh **Suy nghĩ** mở menu với **Thêm ảnh hoặc tệp** và **Tắt tìm kiếm
web**. Khi đã tắt, mục này đổi thành **Bật tìm kiếm web** để trở về tự động.
Tắt tìm web vẫn dùng được công cụ ngày giờ. Menu đóng khi chọn một mục,
nhấn Escape hoặc nhấp bên ngoài; được khóa khi đang trả lời.

Ví dụ: “Tìm thông báo mới nhất về Python và dẫn nguồn chính thức”, hoặc
“Đọc trang này rồi tóm tắt giúp mình: https://docs.python.org/3/”.
Lựa chọn bật/tắt giữ trong phiên trang hiện tại; tải lại trang về tự động.

Khi dịch vụ báo bắt đầu tra, giao diện hiện **Peto đang tìm trên web…**; sau đó
hiện tiến trình tổng hợp. Nguồn nằm dưới câu trả lời, bấm để mở danh sách và
đọc trang gốc. Chỉ lấy nguồn từ dữ liệu công cụ/annotations của dịch vụ,
không suy ra nguồn từ liên kết AI tự viết. Tối đa 30 URL HTTP(S) khác nhau,
không tải favicon hay truy cập URL nguồn từ máy chủ Peto.

Nguồn được lưu cùng tin nhắn, kể cả phần trả lời dở khi mất kết nối; mở lại
hội thoại vẫn xem được và Peto có thể hiểu câu hỏi tiếp về nguồn đó. Cột
`messages.sources` tự được bổ sung khi khởi động, giữ nguyên tin cũ. Mọi lượt
đọc lịch sử vẫn lọc theo tài khoản. **Dừng** ngắt luồng; sau khi đã nhận tiến
trình tra cứu, backend không tự thử lại khi timeout.

Backend dùng `web_search` của xAI Responses với kết nối hiện có, theo
[tài liệu tìm web](https://docs.x.ai/developers/tools/web-search) và
[nguồn trích dẫn](https://docs.x.ai/developers/tools/citations). Công cụ chạy
ở xAI, dùng giới hạn mặc định của dịch vụ và thời hạn chat hiện có; vòng gọi
công cụ ngày giờ vẫn có giới hạn riêng. Có thể phát sinh phí tìm kiếm theo
tài khoản dịch vụ. `PETO_WEB_SEARCH_ENABLED=true` mặc định; đặt `false` để
tắt toàn bộ tìm web. Quyền tìm kiếm thực tế còn phụ thuộc model và kết nối
AI; nếu dịch vụ không hỗ trợ, mở **+ → Tắt tìm kiếm web** để chat tiếp.

Prompt yêu cầu ưu tiên nguồn chính thức, phân biệt ngày đăng/ngày sự kiện,
không bịa nguồn và bỏ qua chỉ dẫn nằm trong trang web. Đây là chỉ dẫn cho AI,
không phải bảo đảm mọi kết luận từ web đều chính xác.

Provider `mock` nói rõ chưa tìm thật và không tạo nguồn giả. Kiểm thử tự động
dùng HTTP/SSE giả, kiểm tra lưu nguồn, quyền truy cập, lỗi và hủy. Đã thử thêm
một lượt tìm thật về vòng lặp `for`: kết nối xAI hiện có chạy được tìm kiếm,
trả nguồn và dẫn tới tài liệu Python chính thức trong câu trả lời. Kiểm tra
này không dùng lịch sử hoặc tệp riêng; chưa triển khai VPS.

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
  trở lại AI. Giao diện nhận văn bản, tiến trình và nguồn tham khảo, không nhận
  JSON công cụ ngày giờ. Tối đa 3 vòng thực thi, 8 lời gọi công cụ ngày giờ
  trong một lượt; kết thúc bằng thông báo rõ nếu vượt giới hạn.
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
- Prompt trợ lý không chứa phần nhập vai hay nội dung người lớn. Persona nhập vai chỉ bật được ở hội thoại mới, cho
  tài khoản Discord/Google đã xác nhận đủ 18 tuổi (có test).
- Peto xem ảnh đính kèm và tìm web trong chat, tạo/sửa ảnh trong tab Tạo ảnh;
  chưa có nhạc. Tab Companion nói thành tiếng khi máy tạo giọng của chủ web đang kết nối (xem bên dưới).
- Database riêng và **file token xAI riêng**; không dùng chung file nào với
  production Discord.
- Không có credential AI nào xuống trình duyệt, kể cả khóa `PETO_VOICE_WORKER_TOKEN` của máy tạo
  giọng. Discord access token chỉ dùng một lần để đọc hồ sơ rồi bỏ, không lưu.
- Đăng ký MỞ: Discord, Google, hoặc khách — không có allowlist. Ai có địa chỉ
  cũng dùng được và cũng tiêu quota AI của máy chủ.
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
- Tên hội thoại là câu tóm tắt ngắn do AI đặt ngay ở lượt đầu, không phải tin nhắn
  đầu bị cắt. Tên được đặt song song với câu trả lời nên không phải chờ thêm; đặt
  hỏng, quá chậm, hoặc tin nhắn chỉ có tệp thì giữ tên cắt tạm. Các lượt sau không
  đổi tên nữa.
- Xóa hội thoại có xác nhận; danh sách có nút tải thêm các hội thoại cũ hơn 50.
- Bảng Markdown và khối mã cuộn ngang; đọc tin cũ không bị kéo xuống mỗi đoạn
  trả lời mới. Giao diện chạy theo cài đặt sáng/tối của máy, đổi tay được trong
  Cài đặt; cột chat thu gọn trên màn hình rộng và thanh bên thu lại được.
- Tối đa 16 tệp/tin, trong đó ảnh, PDF và Word tối đa 4; 8 MB/tệp, tổng 16 MB
  theo cấu hình mặc định. Ảnh, lớp chữ PDF, phần thân và bảng Word (.docx),
  tệp chữ/code được chuyển vào ngữ cảnh AI. Tệp được kiểm tra và chỉ chủ sở hữu đọc được.

## Đọc tài liệu

Bấm **+ → Thêm ảnh hoặc tệp**, chọn PDF, Word **.docx** hoặc tệp chữ rồi gửi
câu hỏi, chẳng hạn “Tóm tắt tài liệu này” hoặc “So sánh hai bản kế hoạch”.
Chat hiện tiến trình đọc; dưới mỗi tệp có **Đã đọc chữ**, **Đọc được một phần**
hoặc **Chưa đọc được**. Bấm trạng thái để xem chi tiết, bấm tên tệp để tải lại.

- PDF được trích lớp chữ kèm số trang. Word giữ thứ tự đoạn và bảng, không
  tự gán số trang. Peto được hướng dẫn dẫn tên tệp và vị trí khi trả lời.
- Nội dung đã trích lưu trong SQLite riêng của web, dùng lại khi hỏi tiếp trong
  phạm vi lịch sử gần nhất (mặc định 20 tin). Tệp gửi từ bản cũ được đọc dần khi
  hỏi tiếp, tối đa 16 tệp mỗi lượt tính cả tệp mới (ảnh, PDF, Word vẫn tối đa 4).
  Xóa hội thoại xóa cả bản trích.
- Mặc định đọc tối đa 100 trang PDF, 80.000 ký tự/tệp, 160.000 ký tự tài liệu
  cho cả lượt. Ưu tiên tệp mới, chia phần còn lại giữa các tệp cùng tin nhắn;
  Peto nhận thông báo khi nội dung bị cắt. Tài liệu dài nên chia riêng phần cần hỏi.
- Bộ đọc chạy trong tiến trình riêng, có thể dừng và có thời hạn 15 giây/tệp.
  Word được kiểm tra kích thước nén/XML và chặn thực thể ngoài; PDF giới hạn
  stream giải nén. Không chạy macro, tệp nhúng hoặc lệnh chứa trong tài liệu.
- **Chưa OCR PDF dạng ảnh scan**, chưa xem ảnh/biểu đồ/bố cục gốc trong PDF hoặc
  Word. Word chưa đọc đầu/chân trang, chú thích, tệp nhúng và định dạng **.doc** cũ.
  PDF có mã hóa/mật khẩu cần gửi bản đã mở khóa. Tệp lỗi vẫn lưu để tải lại,
  nhưng Peto nhận đúng trạng thái chưa đọc được.

Khi cập nhật máy chủ, cài lại `backend/requirements.txt` để có `pypdf` và
`defusedxml`, xây dựng lại frontend rồi khởi động lại backend. Cột lưu chữ được
bổ sung tự động, giữ nguyên hội thoại cũ. Các giới hạn có trong `.env.example`.

Đã kiểm tra trích chữ bằng PDF/Word mẫu, hỏi tiếp từ bản trích đã lưu, giới hạn
giải nén, tệp lỗi/mã hóa, quyền riêng tư, dừng đọc và dữ liệu cũ. Đã thử tải tệp
trên giao diện máy tính và điện thoại bằng máy chủ riêng với phản hồi giả;
đợt này chưa kiểm chứng câu trả lời tài liệu bằng AI thật hoặc cập nhật VPS.

## Hồ sơ cá nhân

Trong **Cài đặt → Hồ sơ**, mỗi người tự điền họ tên, tên muốn Peto gọi, công việc
(chọn trong danh sách) và **Hướng dẫn cho Peto** — tối đa 1.500 ký tự, ví dụ "giải
thích ngắn gọn, đi thẳng vào vấn đề".

- Lưu theo tài khoản trong bảng `user_profiles`, tách khỏi thông tin Discord/Google
  vốn bị ghi đè mỗi lần đăng nhập.
- Máy chủ ghép hồ sơ vào prompt ở mỗi lượt chat, nên lưu xong là tin nhắn kế tiếp đã
  theo, kể cả trong hội thoại cũ.
- Hướng dẫn riêng được đóng khung và ghi rõ không thay được quy tắc của Peto; người
  dùng không thể tự chèn dấu kết thúc khung để viết tiếp như lệnh hệ thống.
- Chỉ dùng cho Peto trên web này, không gửi sang bot Discord.
- Lời chào ở màn hình trống gọi bằng tên này (chưa đặt thì dùng tên tài khoản) và
  đổi theo giờ trên máy: sáng, trưa, chiều, tối, khuya; ban ngày thỉnh thoảng có câu
  theo thứ trong tuần.
- Ảnh đại diện lấy từ Discord/Google, khách thì hiện chữ cái đầu; chưa tải được ảnh
  riêng lên.

## Chế độ nhập vai

Mặc định Peto là trợ lý AI. Muốn Peto trò chuyện như nhân vật của bot Discord, bấm dấu **+** cạnh ô nhắn ở một hội
thoại mới rồi chọn **Chế độ nhập vai**.

- Chế độ được chọn lúc bắt đầu và giữ suốt hội thoại: ô nhắn có nhãn **Nhập vai**, thanh bên ghi **· Nhập vai**. Muốn
  quay lại trợ lý thì mở hội thoại mới.
- Persona nhập vai có thể có nội dung người lớn, nên chỉ tài khoản Discord hoặc Google bật được, và lần đầu phải xác
  nhận đủ 18 tuổi (lưu theo tài khoản). Máy chủ tự kiểm tra lại điều kiện này, không chỉ dựa vào giao diện.
- Để giữ mạch truyện dài, hội thoại nhập vai gửi 100 tin gần nhất cho AI thay vì 20 tin như chat thường (đổi bằng
  `PETO_ROLEPLAY_MAX_HISTORY`), nên mỗi lượt tốn token hơn.
- Trí nhớ từ Discord, hồ sơ cá nhân, đọc tệp và tìm web vẫn dùng như chat thường. Tab Companion và Peto Agent luôn là
  trợ lý.

## Companion

Tab **Companion** nằm cạnh Trò chuyện và Tạo ảnh. Ở đây Peto trả lời một hai câu ngắn bằng tiếng
Anh như đang trò chuyện, rồi tự nói thành tiếng. Tab Trò chuyện vẫn trả lời đầy đủ bằng tiếng Việt.

- Companion có một mạch trò chuyện riêng, không hiện trong danh sách Trò chuyện. Nút **Bắt đầu lại**
  xóa mạch đó sau khi xác nhận.
- Lượt Companion luôn suy nghĩ ở mức thấp, không tìm web, không nhận ảnh hay tệp và không đặt tên
  hội thoại, để trả lời nhanh nhất có thể.
- Trên máy tính, màn hình chia hai: bên trái là sân khấu chỉ có nhân vật Live2D (model mẫu Hiyori Momose của Live2D
  Inc.), bên phải là cột chat với trạng thái Peto đang nhắn hay đang nói, nút **Tắt tiếng** và nút
  **Bắt đầu lại**.
- Trên máy tính, cuộn chuột hoặc chụm hai ngón trên sân khấu để phóng to/thu nhỏ quanh chỗ đang chỉ,
  giữ chuột giữa (hoặc một ngón tay trên màn cảm ứng) kéo để dời, bấm đúp để về cỡ vừa khung; trình duyệt
  nhớ góc nhìn đã chọn.
- Trên điện thoại, giao diện theo kiểu AIRI: nhân vật phủ cả màn hình ở khung cố định; tiêu đề, tin
  nhắn và ô nhắn nổi trong suốt bên trên. Không phóng hay kéo được; giữ ngón tay trên màn hình thì
  nhân vật nhìn theo ngón tay, nhấc tay thì nhìn thẳng lại.
- Trên điện thoại Android, mở bàn phím thì cả giao diện co lên phía trên bàn phím: hàng nút vẫn ở trên
  cùng, nhân vật giữ nguyên cỡ và chỗ đứng, tin nhắn và ô nhắn nằm ngay trên bàn phím. Safari trên iPhone
  chưa hỗ trợ cách này.
- Nhân vật lắc lư theo motion có sẵn, thở, chớp mắt và nhìn theo con trỏ ở mọi chỗ trên trang. Miệng
  mấp máy theo giọng đọc đang phát; không có tiếng thì ngậm miệng.
- Thiết bị bật giảm chuyển động (trên Windows là tắt Animation effects) thì mặc định nhân vật đứng yên.
  Muốn vẫn cử động, chọn **Luôn cử động** ở **Cài đặt → Giao diện → Nhân vật cử động**.
- Giọng đọc được tạo trên máy Windows của chủ web, không trên VPS. Máy chủ giọng nói
  `local-tts/speak_server.py` (thư mục `local-tts` không nằm trong git) dùng Qwen3-TTS 0.6B trên GPU
  của máy đó với hai giọng mẫu `playful-1` và `gentle-2`. Chương trình `voice-worker/relay.py` trên
  cùng máy tự kết nối ra VPS qua HTTPS để nhận câu cần đọc rồi gửi âm thanh về, nên máy nhà không
  phải mở cổng nào. Cách cấu hình nằm ở [voice-worker/README.md](voice-worker/README.md).
- Người nghe chỉ cần đăng nhập, không cài model hay cấp quyền mạng cục bộ. Bật trong **Cài đặt →
  Giọng nói** bằng nút **Bật giọng nói**; chọn giọng và **Nghe thử** cũng nằm ở mục này. Trang chỉ
  gọi `/api/voice` sau khi bật.
- Có giọng nói thì Peto đọc ngay khi trả lời xong. **Tắt tiếng** thì thôi tự đọc; bấm biểu tượng loa
  dưới tin để nghe lại. Rời tab thì Peto thôi đọc. Đã bật giọng nói mà máy tạo giọng đang ngoại tuyến
  thì cột chat báo và có nút **Kiểm tra lại**; chat chữ vẫn chạy bình thường.
- Mọi tài khoản đã đăng nhập, kể cả khách, đều nghe được khi relay đang chạy; tắt relay là ngừng chia
  sẻ. VPS giữ tối đa bốn lượt chờ, mỗi tài khoản một lượt, 300 ký tự mỗi lượt và chờ tối đa 120 giây.
  Khoảng 15 giây không nhận tín hiệu từ relay thì coi là ngoại tuyến.
- Relay xác thực với VPS bằng khóa `PETO_VOICE_WORKER_TOKEN`, đặt trong môi trường dịch vụ Peto trên
  VPS (xem `.env.example`). Máy chủ giọng nói vẫn chỉ nghe ở 127.0.0.1; trình duyệt không gọi thẳng
  tới nó nữa.
- Hàng chờ nằm trong RAM, nên backend phải chạy một tiến trình và chỉ một relay; khởi động lại VPS là
  mất các lượt đang chờ. VPS không lưu WAV.
- Trên GTX 1650 Ti, tạo tiếng mất xấp xỉ độ dài câu nói: câu 7 giây chờ khoảng 7 giây. Chưa đọc dần
  trong lúc Peto đang trả lời, và chưa có nhân vật 3D.

Đợt thử local ngày 13/9/2026 dùng phản hồi giả: bật giọng nói, gửi tin, Peto tự nói khi trả lời xong và
bắt đầu lại đều chạy trong trình duyệt; đợt đó chưa thử persona Companion với Grok thật. Đường chuyển
giọng qua VPS có test tự động bằng WAV giả (`backend/tests/test_voice.py`,
`backend/tests/test_voice_worker.py`); nghe thật qua mạng sau khi triển khai cần thử theo mục
**Kiểm chứng trước khi dùng thật** trong `voice-worker/README.md`.

## Peto Agent

Peto Agent là chương trình dòng lệnh chạy trên máy Windows của bạn, nằm ở `agent-cli/`. Mở nó trong thư mục dự án
rồi nhờ Peto sửa code: Peto đọc, tìm, sửa tệp và chạy lệnh kiểm tra ngay trên máy bạn, còn VPS chỉ xác thực, đếm số bước
và gọi mô hình AI. Cách cài, đăng nhập và sử dụng nằm trong `agent-cli/README.md`.

- **Cài:** mở PowerShell và chạy `irm https://<địa chỉ Peto>/install.ps1 | iex` (cần Python 3.12 trở lên). Bộ cài tải
  gói từ chính VPS, cài vào `%LOCALAPPDATA%\PetoAgent` và thêm lệnh `peto` vào PATH; chạy lại lệnh đó để cập nhật.
  Lệnh này không đăng ở đâu khác: hỏi Peto trong khung chat (ví dụ "cách cài Peto Agent") là Peto đưa đúng lệnh cài
  của trang đang mở cùng các bước đăng nhập và sử dụng.
- **Tài khoản:** chỉ Discord hoặc Google dùng được; tài khoản khách thì không.
- **Đăng nhập CLI:** lệnh `peto login` in một liên kết kèm mã. Mở liên kết trên trình duyệt đã đăng nhập Peto,
  bấm **Cho phép** khi mã khớp. **Cài đặt → Peto Agent** hiện số bước còn lại hôm nay và các máy đã kết nối, ngắt được
  từng máy.
- **Giới hạn bước:** mỗi lần gọi mô hình là một bước; mỗi tài khoản có 200 bước mỗi ngày (đổi bằng
  `PETO_AGENT_DAILY_STEPS`). Mức suy nghĩ cao (`/effort cao`) tính 2 bước mỗi lần. Bước bị lỗi trước khi mô hình kịp
  phản hồi thì được trả lại.
- **Trong phiên:** `/moi` bắt đầu hội thoại mới, `/resume` mở lại hội thoại gần nhất của thư mục (lưu trên máy người
  dùng, không chạy lại lệnh nào), `/effort thap|vua|cao` đổi mức suy nghĩ và được nhớ cho lần sau.
- **Quyền:** đọc và tìm trong thư mục thì Peto tự làm; sửa tệp, tạo tệp và chạy lệnh luôn hỏi bạn trước. Peto không đọc
  hay sửa `.env`, khóa và `.git`, và không ra ngoài thư mục dự án.
- **Dữ liệu:** nội dung tệp Peto đọc và output lệnh đi qua VPS tới dịch vụ AI; VPS không lưu hội thoại.

Bản đầu mới được thử trên máy với phản hồi giả; chưa thử với mô hình thật và chưa triển khai lên VPS. Chưa có công cụ
trình duyệt, Docker, chạy nền hay nối lại tác vụ khi mất mạng.

## Chưa có ở bước này

OCR tài liệu scan, giọng nói lúc máy tạo giọng của chủ web tắt, đọc dần trong lúc Peto
đang trả lời, nhân vật 3D, ghi hoặc đồng bộ trí nhớ
hai chiều với Discord. Chưa kiểm chứng chất lượng AI thật và hoạt động VPS trong
đợt kiểm thử local nêu trên.
