# Companion — kế hoạch giọng nói và nhân vật

Tab thứ ba bên cạnh **Trò chuyện** và **Tạo ảnh**: Peto hiện thành nhân vật ở giữa
màn hình, có giọng nói, khung chat dán bên phải. Lấy [AIRI](https://github.com/moeru-ai/airi)
(MIT) làm tài liệu tham khảo, **không fork**: họ dùng Vue + Tauri, monorepo hơn ba
chục package, phạm vi gấp nhiều lần mình.

Tài liệu này ghi hướng đã chốt và thứ tự làm. Nó không cho phép triển khai gì cả:
mỗi bước vẫn bàn lại trước khi viết code.

## Đã thử bước 1 và 2 rồi gỡ (12/9/2026)

Code vẫn nằm trong lịch sử git, từ `b295c79` tới `5b8b7fc`, gỡ bằng `c1003dc`. Muốn lấy
lại phần nào cũng được. Những gì đã học, để lần lên kế hoạch sau khỏi dẫm lại:

- **Giọng có sẵn trong máy nghe giật.** Mỗi lượt đọc của Web Speech đều có quãng im ở đầu
  và cuối, nên đọc dần từng câu là nghe rời rạc. Gom mẩu to hơn thì đỡ, nhưng Chrome lại
  tự tắt tiếng ở lượt đọc dài quá 15 giây, phải gọi `resume()` đều đặn để chữa. Windows có
  sẵn giọng tiếng Việt (Microsoft An) nên vẫn nói tiếng Việt được.
- **Mọi dịch vụ đều gọi thẳng từ trình duyệt được.** Đo thật: ElevenLabs, OpenAI, Azure và
  Google đều không bị CORS chặn. Không cần backend chuyển tiếp, khóa nằm ở máy người dùng.
- **Chỗ chết là hạn mức của gói miễn phí.** Gemini chỉ cho 3 lượt gọi mỗi phút, mà đọc dần
  thì một câu trả lời đã tốn 2–5 lượt; gộp cả lượt thành một request thì chạy được nhưng
  Peto nói muộn hẳn. OpenAI phải nạp tiền trước. ElevenLabs khó tìm chỗ lấy khóa.
- **Azure F0 là gói dễ thở nhất** nhưng chưa kịp thử bằng khóa thật: 20 lượt mỗi phút, 500
  nghìn ký tự mỗi tháng, có giọng tiếng Việt HoaiMy và NamMinh.
- **Không dùng được Official Speech Provider của AIRI:** nó chạy bằng phiên đăng nhập AIRI,
  không có khóa cho bên thứ ba, và tài liệu của họ dặn đừng chia sẻ dữ liệu phiên.
- **Bài học chung:** phần khó không nằm ở code đọc tiếng — chỗ đó làm xong và chạy đúng —
  mà ở việc tìm một nguồn giọng vừa nghe được, vừa không bắt ai trả tiền hay điền khóa.

Phần tách `Composer.tsx` và `files.tsx` (commit `99ba39a`) được giữ lại: đó là dọn dẹp
thuần túy, có test riêng, không dính gì tới giọng nói.

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

## Bước 1 — Giọng nói bằng giọng sẵn có của trình duyệt

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

## Bước 2 — Cắm dịch vụ giọng thật

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
