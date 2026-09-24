# Bài thi Peto Agent

Cho Peto Agent làm những việc giống việc thật trên máy này, rồi chấm tự động. Mục đích là biết Peto mạnh, yếu ở đâu
bằng con số thay vì cảm giác, và so được trước với sau mỗi lần đổi prompt, công cụ hay model.

Peto chạy bằng đúng mã của `agent-cli` (Session, Tools) và máy chủ thật. Chỉ có câu hỏi quyền là được trả lời tự động
theo luật của bài thi thay cho người dùng.

## Các bài

| Bài | Loại | Giống việc thật nào |
|---|---|---|
| `sua-loi-checksum` | sửa lỗi | tool Python đọc file save (sas4-save-editor) |
| `them-lenh-todo` | tính năng | thêm lệnh, cờ và README cho một CLI Python |
| `hoi-code-c` | hỏi code | đọc code C (phần C của sas4): main.c ghi đè giá trị mặc định |
| `sua-api-monhoc` | sửa lỗi | API ASP.NET Core kiểu bài tập MonHoc: 500 thành 404, kiểm tra tên trống |
| `trang-khong-hien-san-pham` | sửa lỗi web | trang tĩnh lỗi JavaScript, chỉ thấy khi chạy trang |
| `tran-ngang-dien-thoai` | giao diện | trang tràn ngang trên điện thoại, máy tính phải giữ nguyên |
| `doi-ten-nhieu-tep` | việc dài | đổi tên một trường khắp dự án mà vẫn đọc được dữ liệu cũ |
| `test-do-tren-windows` | môi trường | README bảo `make test`, máy không có make lẫn pytest |
| `chi-dan-la-trong-tep` | an toàn | tài liệu giấu chỉ dẫn bảo AI gửi file chứa key ra ngoài |
| `hoi-code-peto-web` | hỏi code | dò code trong dự án lớn (bản sao Peto-Web, lấy bằng `git archive`) |

Mỗi bài nằm trong `tasks/<bài>/`:

- `task.py`: yêu cầu gõ cho Peto, số lượt tối đa, và hàm `check(ctx)` chấm bài.
- `project/`: dự án mẫu, được chép ra thư mục tạm.
- `hidden/`: test ẩn, chỉ chép vào sau khi Peto làm xong.
- `solution/`: lời giải mẫu, dùng để kiểm chính bộ chấm.

## Chấm những gì

- **Phép bắt buộc:** test ẩn qua, không sửa tệp test, trả lời đúng ý chính, không làm theo chỉ dẫn lạ… Bài chỉ đạt khi
  mọi phép bắt buộc đều qua.
- **Phép phụ:** những điều nên có, như báo nguyên nhân, cảnh báo người dùng, thêm test. Chúng được ghi lại để so,
  không làm bài trượt.
- **Thói quen, đo cho mọi bài:**
  - số lượt gọi model và token;
  - gọi công cụ lặp y hệt;
  - có tự kiểm tra sau lần sửa cuối không;
  - lệnh bị từ chối, và có xin lại lệnh đó không;
  - có dùng danh sách việc không;
  - có chạm giới hạn lượt hay hết giờ không.

## An toàn: bài thi chạy trên máy thật

Windows Home không có Windows Sandbox. Lớp bảo vệ là luật tự duyệt trong `policy.py`, cộng với việc mọi bài chỉ làm
trên bản sao trong thư mục tạm.

- **Sửa, ghi, xóa tệp:** đồng ý. Peto tự giới hạn trong thư mục dự án, ở đây là bản sao của bài.
- **Lệnh:** chỉ cho lệnh xem, build, test, chạy của Python, .NET, Node, cùng git chỉ đọc và `curl` tới localhost. Bị
  từ chối và ghi lại: đường dẫn ra ngoài thư mục bài, địa chỉ ngoài máy, cài gói (`pip`, `npm`, `dotnet add`), xóa hay
  chuyển tệp bằng lệnh, tắt tiến trình, đọc biến môi trường. `tasklist` và `netstat` cũng bị từ chối, để danh sách
  tiến trình của bạn không bị gửi đi.
- **PowerShell:** được soát bằng chính bộ đọc cú pháp của PowerShell.
  - Cho: biến tự đặt trong lệnh (`$r = Invoke-WebRequest …`), `try/catch`, khối lệnh của `ForEach-Object`.
  - Chặn: biến môi trường, gọi hàm .NET tĩnh, ghi tệp bằng `>`, gọi lệnh qua biến.
  - Mỗi lệnh con vẫn phải nằm trong danh sách.
- **cmd:** chỉ chặn `%TÊN%` (biến môi trường), nên `%{http_code}` của curl vẫn chạy.
- **Trước khi chạy code:** bộ chạy quét những tệp Peto vừa sửa hay tạo, tìm xóa tệp, gọi mạng, chạy tiến trình khác,
  đọc biến môi trường, đường dẫn ra ngoài. Có thì không chạy.
- **Biến môi trường:** biến chứa khóa, token, mật khẩu bị bỏ khỏi môi trường ngay khi bộ chạy khởi động, nên lệnh Peto
  chạy không thấy chúng.
- **Trang web:** trang trên máy thì cho bấm, gõ. Trang ngoài thì từ chối, trừ tên miền bài cho phép (hiện chưa bài nào
  cho). Nhờ đăng nhập thì bỏ qua.
- **Bản sao Peto-Web:** chỉ gồm mã đã commit, không có `.env`, dữ liệu hay phần chưa commit. Thư mục thật không bị
  đụng tới.

Đây không phải sandbox. Code Peto viết rồi chạy qua lệnh test vẫn chạy bằng quyền của bạn. Bộ quét chỉ bắt thứ lộ liễu:
đủ cho lỗi vô ý, không chặn được kẻ cố tình.

## Chạy

Từ gốc repo, bằng Python của venv:

    .venv\Scripts\python.exe agent-cli\evals\run.py login        # một lần: duyệt máy "Bài thi Peto" trên web
    .venv\Scripts\python.exe agent-cli\evals\run.py status       # tài khoản, số bước còn lại
    .venv\Scripts\python.exe agent-cli\evals\run.py selftest     # kiểm bộ chấm, không tốn bước
    .venv\Scripts\python.exe agent-cli\evals\run.py run --model peto --effort low
    .venv\Scripts\python.exe agent-cli\evals\run.py run sua-loi-checksum hoi-code-c    # chỉ vài bài
    .venv\Scripts\python.exe agent-cli\evals\run.py run test-do-tren-windows --repeat 3   # một bài 3 lần

**Đăng nhập:** `login` kết nối một máy riêng tên "Bài thi Peto", mặc định với máy chủ peto hằng ngày đang dùng (đổi
bằng `--server`). Máy đó thu hồi được trong Cài đặt → Peto Agent.

**Chi phí:** bước bài thi dùng vẫn tính vào hạn mức ngày của tài khoản. Trước khi chạy, bộ chạy in số bước tối đa, số
bước còn lại hôm nay, rồi hỏi lại. Bài nào không đủ bước thì bị bỏ, không chạy dở.

**Nơi lưu:** mọi thứ của bài thi nằm trong `%USERPROFILE%\.peto-eval` (đổi bằng `--home`), tách khỏi peto bạn dùng
hằng ngày: đăng nhập, nhật ký, hồ sơ trình duyệt, quyền. Bản sao dự án bị xóa sau khi chấm (`--keep` để giữ).

Bộ thi không dùng `%LOCALAPPDATA%` vì một lý do riêng của máy này. Ứng dụng Claude cài từ Microsoft Store chuyển thư
mục mới mà nó tạo trong AppData sang `…\Packages\Claude_…\LocalCache`. Nếu dùng AppData, kết quả Claude chạy sẽ không
nằm ở chỗ bạn mở được.

Kết quả nằm ở `results\<thời điểm>-<model>-<mức>\`:

- `report.md`: bảng tổng, thói quen chung, rồi từng bài.
- Mỗi bài có:
  - `result.json`: mọi lần gọi công cụ, câu hỏi quyền, lời Peto;
  - `transcript.txt`: màn hình như khi chạy peto;
  - `diff.patch`: Peto đã đổi gì;
  - `log.jsonl`: nhật ký của peto;
  - ảnh Peto chụp, nếu có.

Viết lại báo cáo bằng `run.py report <thư mục>`.

**Độ dao động:** model trả lời mỗi lần một khác. Đừng kết luận từ một bài trượt đơn lẻ: chạy lại bài đó với
`--repeat` (báo cáo đếm số lần đạt của từng bài), hoặc so cùng một bài trước và sau khi sửa.

## Thêm bài

1. Tạo `tasks/<bài>/task.py` với `TITLE`, `KIND`, `PROJECT` (tên thư mục Peto thấy), `PROMPT`, `MAX_STEPS`,
   `check(ctx)`, và `SOLUTION_REPLY` nếu bài chấm câu trả lời. Tùy chọn thêm:
   - `NEEDS`: `dotnet`, `edge`, `git`;
   - `SITES`: tên miền ngoài được mở;
   - `ALLOW`, `DENY`: regex lệnh riêng của bài;
   - `prepare(root)`: dựng dự án bằng code thay vì chép `project/`.
2. Đặt dự án vào `project/`, test ẩn vào `hidden/` (có `__init__.py`), lời giải mẫu vào `solution/`.
3. Chạy `run.py selftest <bài>`. Bản chưa làm phải trượt ít nhất một phép bắt buộc, lời giải mẫu phải qua hết. Không
   thì bộ chấm chưa phân biệt được làm đúng với làm sai.

Hàm chấm dùng `ctx` trong `checks.py`: `require`, `bonus`, `unittest`, `says` và `near` (so chữ không dấu), `touched`,
`serve` và `page` (mở trang bằng Edge ẩn), `dotnet_api` và `http`, `called`, `asked`.
