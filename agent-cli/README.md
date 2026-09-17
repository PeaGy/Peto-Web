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

- `peto status`: tài khoản, tên máy, model, mức suy nghĩ, số bước còn lại và số token đã dùng hôm nay.
- `peto logout`: ngắt kết nối máy này.
- Ngắt từ xa (ví dụ mất máy): trên web, **Cài đặt → Peto Agent → Ngắt kết nối**.

## Làm việc

```powershell
cd C:\Projects\website-a
peto
```

Gõ yêu cầu trong khung nền xám trải ngang terminal. Khung trống hiện **Nhờ Peto làm gì đó…**; bên dưới là mức suy nghĩ
và thư mục đang mở. Khi nhập nhiều dòng, khung tự giãn theo nội dung; tin quá dài được cuộn quanh vị trí con trỏ.
Gõ `/` thì danh sách lệnh hiện ngay dưới khung nhập và lọc dần theo chữ bạn gõ:

```text
› /re
  ❯ /resume  Mở lại hội thoại gần nhất của thư mục này
    /retry   Thử lại bước bị gián đoạn kết nối
```

Mũi tên lên/xuống chọn lệnh, Tab điền lệnh, Enter chạy lệnh đang chọn, Esc ẩn danh sách. Mới gõ mỗi `/` thì chưa có lệnh
nào được chọn, nên Enter không tự chạy gì. Các lệnh:

- `/moi`: bắt đầu hội thoại mới.
- `/resume`: mở lại hội thoại gần nhất của thư mục này, kể cả sau khi đã thoát. Không lệnh nào được chạy lại, và muốn
  sửa tệp thì Peto phải đọc lại tệp trước. Mở `peto` ở thư mục có hội thoại cũ sẽ có dòng nhắc.
- `/retry`: thử lại bước bị gián đoạn kết nối, dùng kết quả các bước đã hoàn tất. Không tự phát lại lệnh hay thao tác
  sửa tệp cũ; thao tác mới vẫn hỏi quyền. Nếu đã thoát thì `/resume` trước, rồi `/retry`.
- `/diff`: xem thay đổi do công cụ sửa/ghi tệp tạo ra trong yêu cầu gần nhất. Diff dài có thể xem tiếp bằng `v`.
- `/undo`: xem diff rồi xác nhận hoàn tác yêu cầu gần nhất; giữ nguyên BOM và kiểu xuống dòng ban đầu, xóa các tệp
  mới do công cụ ghi tạo ra. Nếu bất kỳ tệp nào đã bị sửa/xóa bên ngoài, từ chối trước khi hoàn tác. Đây là bản nhớ
  trong phiên, không còn sau khi thoát, `/moi`, `/resume` hoặc bắt đầu yêu cầu mới; `/retry` vẫn giữ bản nhớ đó.
  Thay đổi do lệnh terminal, đổi tên/xóa qua shell không thuộc bản hoàn tác. Nếu lỗi ổ đĩa xảy ra giữa chừng,
  những tệp chưa khôi phục vẫn được giữ trong bản nhớ để kiểm tra lại; không có giao dịch nguyên khối nhiều tệp.
- `/permissions`: xem lệnh được ghi nhớ trong phiên; `/permissions clear` thu hồi tất cả. Quyền không lưu xuống đĩa
  và bị xóa khi `/moi` hoặc `/resume`.
- `/compact`: tóm tắt phần hội thoại cũ, giữ các bước gần nhất và yêu cầu gần nhất nằm trong phần được tóm tắt.
  Peto cũng tự tóm tắt giữa các bước khi lịch sử đạt 180 mục hoặc khoảng 200.000 ký tự chữ. Tóm tắt dùng một lượt
  gọi model ở mức suy nghĩ thấp, vẫn tính bước theo model và token như bình thường. Cần cập nhật cả VPS và CLI.
  Không chạy công cụ khi tóm tắt, không tách cặp gọi công cụ/kết quả. Lỗi, hủy hoặc máy chủ cũ thì giữ nguyên lịch sử.
  Tóm tắt có thể bỏ sót chi tiết; tệp phải được đọc lại trước khi sửa và ảnh cũ trong phần tóm tắt được thay bằng ghi chú.
- `/effort thap`, `/effort vua`, `/effort cao`: mức suy nghĩ, được nhớ trên máy này cho lần sau. Mức cao suy nghĩ kỹ
  hơn nhưng mỗi bước tính 2 bước. Gõ `/effort` để xem mức đang dùng; chưa chọn thì theo mặc định của máy chủ. Gõ
  `/effort` kèm dấu cách thì chọn mức trong danh sách.
- `/model peto`, `/model luna`: đổi model, được nhớ trên máy này cho lần sau. Peto là mặc định; 5.6 Luna (của OpenAI)
  dùng được với tài khoản Discord/Google. Chủ web còn chọn được `/model terra` và `/model sol`. Gõ `/model` để xem model
  đang dùng và các model tài khoản của bạn được chọn; gõ `/model` kèm dấu cách thì chọn trong danh sách. Model đắt hơn
  tính nhiều bước hơn: Terra 2, Sol 4, nhân với mức suy nghĩ. Đổi model giữa hội thoại vẫn làm tiếp được; phần suy nghĩ
  của model cũ được bỏ vì model mới không đọc được.
- `/usage`: số bước còn lại và số token đã dùng hôm nay, độ dài hội thoại đang mở, model và mức suy nghĩ.
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
› giao diện lỗi như [Ảnh 1] sửa giúp mình
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
danh sách lệnh, lịch sử, dán nhiều dòng hay gửi ảnh. Khi input được chuyển từ tệp hay ống dẫn, `peto` cũng dùng dấu nhắc
đơn giản `›`, không vẽ khung. `NO_COLOR` tắt cả màu nền của khung.

Trong lúc chờ, một dòng tạm `… Peto đang nghĩ · 8s` tự đếm giây rồi biến mất khi có chữ. Câu dài đang viết hiện dần trên
dòng tạm; khi xong dòng sẽ in đủ nội dung cùng chữ đậm và `mã`. Nội dung đã in nằm trong lịch sử cuộn của terminal.
Không chuyển sang màn hình toàn phần, không cần cài thêm thư viện. `NO_COLOR` tắt màu; khi output chuyển sang tệp hoặc
ống dẫn, không có mã điều khiển hay dòng trạng thái vẽ lại.

Mỗi lần Peto muốn sửa hay tạo tệp, CLI hiện diff có cột **Cũ / Mới**, số dòng thêm/xóa và ngắt dòng code dài theo chiều
rộng terminal. Diff dài hiện từng phần; gõ `v` tại câu hỏi đồng ý để xem phần tiếp theo, không cấp quyền sửa tệp.
Mỗi lần muốn chạy lệnh, CLI hiện nguyên lệnh, thư mục và giới hạn thời gian. Khi chạy có bộ đếm thời gian và dòng output
mới nhất (ở terminal đủ rộng); khi xong hiện tối đa 8 dòng output cuối cùng cùng kết quả hoặc mã lỗi. Bạn trả lời:

- `y`: đồng ý bước này.
- `n`: không đồng ý. Peto được báo lại để hỏi bạn cách khác.
- `a`: đồng ý mọi bước còn lại trong yêu cầu đang chạy.
- `s` (chỉ khi chạy lệnh): đồng ý và ghi nhớ **đúng chuỗi lệnh, thư mục, thời hạn** trong phiên. Không phải quyền theo
  tiền tố: `npm test` không cấp quyền cho `npm test && ...` hay lệnh có tham số khác. Script mà lệnh gọi vẫn có thể
  thay đổi theo nội dung dự án; chỉ ghi nhớ lệnh bạn tin tưởng.

### Hướng dẫn dự án và kiểm tra sau sửa

`AGENTS.md` ở gốc dự án được đọc lại ở mỗi bước. Khi đọc một tệp, Peto nhận thêm hướng dẫn trên đường từ gốc tới
thư mục chứa tệp đó; thư mục con có phạm vi riêng, không áp dụng sang thư mục ngang hàng. Khi hướng dẫn mới xuất hiện
hoặc thay đổi, công cụ sửa sẽ trả hướng dẫn trước và yêu cầu Peto xem lại rồi mới sửa. Tổng hướng dẫn cho một tệp
giới hạn 32.000 ký tự; vượt giới hạn thì báo lỗi, không âm thầm cắt. Không đọc hướng dẫn bên ngoài thư mục dự án.

Peto chọn test/build/lint từ hướng dẫn và cấu hình đã đọc. Nếu kết thúc sau khi sửa mà chưa chạy lệnh nào kể từ lần
sửa cuối, CLI nhắc kiểm tra thêm một lần; không cần hoặc không thể kiểm tra thì Peto phải nói rõ. Mọi lệnh vẫn qua
cơ chế xin quyền. Sau tổng cộng 3 lệnh trả lỗi trong một yêu cầu, chặn chạy lệnh và sửa tiếp, để Peto báo việc còn lại.
`/retry` giữ bộ đếm này; yêu cầu mới bắt đầu bộ đếm mới. CLI không tự coi mã thoát 0 của một lệnh bất kỳ là bằng chứng
rằng toàn bộ dự án đã được kiểm thử.

Cuối mỗi yêu cầu có một dòng tổng kết: thời gian, số tệp đã sửa, số lệnh đã chạy, độ dài hội thoại (tính bằng token) và
số bước còn lại hôm nay. Có thể dùng `/compact` để giảm ngữ cảnh hoặc `/moi` để bắt đầu việc khác.
Nhật ký từng phiên lưu ở `%LOCALAPPDATA%\PetoAgent\logs\`.

### Khi mất kết nối

CLI chỉ chạy công cụ sau khi nhận đủ sự kiện hoàn tất bước. Kết nối bị cắt giữa câu trả lời thì giữ kết quả các bước
trước, đánh dấu bước hiện tại chưa xong và trả về ô nhập. Khi mạng ổn, gõ `/retry`. Không tự gửi lại ngầm, vì một bước
AI mà máy chủ đã nhận có thể vẫn được tính vào lượt dùng. `/retry` xóa quyền `a` cũ; quyền `s` cho đúng lệnh vẫn giữ
trong phiên, các thao tác khác sẽ hỏi lại.

Nếu đã đóng CLI, mở lại trong cùng thư mục, gõ `/resume` rồi `/retry`. `/moi` hoặc gửi yêu cầu mới bỏ trạng thái chờ thử
lại. Lỗi đăng nhập hay hết lượt vẫn cần xử lý theo thông báo; `/retry` không bỏ qua các giới hạn đó. Khi mạng im lặng
hoàn toàn, socket có thể cần chờ tới timeout mới nhận ra; Ctrl+C vẫn dừng được trong lúc đọc stream.

### Cấu trúc giao diện

`presentation.py` khai báo giao diện mà `Session` và `Tools` sử dụng; `ui.py` chịu trách nhiệm Markdown đang stream,
diff, câu hỏi quyền, khối lệnh và các dòng trạng thái. Bộ chạy lệnh chỉ báo tiến độ qua callback, không tự in chữ.
Nhờ đó có thể thay lớp hiển thị sau này mà không thay cách thực thi công cụ hay lưu hội thoại.

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
  suy nghĩ cao, mỗi bước tính 2; với 5.6 Terra nhân thêm 2, với 5.6 Sol nhân thêm 4.

## Dữ liệu gửi đi

Nội dung tệp Peto đọc, kết quả tìm kiếm, diff, output lệnh và ảnh bạn gửi kèm đi qua máy chủ Peto tới dịch vụ AI của
model đang chọn (xAI với Peto, OpenAI với 5.6 Luna, Terra, Sol) để Peto quyết định bước tiếp theo. Máy chủ không lưu hội
thoại; nó chỉ lưu tên máy, mã băm của token và số bước đã dùng. Đừng mở Peto Agent trong thư mục có dữ liệu bạn không
muốn gửi đi.

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
