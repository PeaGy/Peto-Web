# Bật giọng cloud cho Peto

Code đã có OpenAI, Qwen Cloud và relay Qwen local. Chưa gọi API thật vì máy phát
triển không có khóa. Không có mẫu giọng nào được tải lên cloud.

Trong Cài đặt → Giọng nói, người dùng chọn một trong ba loại nguồn:

- **Giọng Peto**: các giọng cloud bật trong file này, chạy bằng khóa của chủ web.
  Mỗi tài khoản Discord, Google có một lượt ký tự miễn phí mỗi tháng; khách không có.
- **Máy nhà của Peto**: Qwen3-TTS trên máy Windows của chủ web, qua relay
  (`voice-worker/README.md`). Không tốn tiền API.
- **Khóa của bạn**: người dùng tự nhập khóa OpenAI, ElevenLabs, Azure, Gemini,
  MiniMax, Qwen Cloud, StepFun hoặc máy chủ tương thích OpenAI. Tiền tính vào tài
  khoản của họ, không đụng khóa hay ngân sách trong file này.

## OpenAI trên VPS

Giữ OPENAI_API_KEY đang dùng, thêm vào .env của VPS:

```env
PETO_TTS_OPENAI_ENABLED=true
PETO_TTS_OPENAI_MODEL=tts-1
PETO_TTS_MONTHLY_USD=10
```

Có thể chọn tts-1-hd để so chất lượng. Bản đầu chỉ hỗ trợ hai model tính phí theo
ký tự này; chưa hỗ trợ gpt-4o-mini-tts (cần tính phí token/audio riêng).
Sau git pull, build frontend và restart peto-web như thường. Vào Cài đặt → Giọng
nói → bật → thẻ Giọng Peto → chọn giọng "OpenAI · …" → Nghe thử (trừ lượt tháng này
của tài khoản đang đăng nhập). Model chat không bị thay đổi.
Danh sách giọng chỉ xác nhận có cấu hình; Nghe thử mới kiểm tra quyền TTS/billing.

## StepFun: chuẩn bị sẵn, bật sau khi có số dư

Mặc định tắt. Không tự gọi thử hoặc kiểm tra khóa bằng yêu cầu tính phí.
Khi đã sẵn sàng, đặt trong `.env` trên VPS (không gửi khóa vào chat):

```env
PETO_TTS_STEPFUN_ENABLED=true
STEP_API_KEY=your-stepfun-key
PETO_TTS_STEPFUN_MODEL=stepaudio-2.5-tts
PETO_TTS_STEPFUN_VOICES=jilingshaonv
PETO_TTS_MONTHLY_USD=10
```

Sau khi đưa code mới lên và build frontend, chạy `sudo systemctl restart peto-web`.
Vào Cài đặt → Giọng nói → thẻ Giọng Peto → Giọng: "Jiling, tinh nghịch" → Nghe thử.
Thẻ StepFun trong nhóm "Khóa của bạn" là đường khóa riêng của người dùng, không
dùng `STEP_API_KEY` này.
Trước khi nạp tiền, giữ `PETO_TTS_STEPFUN_ENABLED=false` kể cả đã đặt khóa.

Kết nối trực tiếp API quốc tế `https://api.stepfun.ai/v1/audio/speech`, tính phí
theo lượng dùng từ số dư Billing. Chưa hỗ trợ Step Plan; không tự chuyển kênh.
Giọng mặc định giữ đúng ID người dùng đã nghe trên AIRI. Tài liệu quốc tế hiện
liệt kê `lively-girl` (Lively Girl), chưa xác nhận `jilingshaonv` dùng được với
tài khoản quốc tế hay hai ID tương đương. Nếu báo sai giọng, kiểm tra danh sách
giọng tài khoản rồi sửa `PETO_TTS_STEPFUN_VOICES`; không tự đổi giọng. Có thể khai
báo nhiều ID ngăn bằng dấu phẩy. Chất giọng thực tế chưa được kiểm chứng.

Đầu ra WAV, tiếng Anh, dùng chung phát/dừng/lip sync và nguồn dự phòng hiện có.
StepFun xem chữ trong ngoặc tròn là chỉ dẫn diễn xuất, có thể không đọc thành tiếng.
Không gọi lại tự động hoặc chuyển dự phòng cho HTTP 400/402/429. Khóa chỉ ở server.

Giá tham chiếu ngày 2026-09-24: $0.85/10.000 ký tự tính phí. Bộ giới hạn Peto
dự trù $85/triệu ký tự thô để tránh đánh giá thấp: chưa áp dụng ưu đãi quy đổi hai
chữ cái tiếng Anh thành một ký tự của StepFun. Vì vậy Peto có thể chạm giới hạn
sớm hơn số dư thực tế. Đây là trần ước tính chung mọi nguồn, không phải số dư StepFun.

Nguồn:
- https://platform.stepfun.ai/docs/en/api-reference/audio/create-audio
- https://platform.stepfun.ai/docs/en/guides/developer/tts
- https://platform.stepfun.ai/docs/en/guides/pricing/details

## Qwen Cloud: cấu hình khi đã có tài khoản

Tạo khóa Alibaba Cloud Model Studio Singapore rồi thêm:

```env
PETO_TTS_QWEN_ENABLED=true
DASHSCOPE_API_KEY=your-key
PETO_TTS_QWEN_MODEL=qwen3-tts-flash
PETO_TTS_QWEN_VOICES=Cherry,Serena
```

Endpoint mặc định là Singapore DashScope. Tài khoản dùng workspace endpoint
có thể đặt PETO_TTS_QWEN_ENDPOINT theo HTTPS endpoint multimodal generation
trong console Alibaba. Không đưa khóa vào frontend.

Để giữ hai giọng Peto: đăng ký mẫu sạch của mỗi giọng qua API voice cloning,
đặt target_model=qwen3-tts-vc-2026-01-22. Sau đó chọn model đó ở cấu hình và điền
hai voice ID nhận được vào PETO_TTS_QWEN_VOICES (ngăn bằng dấu phẩy).
Tên local và checkpoint local không phải voice ID cloud. Việc tạo giọng chưa
được thực hiện; cần nghe so sánh trước khi chọn mặc định.

## Giọng Peto: lượt miễn phí mỗi tài khoản

```env
PETO_TTS_FREE_CHARS_MONTHLY=5000
```

Mỗi tài khoản Discord, Google được đọc bằng Giọng Peto chừng này ký tự mỗi tháng,
tính theo giờ `PETO_DEFAULT_TIMEZONE` (bảng `voice_usage`). 5.000 ký tự khoảng 40
câu trả lời ngắn của Companion, với StepFun khoảng $0,43 mỗi tài khoản. Khách không
có lượt: tạo tài khoản khách không giới hạn, nên chia lượt theo khách thì một người
rút cạn được cả tháng. Máy chủ trừ lượt trước khi gọi nhà cung cấp và trả lại nếu
câu đó không đọc được. Nghe thử cũng trừ lượt. Hết lượt thì trang báo ngày làm mới,
và máy chủ đọc bằng giọng dự phòng nếu người dùng đã chọn. `PETO_TTS_MONTHLY_USD`
vẫn là trần chung của mọi người, chặn trước cả khi còn lượt.

## Khóa riêng của người dùng

Khóa người dùng nhập nằm trong trình duyệt của họ (localStorage), không lên máy chủ.
Trình duyệt gọi thẳng OpenAI, ElevenLabs, Azure, Gemini, MiniMax và máy chủ tương
thích OpenAI. StepFun chặn trình duyệt gọi thẳng, còn Qwen Cloud trả địa chỉ tệp
âm thanh trình duyệt không tải được, nên hai nguồn này đi qua `POST /api/voice/relay`:
khóa nằm trong header `X-Voice-Key`, chỉ dùng cho đúng lượt đó, không lưu, không ghi
nhật ký, không trừ lượt hay ngân sách của chủ web. Khách cũng dùng được. Relay dùng
chung giới hạn đồng thời với Giọng Peto. Azure Speech đã chạy với khóa thật (chủ web
thử ngày 2026-09-24); các nguồn còn lại chưa thử, cách gọi theo tài liệu của từng nhà
cung cấp cùng ngày.

## Dự phòng, ngân sách và giới hạn

Nguồn dự phòng do người dùng chọn ("Khi nguồn chính không nói được"): Máy nhà, Giọng
Peto hoặc chỉ hiện chữ; chưa chọn bao giờ thì là Máy nhà. Máy chủ chỉ chuyển một lần,
khi lỗi 502/503/504 hoặc khi tài khoản đã hết lượt Giọng Peto tháng này; không chuyển
khi chạm trần ngân sách chung. Khóa riêng lỗi (kể cả khóa sai) thì trình duyệt chuyển
và báo lý do. Riêng Nghe thử không bao giờ chuyển, để lỗi của nguồn đang thử hiện ra.
UI báo giọng đã chuyển. Các đoạn còn lại trong cùng lượt dùng giọng dự phòng; lượt mới
thử nguồn chính.
Dừng đọc hủy phát và yêu cầu đang chờ. Nhà cung cấp có thể vẫn tính phí lượt hủy.

Bảng speech_budget trong database hiện có lưu chi phí ước tính theo tháng UTC,
đơn vị micro-USD. Giao dịch SQLite giữ ngân sách TRƯỚC khi gọi API: dùng chung
mọi người/nguồn, tồn tại qua restart. Lượt lỗi/hủy vẫn giữ phần đã dự trù để tránh
đánh giá thấp chi phí. Không xóa bảng này để reset giới hạn.
Giá trên 1 triệu ký tự: tts-1 $15, tts-1-hd $30, Qwen Flash $10, Qwen VC $11.5.
Phải cập nhật bảng giá code khi nhà cung cấp đổi giá. Mức $10 là ước tính tại Peto,
không phải cam kết hóa đơn: chưa gồm thuế, tạo giọng, ứng dụng khác dùng cùng
khóa hoặc thay đổi giá. Nên đặt thêm cảnh báo chi phí ở nhà cung cấp.
Giới hạn đồng thời: 4 lượt/process, 1 lượt/người/process. Budget chia sẻ qua DB.

Bản này giữ chia đoạn, tạo trước đoạn sau và lip sync hiện có. Chưa đọc khi LLM
đang stream; mỗi đoạn nhận WAV đầy đủ trước khi phát. Không tự bật dịch vụ trả phí.

Nguồn đối chiếu ngày 2026-09-24:
- https://developers.openai.com/api/docs/guides/text-to-speech
- https://developers.openai.com/api/docs/models/tts-1
- https://www.alibabacloud.com/help/en/model-studio/qwen-tts-api
- https://www.alibabacloud.com/help/en/model-studio/voice-cloning-user-guide
- https://www.alibabacloud.com/help/en/model-studio/model-pricing
