# Bật giọng cloud cho Peto

Code đã có OpenAI, Qwen Cloud và relay Qwen local. Chưa gọi API thật vì máy phát
triển không có khóa. Không có mẫu giọng nào được tải lên cloud.

## OpenAI trên VPS

Giữ OPENAI_API_KEY đang dùng, thêm vào .env của VPS:

```env
PETO_TTS_OPENAI_ENABLED=true
PETO_TTS_OPENAI_MODEL=tts-1
PETO_TTS_MONTHLY_USD=10
```

Có thể chọn tts-1-hd để so chất lượng. Bản đầu chỉ hỗ trợ hai model tính phí theo
ký tự này; chưa hỗ trợ gpt-4o-mini-tts (cần tính phí token/audio riêng).
Sau git pull, build frontend và restart peto-web như thường. Vào Cài đặt > Giọng
nói > Bật > OpenAI > chọn giọng > Nghe thử. Model chat không bị thay đổi.
Danh sách giọng chỉ xác nhận có cấu hình; Nghe thử mới kiểm tra quyền TTS/billing.

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

## Dự phòng, ngân sách và giới hạn

Nguồn dự phòng do người dùng chọn, mặc định tắt. Chỉ thử lại một lần với lỗi
502/503/504; không thử lại khi chạm ngân sách/giới hạn. UI báo giọng đã chuyển.
Các đoạn còn lại trong cùng lượt dùng giọng dự phòng; lượt mới thử nguồn chính.
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
