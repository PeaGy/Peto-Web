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

Đổi mascot ở đầu phiên: thay ảnh trong `tools/` (PNG nền trong suốt: `mascot.png` cho hai cỡ lớn, `pear.png` cho cỡ
nhỏ), hoặc sửa danh sách `SIZES` trong công cụ, rồi chạy công cụ sinh lại `peto_agent/mascot.py`. Công cụ cần Pillow,
chỉ dùng khi phát triển; thư mục `tools/` không nằm trong gói cài, và đừng sửa tay `mascot.py`.

```powershell
.venv\Scripts\python.exe agent-cli\tools\make_mascot.py
```

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

Màn hình gọn như Claude Code, để phần giữa chỉ còn lời Peto. Đầu phiên là mascot của Peto (ký tự khối có màu) đứng cạnh
ba dòng ngắn, cỡ theo cửa sổ: từ 19 dòng là hình 24 cột × 12 dòng, từ 16 dòng là 18 × 9, từ 13 dòng (bảng terminal thấp
của VS Code) là quả lê 6 × 6. Thấp hơn nữa, hẹp dưới 41 cột, hay terminal tắt màu (`NO_COLOR`), thì chỉ còn ba dòng
chữ. Trong terminal của VS Code, Peto chừa thêm 2 cột bên phải, vì VS Code che khoảng hai cột sát mép:

```text
 [mascot]   Peto Agent 0.9.7
 [mascot]   Peto · mức vừa
 [mascot]   ~\Projects\website-a

                                                  ◉ Peto · vừa
──────────────────────────────────────────────────────────────
› Nhờ Peto làm gì đó…
──────────────────────────────────────────────────────────────
  còn 193/200 bước · /resume mở hội thoại lúc 14:45 hôm qua
```

Gõ yêu cầu giữa hai đường kẻ. Phía trên, bên phải là model và mức suy nghĩ đang dùng; phía dưới là số bước còn lại hôm
nay (cập nhật sau mỗi bước) và lời nhắc `/resume` khi thư mục có hội thoại cũ, tự tắt khi bạn bắt đầu hội thoại mới. Tên
tài khoản xem bằng `peto status`, các phím tắt và lệnh xem bằng `/help`. Khi nhập nhiều dòng, khung tự giãn theo nội
dung; tin quá dài được cuộn quanh vị trí con trỏ. Mỗi yêu cầu kết thúc bằng đúng một dòng mờ, ví dụ
`✓ Xong trong 12 giây · sửa 2 tệp · chạy 1 lệnh · hội thoại 15k token`; thời gian từng phần và token chi tiết xem bằng
`/usage`, và vẫn ghi đủ trong nhật ký.

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
- `/diff`: xem bản sửa/ghi tệp trực tiếp gần nhất đã lưu cho dự án. Diff dài có thể xem tiếp bằng `v`.
- `/undo`: xem diff rồi xác nhận hoàn tác yêu cầu gần nhất; giữ nguyên BOM và kiểu xuống dòng ban đầu, xóa các tệp
  mới do công cụ ghi tạo ra. Nếu bất kỳ tệp nào đã bị sửa/xóa bên ngoài, từ chối trước khi hoàn tác. Bản lưu nằm ở
  `%LOCALAPPDATA%\PetoAgent\checkpoints`, mở lại CLI tại đúng dự án rồi dùng `/diff` hoặc `/undo`, không cần `/resume`.
  `/moi`, `/resume` và yêu cầu chỉ đọc không xóa bản này; yêu cầu mới có sửa tệp sẽ thay thế bằng bản của yêu cầu mới.
  Mỗi dự án giữ một bản, tối đa 16 MB/bản (tính cả mã hóa), tổng 64 MB, dọn bản cũ nhất khi vượt dung lượng và hết hạn
  sau 30 ngày. Bản đã hoàn tác được lưu trạng thái rỗng để không khôi phục lần nữa. `/retry` tiếp tục cùng bản.
  Checkpoint chứa nội dung trước/sau của tệp, chỉ nằm trên máy, không gửi lên VPS. Nếu lưu checkpoint lỗi hoặc vượt
  giới hạn, thao tác ghi mới bị chặn. Đây không thay thế Git/backup và không bảo đảm giao dịch nhiều tệp khi mất điện.
  Xóa và đổi tên do Peto làm bằng công cụ thì thuộc bản hoàn tác; thay đổi do lệnh terminal thì không. Nếu lỗi ổ đĩa
  xảy ra giữa chừng, những tệp chưa khôi phục vẫn được giữ trong bản nhớ để kiểm tra lại; không có giao dịch nguyên
  khối nhiều tệp.
- `/permissions`: xem lệnh được ghi nhớ trong phiên; `/permissions clear` thu hồi tất cả. Quyền không lưu xuống đĩa
  và bị xóa khi `/moi` hoặc `/resume`.
- `/init`: Peto xem qua dự án (cấu trúc thư mục được gửi sẵn trong yêu cầu, khỏi tốn một bước), đọc README cùng các tệp
  cấu hình rồi viết `AGENTS.md` ở gốc dự án. Đây là một yêu cầu bình thường nên tốn vài bước, và bản ghi tệp vẫn hiện
  diff để bạn đồng ý. Dự án đã có `AGENTS.md` thì Peto đọc trước và chỉ sửa chỗ sai hoặc thiếu.
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

### Đính kèm tệp bằng @

Gõ `@` rồi tên tệp ngay trong yêu cầu thì bảng gợi ý đường dẫn hiện ra như bảng lệnh; Tab hoặc Enter điền tiếp.

```text
› sửa hàm đăng nhập trong @src/auth.ts cho khớp @docs/api.md
```

Lúc gửi, peto đọc các tệp đó trên máy bạn và gắn nội dung vào chính yêu cầu, nên Peto khỏi tốn một bước gọi công cụ
đọc tệp. Nội dung này được tính là đã đọc: Peto sửa thẳng bằng công cụ sửa tệp, vẫn hiện diff và vẫn hỏi bạn trước khi
ghi. Nếu tệp bị đổi sau lúc đính kèm, lần sửa vẫn bị từ chối như thường.

- **Chỉ một đoạn:** `@backend/main.py:120-180` đính kèm đúng khoảng dòng đó, `@backend/main.py:120` thì từ dòng 120
  tới cuối tệp. Tệp lớn mà bạn biết chỗ cần thì dùng cách này cho đỡ tốn token.
- Gõ `@` một thư mục thì đính kèm danh sách tệp trong đó (tối đa 200 mục), không kèm nội dung.
- Tệp bị chặn (`.env`, khóa, `.git`), tệp nhị phân hay tệp trên 1 MB thì không đính kèm được; một dòng vàng nói rõ lý do.
- Tệp dài chỉ đính kèm 1000 dòng đầu, và mỗi tin đính kèm tối đa 120.000 ký tự; phần còn lại Peto tự đọc khi cần.
- Chuỗi không phải đường dẫn trong dự án (`a@b.com`, `@app.route`) được để nguyên, không báo gì.

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

### Tìm web

Khi câu trả lời nằm ngoài dự án (tài liệu thư viện, thông báo lỗi lạ, API hay phiên bản mới), Peto tự tra web. Việc tìm
chạy ở phía dịch vụ AI, không mở gì trên máy bạn; trong CLI nó hiện thành một dòng `• Tìm trên web` trong bước đó.
Peto được nhắc chỉ đưa từ khóa cần thiết vào truy vấn, không đưa nội dung tệp hay đường dẫn trên máy bạn, và coi nội
dung trang web là dữ liệu chứ không phải lệnh. Mỗi lượt tìm tính phí vào tài khoản dịch vụ AI của chủ web, nên chủ web
tắt được bằng `PETO_AGENT_WEB_SEARCH=false`; khi tắt, Peto được yêu cầu nói rõ là mình không tra cứu được.

### Việc dài, lệnh nền và chuông báo

- **Danh sách việc:** yêu cầu từ ba việc trở lên thì Peto liệt kê các việc định làm và cập nhật khi xong từng mục, hiện
  ngay trong terminal: `☑` đã xong, `▶` đang làm, `☐` chưa làm. Còn mục chưa xong thì dòng tóm tắt cuối yêu cầu nói rõ
  còn bao nhiêu, để không ai tưởng đã xong hết.
- **Lệnh nền:** lệnh không tự kết thúc (dev server, `--watch`) được chạy nền và trả về ngay, thay vì chờ tới khi xong.
  Bạn vẫn duyệt trước khi chạy, và ô hỏi nói rõ lệnh sẽ sống tiếp sau khi yêu cầu xong. Tối đa 3 lệnh nền một lúc;
  Peto đọc output khi cần và tự dừng khi xong việc. **Đóng peto là mọi lệnh nền bị dừng**, cả cây tiến trình.
- **Chuông và tiêu đề cửa sổ:** terminal kêu một tiếng khi Peto cần bạn duyệt và khi một yêu cầu chạy quá 10 giây vừa
  xong; tiêu đề cửa sổ đổi theo trạng thái (`Peto · đang làm · tên-thư-mục`, `· cần bạn duyệt`, `· xong`) nên liếc
  thanh tác vụ là biết. Đặt `PETO_AGENT_NO_BELL=1` để tắt tiếng chuông, tiêu đề vẫn đổi.

### Hướng dẫn dự án và kiểm tra sau sửa

`AGENTS.md` ở gốc dự án được đọc lại ở mỗi bước. Khi đọc một tệp, Peto nhận thêm hướng dẫn trên đường từ gốc tới
thư mục chứa tệp đó; thư mục con có phạm vi riêng, không áp dụng sang thư mục ngang hàng. Khi hướng dẫn mới xuất hiện
hoặc thay đổi, công cụ sửa sẽ trả hướng dẫn trước và yêu cầu Peto xem lại rồi mới sửa. Tổng hướng dẫn cho một tệp
giới hạn 32.000 ký tự; vượt giới hạn thì báo lỗi, không âm thầm cắt. Không đọc hướng dẫn bên ngoài thư mục dự án.

Peto chọn test/build/lint từ hướng dẫn và cấu hình đã đọc. Nếu kết thúc sau khi sửa mà chưa nhận diện được lệnh kiểm tra kể từ lần
sửa cuối, CLI nhắc kiểm tra thêm một lần; không cần hoặc không thể kiểm tra thì Peto phải nói rõ. Mọi lệnh vẫn qua
cơ chế xin quyền. Sau tổng cộng 3 lần kiểm tra code thất bại, chặn sửa và chạy kiểm tra tiếp; vẫn cho đọc/chẩn đoán.
Tìm kiếm đơn giản bằng `rg`, `grep`, `findstr` trả mã 1 và output trống được báo là không có kết quả, không tính lỗi.
Lỗi có dấu hiệu thiếu công cụ/module/script, timeout và lỗi chưa phân loại không tiêu hao bộ đếm sửa code.
Một chuỗi lệnh lỗi lặp lại 3 lần sẽ bị chặn riêng để tránh vòng lặp. Lệnh ghép và script tùy chỉnh có thể chưa được
nhận diện; phân loại chỉ là gợi ý, Peto vẫn phải đọc output. Không tự cấp quyền hay cài thêm công cụ.
`/retry` giữ bộ đếm này; yêu cầu mới bắt đầu bộ đếm mới. CLI không tự coi mã thoát 0 của một lệnh bất kỳ là bằng chứng
rằng toàn bộ dự án đã được kiểm thử.

Cuối mỗi yêu cầu có một dòng tổng kết: thời gian, số tệp đã sửa, số lệnh đã chạy, độ dài hội thoại (tính bằng token) và
số bước còn lại hôm nay. Có thể dùng `/compact` để giảm ngữ cảnh hoặc `/moi` để bắt đầu việc khác.
Nhật ký từng phiên lưu ở `%LOCALAPPDATA%\PetoAgent\logs\`: yêu cầu bạn gõ, từng lời Peto trả lời (mỗi lời giữ tối đa
4000 ký tự, cả phần đầu lẫn phần cuối), các lệnh gọi công cụ và dòng tổng kết. Nhờ vậy xem lại được cả những lần cũ;
tệp hội thoại cho `/resume` thì mỗi dự án chỉ giữ lần gần nhất. Nhật ký chỉ nằm trên máy bạn.

### Giảm nội dung gửi cho model

Mặc định `read_file` đọc 160 dòng; chỉ định khoảng thì tối đa 400 dòng. Kết quả cho biết dòng tiếp theo khi còn nội
dung. Peto được hướng dẫn tìm từ khóa trước rồi đọc đúng khoảng cần thiết; mỗi lần đọc vẫn kiểm tra nội dung trên đĩa.

Trước khi gửi, CLI thay các kết quả đọc trùng hoàn toàn (nội dung, khoảng dòng và hướng dẫn giống nhau) bằng tham
chiếu tới bản mới hơn vẫn có đầy đủ trong cùng ngữ cảnh. Bản khác nội dung hoặc phạm vi không bị gộp. Output lệnh
cũ hơn 6 kết quả công cụ gần nhất được thu gọn còn khoảng 4.000 ký tự đầu/cuối; mã thoát, lỗi và phân loại vẫn giữ.
Các kết quả gần nhất giữ như cũ. Việc này không gọi thêm model, không chạy lại lệnh và không đổi lịch sử lưu tại máy.
Lịch sử cục bộ vẫn tuân theo giới hạn output ban đầu và cơ chế `/compact`, không phải nhật ký output không giới hạn.

### Đo thời gian và token

`/usage` hiện riêng thời gian AI/kết nối, chạy lệnh, công cụ khác, tóm tắt và chờ bạn trả lời xin quyền của yêu cầu
gần nhất (cuối mỗi yêu cầu chỉ in một dòng tổng kết).
Thời gian AI là đo từ CLI, gồm mạng, hàng đợi và nhận phản hồi; không phải thời gian tính toán riêng trên GPU.
Các nhóm không tính chồng thời gian chờ quyền/chạy lệnh vào công cụ khác. Tổng thời gian yêu cầu còn có xử lý nội bộ.

Token vào/ra được cộng từ usage máy chủ báo qua tất cả lượt trong yêu cầu; token tóm tắt hiển thị riêng. Lượt bị
ngắt hoặc máy chủ không báo usage được ghi là thiếu số liệu, không đoán bằng 0. Đây không phải báo giá tiền.
`/retry` cộng tiếp vào yêu cầu hiện tại, không tính thời gian bạn nghỉ giữa hai lần; yêu cầu mới đặt lại thống kê.
Sau khi thoát hoặc `/resume`, không khôi phục số đo cũ. `/compact` thủ công có thống kê riêng, không cộng vào yêu cầu trước.
Nhật ký `summary.metrics` lưu các số đo này để so sánh khi tối ưu; không có thêm dịch vụ thu thập thống kê từ xa.

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

Terminal không vẽ được LaTeX, nên công thức trong câu trả lời được `texmath.py` đổi sang ký hiệu Unicode trước khi in:
`\lnot A \lor B` hiện thành `¬A ∨ B`, `x^2` thành `x²`, `\frac{a+1}{2}` thành `(a+1)/2`, khối `\[ … \]` in thụt vào và
bỏ các dòng chỉ có dấu mở, đóng. Chỉ phần nằm trong dấu công thức mới bị đổi (`$5` hay `$HOME` giữ nguyên), code
không bao giờ bị đổi, và hội thoại gửi lại cho Peto vẫn là chữ gốc.

## Giới hạn và an toàn

- **Phạm vi:** Peto chỉ đụng tới tệp trong thư mục đang mở. Đường dẫn ra ngoài, kể cả qua symlink hay junction, bị chặn.
  CLI không chạy ở gốc ổ đĩa hay thư mục người dùng.
- **Tệp bí mật:** không đọc, không sửa `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*` và thư mục `.git`.
- **Tệp bị bỏ qua:** `node_modules`, `.venv`, `venv`, `dist`, `build` không được liệt kê hay tìm; tệp nhị phân và tệp lớn
  hơn 1 MB không được đọc. Những gì `.gitignore` ở gốc dự án bỏ qua (như `coverage/`, `target/`, `*.log`) cũng không
  được liệt kê, tìm hay gợi ý sau `@`, nhưng biết đường dẫn thì Peto vẫn đọc được. Chỉ đọc `.gitignore` ở gốc, có tính
  dòng `!`; `.gitignore` của thư mục con và cấu hình git toàn máy thì không. Sửa `.gitignore` là có tác dụng ngay.
- **Sửa tệp:** chỉ sửa tệp đã đọc và chưa bị đổi từ lúc đọc; đoạn cần thay phải khớp đúng một chỗ. Kiểu xuống dòng
  (CRLF/LF) và BOM được giữ nguyên.
- **Xóa và đổi tên:** Peto có công cụ riêng cho hai việc này và luôn hỏi trước; xóa thì hiện nội dung sắp mất, đổi tên
  thì hiện đường dẫn cũ và mới. Cả hai đi qua bản nhớ hoàn tác nên `/undo` lấy lại được, khác với xóa bằng lệnh
  terminal. Peto chỉ xóa được tệp chữ đọc được (không phải thư mục, tệp nhị phân hay tệp trên 1 MB), vì bản hoàn tác
  phải giữ được nội dung; đích của đổi tên phải là chỗ chưa có tệp.
- **Chạy lệnh:** chạy trong thư mục dự án bằng `cmd`, hoặc bằng PowerShell khi lệnh cần cmdlet hay biến `$env:` (ô hỏi
  ghi rõ `PS>`). Mặc định dừng sau 120 giây (tối đa 600). Lệnh test cũng chạy code nằm trong dự án, nên hãy xem kỹ các
  thay đổi trước khi đồng ý chạy. Lệnh nền không có thời hạn nhưng bị dừng khi bạn đóng peto.
- **Giới hạn bước:** mỗi yêu cầu tối đa 40 bước; mỗi tài khoản có số bước mỗi ngày do máy chủ đặt (mặc định 200). Ở mức
  suy nghĩ cao, mỗi bước tính 2; với 5.6 Terra nhân thêm 2, với 5.6 Sol nhân thêm 4.

## Dữ liệu gửi đi

Nội dung tệp Peto đọc, kết quả tìm trong dự án, diff, output lệnh và ảnh bạn gửi kèm đi qua máy chủ Peto tới dịch vụ AI của
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
