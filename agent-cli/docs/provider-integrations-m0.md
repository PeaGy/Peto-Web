# Nhiều nguồn model — M0: khảo sát và quyết định kỹ thuật

Ngày 20/10/2026, tại commit `b207e88` (CLI 0.30.0). Đi kèm [lộ trình](provider-integrations-roadmap.md).

## 1. Kiểm kê chỗ CLI phụ thuộc máy chủ Peto

**Gọi `/api/agent/step`** (từ M1 đều đi qua `Session.models` → `providers/peto.py`):

| Lượt | Chỗ gọi | Ghi chú |
|---|---|---|
| work, wrapup | `loop.Session._step` → `_attempt` | Tự thử lại tối đa 3 lần; gọi lại một lần sau khi tóm tắt vì tràn ngữ cảnh. |
| compact | `loop.Session._compact` | Lần thử lại dùng `effort=medium`; thu gọn tối đa ba lần khi tràn. |
| title | `loop.Session._name_conversation` | Luồng nền, nhật ký riêng (`title_journal`); luôn model `peto`, mức `low`. |
| btw | `loop.Session.side_question` | Không ghi nội dung vào nhật ký (riêng tư). |
| explore | `subagent._step` | Agent con, ngữ cảnh riêng; cùng model của phiên, mức thấp. |

**Gọi `/api/agent/me`** (`__main__.py`): lúc mở phiên (model, mức suy nghĩ, `agent_features`, `context_limits`,
`context_transport`, bước đã dùng, bản CLI mới), `/usage`, `peto status`, kiểm tra cập nhật. Thêm `device/start`,
`device/token`, `logout` cho đăng nhập.

**Giả định gắn với máy chủ:**
- Model là khóa của máy chủ (`peto/luna/terra/sol/haiku/sonnet`); `/model` chỉ liệt kê model `/me` trả về.
- Số bước mỗi lượt (`model_step_cost`), mức suy nghĩ hợp lệ (`supported_efforts`), ngân sách ngữ cảnh
  (`configure_models`) đều lấy từ `/me`.
- Khả năng mới chỉ bật khi `/me agent_features` liệt kê (`NEW_FEATURES`).
- Đặt tên hội thoại cố định model `peto`.
- Hội thoại, nhật ký bền và lưu trữ trước tóm tắt (`history`, `journal`, `recall`) đều xếp theo `client.server`.

## 2. Phần đang nằm trên VPS mà nguồn trực tiếp sẽ cần

| Thành phần | Nơi ở hiện nay | Độc lập với FastAPI/DB? |
|---|---|---|
| Lời nhắc Agent | `backend/prompts/agent.py`, `core.py` | Có (chỉ chuỗi). |
| Đoạn riêng theo nhà cung cấp | `backend/prompts/providers.py` | Chưa: tra `ai.models.MODELS` để biết dịch vụ. |
| Ghép lời nhắc theo khả năng, mục đích | `features/agent/api.py` (`_instructions`, `_explore_instructions`, `_btw_instructions`) | Chưa: nằm trong module có FastAPI. |
| Giờ trong lời nhắc | `shared/time_tools.agent_time_context` | Chưa: đọc `core.config`. |
| Schema công cụ | `features/agent/tools.py` | Có (không import gì). |
| Danh mục ngữ cảnh model | `features/agent/budget.py` | Chưa: đọc `core.config` và `MODELS`. |
| Kiểm tra đầu vào bước | `features/agent/api.py` | Chưa. |
| Gọi dịch vụ AI, chuyển đổi Claude | `ai/agent.py`, `ai/claude.py` | Chưa; nguồn trực tiếp cần bộ chuyển của riêng CLI. |
| Hạn mức bước, quyền model | `features/agent/api.py`, `ai/models.py` | Chỉ thuộc nguồn Peto; nguồn trực tiếp không dùng. |

## 3. Quyết định

**Đường chạy.** Nguồn trực tiếp chạy ngay trên máy (CLI gọi thẳng nhà cung cấp), không chuyển khóa qua VPS như
Companion. Lý do: tiêu chí "VPS ngừng vẫn làm được" của lộ trình, và đường ChatGPT chỉ dành cho ứng dụng chạy cục bộ
(mục 5). Nguồn Peto giữ nguyên đường VPS.

**Lời nhắc và schema dùng chung.** Một nguồn duy nhất là các module thuần Python của backend. Ở M3:
- tách phần ghép lời nhắc ra một module thuần (không FastAPI, không DB, nhận cấu hình qua tham số);
- `providers.py` nhận tên dịch vụ thay cho khóa model;
- một công cụ sinh chép các module đó vào `peto_agent/bundle/` kèm dòng "tệp sinh tự động", commit cùng mã;
- một test backend so bản sinh với nguồn: lệch là hỏng;
- wheel đóng gói `peto_agent.bundle`.

Kho mã đã công khai trên GitHub nên đóng gói lời nhắc vào wheel không lộ thêm gì.

**Kho bí mật.** Windows dùng DPAPI qua `ctypes` (`CryptProtectData`, phạm vi người dùng), mỗi kết nối một tệp trong
`%APPDATA%\PetoAgent\credentials\`; vẫn chỉ thư viện chuẩn. Hệ khác: chưa hỗ trợ nguồn trực tiếp cho tới khi có kho
của hệ điều hành; không lưu dạng chữ thường để chữa cháy. `config.json`, hội thoại, nhật ký và bản xuất chỉ giữ mã kết
nối.

**ID token của ChatGPT.** Xác minh lại ở M5 theo trang Token reference của OpenAI. OIDC Core 3.1.3.7 cho phép dựa vào
TLS thay cho kiểm chữ ký khi ID token nhận thẳng từ token endpoint. Nếu OpenAI yêu cầu kiểm chữ ký thì cần thêm thư viện
mật mã được duy trì (ví dụ `cryptography`) và sửa bộ cài; không tự viết RSA.

**Nơi lưu hội thoại.** Vẫn xếp theo địa chỉ máy chủ Peto đã cấu hình, kể cả khi lượt gọi dùng nguồn trực tiếp. Nhờ vậy
đổi nguồn giữa chừng vẫn là cùng một hội thoại (M2). Nguồn của từng lượt gọi được ghi trong nhật ký bền (từ M1: trường
`source` của sự kiện `model.started`).

## 4. Điều kiện dùng hạn mức gói ChatGPT

Theo [tài liệu OpenAI](https://developers.openai.com/siwc/token-sharing-open-source) ngày 20/10/2026: đường này dành
cho "open-source and locally hosted apps". Ứng dụng có thu phí hoặc chạy từ xa phải điền
[đơn bày tỏ quan tâm](https://openai.com/form/sign-in-with-chatgpt-interest/). Ứng dụng tự chọn và giữ một
`ext_agent_host_id`, đăng ký client theo tài khoản và workspace, dùng PKCE, state, nonce, kiểm ID token và scope, rồi
gọi Responses với `store: false`, `stream: true`.

Tình trạng của Peto: CLI chạy trên máy người dùng, nhưng kho `PeaGy/Peto-Web` công khai mà **không có license**, nên chưa
là mã nguồn mở theo nghĩa thông thường. Peto còn có dịch vụ web chạy trên VPS. **Chủ dự án đã chọn ngày 20/10/2026: CLI theo giấy phép MIT** (`agent-cli/LICENSE`, kèm thông báo MIT của phần chuyển
từ opencode; wheel ghi `License: MIT` và đóng kèm tệp). Web và máy chủ Peto không thuộc giấy phép này. OpenAI vẫn là bên
quyết định ứng dụng có đủ điều kiện hay không; trước M5 cần xin client ID của Peto theo trang Request a client ID.

## 5. Baseline kiểm thử

Tại `b207e88`, trước khi sửa: toàn bộ CLI `python -m pytest tests` từ `agent-cli`: **673 passed** (320 giây).
