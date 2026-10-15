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

Khi máy chủ có bản `peto` mới hơn bản trên máy, `peto` nhắc ngay lúc mở phiên và trong `peto status`. Từ 0.22.0 (theo
opencode) gõ `/update` ngay trong `peto`: Peto chạy lại bộ cài của đúng máy chủ đang đăng nhập (vài giây tới một phút,
`Ctrl+C` dừng được), hiện output như một khối lệnh, rồi hỏi "Mở lại ngay". Chọn mở lại thì bản mới mở trong cùng cửa
sổ và vẽ lại đúng hội thoại đang dở. `/update` chỉ tự cài cho bản cài bằng lệnh `irm … | iex` ở trên; chạy từ mã
nguồn thì nó in lệnh cài để bạn tự chạy. `peto --version` xem bản đang dùng.

Ai mở được trang Peto cũng tải được bộ cài và mã nguồn CLI; trong đó không có bí mật nào.

### Gỡ cài đặt

```powershell
peto logout
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\PetoAgent", "$env:APPDATA\PetoAgent"
```

Lệnh thứ hai xóa cả chương trình, nhật ký và cấu hình. Mục `PetoAgent\bin` còn lại trong PATH không ảnh hưởng gì; muốn
bỏ thì mở **Edit environment variables for your account** trên Windows.

### Cài từ mã nguồn

Từ 0.14.1, danh mục lệnh dùng chung nằm ở `peto_agent/command_catalog.json`: CLI dùng tên, mô tả và
options cho `/help`/gợi ý; web dùng cùng dữ liệu và thêm `usage`, `details`, `since` để hướng dẫn.
Thêm hoặc đổi lệnh cần cập nhật danh mục cùng code thực thi. Kiểm thử đối chiếu bộ xử lý lệnh với tài liệu
và kiểm tra danh mục có trong wheel tải về. Các lựa chọn model/effort thực tế vẫn lấy từ máy chủ theo tài khoản.
Web đọc phiên bản từ bộ cài đang phục vụ, không biết phiên bản đang cài trên máy người dùng.
Hướng dẫn chi tiết được chọn theo ba tin nhắn người dùng gần nhất trong hội thoại, không đọc cấu hình MCP hay skills riêng.

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

## Skills của dự án (CLI 0.13.0)

Đặt hướng dẫn tại `.peto/skills/<tên>/SKILL.md` hoặc `.agents/skills/<tên>/SKILL.md` trong dự án đang mở.
Nếu trùng tên, bản trong `.peto/skills` được ưu tiên. Ví dụ:

```markdown
---
name: review
description: Rà thay đổi code và chỉ ra lỗi có thể tái hiện.
---
Đọc README và phần code liên quan trước khi nhận xét.
Ưu tiên lỗi ảnh hưởng người dùng, kèm đường dẫn và cách tái hiện.
```

- `/skill`: xem danh sách, trạng thái đã nạp và lỗi định dạng.
- `/skill review`: nạp hướng dẫn cho hội thoại hiện tại, chưa gọi model.
- `/skill review Rà thay đổi hiện tại`: nạp rồi giao việc ngay.
- Peto cũng có thể tự chọn skill phù hợp: chỉ tên/mô tả được gửi trước, nội dung đầy đủ được nạp khi cần.

Tài liệu hoặc script đi kèm đặt trong thư mục skill; đường dẫn trong hướng dẫn tính từ thư mục đó.
Skill không tự chạy script và không thay đổi quyền công cụ. Nội dung đã nạp được lưu cùng hội thoại.
Sau khi sửa SKILL.md, gọi lại `/skill tên` để nạp bản mới.

Bản đầu hỗ trợ `name` và `description` dạng chuỗi đơn hoặc mô tả nhiều dòng `>`/`|`, không hỗ trợ toàn bộ YAML.
Tên gồm chữ thường, số và gạch nối, tối đa 64 ký tự. Mỗi skill tối đa 24.000 ký tự; tối đa 32 skill,
quét tối đa 128 mục mỗi thư mục gốc. Chưa nạp skills toàn máy và chưa hỗ trợ MCP.
Cập nhật cả máy chủ và CLI để Peto có công cụ tự nạp skill.

## MCP (CLI 0.14.0)

Cập nhật cả backend và CLI. MCP dùng công cụ bên ngoài; cấu hình lưu trong `mcp.json` cạnh cấu hình
đăng nhập của CLI, không tự đọc hay bật MCP từ repo. Mỗi phiên bắt đầu với tất cả kết nối tắt.

Tạo một tệp JSON trong dự án, ví dụ `docs-mcp.json` cho máy chủ từ xa:

```json
{
  "url": "https://dia-chi-nha-cung-cap/mcp",
  "headers": {"Authorization": "Bearer ${DOCS_API_KEY}"}
}
```

URL là ví dụ: thay bằng endpoint MCP thực tế của nhà cung cấp. Bỏ `headers` nếu máy chủ không cần khóa.
Đặt biến môi trường trong terminal trước khi mở Peto; không ghi khóa vào JSON hoặc chat.
Hỗ trợ header `Authorization`, `X-API-Key`, `Api-Key`, giá trị lấy qua `${TEN_BIEN}`.

Máy chủ chạy cục bộ dùng cấu hình riêng:

```json
{
  "command": "node",
  "args": ["C:/tools/my-mcp/server.js"],
  "env": {"SERVICE_API_KEY": "${SERVICE_API_KEY}"}
}
```

Chương trình phải được cài sẵn. CLI chạy trực tiếp command/args ở thư mục dự án, không tự mở shell hay tự cài gói.
Trên Windows ưu tiên chương trình `.exe` hoặc `node` với đường dẫn script. MCP chỉ nhận các biến hệ thống cơ bản
và biến được khai báo trong `env`; không tự thừa hưởng toàn bộ khóa của terminal.

```text
/mcp add docs docs-mcp.json
/mcp enable docs
/mcp tools docs
/mcp
/mcp disable docs
```

`add` lưu cấu hình, chưa chạy. `enable` hiển thị cấu hình và hỏi xác nhận trước khi kết nối;
MCP cục bộ chạy với quyền tài khoản máy, không phải sandbox của công cụ đọc/sửa tệp Peto.
Sau đó giao việc bằng ngôn ngữ bình thường. Peto đọc schema công cụ khi cần rồi gọi MCP.
Mỗi lần gọi hiện tham số và hỏi quyền riêng (chọn `a` cũng chỉ đồng ý lần gọi này).
Mô tả `readOnly` do máy chủ khai báo không được dùng để tự bỏ bước hỏi quyền.

Hỗ trợ tools qua stdio và Streamable HTTP (JSON hoặc SSE), khởi tạo phiên, phân trang danh sách công cụ.
Không theo chuyển hướng HTTP, không tự thử lại lời gọi bị lỗi. Hết thời gian hoặc Ctrl+C đóng kết nối;
thao tác từ xa có thể vẫn đã diễn ra nên cần kiểm tra trước khi gọi lại. Dùng `enable` lại để làm mới danh sách công cụ.
Giới hạn: 16 máy chủ, 128 công cụ và 64 KB schema/máy chủ, 1 MB/phản hồi, 30 giây/yêu cầu.
Bản này chưa hỗ trợ OAuth, SSE cũ, tự nối lại stream, MCP prompts/resources/sampling/elicitation.
Các kết nối dừng khi thoát CLI bình thường; chưa tự phục hồi MCP khi `/resume`.
Tham chiếu giao thức: [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

## Đăng nhập tài khoản

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

Giao diện theo OpenCode (từ 0.16.0, chủ web chọn từ bản mô phỏng ngày 2026-10-12). Từ 0.19.0 Peto chiếm cả cửa sổ
terminal như Claude Code và opencode: đầu phiên và hội thoại ở trên, ô nhập ghim ở đáy, thoát ra (`Ctrl+C` lúc ô trống,
`/exit`) thì terminal trở lại y như trước khi gõ `peto`. Đầu phiên là mascot của Peto (ký tự khối có màu) đứng cạnh ba
dòng ngắn, cỡ theo cửa sổ: từ 19 dòng là hình 24 cột × 12 dòng, từ 16 dòng là 18 × 9, từ 13 dòng (bảng terminal thấp của VS Code) là
quả lê 6 × 6. Thấp hơn nữa, hẹp dưới 41 cột, hay terminal tắt màu (`NO_COLOR`), thì chỉ còn ba dòng chữ. Trong terminal
của VS Code, Peto chừa thêm 2 cột bên phải, vì VS Code che khoảng hai cột sát mép:

```text
 [mascot]   Peto Agent 0.27.0
 [mascot]   6 Luna · mức thấp
 [mascot]   ~\Projects\website-a

  ┃
  ┃  Nhờ Peto làm gì đó…
  ┃
  ┃  Peto · 6 Luna · Thấp
  ╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
  còn 193/200 bước · ngữ cảnh 12% tới lúc tự tóm tắt · /resume mở hội thoại lúc 14:45 hôm qua
```

Ô nhập luôn nằm ở đáy, kể cả lúc Peto đang làm. Trong lúc Peto làm, ngay trên ô có dòng đang làm (`⠋ Đang nghĩ · 8s`,
lệnh đang chạy, việc hiện tại của danh sách việc). `Esc` hai lần hoặc `Ctrl+C` dừng yêu cầu đang chạy; `Ctrl+C` lúc ô
trống và Peto đang rảnh thì thoát `peto`. Câu hỏi quyền thay chỗ ô nhập cho tới khi bạn trả lời, chữ đang gõ dở vẫn còn.
Từ 0.22.0, lúc Peto làm, dưới ô nhập có một dãy 8 ô chạy qua lại kiểu Knight Rider như opencode (`■■■■⬝⬝⬝⬝`, màu hồng;
xanh ở chế độ Lập kế hoạch) cạnh dòng `esc esc hoặc ctrl+c dừng`, nghỉ một nhịp rồi chạy tiếp.

Khi hội thoại đã có tên (từ tin đầu, rồi tên Peto đặt), hàng trên cùng màn hình là thanh tên: tên hội thoại đậm bên trái,
thư mục mờ bên phải. Tên đó cũng nằm trên tab của terminal (`Peto · đang làm · Sửa lỗi checksum…`).

**Nhắn thêm giữa chừng** (từ 0.20.0, theo opencode). Gõ tin rồi Enter lúc Peto đang làm thì tin hiện `↳ Nhắn thêm: …`
trên ô nhập và được chèn vào bước kế tiếp, để chỉnh việc đang làm ("dùng tiếng Anh", "đừng đụng tệp test") mà không
phải dừng. Peto coi tin đó là điều chỉnh, trừ khi bạn bảo dừng hay đổi việc. Peto vừa viết xong mà bạn kịp nhắn thì
Peto làm thêm một bước để đọc. Lệnh gạch chéo (`/diff`…) gõ lúc Peto bận thì hiện `↳ Chờ chạy: …` và chạy sau khi xong.

**Chế độ Lập kế hoạch** (từ 0.20.0). `Shift+Tab` hoặc `/plan` đổi qua lại; ô nhập đổi sang màu xanh và ghi
"Lập kế hoạch". Peto chỉ tìm hiểu (đọc, tìm, xem trang) và bàn kế hoạch với bạn: sửa, tạo, xóa, đổi tên tệp và bấm, gõ
trên trang bị chặn ngay trên máy. Lệnh vẫn chạy được nhưng vẫn hỏi bạn như thường. Đổi chế độ giữa chừng thì áp dụng từ
bước kế tiếp.

**Lệnh nền tự báo khi xong** (từ 0.20.0). Lệnh chạy nền (dev server…) tự dừng thì Peto nhận tin ở bước kế tiếp, kèm
mã thoát và phần output chưa đọc, nên không phải đọc đi đọc lại chờ nó xong; màn hình hiện dòng
`· Lệnh nền #2 đã dừng · mã thoát 1`. Lúc Peto đang rảnh thì tin đó đi kèm yêu cầu kế tiếp, không tự gọi model.

**Câu hỏi có lựa chọn** (từ 0.21.0, theo opencode). Khi có một quyết định thật sự của bạn mà mã nguồn không trả lời
được (lưu dữ liệu ở đâu, giữ hay bỏ một tính năng), Peto hỏi bằng một khung thay chỗ ô nhập: tối đa 3 câu, mỗi câu 2–4
lựa chọn kèm mô tả, phương án Peto đề xuất đứng đầu với nhãn "(nên chọn)". ↑/↓ rồi Enter, hoặc phím số để chọn thẳng;
câu hỏi nhiều đáp án thì `Space` đánh dấu rồi Enter. Dòng cuối "✎ Tự trả lời…" mở ô gõ ngay trong khung. `Esc` là bỏ
qua: Peto tự chọn phương án hợp lý và nói rõ. Peto không dùng khung này để xin quyền sửa tệp hay chạy lệnh, vì CLI đã
hỏi những việc đó; khung dùng được cả trong chế độ Lập kế hoạch.

Hội thoại nằm trong màn hình của Peto chứ không trong lịch sử cuộn của terminal, nên Peto tự cuộn:

| Phím, chuột | Làm gì |
|---|---|
| Lăn chuột | Cuộn hội thoại 3 dòng mỗi nấc |
| `PgUp` / `PgDn` | Cuộn nửa màn hình |
| `Ctrl+Home` / `Ctrl+End` | Về đầu phiên / về cuối và bám theo chữ mới |
| Kéo chuột | Chọn chữ; thả tay là chép vào clipboard |
| Bấm đúp | Chọn và chép một từ (cả đường dẫn `src/app.py:42`) |
| `Ctrl+C` khi đang chọn chữ | Chép lại, không dừng Peto |
| `Shift` + kéo chuột | Chọn chữ kiểu terminal như cũ |
| `Ctrl+L` | Vẽ lại cả màn hình khi có gì vẽ đè lên |

**Bấm chuột** (từ 0.24.0, như opencode). Rê chuột qua chỗ bấm được thì nó sáng lên (gạch chân, hay sáng nền với khung
tin của bạn); terminal không đổi được hình con trỏ, nên đó là dấu hiệu bấm được. Bấm rồi thả tại chỗ mới tính là bấm;
kéo đi vẫn là chọn chữ.

| Bấm vào | Làm gì |
|---|---|
| Nút trong khung duyệt quyền (Cho phép, Cả yêu cầu này, Từ chối…) | Chọn nút đó; rê qua nút là nút đó được chọn |
| Dòng `+ Đã nghĩ` | Mở toàn văn suy nghĩ ngay dưới; bấm lần nữa thu lại (`/thinking` vẫn mở tất cả) |
| `↓ còn N dòng bên dưới` | Về cuối hội thoại |
| `→ Đã xem: 3 lần đọc…` | Hiện từng lần đọc, tìm trên một dòng; bấm lần nữa thu lại |
| `… còn N dòng · bấm để xem đủ` (diff), `(N dòng trước đó · bấm để xem đủ)` (output lệnh) | Hiện đủ; `▴ thu gọn` để thu lại |
| Tin của bạn | Menu Chép / Tách hội thoại từ đây; lúc Peto đang làm thì chỉ chép |
| Dòng trong bảng chọn (`/resume`, `/model`, `/timeline`, câu hỏi của Peto) | Chọn dòng đó; câu nhiều đáp án thì đánh dấu |
| `esc thôi`, `enter xong` ở chân khung; `c chép`, `esc đóng` của hộp `/btw` | Như bấm phím đó |
| Lệnh trong danh sách gợi ý khi gõ `/` | Chạy lệnh; lệnh còn cần gõ thêm (`/btw`, `/model`) thì điền vào ô |

Khung vừa hiện thì 0,3 giây đầu cú bấm không tính, như phím, để một cú bấm lỡ tay không trả lời thay bạn.

Đang cuộn lên thì chữ mới không kéo màn hình đi; hàng cuối khung hội thoại báo còn bao nhiêu dòng bên dưới. Gửi tin là về
cuối. Đổi cỡ cửa sổ thì Peto vẽ lại mọi thứ theo bề ngang mới. Ngoài VS Code, `Ctrl` + bấm vào đường dẫn ảnh chụp hay
địa chỉ web thì mở nó; VS Code tự mở link khi `Ctrl` + bấm. Terminal nào vẽ sót mảnh cũ thì đặt
`$env:PETO_AGENT_FULL_REPAINT = '1'` để Peto vẽ lại mọi hàng mỗi lần. `PETO_AGENT_UI=inline` giữ kiểu 0.17: ô nhập ở
đáy nhưng chữ in vào lịch sử cuộn của terminal (cửa sổ hẹp lại có thể để sót một mảnh khung cũ).

Gõ yêu cầu trong ô có thanh `┃` hồng. Trong ô là model và mức suy nghĩ đang dùng; dưới ô là số bước còn lại hôm nay
(cập nhật sau mỗi bước), hội thoại đã tới đâu so với lúc Peto tự tóm tắt phần cũ (để biết khi nào nên `/compact`) và lời
nhắc `/resume` khi thư mục có hội thoại cũ. Gửi xong, tin của bạn nằm lại thành một khung nền nhạt. Tên tài khoản xem
bằng `peto status`, các phím tắt và lệnh xem bằng `/help`. Khi nhập nhiều dòng, ô tự giãn theo nội dung; tin quá dài
được cuộn quanh vị trí con trỏ.

Lời Peto thụt vào, tự xuống dòng theo bề ngang, có danh sách, bảng kẻ khung và khối code tô màu. Mỗi công cụ là một
dòng mờ (`→ Đọc app.py:1-40`, `✱ Tìm "checksum" 3 kết quả`); các lần đọc, tìm liền nhau gộp thành
`→ Đã xem: 2 lần đọc, 1 lần tìm` kèm danh sách tệp. Sửa tệp là một khối có diff, chạy lệnh là một khối có phần cuối
output và kết quả. Suy nghĩ của model chỉ hiện một dòng `+ Đã nghĩ: … · 3,2s`; `/thinking` bật hiện cả phần tóm tắt suy
nghĩ. Mỗi yêu cầu kết thúc bằng một dòng như
`▣ Peto · 6 Luna · 12 giây · sửa 2 tệp · chạy 1 lệnh · 15k token · 8% tới lúc tự tóm tắt`; thời gian từng phần và token
chi tiết xem bằng `/usage`, và vẫn ghi đủ trong nhật ký. `PETO_AGENT_THEME=light` dùng màu cho terminal nền sáng;
`PETO_AGENT_UI=classic` quay về giao diện chữ trước 0.16.0.

Gõ `/` thì danh sách lệnh hiện ngay trên ô nhập và lọc dần theo chữ bạn gõ:

```text
  ┃ /resume    Mở lại một hội thoại đã lưu của thư mục này      (dòng đang chọn tô nền hồng)
  ┃ /retry     Thử lại bước bị gián đoạn kết nối
  ┃ /remember  Ghi một điều Peto cần nhớ về dự án vào AGENTS.md
  ┃
  ┃  /re
```

Mũi tên lên/xuống chọn lệnh, Tab điền lệnh, Enter chạy lệnh đang chọn, Esc ẩn danh sách. Mới gõ mỗi `/` thì chưa có lệnh
nào được chọn, nên Enter không tự chạy gì. Từ 0.20.0 tên lệnh là tiếng Anh (chủ web chọn cho quen tay); tên cũ
`/moi`, `/thoat`, `/nho`, `/trinhduyet`, `/suynghi` vẫn gõ được, và gõ tên cũ thì danh sách gợi ý tên mới. Các lệnh:

- `/new`: bắt đầu hội thoại mới; màn hình xóa hội thoại cũ, chỉ để lại đầu phiên. Hội thoại cũ vẫn mở lại được bằng
  `/resume`.
- `/resume`: mở lại một hội thoại đã lưu của thư mục này, kể cả sau khi đã thoát. Từ 0.20.0 mỗi thư mục giữ nhiều hội
  thoại có tên (tối đa 50, 30 ngày); `/resume 2` mở thẳng cái thứ hai. Từ 0.22.0 (theo opencode) có từ hai hội thoại
  thì hiện bảng hội thoại: gõ chữ để tìm theo tên (không phân biệt dấu), nhóm "Hôm nay", "Hôm qua" rồi theo ngày, ↑/↓
  và Enter để mở, `Ctrl+R` đổi tên ngay trên dòng (Enter lưu, Esc thôi), `Ctrl+D` bấm hai lần để xóa (không xóa được
  hội thoại đang mở). Mở ra thì màn hình vẽ lại cả hội thoại như lúc đang làm: tin của bạn, lời Peto, các lần đọc,
  khối sửa tệp có diff, khối lệnh có output và danh sách việc; trước 0.22.0 chỉ in mờ tin cuối. Suy nghĩ của model và
  ảnh chụp trang không được lưu nên không có, và diff của một lần sửa chỉ là đoạn bị thay, không số dòng. Từ 0.21.0,
  sau yêu cầu đầu tiên của mỗi hội thoại Peto tự đặt một
  tên ngắn ở nền (tốn 1 bước Peto mức thấp, dù đang chọn model nào); máy chủ cũ hay khi lỗi thì tên lấy từ tin đầu
  tiên. Không lệnh nào được chạy lại, và muốn
  sửa tệp thì Peto phải đọc lại tệp trước. Mở `peto` ở thư mục có hội thoại cũ sẽ có dòng nhắc. Hội thoại được lưu
  sau từng bước, nên lỡ đóng cửa sổ hay tắt máy khi Peto đang làm thì lần mở sau dòng nhắc thành
  `/resume làm tiếp yêu cầu bị ngắt …`. Mở lại sẽ thấy danh sách việc còn dở; gõ "làm tiếp" để Peto làm nốt. Công cụ
  đang chạy dở lúc đóng được ghi là bị ngắt, nên Peto kiểm tra lại tệp trước khi làm tiếp.
- `/timeline` (từ 0.22.0, theo opencode): danh sách các tin bạn đã gửi trong hội thoại đang mở. Chọn một tin rồi
  "Nhảy tới" (cuộn màn hình tới đúng tin đó), "Chép" (chép chữ của tin vào clipboard) hoặc "Tách hội thoại từ đây".
  Từ 0.26.0 còn có "Khôi phục tệp về lúc trước tin này" (xem "Ảnh chụp dự án" bên dưới).
- `/fork` (từ 0.22.0): chọn một tin của bạn để tách. Peto mở một hội thoại mới gồm mọi thứ trước tin đó, tên
  "<tên cũ> (nhánh)", và đặt sẵn chữ của tin vào ô nhập để bạn sửa rồi gửi lại. Hội thoại cũ giữ nguyên trong
  `/resume`. Tách chỉ đổi hội thoại; từ 0.26.0, nếu có ảnh chụp của tin đó, Peto hỏi thêm có khôi phục cả tệp về lúc
  đó không (mặc định là không).
- `/btw <câu hỏi>` (từ 0.23.0, theo opencode và Claude Code): hỏi nhanh bên lề về hội thoại, kể cả lúc Peto đang làm,
  mà không chen vào việc đang làm. Trong lúc chờ, trên ô nhập có dòng `⠋ /btw …`; có câu trả lời thì nó hiện trong một
  hộp ở chỗ ô nhập: ↑/↓, `PgUp`/`PgDn` cuộn, `c` chép, `Esc` hay Enter đóng (`Ctrl+C` trong hộp cũng chỉ đóng hộp, không
  dừng Peto). Câu hỏi và câu trả lời không vào hội thoại hay tệp lưu, nên Peto không "nhớ" chúng ở bước sau. Peto trả
  lời từ những gì đã có trong hội thoại, không đọc tệp hay chạy lệnh. Mỗi câu tốn một bước của model đang dùng ở mức
  suy nghĩ thấp. Cần máy chủ Peto đã cập nhật; máy chủ cũ thì `peto` báo "Máy chủ chưa hỗ trợ /btw".
- `/editor [chữ]` (từ 0.23.0): soạn yêu cầu dài trong trình soạn của bạn. Peto lấy trình soạn từ biến `VISUAL` rồi
  `EDITOR` (như git, ví dụ `$env:EDITOR = 'code --wait'`); không đặt thì dùng VS Code khi đang ở terminal của nó, không
  thì Notepad. Trong lúc soạn, Peto nhường cả cửa sổ terminal (trình soạn chạy trong terminal như vim cũng dùng được);
  lưu rồi đóng tệp là quay lại, chữ nằm sẵn trong ô nhập để xem lại, Enter mới gửi. Tệp trống hay không đổi gì thì ô
  nhập để nguyên.
- `/export` (từ 0.23.0): xuất hội thoại đang mở ra Markdown, lưu thành `peto-<tên>-<ngày>.md` ở gốc dự án (không ghi đè
  tệp có sẵn, thêm `-2`, `-3`…) hoặc chép vào clipboard. Tệp có tin của bạn, lời Peto, mỗi công cụ một dòng
  ("Sửa `app.py` (+1 −1)", "Chạy `$ npm test` → mã thoát 0") và danh sách việc; không có nội dung tệp, output lệnh hay
  ảnh, nên gửi cho người khác được.
- `/guide` (từ 0.25.0): sửa hướng dẫn cho Peto trong trình soạn của `/editor`. Chọn "Hướng dẫn chung" (một tệp
  AGENTS.md trong hồ sơ của bạn, `%APPDATA%\PetoAgent\AGENTS.md`, đi kèm mọi bước ở mọi dự án: cách xưng hô, trình quản
  lý gói, quy ước commit…) hoặc "AGENTS.md của dự án này". Về quy ước code thì AGENTS.md của dự án được ưu tiên; yêu
  cầu trong hội thoại đứng trên cả hai. Ghi ngay trên máy, không tốn bước và không vào `/undo`. Peto không bao giờ đọc
  hướng dẫn chung từ thư mục dự án. Cần máy chủ đã cập nhật; máy chủ cũ thì tệp vẫn lưu, Peto dùng khi máy chủ có.
- `/retry`: thử lại bước bị gián đoạn kết nối, dùng kết quả các bước đã hoàn tất. Không tự phát lại lệnh hay thao tác
  sửa tệp cũ; thao tác mới vẫn hỏi quyền. Nếu đã thoát thì `/resume` trước, rồi `/retry`.
- `/diff`: xem bản sửa/ghi tệp gần nhất đã lưu cho dự án; từ 0.26.0 có cả tệp do lệnh Peto chạy đổi (ghi "do lệnh";
  tệp nhị phân chỉ ghi cỡ). Diff dài có thể xem tiếp bằng `v`.
- `/undo`: xem diff rồi xác nhận hoàn tác yêu cầu gần nhất; giữ nguyên BOM và kiểu xuống dòng ban đầu, xóa các tệp
  mới do công cụ ghi tạo ra. Nếu bất kỳ tệp nào đã bị sửa/xóa bên ngoài, từ chối trước khi hoàn tác. Bản lưu nằm ở
  `%LOCALAPPDATA%\PetoAgent\checkpoints`, mở lại CLI tại đúng dự án rồi dùng `/diff` hoặc `/undo`, không cần `/resume`.
  Từ 0.26.0 `/undo` hoàn tác cả tệp do lệnh tạo, sửa hay xóa (xem "Ảnh chụp dự án").
  `/new`, `/resume` và yêu cầu chỉ đọc không xóa bản này; yêu cầu mới có sửa tệp sẽ thay thế bằng bản của yêu cầu mới.
  Mỗi dự án giữ một bản, tối đa 16 MB/bản (tính cả mã hóa), tổng 64 MB, dọn bản cũ nhất khi vượt dung lượng và hết hạn
  sau 30 ngày. Bản đã hoàn tác được lưu trạng thái rỗng để không khôi phục lần nữa. `/retry` tiếp tục cùng bản.
  Checkpoint chứa nội dung trước/sau của tệp, chỉ nằm trên máy, không gửi lên VPS. Nếu lưu checkpoint lỗi hoặc vượt
  giới hạn, thao tác ghi mới bị chặn. Đây không thay thế Git/backup và không bảo đảm giao dịch nhiều tệp khi mất điện.
  Xóa và đổi tên do Peto làm bằng công cụ thì thuộc bản hoàn tác; thay đổi do lệnh terminal thì không. Nếu lỗi ổ đĩa
  xảy ra giữa chừng, những tệp chưa khôi phục vẫn được giữ trong bản nhớ để kiểm tra lại; không có giao dịch nguyên
  khối nhiều tệp.
- `/permissions`: xem lệnh, trang (được bấm, gõ) và tên miền ngoài (được xem) đã nhớ trong phiên (`s`) và luôn cho
  phép ở dự án này (`l`); `/permissions clear` thu hồi hết. Lệnh nhớ trong phiên mất khi `/new` hoặc `/resume`; lệnh luôn cho phép thì còn tới
  khi bạn xóa.
- `/browser`: hiện hoặc ẩn cửa sổ trình duyệt của Peto, để xem Peto bấm, gõ trên trang (xem "Bấm, gõ trên trang"
  bên dưới). `/browser clear`: quên đăng nhập, cookie và dữ liệu trang mà trình duyệt của Peto lưu cho dự án này.
- `/init`: Peto xem qua dự án (cấu trúc thư mục được gửi sẵn trong yêu cầu, khỏi tốn một bước), đọc README cùng các tệp
  cấu hình rồi viết `AGENTS.md` ở gốc dự án. Đây là một yêu cầu bình thường nên tốn vài bước, và bản ghi tệp vẫn hiện
  diff để bạn đồng ý. Dự án đã có `AGENTS.md` thì Peto đọc trước và chỉ sửa chỗ sai hoặc thiếu.
- `/plan`: bật hoặc tắt chế độ Lập kế hoạch (cũng là `Shift+Tab`), xem ở trên.
- `/remember <ghi chú>`: ghi một điều Peto cần nhớ về dự án vào mục `## Ghi nhớ` của `AGENTS.md` ở gốc (chưa có mục
  hay chưa có tệp thì tạo), ví dụ `/remember chạy test bằng python -m pytest`. Ghi ngay trên máy, không gọi model nên không tốn
  bước nào; Peto đọc `AGENTS.md` ở mọi bước nên nhớ từ yêu cầu tiếp theo. Dòng này không nằm trong bản `/undo`: muốn bỏ
  thì sửa `AGENTS.md`.
- `/compact`: tóm tắt phần hội thoại cũ, giữ các bước gần nhất và yêu cầu gần nhất nằm trong phần được tóm tắt.
  Peto cũng tự tóm tắt giữa các bước khi lịch sử đạt 180 mục hoặc khoảng 200.000 ký tự chữ. Tóm tắt dùng một lượt
  gọi model ở mức suy nghĩ thấp, vẫn tính bước theo model và token như bình thường. Cần cập nhật cả VPS và CLI.
  Không chạy công cụ khi tóm tắt, không tách cặp gọi công cụ/kết quả. Lỗi, hủy hoặc máy chủ cũ thì giữ nguyên lịch sử.
  Tóm tắt có thể bỏ sót chi tiết; tệp phải được đọc lại trước khi sửa và ảnh cũ trong phần tóm tắt được thay bằng ghi chú.
- `/effort low`, `/effort medium`, `/effort high`: mức suy nghĩ, được nhớ trên máy này cho lần sau (`thap`, `vua`,
  `cao` vẫn nhận). Mức cao suy nghĩ kỹ
  hơn nhưng mỗi bước tính 2 bước. Gõ `/effort` để xem mức đang dùng; chưa chọn thì theo mặc định của máy chủ. Gõ
  `/effort` kèm dấu cách thì chọn mức trong danh sách.
  Từ bản 0.12.1 (cần cập nhật cả VPS), model OpenAI còn nhận `/effort none`, `/effort xhigh`, `/effort max`;
  `none` không suy luận, `xhigh` rất cao, `max` tối đa.
  Các mức high/xhigh/max nhân đôi số bước của model; mức cao hơn có thể chờ lâu và dùng nhiều token hơn.
  Danh sách chỉ hiện mức model hỗ trợ. Khi đổi model không hỗ trợ mức đang dùng, CLI chuyển về vừa và thông báo.
- `/model peto`, `/model luna`: đổi model, được nhớ trên máy này cho lần sau. Peto là mặc định; 6 Luna (của OpenAI)
  dùng được với tài khoản Discord/Google. Chủ web còn chọn được `/model terra` (5.6 Terra) và `/model sol`. Gõ `/model` để xem model
  đang dùng và các model tài khoản của bạn được chọn; gõ `/model` kèm dấu cách thì chọn trong danh sách. Model đắt hơn
  tính nhiều bước hơn: Terra 2, Sol 4, nhân với mức suy nghĩ. Đổi model giữa hội thoại vẫn làm tiếp được; phần suy nghĩ
  của model cũ được bỏ vì model mới không đọc được.
- Từ bản **0.14.2**, có `/model haiku` (Haiku 5.5 cho tài khoản đã đăng nhập) và `/model sonnet` (Sonnet 5.5 chỉ
  chủ web). Cần máy chủ có `ANTHROPIC_API_KEY`; CLI không cần khóa Claude. Cả hai nhận `low`, `medium`, `high`,
  `xhigh`, `max`; không nhận `none`. Haiku tính 1 bước, Sonnet 2 bước trước khi nhân mức suy nghĩ; `high/xhigh/max`
  nhân đôi. Danh sách model và effort vẫn lấy từ máy chủ. Cập nhật CLI để giữ nguyên block suy nghĩ có chữ ký và
  nhóm công cụ của Claude khi tóm tắt, và mở lại hội thoại có tìm web bằng `/resume`.
- `/usage`: số bước còn lại và số token đã dùng hôm nay, độ dài hội thoại đang mở, model và mức suy nghĩ.
- `/update` (từ 0.22.0): cập nhật lên bản mới nhất của máy chủ rồi mở lại đúng hội thoại, xem "Cập nhật" ở trên.
- `/thinking`: bật hoặc tắt hiện toàn văn suy nghĩ của Peto dưới dòng `+ Đã nghĩ` (không phải model nào cũng gửi).
- `/help`: xem các lệnh. `/exit`: thoát. Tên lệnh gõ có dấu (`/thoát`) vẫn được nhận.
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

Trong lúc chờ, một dòng tạm `⠋ Đang nghĩ · 8s` tự đếm giây rồi biến mất khi có chữ. Câu dài đang viết hiện dần trên
dòng tạm; ở màn hình toàn phần câu trả lời hiện dần ngay trong hội thoại. Không cần cài thêm thư viện. `NO_COLOR`
tắt màu; khi output chuyển sang tệp hoặc ống dẫn, Peto dùng giao diện chữ thường, không có mã điều khiển hay dòng trạng
thái vẽ lại.

Mỗi lần Peto muốn sửa hay tạo tệp, một khung "Cần bạn duyệt" hiện ở cuối màn hình với diff có cột số dòng, nền xanh cho
dòng thêm, đỏ cho dòng xóa; terminal rộng hơn 120 cột thì diff chia hai cột cũ và mới. Chọn bằng `←`/`→` rồi `Enter`
(`Esc` là từ chối), hoặc gõ thẳng chữ của lựa chọn (`y`, `a`, `s`, `l`, `n`). Phím gõ trước khi khung hiện không được
tính. Diff dài hơn màn hình thì `v` hoặc `PgDn` xem tiếp, không cấp quyền sửa tệp. Trả lời xong khung biến mất; tệp đã
sửa hiện thành một khối có diff, bị từ chối thì một dòng `✗ Không sửa …`.
Mỗi lần muốn chạy lệnh, CLI hiện nguyên lệnh, thư mục và giới hạn thời gian. Khi chạy có bộ đếm thời gian và dòng output
mới nhất (ở terminal đủ rộng); khi xong hiện tối đa 8 dòng output cuối cùng cùng kết quả hoặc mã lỗi. Bạn trả lời:

- `y`: đồng ý bước này.
- `n`: không đồng ý. Peto được báo lại để hỏi bạn cách khác.
- `a`: đồng ý mọi bước còn lại trong yêu cầu đang chạy.
- `s` (chỉ khi chạy lệnh): đồng ý và ghi nhớ **đúng chuỗi lệnh, thư mục, thời hạn** trong phiên. Không phải quyền theo
  tiền tố: `npm test` không cấp quyền cho `npm test && ...` hay lệnh có tham số khác. Script mà lệnh gọi vẫn có thể
  thay đổi theo nội dung dự án; chỉ ghi nhớ lệnh bạn tin tưởng.
- `l` (chỉ khi chạy lệnh): luôn cho phép **đúng chuỗi lệnh đó, ở đúng thư mục chạy và shell đó, trong dự án này**, kể cả
  ở các phiên sau. Lần sau lệnh chạy luôn và CLI in một dòng mờ báo đã được cho phép. Thời hạn không tính vào, vì nó chỉ
  là mức trần và Ctrl+C vẫn dừng được lệnh. Quyền lưu trong `%APPDATA%\PetoAgent\permissions.json` trên máy bạn, **không
  bao giờ đọc từ thư mục dự án**, để một repo tải về không thể kèm sẵn tệp cấp quyền. Xem và xóa bằng `/permissions`.

### Tìm web

Khi câu trả lời nằm ngoài dự án (tài liệu thư viện, thông báo lỗi lạ, API hay phiên bản mới), Peto tự tra web. Việc tìm
chạy ở phía dịch vụ AI, không mở gì trên máy bạn; trong CLI nó hiện thành một dòng `• Tìm trên web` trong bước đó.
Peto được nhắc chỉ đưa từ khóa cần thiết vào truy vấn, không đưa nội dung tệp hay đường dẫn trên máy bạn, và coi nội
dung trang web là dữ liệu chứ không phải lệnh. Mỗi lượt tìm tính phí vào tài khoản dịch vụ AI của chủ web, nên chủ web
tắt được bằng `PETO_AGENT_WEB_SEARCH=false`; khi tắt, Peto được yêu cầu nói rõ là mình không tra cứu được.

### Xem trang web trên máy

Từ bản 0.10.0 (cần cả VPS mới), Peto tự mở trang web đang chạy trên máy bạn để kiểm tra sau khi sửa giao diện, thay vì
đoán. Ví dụ bạn nhờ "nút Gửi bị tràn trên điện thoại": Peto sửa CSS, chạy dev server nền, mở trang ở cỡ điện thoại,
chụp ảnh xem còn tràn không, rồi mới báo xong.

```text
  • Xem trang http://localhost:5173/ · máy tính 1280×800
    Tải xong 0,8 giây · "Peto" · 3 lỗi
    ✗ console.error: Không tải được cấu hình: thiếu API_URL
    ✗ ReferenceError: hamKhongTonTai is not defined (src/main.tsx:12)
    ✗ 404 /khong-co-anh.png
  • Chụp trang · điện thoại 390×844
    ảnh: C:\Users\ban\AppData\Local\PetoAgent\screenshots\web_test-0923-180711-1.png
```

- **Peto thấy gì:** tiêu đề, mã HTTP, lỗi console, lỗi JavaScript, request hỏng (404, 500, mất kết nối), các nút, ô
  nhập, liên kết và ảnh thiếu `alt` đang hiện; chữ trên trang khi cần; và ảnh chụp cỡ máy tính (1280×800), cỡ điện thoại
  (390×844) hoặc cả trang dài (tối đa 4000px). Dưới mỗi lần xem, terminal in tối đa 5 lỗi; Peto nhận đủ.
- **Ảnh chụp** được lưu ở `%LOCALAPPDATA%\PetoAgent\screenshots\` 7 ngày để bạn xem đúng thứ Peto đã thấy; trong
  terminal VS Code, Ctrl+Click đường dẫn để mở. Mỗi lần xem là một bước, và ảnh tốn token hơn chữ, nên Peto chỉ chụp
  khi cần nhìn bố cục.
- **Chỉ trang trên máy:** `localhost`, `127.0.0.1`, `::1`. Trang ngoài, `file://`, và trang chuyển hướng ra ngoài đều
  bị từ chối, để Peto không thể mở một địa chỉ mang theo nội dung tệp của bạn, và trang lạ không nhét được chỉ dẫn vào.
  Xem trang trên máy không hỏi quyền, như đọc tệp.
- **Hộp thoại của trang** (`alert`, `confirm`, `prompt`) được Peto tự trả lời ngay rồi báo ở dòng chi tiết mờ, không
  tính là lỗi: `alert` thì đóng, `confirm` và `prompt` thì chọn Hủy, để Peto không thay bạn đồng ý một việc có thể đổi
  dữ liệu. Trước 0.10.1, trang gọi `alert()` làm Peto chờ gần một phút rồi báo lỗi, và trình duyệt kẹt tới hết phiên.
  Trang treo hẳn (JavaScript chạy mãi) thì sau 30 giây Peto đóng trình duyệt, lần xem sau mở trình duyệt mới.
- **Trình duyệt:** Microsoft Edge có sẵn trong Windows (không có thì Chrome), chạy ẩn, không có cửa sổ nào bật lên trừ
  khi bạn gõ `/browser` hay Peto nhờ bạn đăng nhập. Nó dùng một hồ sơ riêng tên "Peto" cho từng dự án, không có tài
  khoản, cookie hay tiện ích nào của Edge bạn đang dùng. Đóng peto, kể cả bấm X đóng cửa sổ terminal, là trình duyệt
  tắt theo. Muốn dùng trình duyệt khác thì đặt `PETO_AGENT_BROWSER` là đường dẫn tới tệp chạy của nó.
- Ảnh và chữ trên trang đi qua máy chủ Peto tới dịch vụ AI như nội dung tệp.

### Bấm, gõ trên trang

Từ bản 0.11.0 (cần cả VPS mới), Peto thử trang như người dùng: bấm nút, mở menu, điền và gửi form, đi hết một luồng rồi
báo chỗ hỏng. Lần đầu Peto thao tác trên một trang, bạn được hỏi:

```text
  ▶ Muốn bấm và gõ trên http://localhost:5173
    Trước tiên: bấm nút "Đặt vé (ảo)"
    Đây là thao tác thật trên app đang chạy: có thể gửi form, xóa dữ liệu hay gọi dịch vụ thật như bạn bấm.
    [s] cả phiên  [l] luôn cho phép ở dự án này · Đồng ý cho trang này tới hết yêu cầu? [y] có  [n] không  [a] …
    Chọn › y
  • Bấm nút "Đặt vé (ảo)"
    Hiện thêm: "Chọn số vé" · không lỗi
  • Gõ "2" vào ô "Số vé"
  • Bấm nút "Xác nhận"
    Hiện thêm: "Đã đặt 2 vé! Mã MEO-042" · 1 lỗi
    ✗ console.error: Không lưu được vé
```

- **Hỏi một lần cho mỗi trang** (mỗi địa chỉ và cổng, ví dụ `localhost:5173`): `y` cho tới hết yêu cầu này, `s` cả
  phiên, `l` luôn cho phép trang đó trong dự án này (lưu cùng chỗ với lệnh luôn cho phép, không bao giờ trong thư mục
  dự án), `a` đồng ý mọi bước còn lại của yêu cầu. Thao tác là thật: nếu app đang nối dịch vụ thật (gọi AI, gửi mail,
  thanh toán thử), bấm Gửi là gọi thật. Mở, chụp, đọc trang vẫn không hỏi.
- **Bấm, gõ như người thật:** chuột và bàn phím thật (trang thấy như bạn bấm), gõ tiếng Việt đúng dấu. Nút bị một lớp
  khác che thì Peto báo "bị … che" thay vì bấm xuyên qua, vì bạn cũng không bấm được. Mỗi thao tác in một dòng, kèm chữ
  mới hiện, trang chuyển tới đâu và lỗi mới.
- **Không ra khỏi máy:** link, form, chuyển hướng hay JavaScript đưa trang ra ngoài đều bị chặn trước khi request rời
  máy; trang giữ nguyên. Liên kết mở tab mới được mở ngay trong tab đang xem; tab, cửa sổ mới khác bị đóng. Peto không
  tải tệp lên hay tải tệp về.
- **Mật khẩu:** Peto không bao giờ gõ vào ô mật khẩu và không đọc chữ trong đó. Trang cần đăng nhập thì Peto hiện cửa sổ
  ở trang đó và nhờ bạn tự đăng nhập, rồi bấm Enter trong terminal (gõ `n` để bỏ qua). Đăng nhập bằng Discord hay Google
  cũng được, vì lúc đó Peto tạm thôi chặn trang ngoài.
- **Đăng nhập được nhớ cho dự án:** hồ sơ trình duyệt của Peto nằm ở `%LOCALAPPDATA%\PetoAgent\browser\`, mỗi dự án
  một thư mục, nên phiên sau không phải đăng nhập lại (trừ trang dùng cookie hết hạn khi đóng trình duyệt).
  `/browser clear` để quên; dự án 30 ngày không dùng thì tự dọn. Hai phiên peto cùng mở một dự án thì phiên sau dùng hồ
  sơ tạm, không có đăng nhập.
- **Cửa sổ:** vẫn chạy ẩn. `/browser` hiện cửa sổ để xem Peto bấm, gõ; gõ lần nữa để ẩn. Hiện hay ẩn là mở lại
  trình duyệt nên trang tải lại từ đầu, đăng nhập vẫn giữ. Cửa sổ mở lên sẽ giành con trỏ, như mọi cửa sổ mới.
- **Tiết kiệm bước:** chuỗi thao tác đoán trước được (gõ các ô, bấm Gửi, chụp) Peto gọi chung một bước; một thao tác
  lỗi thì các thao tác sau trong bước đó bị bỏ qua. Có lệnh nền đang chạy (dev server vừa bật) thì `browser_open` chờ
  server lên tối đa 15 giây, nên chạy dev server rồi mở trang chỉ tốn một bước.

### Xem trang ngoài

Từ bản 0.12.0 (cần cả VPS mới), Peto xem được cả trang ngoài máy khi bạn đưa địa chỉ, nhờ xem trang đã deploy hay nhờ
đọc một trang cụ thể. Tra cứu chung vẫn dùng tìm web, rẻ hơn và không mở gì trên máy.

```text
  ▶ Muốn mở trang ngoài
    https://docs.python.org/3/library/asyncio.html
    Trình duyệt riêng, không cookie hay đăng nhập nào; Peto chỉ xem.
    [s] docs.python.org cả phiên  [l] luôn cho phép ở dự án này · Đồng ý cho docs.python.org tới hết yêu cầu? …
    Chọn › y
  • Xem trang https://docs.python.org/3/library/asyncio.html · máy tính 1280×800
    Tải xong 1,1 giây · "asyncio — Asynchronous I/O" · không lỗi
```

- **Hỏi mỗi tên miền:** `y` tới hết yêu cầu, `s` cả phiên, `l` luôn trong dự án này. Cho `python.org` là gồm cả
  `www.python.org` và `docs.python.org`. Địa chỉ dài bất thường (phần sau tên miền quá 200 ký tự) thì luôn hỏi lại
  đúng địa chỉ đó, vì nó có thể đang mang dữ liệu của bạn tới trang đó.
- **Chỉ xem:** mở, chụp, đọc chữ. Danh sách phần tử ghi địa chỉ của từng link để Peto mở tiếp trang khác; Peto không
  bấm, gõ hay đăng nhập trên trang ngoài. Trang cần đăng nhập thì Peto chỉ thấy trang đăng nhập.
- **Trình duyệt riêng:** trang ngoài mở trong một trình duyệt khác hẳn trình duyệt của dự án, hồ sơ tạm không cookie
  hay đăng nhập nào, xóa khi đóng peto. Nên dù bạn từng đăng nhập Discord hay Google trong cửa sổ Peto, trang ngoài
  không thấy những đăng nhập đó.
- **Không vào mạng nhà:** địa chỉ router, máy khác trong nhà (`192.168.x.x`, `10.x`, tên như `nas.local`) bị từ chối, và
  trang ngoài không được chuyển về máy bạn.

### Việc dài, lệnh nền và chuông báo

- **Danh sách việc:** yêu cầu từ ba việc trở lên thì Peto liệt kê các việc định làm và cập nhật khi xong từng mục, hiện
  ngay trong terminal: `☑` đã xong, `▶` đang làm, `☐` chưa làm. Còn mục chưa xong thì dòng tóm tắt cuối yêu cầu nói rõ
  còn bao nhiêu, để không ai tưởng đã xong hết. Với 6 Luna, 5.6 Terra và 6 Sol thì không có danh sách này (từ
  2026-10-14): các model GPT dành gần một phần ba số bước chỉ để cập nhật nó, nên câu trả lời cuối thay cho nó.
- **Lệnh nền:** lệnh không tự kết thúc (dev server, `--watch`) được chạy nền và trả về ngay, thay vì chờ tới khi xong.
  Bạn vẫn duyệt trước khi chạy, và ô hỏi nói rõ lệnh sẽ sống tiếp sau khi yêu cầu xong. Tối đa 3 lệnh nền một lúc;
  Peto đọc output khi cần và tự dừng khi xong việc. **Đóng peto là mọi lệnh nền bị dừng**, cả cây tiến trình.
- **Chuông và tiêu đề cửa sổ:** terminal kêu một tiếng khi Peto cần bạn duyệt và khi một yêu cầu chạy quá 10 giây vừa
  xong; tiêu đề cửa sổ đổi theo trạng thái (`Peto · đang làm · tên-thư-mục`, `· cần bạn duyệt`, `· xong`) nên liếc
  thanh tác vụ là biết. Đặt `PETO_AGENT_NO_BELL=1` để tắt tiếng chuông, tiêu đề vẫn đổi.

### Agent con khám phá (từ 0.27.0)

Theo agent "explore" của opencode: khi cần dò rộng nhiều tệp mà chỉ cần kết luận (tìm nơi xử lý một việc, liệt kê chỗ
gọi một hàm, nắm một phần dự án lạ), Peto giao việc cho một agent con bằng `explore`. Agent con có hội thoại riêng, chỉ
tìm và đọc (`list_files`, `find_files`, `search_files`, `read_file`), không sửa, không chạy lệnh, rồi chỉ trả kết luận
về hội thoại chính, nên hội thoại chính gọn hơn và ít phải tự tóm tắt.

- Chạy cùng model đang dùng, ở mức suy nghĩ thấp (chủ web chọn). Mỗi bước của agent con trừ hạn mức như một bước
  thường; Peto chọn độ kỹ quick (tối đa 4 bước), medium (8) hay thorough (15). Bước cuối không có công cụ để luôn có câu
  trả lời.
- Màn hình hiện "Khám phá · Đọc app.py…" ở dòng trạng thái trong lúc chạy, rồi một dòng "◇ Khám phá … · 3 bước · đọc 2
  tệp"; bấm vào để xem từng việc agent con làm và kết luận nó trả về.
- Agent con đọc không tính là Peto đã đọc: muốn sửa tệp nào Peto vẫn phải tự đọc trước. Ctrl+C dừng cả agent con lẫn yêu
  cầu. Không có agent con lồng nhau. Cần máy chủ đã cập nhật.

### Ảnh chụp dự án (từ 0.26.0)

Theo opencode: trước và sau mỗi lệnh Peto chạy (`run_command`), CLI chụp lại cả dự án vào một kho git ẩn riêng ở
`%LOCALAPPDATA%\PetoAgent\snapshots\`, so hai ảnh để biết lệnh đã tạo, sửa hay xóa tệp nào. Những thay đổi đó vào bản
hoàn tác như lần Peto tự sửa, nên `/diff` thấy và `/undo` trả lại được (`dotnet ef migrations add`, `copy`, `del`…). Kết
quả lệnh ghi "đổi N tệp", Peto được báo tên các tệp đó, và dòng cuối yêu cầu thêm "lệnh đổi N tệp". Ảnh lúc bắt đầu
mỗi yêu cầu được nhớ theo tin của bạn, nên bấm vào một tin (hay `/timeline`) rồi chọn "Khôi phục tệp về lúc trước tin
này" đưa tệp về đúng lúc đó; danh sách tệp sẽ đổi hiện trước để bạn duyệt, và `/undo` ngay sau đó trả lại như trước.

- Cần máy có git; không có thì như trước 0.26.0 và CLI báo một lần. Thư mục chưa phải kho git vẫn chụp được. CLI không
  bao giờ đụng `.git` của dự án hay checkout vào thư mục dự án: khôi phục là CLI tự ghi từng tệp.
- Không chụp: những gì `.gitignore` bỏ qua, `node_modules`, `.venv`, `dist`, `build`…, `.env`, khóa, tệp trên 2 MB và
  symlink. Những tệp đó không được khôi phục.
- Lệnh nền (`start_command`), cơ sở dữ liệu (`dotnet ef database update`) và gói đã cài vào hệ thống không nằm trong
  `/undo`.
- Lần chụp đầu ở một dự án băm cả dự án, chạy nền trong lúc chờ model (Peto-Web, khoảng 950 tệp: 7–10 giây); các lần
  sau dưới nửa giây. Lần sửa tệp hay chạy lệnh đầu tiên của yêu cầu đợi ảnh đầu yêu cầu chụp xong.
- Một lệnh đổi hơn 200 tệp hay hơn 12 MB thì không đưa vào `/undo` (CLI báo). Kho dọn mỗi ngày một lần: ảnh quá 30 ngày
  bị bỏ, kho của dự án không dùng 30 ngày bị xóa.

### Hướng dẫn dự án và kiểm tra sau sửa

Một yêu cầu chạy tối đa 40 bước. Từ 0.25.0 (theo opencode), chạm mức đó thì Peto dùng thêm một bước không có công cụ để
tóm tắt: đã làm được gì, còn gì dở, nên làm gì tiếp; rồi bạn gõ "làm tiếp" nếu muốn. Máy chủ cũ thì chỉ có lời nhắc.

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
số bước còn lại hôm nay. Có thể dùng `/compact` để giảm ngữ cảnh hoặc `/new` để bắt đầu việc khác.
Nhật ký từng phiên lưu ở `%LOCALAPPDATA%\PetoAgent\logs\`: yêu cầu bạn gõ, từng lời Peto trả lời (mỗi lời giữ tối đa
4000 ký tự, cả phần đầu lẫn phần cuối), các lệnh gọi công cụ và dòng tổng kết. Nhờ vậy xem lại được cả những lần cũ;
tệp hội thoại cho `/resume` thì mỗi dự án chỉ giữ lần gần nhất. Nhật ký chỉ nằm trên máy bạn.

### Giảm nội dung gửi cho model

Từ 0.25.0 (khi máy chủ đã cập nhật), `read_file` đọc tới 1000 dòng mỗi lần, cắt ở ranh giới dòng khi quá khoảng 32.000
ký tự, và Peto được dặn đọc cả tệp vừa phải trong một lần thay vì nhiều khúc nhỏ. Nhật ký thật của chủ web có 88 trên
269 lần đọc bị cắt ở mức cũ 160 dòng, một nửa là tệp chừng 186 dòng, mà mỗi lần đọc thiếu tốn thêm một bước (mỗi bước
gửi lại cả hội thoại, đắt hơn nhiều so với vài trăm dòng đọc thêm). Máy chủ cũ thì vẫn như trước: 160 dòng, chỉ định
khoảng thì tối đa 400 dòng. Kết quả cho biết dòng tiếp theo khi còn nội dung; mỗi lần đọc vẫn kiểm tra nội dung trên đĩa.

Cũng từ 0.25.0: Peto sửa một tệp chưa đọc (hay đã đổi kể từ lần đọc) thì vẫn bị từ chối, nhưng lời từ chối gửi kèm nội
dung hiện tại của tệp (quanh đoạn định sửa, nếu tìm được) và tính là đã đọc, nên bước sau sửa được ngay thay vì mất một
bước chỉ để đọc. Màn hình hiện dòng vàng "Chưa đọc X · đã gửi nội dung cho Peto". Các lần sửa khác của tệp đó trong cùng
bước vẫn bị từ chối, vì chúng được viết khi Peto chưa thấy tệp. Với `apply_patch`, nội dung của tối đa hai tệp được gửi
kèm và không tệp nào bị ghi.

Output của một lệnh dài hơn khoảng 20.000 ký tự vẫn chỉ gửi phần đầu và cuối cho Peto, nhưng từ 0.25.0 cả output được
lưu vào `%LOCALAPPDATA%\PetoAgent\outputs\` (tối đa 20 MB mỗi lệnh, giữ 7 ngày) và kết quả kèm `output_id`. Peto tìm
hay đọc phần giữa bằng `read_output`, không cần chạy lại lệnh và không phải hỏi bạn. Lệnh nền cũng vậy khi có lần đọc
bị cắt. Output ngắn thì không lưu gì.

Từ 0.18.0 (khi máy chủ đã cập nhật), công cụ làm việc theo OpenCode:
- `read_file` và tệp đính kèm bằng `@` có số dòng ở đầu mỗi dòng, nên Peto dẫn chỗ code kiểu `app.py:42`.
- `search_files` gộp kết quả theo tệp, tệp sửa gần nhất trước. `find_files` tìm tệp theo tên bằng mẫu như `**/*.py`.
- `edit_file` khớp gần đúng có kiểm soát (chủ web duyệt ngày 2026-10-12). Khi đoạn cũ Peto gửi chỉ lệch khoảng trắng,
  thụt lề, hoặc lỡ chép cả số dòng, CLI vẫn tìm được, nhưng vẫn phải đúng một chỗ, và khung duyệt ghi rõ "khớp gần
  đúng: …". Khác chữ thì không bao giờ khớp. `replace_all` thay mọi chỗ khớp nguyên văn, dùng khi đổi tên.
- Peto gọi y hệt một công cụ ba lần liền mà không có tệp nào đổi thì CLI hỏi bạn có cho gọi tiếp không. Từ chối thì
  Peto phải đổi cách làm. Chờ lệnh nền và xem trang không tính.

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

CLI chỉ chạy công cụ sau khi nhận đủ sự kiện hoàn tất bước. Từ 0.25.0 (theo opencode), lỗi tạm thời mà bước chưa có
phản hồi thì CLI tự thử lại tối đa 3 lần, chờ 2, 5 rồi 10 giây, dòng trạng thái ghi "thử lại lần 1/3 sau 2s · Ctrl+C
dừng". Đó là: không nối được máy chủ Peto, máy chủ trả 502/503/504 trước sự kiện đầu tiên (thường là lúc VPS khởi động
lại), hoặc máy chủ báo lỗi tạm thời của dịch vụ AI (giới hạn lượt, mất kết nối, lỗi 5xx) kèm cờ đã hoàn lại bước. Những
lần đó không tốn bước. Kết nối bị cắt giữa câu trả lời thì giữ kết quả các bước trước, đánh dấu bước hiện tại chưa xong
và trả về ô nhập. Khi mạng ổn, gõ `/retry`. Lần này không tự gửi lại, vì một bước AI mà máy chủ đã nhận có thể vẫn được
tính vào lượt dùng. `/retry` xóa quyền `a` cũ; quyền `s` cho đúng lệnh vẫn giữ
trong phiên, các thao tác khác sẽ hỏi lại.

Nếu đã đóng CLI, mở lại trong cùng thư mục, gõ `/resume` rồi `/retry`. `/new` hoặc gửi yêu cầu mới bỏ trạng thái chờ thử
lại. Lỗi đăng nhập hay hết lượt vẫn cần xử lý theo thông báo; `/retry` không bỏ qua các giới hạn đó. Khi mạng im lặng
hoàn toàn, socket có thể cần chờ tới timeout mới nhận ra; Ctrl+C vẫn dừng được trong lúc đọc stream.

### Cấu trúc giao diện

`presentation.py` khai báo giao diện mà `Session` và `Tools` sử dụng. Công cụ không tự in chữ: mỗi lần gọi báo sự kiện
có cấu trúc (`events.py`: bắt đầu, xem trước, câu hỏi quyền, kết quả kèm phần chỉ để hiển thị), và giao diện tự quyết
định vẽ thế nào. `tui/` là giao diện kiểu OpenCode cho terminal (theme, Markdown, diff, ô nhập, khung duyệt; `screen.py`
là màn hình toàn phần, `footer.py` kiểu chân cố định); `ui.py` là bản chữ thường cho ống dẫn, tệp, test và bài thi. Bộ chạy lệnh chỉ báo tiến độ qua callback. `transcript.py` đọc hội thoại đã lưu thành chuỗi sự kiện (tin, lời Peto, công cụ kèm kết quả), để `/resume` và `/fork` vẽ lại bằng đúng các hàm vẽ lúc đang làm, và `export.py` dựng Markdown của `/export`.
`external_editor.py` mở trình soạn của `/editor`.

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
- **Bản patch cho model GPT** (từ 0.21.0, theo opencode): với 6 Luna, 5.6 Terra và 6 Sol, Peto sửa tệp bằng một bản
  patch (`*** Begin Patch` … `*** End Patch`) có thể tạo, sửa, xóa và đổi tên nhiều tệp cùng lúc, vì các model này
  quen định dạng đó. Luật vẫn như trên: tệp sửa hay xóa phải đã đọc và chưa đổi, tệp tạo mới chưa có, đoạn sửa khớp
  đúng một chỗ (chỉ bỏ qua khoảng trắng đầu, cuối dòng). Bạn duyệt một lần cho cả bản, khung hiện diff từng tệp; một
  đoạn không khớp là không tệp nào bị ghi, và `/undo` hoàn tác cả bản. Peto (Grok) và Claude vẫn sửa từng đoạn.
- **Xóa và đổi tên:** Peto có công cụ riêng cho hai việc này và luôn hỏi trước; xóa thì hiện nội dung sắp mất, đổi tên
  thì hiện đường dẫn cũ và mới. Cả hai đi qua bản nhớ hoàn tác nên `/undo` lấy lại được, khác với xóa bằng lệnh
  terminal. Peto chỉ xóa được tệp chữ đọc được (không phải thư mục, tệp nhị phân hay tệp trên 1 MB), vì bản hoàn tác
  phải giữ được nội dung; đích của đổi tên phải là chỗ chưa có tệp.
- **Chạy lệnh:** chạy ở gốc dự án, hoặc trong một thư mục con có thật của dự án khi lệnh thuộc về đó (ví dụ `frontend`
  có `package.json` riêng; ô hỏi ghi rõ thư mục). Thư mục ngoài dự án hay `.git` bị từ chối. Chạy bằng `cmd`, hoặc bằng
  PowerShell khi lệnh cần cmdlet hay biến `$env:` (ô hỏi ghi rõ `PS>`). Từ 0.22.0 lệnh PowerShell in tiếng Việt đúng
  dấu; trước đó Windows PowerShell 5.1 làm mất chữ có dấu trong output. Mặc định dừng sau 120 giây (tối đa 600). Lệnh
  test cũng chạy code nằm trong dự án, nên hãy xem kỹ các thay đổi trước khi đồng ý chạy. Lệnh nền không có thời hạn
  nhưng bị dừng khi bạn đóng peto, kể cả khi đóng hẳn cửa sổ terminal. Chạy lệnh trong thư mục con cần VPS và CLI từ
  bản 0.9.8; CLI cũ hơn vẫn nhận công cụ như trước.
- **Giới hạn bước:** mỗi yêu cầu tối đa 40 bước; mỗi tài khoản có số bước mỗi ngày do máy chủ đặt (mặc định 200). Ở mức
  suy nghĩ cao, mỗi bước tính 2; với 5.6 Terra nhân thêm 2, với 6 Sol nhân thêm 4.

## Dữ liệu gửi đi

Nội dung tệp Peto đọc, kết quả tìm trong dự án, diff, output lệnh và ảnh bạn gửi kèm đi qua máy chủ Peto tới dịch vụ AI của
model đang chọn (xAI với Peto, OpenAI với 6 Luna, 5.6 Terra hoặc 6 Sol) để Peto quyết định bước tiếp theo. Máy chủ không lưu hội
thoại; nó chỉ lưu tên máy, mã băm của token và số bước đã dùng. Đừng mở Peto Agent trong thư mục có dữ liệu bạn không
muốn gửi đi.

Tên hội thoại (từ 0.21.0) do Peto đặt: tối đa 2.000 ký tự đầu tin đầu tiên của bạn và 1.000 ký tự đầu câu trả lời
được gửi qua máy chủ tới xAI một lần cho mỗi hội thoại, kể cả khi bạn đang dùng model OpenAI hay Claude.

`/update` tải bộ cài và gói `peto` từ đúng máy chủ trong `config.json` (chỗ bạn đã đăng nhập), không gửi gì của dự án.

`/btw` (từ 0.23.0) gửi hội thoại đang mở kèm câu hỏi đi như một bước bình thường, tới dịch vụ AI của model đang chọn.
`/export` chỉ ghi tệp trên máy bạn hoặc chép vào clipboard, không gửi gì đi.

Hướng dẫn chung của `/guide` (từ 0.25.0) được gửi kèm mọi bước ở mọi dự án, như AGENTS.md của dự án. Output đầy đủ của
lệnh dài nằm trên máy bạn ở `%LOCALAPPDATA%\PetoAgent\outputs\`; chỉ phần Peto đọc bằng `read_output` mới được gửi đi. Ảnh chụp dự án (từ
0.26.0) là bản sao các tệp của dự án trong `%LOCALAPPDATA%\PetoAgent\snapshots\`, chỉ nằm trên máy bạn; Peto chỉ được
báo tên các tệp lệnh đã đổi. Agent con khám phá (từ 0.27.0) gửi task và các tệp nó đọc đi như những bước
bình thường.

Để `/resume` hoạt động, các hội thoại của mỗi thư mục (tối đa 50) được lưu trên chính máy bạn ở
`%LOCALAPPDATA%\PetoAgent\sessions\` sau từng bước, gồm cả nội dung tệp Peto đã đọc, output lệnh và các ảnh còn giữ
trong hội thoại. Tệp không dùng quá 30 ngày được tự xóa; gỡ Peto Agent cũng xóa thư mục này. Lệnh "luôn cho phép" nằm
ở `%APPDATA%\PetoAgent\permissions.json`, cạnh `config.json`.

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
