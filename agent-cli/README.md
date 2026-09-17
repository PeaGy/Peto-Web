# Peto Agent CLI

Chương trình dòng lệnh chạy trên máy Windows của bạn. Mở nó trong thư mục dự án rồi nhờ Peto sửa code: Peto đọc, tìm,
sửa tệp và chạy lệnh kiểm tra ngay trên máy bạn. Máy chủ Peto chỉ xác thực, đếm số bước và gọi mô hình AI; token của
dịch vụ AI không bao giờ xuống máy bạn.

## Cần gì

- Windows có Python 3.12 trở lên. Chưa có thì cài bằng `winget install -e --id Python.Python.3.14` hoặc tải ở
  [python.org](https://www.python.org/downloads/). Không cần cài thêm gói Python nào.
- Tài khoản Peto đăng nhập bằng Discord hoặc Google. Tài khoản khách không dùng được Peto Agent.

## Cài đặt

Mở PowerShell (không cần quyền quản trị) và chạy:

```powershell
irm https://dia-chi-peto/install.ps1 | iex
```

Bộ cài lấy mọi thứ từ chính máy chủ Peto đó:

- tải gói `peto` và so mã băm SHA-256;
- cài vào môi trường Python riêng ở `%LOCALAPPDATA%\PetoAgent\venv`, không đụng các gói Python khác trên máy;
- chép `peto.exe` sang `%LOCALAPPDATA%\PetoAgent\bin` và thêm thư mục đó vào PATH của tài khoản Windows;
- ghi địa chỉ Peto vào gói, nên `peto login` không phải hỏi.

`peto` được cài một lần cho cả tài khoản Windows và dùng được ở mọi thư mục; không cần cài lại cho từng thư mục. Muốn cập
nhật thì chạy lại đúng lệnh trên, kể cả khi đang có cửa sổ khác chạy `peto`.

Cửa sổ vừa chạy lệnh cài gõ được `peto` ngay. Cửa sổ khác báo `The term 'peto' is not recognized` là vì ứng dụng terminal
mở từ trước lúc cài (Windows Terminal, VS Code…) vẫn giữ PATH cũ, kể cả khi mở tab mới. Đóng hẳn ứng dụng rồi mở lại,
hoặc mở PowerShell từ menu Start. Muốn dùng ngay trong cửa sổ đó thì nạp lại PATH:

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
```

Biến môi trường tùy chọn: `PETO_AGENT_INSTALL_DIR` để cài chỗ khác, `PETO_AGENT_NO_MODIFY_PATH=1` để không sửa PATH.

### Cập nhật

Khi máy chủ có bản `peto` mới hơn bản trên máy, `peto` nhắc ngay lúc mở phiên và trong `peto status`, kèm lệnh cài để
chạy lại. `peto --version` xem bản đang dùng.

Ai mở được trang Peto cũng tải được bộ cài và mã nguồn CLI; trong đó không có bí mật nào.

### Gỡ cài đặt

```powershell
peto logout
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\PetoAgent", "$env:APPDATA\PetoAgent"
```

Lệnh thứ hai xóa cả chương trình, nhật ký và cấu hình. Mục `PetoAgent\bin` còn lại trong PATH không ảnh hưởng gì; muốn
bỏ thì mở **Edit environment variables for your account** trên Windows.

### Cài từ mã nguồn

Khi sửa chính CLI này:

```powershell
py -m pip install --user -e C:\duong-dan\Peto-Web\agent-cli
```

Nếu Windows báo không tìm thấy lệnh `peto`, thêm thư mục `Scripts` của Python vào PATH, hoặc chạy `py -m peto_agent`. Bản
cài từ mã nguồn không kèm địa chỉ Peto, nên `peto login` sẽ hỏi địa chỉ, hoặc thêm `--server https://dia-chi-peto`.

## Đăng nhập

```powershell
peto login
```

CLI in một liên kết và một mã dạng `KXMT-4P2Q`, rồi thử mở liên kết trên trình duyệt. Trên trang Peto (đã đăng nhập bằng
Discord hoặc Google), kiểm tra mã trong hộp "Kết nối Peto Agent?" giống hệt mã trên máy rồi bấm **Cho phép**. Mã hết hạn
sau 10 phút.

Token được lưu ở `%APPDATA%\PetoAgent\config.json`. Đừng chia sẻ tệp này.

- `peto status`: tài khoản, tên máy, mức suy nghĩ, số bước còn lại và số token đã dùng hôm nay.
- `peto logout`: ngắt kết nối máy này.
- Ngắt từ xa (ví dụ mất máy): trên web, **Cài đặt → Peto Agent → Ngắt kết nối**.

## Làm việc

```powershell
cd C:\Projects\website-a
peto
```

Gõ yêu cầu như nhắn tin cho Peto. Gõ `/` thì danh sách lệnh hiện ngay dưới dòng nhập và lọc dần theo chữ bạn gõ:

```text
Bạn › /re
  ❯ /resume  Mở lại hội thoại gần nhất của thư mục này
```

Mũi tên lên/xuống chọn lệnh, Tab điền lệnh, Enter chạy lệnh đang chọn, Esc ẩn danh sách. Mới gõ mỗi `/` thì chưa có lệnh
nào được chọn, nên Enter không tự chạy gì. Các lệnh:

- `/moi`: bắt đầu hội thoại mới.
- `/resume`: mở lại hội thoại gần nhất của thư mục này, kể cả sau khi đã thoát. Không lệnh nào được chạy lại, và muốn
  sửa tệp thì Peto phải đọc lại tệp trước. Mở `peto` ở thư mục có hội thoại cũ sẽ có dòng nhắc.
- `/effort thap`, `/effort vua`, `/effort cao`: mức suy nghĩ, được nhớ trên máy này cho lần sau. Mức cao suy nghĩ kỹ
  hơn nhưng mỗi bước tính 2 bước. Gõ `/effort` để xem mức đang dùng; chưa chọn thì theo mặc định của máy chủ. Gõ
  `/effort` kèm dấu cách thì chọn mức trong danh sách.
- `/usage`: số bước còn lại và số token đã dùng hôm nay, độ dài hội thoại đang mở và mức suy nghĩ.
- `/help`: xem các lệnh. `/thoat`: thoát. Tên lệnh gõ có dấu (`/thoát`) vẫn được nhận.
- **Ctrl+C**: dừng yêu cầu đang chạy; lệnh đang chạy bị dừng cả cây tiến trình. Ở dòng nhập, Ctrl+C xóa chữ đang gõ;
  dòng đã trống thì thoát.

Dòng nhập còn có:

- **Mũi tên lên/xuống** (khi không có danh sách lệnh) gọi lại các tin đã gửi trong phiên, hoặc chuyển dòng khi tin có
  nhiều dòng.
- **Dán nhiều dòng**, ví dụ log lỗi: cả đoạn nằm trong một tin, không bị gửi từng dòng. Đoạn từ 4 dòng hoặc dài hơn 1000
  ký tự hiện gọn thành `[Đã dán 42 dòng]` nhưng vẫn gửi đủ; gõ thêm lời nhắn rồi Enter để gửi.
- **Shift+Enter** xuống dòng trong Windows Terminal và cửa sổ PowerShell.

### Gửi ảnh

Muốn Peto xem ảnh, ví dụ ảnh chụp lỗi giao diện:

- **Alt+V** dán ảnh trong clipboard: ảnh vừa chụp bằng Win+Shift+S hay PrtScn, ảnh copy từ trình duyệt, hoặc tệp ảnh copy
  trong Explorer. Ctrl+V vẫn là dán chữ, vì terminal giữ phím đó.
- **Kéo tệp ảnh** (.png, .jpg, .gif, .webp, .bmp) từ Explorer thả vào cửa sổ terminal.

Ảnh hiện thành nhãn ngay chỗ con trỏ, rồi bạn gõ tiếp như thường:

```text
Bạn › giao diện lỗi như [Ảnh 1] sửa giúp mình
```

Xóa nhãn là bỏ ảnh. Ảnh được đánh số tăng dần trong phiên. Clipboard không có ảnh thì một dòng nhắc màu vàng hiện dưới
dòng nhập, gõ phím tiếp là biến mất.

- **Ảnh lớn:** ảnh có cạnh dài quá 2000px được thu nhỏ còn 2000px; ảnh vẫn nặng quá 2 MB thì chuyển sang JPEG hoặc thu
  nhỏ thêm. Ảnh chụp bằng điện thoại được xoay theo đúng chiều chụp. Ảnh WebP không thu nhỏ được nên phải dưới 2 MB.
- **Gửi lại ảnh:** máy chủ không lưu hội thoại, nên bước nào Peto cũng gửi lại các ảnh trong hội thoại. Peto chỉ giữ 4
  ảnh gần nhất; ảnh cũ hơn được thay bằng một dòng ghi chú.

Dòng nhập này tự đọc từng phím của console Windows. Bộ gõ như Unikey, EVKey sửa chữ bằng cách gửi phím xóa rồi gửi chữ
mới, nên mỗi lần xóa bỏ đúng một ký tự như ô nhập thường. Nếu dòng nhập hiển thị sai hay gõ tiếng Việt bị lỗi trong
terminal của bạn, đặt `$env:PETO_AGENT_SIMPLE_INPUT = '1'` trước khi chạy `peto` để quay về dòng nhập đơn giản, không có
danh sách lệnh, lịch sử, dán nhiều dòng hay gửi ảnh. Khi input được chuyển từ tệp hay ống dẫn, `peto` cũng dùng dòng nhập đơn giản.

Trong lúc chờ, một dòng tạm `… Peto đang nghĩ · 8s` tự đếm giây rồi biến mất khi có chữ. Câu trả lời hiện theo từng dòng
để tô được chữ đậm và `mã`; khi output bị chuyển sang tệp thì giữ nguyên chữ gốc.

Mỗi lần Peto muốn sửa hay tạo tệp, CLI hiện diff; mỗi lần muốn chạy lệnh, CLI hiện lệnh đó. Bạn trả lời:

- `y`: đồng ý bước này.
- `n`: không đồng ý. Peto được báo lại để hỏi bạn cách khác.
- `a`: đồng ý mọi bước còn lại trong yêu cầu đang chạy.

Cuối mỗi yêu cầu có một dòng tổng kết: thời gian, số tệp đã sửa, số lệnh đã chạy, độ dài hội thoại (tính bằng token) và
số bước còn lại hôm nay. Mỗi bước gửi lại cả hội thoại cho Peto, nên khi hội thoại dài làm Peto chậm hay báo lỗi thì gõ
`/moi`. Nhật ký từng phiên lưu ở `%LOCALAPPDATA%\PetoAgent\logs\`.

## Giới hạn và an toàn

- **Phạm vi:** Peto chỉ đụng tới tệp trong thư mục đang mở. Đường dẫn ra ngoài, kể cả qua symlink hay junction, bị chặn.
  CLI không chạy ở gốc ổ đĩa hay thư mục người dùng.
- **Tệp bí mật:** không đọc, không sửa `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*` và thư mục `.git`.
- **Tệp bị bỏ qua:** `node_modules`, `.venv`, `venv`, `dist`, `build` không được liệt kê hay tìm; tệp nhị phân và tệp lớn
  hơn 1 MB không được đọc.
- **Sửa tệp:** chỉ sửa tệp đã đọc và chưa bị đổi từ lúc đọc; đoạn cần thay phải khớp đúng một chỗ. Kiểu xuống dòng
  (CRLF/LF) và BOM được giữ nguyên.
- **Chạy lệnh:** chạy bằng `cmd` trong thư mục dự án, mặc định dừng sau 120 giây (tối đa 600). Lệnh test cũng chạy code
  nằm trong dự án, nên hãy xem kỹ các thay đổi trước khi đồng ý chạy.
- **Giới hạn bước:** mỗi yêu cầu tối đa 40 bước; mỗi tài khoản có số bước mỗi ngày do máy chủ đặt (mặc định 200). Ở mức
  suy nghĩ cao, mỗi bước tính 2.

## Dữ liệu gửi đi

Nội dung tệp Peto đọc, kết quả tìm kiếm, diff, output lệnh và ảnh bạn gửi kèm đi qua máy chủ Peto tới dịch vụ AI (xAI)
để Peto quyết định bước tiếp theo. Máy chủ không lưu hội thoại; nó chỉ lưu tên máy, mã băm của token và số bước đã dùng. Đừng mở Peto Agent
trong thư mục có dữ liệu bạn không muốn gửi đi.

Để `/resume` hoạt động, hội thoại gần nhất của mỗi thư mục được lưu trên chính máy bạn ở
`%LOCALAPPDATA%\PetoAgent\sessions\`, gồm cả nội dung tệp Peto đã đọc, output lệnh và các ảnh còn giữ trong hội thoại. Tệp không dùng quá 30 ngày được tự
xóa; gỡ Peto Agent cũng xóa thư mục này.

## Thử trên máy

Chạy backend với `PETO_AI_PROVIDER=mock` và `PETO_FRONTEND_URL=http://localhost:5173` cùng Vite, rồi
`peto login --server http://127.0.0.1:8000`. Chỉ máy chủ chạy ngay trên máy này mới được dùng `http`. Với nhà cung
cấp giả, yêu cầu có `__demo__` chạy một vòng mẫu: đọc `README.md` → sửa dòng đầu → chạy một lệnh → tóm tắt.

Thử bộ cài mà không đụng PATH và cấu hình thật (gọi thẳng backend ở cổng 8000; Vite không chuyển `/install.ps1`):

```powershell
$env:PETO_AGENT_INSTALL_DIR = "$env:TEMP\peto-thu"
$env:PETO_AGENT_NO_MODIFY_PATH = '1'
$env:PETO_AGENT_HOME = "$env:TEMP\peto-thu\home"
irm http://127.0.0.1:8000/install.ps1 | iex
```

Script bộ cài chưa có test tự động; khi sửa `install.ps1`, chạy lại lệnh trên bằng Windows PowerShell 5.1.

Phần đọc phím của dòng nhập (`WindowsConsole` trong `line_editor.py`) không chạy được trong pytest, vì pytest không có
console thật. Khi sửa nó, thử lại trong Windows Terminal và cửa sổ PowerShell: gõ `/` rồi chọn lệnh, dán nhiều dòng, gõ
chữ dài tới lúc xuống hàng, gõ tiếng Việt bằng bộ gõ, Alt+V một ảnh chụp màn hình, kéo thả một tệp ảnh, và trả lời câu hỏi
y/n sau đó. Phần giải mã và thu nhỏ ảnh (GDI+) thì có test; phần đọc clipboard thật thì không.

Mỗi lần đổi CLI, tăng `version` trong `pyproject.toml` cùng `__version__` trong `peto_agent/__init__.py` (hai số phải bằng
nhau). Không tăng thì máy đang cài bản cũ không được nhắc cập nhật.

## Test

```bash
.venv/Scripts/python.exe -m pytest agent-cli/tests
cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_agent_install.py   # gói wheel và script bộ cài
```
