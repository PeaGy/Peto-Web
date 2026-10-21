# Nguồn model của Peto Agent

Tài liệu dùng và vận hành cho lộ trình nhiều nguồn (M0–M6, CLI 0.31–0.33). Chi tiết thiết kế ở
[provider-integrations-roadmap.md](provider-integrations-roadmap.md) và [provider-integrations-m0.md](provider-integrations-m0.md).

## Ba nguồn

| Nguồn | Kết nối | Tính vào đâu | Cần máy chủ Peto | Tìm web |
|---|---|---|---|---|
| Peto | `peto login` | Bước Peto mỗi ngày (giờ Việt Nam) | Có | Có, nếu máy chủ bật |
| Khóa API OpenAI riêng | `peto connect openai`, hoặc `/connect` → OpenAI → Khóa API | Tài khoản API OpenAI của bạn | Không | Chưa |
| Gói ChatGPT | `peto connect chatgpt`, hoặc `/connect` → OpenAI → Continue with ChatGPT | Hạn mức gói ChatGPT của bạn | Không | Chưa |

Hai nguồn trực tiếp gọi OpenAI thẳng từ máy bạn, với cùng lời nhắc và công cụ như khi qua máy chủ Peto (CLI mang bản
chép của máy chủ trong `peto_agent/bundle/`). Đặt tên hội thoại, `/btw`, tóm tắt, agent con khám phá và lượt tóm lại
khi hết bước đều đi qua nguồn của hội thoại, không về máy chủ Peto.

## Chọn model

- `/models` (hoặc `/model` không kèm tên): bảng nổi có nhóm Yêu thích, Gần đây, rồi theo nguồn. Gõ để tìm. `ctrl+f`
  yêu thích, `ctrl+d` đặt mặc định, `ctrl+a` mở `/connect`. `/model tên` đổi thẳng.
- Đổi model chỉ áp cho hội thoại đang mở. Mặc định cho các lần mở peto sau đặt bằng `ctrl+d` hay
  `peto models default <tên>`. `peto models [--json]` liệt kê model dùng được trên máy.
- `/resume` đi tiếp bằng model của hội thoại đó nếu máy còn dùng được; không thì giữ model đang chọn và nói rõ. Đổi
  nguồn giữa chừng giữ nguyên yêu cầu, kết quả công cụ, kế hoạch và tiêu chí nghiệm thu; chỉ bỏ phần mờ (suy nghĩ mã
  hóa, mã item) mà nguồn mới không đọc được. Không lệnh nào bị chạy lại.
- Ô nhập ghi tên nguồn sau tên model; khi dùng gói ChatGPT, dòng dưới ô nhập ghi “Using ChatGPT plan”.

## Hạn mức và lỗi

Peto không bao giờ tự chuyển sang một nguồn tốn tiền khác.

- **Peto hết bước:** báo lỗi; gõ `/models` để chọn khóa riêng hay gói ChatGPT, hội thoại giữ nguyên.
- **Khóa API hết tiền hay hạn mức:** báo lỗi; nạp thêm ở trang OpenAI hoặc chọn nguồn khác. Lỗi tạm (mạng, 5xx, giới
  hạn lượt) được thử lại có giới hạn khi bước chưa sinh gì.
- **Gói ChatGPT chạm giới hạn:** báo kèm “Manage usage” (ChatGPT → Settings → Usage). Giới hạn có thể là của cả gói hay
  riêng cho Peto Agent; Peto không biết còn bao nhiêu và không đăng nhập lại để chữa lỗi hạn mức.
- **Đăng nhập ChatGPT hết hiệu lực:** token được làm mới tự động; refresh token hỏng hẳn thì kết nối chuyển sang “cần
  đăng nhập lại”, chọn nó trong `/connect` để đăng nhập lại (giữ client ID cũ).
- `/usage` tách model và nguồn đang dùng, bước Peto hôm nay, ngữ cảnh, token khóa riêng hay gói ChatGPT của phiên. Số
  token là số OpenAI trả về, không phải hóa đơn.

## Ngắt kết nối

- **Khóa API:** `ctrl+d` hai lần trong `/connect`, hoặc `peto disconnect <mã>`. Chỉ xóa trên máy này; muốn vô hiệu khóa
  thì thu hồi ở platform.openai.com/api-keys.
- **Gói ChatGPT:** như trên; peto thu hồi refresh token ở OpenAI trước khi xóa. Không xác nhận được thì báo, và bạn
  ngắt Peto Agent trong ChatGPT → Settings → Security and login → Login connections. Đăng ký client của tài khoản được
  giữ để lần sau đăng nhập lại (“Đã đăng nhập trước đây”).
- Xóa kết nối đang dùng: hội thoại chuyển sang model mặc định còn lại và có báo.

## Bí mật nằm ở đâu

- Khóa và bộ token: `%APPDATA%\PetoAgent\credentials\<mã kết nối>.bin`, mã hóa DPAPI theo tài khoản Windows. Không có
  bản chữ thường; máy không có DPAPI thì không lưu.
- Hồ sơ không bí mật: `connections.json` (mã, tên, địa chỉ API, model; ChatGPT có thêm client ID, email, quyền dùng
  gói). `config.json`: mặc định, yêu thích, gần đây, mã máy `chatgpt_host_id` (`urn:uuid:`).
- Khóa và token không nằm trong hội thoại, nhật ký bền, nhật ký công việc, `/export`, lời nhắc hay môi trường của lệnh
  peto chạy. Chỉ gửi tới địa chỉ chính thức (api.openai.com, auth.openai.com) qua HTTPS, không theo chuyển hướng.

## Tắt một nguồn

- **Cho mọi người (chủ máy chủ):** `PETO_AGENT_DISABLED_SOURCES=chatgpt-plan` (hay `openai-key`, cách nhau bằng dấu
  phẩy) trong `.env` của máy chủ rồi khởi động lại. CLI 0.33.3+ đọc từ `/me` khi mở phiên: model của nguồn đó bị ẩn,
  phiên đang mặc định dùng nó chuyển sang Peto và báo. Máy không gọi được máy chủ Peto thì không biết công tắc này.
- **Cho riêng máy này:** thêm `"disabled_sources": ["chatgpt-plan"]` vào `%APPDATA%\PetoAgent\config.json`.
- Kết nối, bí mật và hội thoại đã lưu vẫn còn; bỏ công tắc là dùng lại được ngay, kể cả mặc định cũ.

## Lên bản, quay về bản cũ

- Lần đầu một bản peto khác chạy, `config.json`, `connections.json`, `permissions.json` và `AGENTS.md` chung được chép
  sang `%APPDATA%\PetoAgent\backups\<thời điểm>-<bản cũ>-to-<bản mới>\` (giữ 5 bản gần nhất). Không chép
  `credentials\` (khóa vẫn nằm nguyên chỗ, không nhân bản bí mật) và hội thoại.
- Quay về bản cũ hơn 0.32: chép các tệp trong bản sao lưu phù hợp về `%APPDATA%\PetoAgent\`. Những gì thêm sau lúc sao
  lưu (kết nối mới, mặc định mới) phải làm lại. Bản 0.31 trở về trước bỏ qua kết nối ChatGPT và trường `extra`, và
  **xóa chúng khỏi `connections.json` nếu chính nó ghi lại tệp** (khi `peto connect openai` hay `peto disconnect`);
  từ 0.33.3, peto giữ nguyên những dòng nó không hiểu và không ghi đè tệp có định dạng mới hơn.
- Hội thoại tự mang số bản: hội thoại nguồn Peto vẫn lưu bản 2; nguồn khác lưu bản 3 để bản cũ bỏ qua thay vì mở nhầm
  bằng nguồn Peto. Bản cũ không đọc được nhật ký bền mới hơn của nó (lược đồ nhật ký vẫn là 1 từ 0.29).
- Máy chủ cũ và CLI mới: CLI chỉ khai báo khả năng máy chủ có trong `/me`; `disabled_sources` thiếu thì coi như không
  tắt gì. CLI cũ và máy chủ mới: các trường mới trong `/me` bị bỏ qua, schema công cụ cũ giữ nguyên từng byte.

## Đã kiểm tới đâu

| Phần | Bằng chứng |
|---|---|
| Nguồn Peto sau khi tách cổng model (M1–M2) | Toàn bộ test CLI và backend; dùng hằng ngày |
| Khóa API OpenAI riêng | Chủ web chạy thật với khóa của mình (20/10, CLI 0.31.0); test với OpenAI giả |
| Bảng `/models`, `/connect` (M4) | Test màn hình giả; khung vẽ bằng mã thật, phát lại bằng xterm.js |
| Đăng nhập ChatGPT (M5) | Chủ web đăng nhập thật được (21/10, CLI 0.33.2, sau hai lần sửa: mã máy `urn:uuid`, kho chứng chỉ Windows có ISRG Root X2 cũ hết hạn) |
| Gọi model qua gói ChatGPT, công cụ, tóm tắt, mở lại, làm mới token, thu hồi | Test với máy chủ auth và API giả; **chưa xác nhận bằng tài khoản thật** |
| Bài nghiệm thu xuyên suốt (đổi nguồn giữa chừng, tóm tắt, mở lại) | `tests/test_acceptance_sources.py` cho cả khóa riêng và gói ChatGPT, máy chủ giả |
| Bộ cài | Wheel có đủ mọi mô-đun; cài vào thư mục sạch, nạp mọi mô-đun, chạy `peto --version` và `peto models` |
