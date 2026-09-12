# Companion — kế hoạch giọng nói và nhân vật

Tab thứ ba bên cạnh **Trò chuyện** và **Tạo ảnh**: Peto hiện thành nhân vật ở giữa
màn hình, có giọng nói, khung chat dán bên phải. Lấy [AIRI](https://github.com/moeru-ai/airi)
(MIT) làm tài liệu tham khảo, **không fork**: họ dùng Vue + Tauri, monorepo hơn ba
chục package, phạm vi gấp nhiều lần mình.

Tài liệu này ghi hướng đã chốt và thứ tự làm. Nó không cho phép triển khai gì cả:
mỗi bước vẫn bàn lại trước khi viết code.

## Đã chốt

- **Mỗi người tự cắm khóa API của mình**, khóa nằm trong trình duyệt của họ, không
  gửi lên máy chủ. Giống AIRI. Ai muốn nghe thì tự trả tiền, nên không cần hạn mức
  hay allowlist. Nguyên tắc "không để khóa AI của máy chủ xuống trình duyệt" vẫn nguyên.
- **Model nhân vật cũng nằm trong trình duyệt** (IndexedDB), không upload lên VPS.
  File VRM nặng 10–40 MB, mà ai cũng đăng ký được, nên để trên VPS là hỏng ổ cứng.
  Bản build kèm sẵn một model mặc định cho người chưa nạp gì.
- **Người dùng tự chọn ngôn ngữ** của Companion (Anh, Nhật, Trung...). Peto viết và
  nói cùng một thứ tiếng, chữ trong bóng chat khớp với tiếng nói. Tiếng Việt chưa
  bật vì giọng đọc tiếng Việt của các dịch vụ kiểu AIRI còn hạn chế; sau này thêm
  thì chỉ là thêm một lựa chọn trong danh sách.
- **Làm giọng nói trước, nhân vật sau.** Giọng nói mới là thứ đổi hẳn cảm giác trò
  chuyện; nhân vật không có giọng chỉ là hình trang trí.
- Companion dùng chung bảng `conversations` và chung lịch sử với tab Trò chuyện.
  Chưa cần cột `mode` hay bảng riêng.

## Không làm

- Không port code AIRI sang React. Chỉ mượn cách làm và tên thư viện.
- Không chạy model AI trong trình duyệt (WebGPU, transformers.js) như AIRI. Peto đã
  có máy chủ rồi.
- Không làm Discord, Minecraft, Telegram như họ.
- Chưa nhận tiếng Việt cho phần nói ra.

## Bước 1 — Giọng nói bằng giọng sẵn có của trình duyệt — XONG

Nút loa hiện nằm trong ô nhắn của tab **Trò chuyện**, chưa có tab Companion nên để
tạm ở đó; khi dựng Companion thì chuyển sang. Máy Windows có sẵn giọng tiếng Việt
(Microsoft An), nên ở bước này Peto nói tiếng Việt được — hạn chế tiếng Việt chỉ
đúng với các dịch vụ trả tiền ở bước 2.

Đã chỉnh sau hai lần nghe thử. Tốc độ mặc định lên 1.2, và bản lưu cũ ở mức 1.0 được
nâng một lần. Quan trọng hơn: người nghe thấy giật là vì mỗi lượt đọc của Web Speech
đều có quãng im ở đầu và cuối, nên giờ mẩu đọc phình dần (câu đầu đọc ngay, rồi ~240,
rồi ~480 ký tự) và có nhịp `resume()` để Chrome không tự tắt tiếng ở lượt đọc dài quá
15 giây. AIRI không gặp chuyện này vì họ phát nguyên file âm thanh từ dịch vụ.

Hai thứ trong bước này bị dời đi: ô chọn ngôn ngữ và trường `language` của
`/api/chat` dời sang lúc dựng Companion (giọng của máy tự khớp ngôn ngữ nên chưa
cần), còn nhép miệng phải đợi bước 2 mới có luồng âm thanh để đo.

Mục tiêu: dựng xong **toàn bộ đường đi của tiếng nói** mà không tốn đồng nào và
không cần khóa của ai.

- `frontend/src/speech.ts`: bọc `window.speechSynthesis`, liệt kê giọng theo ngôn
  ngữ, chỉnh tốc độ và cao độ, hủy ngang.
- **Cắt câu từ dòng chữ đang chảy về**: gom delta của SSE, cắt ở `.`, `?`, `!`, `…`
  và xuống dòng, rồi xếp hàng đọc. Nhờ vậy Peto bắt đầu nói khi câu trả lời còn
  đang gõ, thay vì đợi hết. Đây là mẹo quyết định cảm giác "đang nói chuyện".
- Nút **Dừng** phải cắt cả dòng chữ lẫn tiếng nói. Đổi hội thoại, đổi tab, đóng tab
  cũng phải cắt.
- **iOS Safari không cho phát tiếng khi người dùng chưa chạm vào trang**, nên vào
  Companion phải có một nút bật tiếng ở lần đầu.
- Ngôn ngữ lưu ở `localStorage` như `peto-effort` và `peto-theme` hiện có.
- Test: tách câu (bài test thuần), và một bài ở tầng App kiểm delta ra đúng thứ tự
  câu, bấm Dừng thì im.

Giới hạn phải biết trước: `speechSynthesis` **không cho chạm vào luồng âm thanh**,
nên bước này chưa nhép miệng theo biên độ thật được. Nhép miệng thật phải đợi bước 2.

## Bước 2 — Cắm dịch vụ giọng thật — XONG

Đã có ElevenLabs và OpenAI, chọn trong Cài đặt → Giọng nói. Đo thật trước khi viết:
**cả ElevenLabs, OpenAI, Azure và Google đều cho gọi thẳng từ trình duyệt**, không bị
CORS chặn, nên bỏ được dự định nhờ backend chuyển tiếp cho Azure. Âm thanh phát qua
một `AudioContext` dùng chung, mẩu sau hẹn đúng lúc mẩu trước dứt nên không hở tiếng,
và giữ đúng thứ tự kể cả khi mẩu sau tải xong trước. `AnalyserNode` đã nối sẵn cho
bước 3.

Có ba dịch vụ: **Gemini (Google AI Studio)**, ElevenLabs và OpenAI. Gemini là đường dễ
nhất cho nhóm mình: khóa lấy miễn phí ở aistudio.google.com, không cần thẻ. Nó trả PCM
thô nên phải bọc thành WAV mới phát được, còn khóa thì gửi bằng header `x-goog-api-key`
chứ không nhét vào đường dẫn.

Thông báo lỗi bám vào **nội dung** lỗi chứ không chỉ mã số: Google trả 400 cho khóa sai,
nhìn mỗi mã số là báo nhầm thành sai mã giọng. Kèm luôn câu giải thích của chính dịch vụ.

**Không dùng Official Speech Provider của AIRI.** Theo tài liệu của họ, nó chạy bằng
phiên đăng nhập AIRI và tính tiền bằng số dư Flux, không có khóa cho bên thứ ba, và họ
dặn rõ đừng chia sẻ dữ liệu phiên. Muốn xài ké thì phải bê session của người dùng sang,
tức là đúng thứ họ cấm.

Chưa làm: Azure và Google Cloud TTS (mới chỉ đo là gọi được từ trình duyệt), và đường qua
backend dùng chung khóa của chủ dự án.

Ghi chú gốc của bước này:

- Tách lớp `SpeechProvider` ở frontend, đúng kiểu `ChatProvider` bên backend:
  `browser` (mặc định, miễn phí), `elevenlabs`, `azure`, `openai-compatible`.
- Khóa lưu trong `localStorage`, gọi thẳng từ trình duyệt sang dịch vụ. Cần kiểm tra
  CORS từng bên: ElevenLabs gọi thẳng được, Azure phải đổi khóa lấy token nên có thể
  phải nhờ backend chuyển tiếp.
- Phát bằng `AudioContext`, xếp hàng theo câu cho liền mạch, và cắm `AnalyserNode`
  để lấy biên độ cho bước 3.
- Hiện số ký tự đã đọc trong phiên, để người dùng thấy mình đang tiêu bao nhiêu.
- Sau này nếu bạn muốn cả nhóm dùng chung khóa của bạn: thêm đường qua backend, có
  công tắc bật/tắt và hạn mức. Chưa làm bây giờ.

## Bước 3 — Nhân vật

- `three.js` + `@pixiv/three-vrm`. Cân nhắc `@react-three/fiber` cho hợp React, hoặc
  tự viết một hook mỏng nếu không muốn thêm phụ thuộc nặng.
- Định dạng theo thứ tự: `.vrm` trước, `.glb` gần như miễn phí vì chung loader, Live2D
  sau cùng (`pixi-live2d-display`, nhớ đọc giấy phép Cubism trước khi làm).
- Nạp model: `<input type="file">` rồi cất vào IndexedDB. Có nút trả về model mặc định.
- Cử động: thở và chớp mắt tự động, mắt nhìn theo con trỏ, vài biểu cảm.
- **Nhép miệng**: `AnalyserNode` → RMS → blendshape `aa` của VRM. Chỉ chạy được với
  giọng ở bước 2.

## Bước 4 — Nói vào cho Peto nghe

- Bấm giữ để nói trước: `MediaRecorder` gửi về backend, phiên âm bằng Whisper. Tốn tiền
  nên phải cân nhắc ai được dùng.
- Rảnh tay sau: VAD trong trình duyệt (`@ricky0123/vad-web`, Silero) như AIRI.

## Đụng vào backend chỗ nào

Rất ít, và chỉ ở bước 1:

- `POST /api/chat` nhận thêm trường `language` không bắt buộc. Máy chủ kiểm tra nó nằm
  trong danh sách cố định rồi ghép một dòng vào system prompt. Sai giá trị thì trả 400
  tiếng Việt như các lỗi khác.
- Phần còn lại của bước 1–3 nằm hết ở trình duyệt.

## Bố cục

Mượn AIRI: nhân vật giữa màn, khung chat cột phải khoảng 380px, dãy nút nhỏ góc dưới
(micro, loa, cài đặt). Trên điện thoại thì nhân vật nằm trên, chiếm khoảng 40% chiều
cao, chat ở dưới.

## Phải dọn trước khi làm

`App.tsx` đã hơn 1.500 dòng và đang giữ cả khung ứng dụng lẫn chat. Companion cần
dùng lại ô nhắn và bóng chat, nên tách `Composer.tsx` (và có thể `MessageList.tsx`)
ra trước, không thì file sẽ phình thêm lần nữa.

## Rủi ro đã biết

- WebGL với model VRM ăn pin trên điện thoại; file nặng khi tải bằng 4G.
- iOS Safari chặn tự phát tiếng, và tab chạy nền bị treo âm thanh.
- Giấy phép Cubism nếu làm Live2D.
- Model mặc định kèm trong bản build phải là model mình có quyền dùng.
- Người dùng tự nạp model của người khác: nằm trong máy họ nên là chuyện của họ, mình
  không lưu trữ gì.

## Mượn gì từ AIRI

Giấy phép MIT nên đọc và mượn thoải mái, chỉ cần ghi nguồn:

- `model-driver-lipsync` — cách tách nhép miệng khỏi loại nhân vật.
- `pipelines-audio` — cắt câu và xếp hàng phát.
- Cách tách lớp nhà cung cấp giọng nói và màn hình cắm khóa.
- Bố cục sân khấu, và cách họ chọn VAD.
