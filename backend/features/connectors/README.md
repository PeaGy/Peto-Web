# Kết nối GitHub

Mục **Cài đặt → Kết nối** quản lý GitHub riêng cho từng tài khoản Peto. Trong chat, Peto có thể liệt kê repo được cấp quyền, đọc thư mục/tệp UTF-8, xem các lần chạy GitHub Actions, các job/bước và log của job. Công cụ chỉ gọi API đọc; không tạo bình luận, sửa tệp hay chạy lại workflow. Companion và tác vụ đặt tên không có các công cụ này.

## Cấu hình máy chủ

1. Trong GitHub **Settings → Developer settings → GitHub Apps**, tạo một GitHub App dành riêng cho Peto. Dùng GitHub App để chọn repo và quyền chi tiết, thay vì OAuth App với quyền `repo` rộng.
2. Homepage URL là địa chỉ web Peto. **Callback URL** phải khớp `PETO_GITHUB_REDIRECT_URI`, ví dụ `https://peto.example/api/connectors/github/callback`. Để thử local, dùng `http://localhost:5173/api/connectors/github/callback` với Vite proxy đang chạy.
3. Chỉ cấp **Repository permissions**: **Contents: Read-only**, **Actions: Read-only**, **Metadata: Read-only**. Không cần quyền ghi hay quyền tài khoản bổ sung. Tắt webhook; bản này không dùng webhook hoặc khóa riêng của App.
4. Giữ token người dùng có thời hạn. Không bật tự cấp quyền người dùng trong lúc cài App: Peto bắt đầu cấp quyền bằng nút **Kết nối**, kèm state và PKCE gắn với phiên Peto hiện tại. Không đặt Setup URL trỏ thẳng vào callback.
5. Tạo Client secret và đặt các biến dưới đây trong `.env` riêng của máy chủ. `APP_SLUG` là tên trong URL `github.com/apps/<tên-app>`, không phải App ID. Có thể đặt App dùng cho mọi tài khoản nếu web phục vụ nhiều người.

```dotenv
PETO_GITHUB_CLIENT_ID=<Client ID của GitHub App>
PETO_GITHUB_CLIENT_SECRET=<Client secret>
PETO_GITHUB_APP_SLUG=<tên-app-trong-url>
PETO_GITHUB_REDIRECT_URI=https://peto.example/api/connectors/github/callback
PETO_CONNECTOR_SECRET=<chuỗi-ngẫu-nhiên-riêng-tối-thiểu-32-ký-tự>
```

Cài lại `backend/requirements.txt` để có `cryptography`, rồi khởi động lại backend. Có thể tạo khóa ngẫu nhiên bằng Python: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Không đưa khóa vào Git, chat hoặc log. Bản sao lưu database chứa khóa GitHub đã mã hóa; giữ `PETO_CONNECTOR_SECRET` riêng để khôi phục. Đổi khóa này khiến các kết nối cũ phải cấp quyền lại.

## Sử dụng

1. Mở **Cài đặt → Kết nối → Khám phá → GitHub → Kết nối**. GitHub hỏi cấp quyền rồi đưa về mục Kết nối của đúng tài khoản Peto.
2. Bấm **Quản lý**, sau đó **Quản lý repo** để cài GitHub App cho tài khoản/tổ chức và chọn repo được phép đọc. Cấp quyền ứng dụng và chọn repo là hai bước riêng. Nếu tổ chức cần quản trị viên phê duyệt thì chờ phê duyệt trước khi đọc repo đó.
3. Bấm **Kiểm tra kết nối** để xác minh token còn được GitHub chấp nhận. Phép kiểm này xác minh tài khoản; nó không cam kết quyền của mọi repo. Thử trong chat: “Kiểm tra lần chạy GitHub Actions mới nhất của owner/repo và giải thích lỗi.” Hoặc “Đọc README.md của owner/repo.”
4. **Ngắt kết nối** xóa khóa đang lưu và các phiên cấp quyền chờ của tài khoản khỏi Peto. Nó không gỡ GitHub App hay thu hồi cấp quyền phía GitHub; muốn thu hồi hoàn toàn, vào GitHub Settings → Applications. Dữ liệu đã trích dẫn trong chat vẫn còn trong lịch sử và có thể tiếp tục được AI sử dụng; việc ngắt chỉ chặn các lần đọc mới.

Khóa không đưa về frontend, không gửi cho model, không nằm trong URL trang. State dùng một lần, hết hạn sau 10 phút và gắn với tài khoản cùng cookie phiên Peto. Token và refresh token được mã hóa; token được làm mới khi cần. Callback không bao giờ dùng `installation_id` do trình duyệt gửi để cấp quyền vào repo.

Mỗi lượt chat dùng giới hạn công cụ/timeout hiện có. Dữ liệu từ tệp/log được đánh dấu là nguồn bên ngoài, không phải chỉ dẫn; việc phân tích vẫn có thể sai và cần đối chiếu nguồn GitHub. Tệp chữ tối đa 512 KB, trích tối đa 24.000 ký tự; danh sách có phân trang. Log tải theo job, giới hạn 2 MB, giữ vùng báo lỗi cùng đoạn đầu/cuối khi dài. Địa chỉ tải log chỉ được nhận từ API GitHub và phải thuộc HTTPS của Azure Blob hoặc GitHub Actions; khóa Authorization không được chuyển sang máy chủ tải log. Máy chủ GitHub Enterprise và MCP tùy chỉnh chưa được hỗ trợ.

Lượt chat có kết nối GitHub được tra cứu tối đa 12 vòng và thực thi tối đa 30 lần gọi công cụ, tính chung các công cụ trong lượt. Peto tự chọn số lần tra cứu theo câu hỏi và dữ liệu cần đọc; không bắt buộc dùng hết giới hạn hoặc đọc toàn bộ repo. Khi chạm giới hạn, lần gọi AI cuối tắt toàn bộ công cụ và yêu cầu tổng hợp kết quả đã có, nêu rõ phần chưa đọc hoặc chưa xác minh. Các lời gọi vượt số lượng không được thực thi. Timeout của lượt chat vẫn áp dụng; không tự gửi lại lượt bị ngắt hay quá thời gian.

Trạng thái **Đã kết nối** là thông tin lần cấp quyền đã lưu, không phải kiểm tra online liên tục. Quyền bị thu hồi được báo khi bấm Kiểm tra hoặc khi Peto đọc dữ liệu. Nếu thiếu cấu hình, mục GitHub vẫn có mô tả nhưng nút Kết nối bị khóa và nói rõ máy chủ chưa bật.

Tiến trình GitHub trong chat được gom thành một dòng đếm mục đã đọc/chưa đọc; lỗi chi tiết có thể mở riêng. Lỗi 404 không tự xác nhận thiếu quyền: khi một đường dẫn tệp không tìm thấy, Peto kiểm tra thư mục gốc trên cùng nhánh để phân biệt đường dẫn sai với trường hợp chưa xác minh được truy cập. Hạn mức GitHub và phản hồi từ chối quyền được diễn đạt riêng; chỉ lỗi quyền đã xác nhận mới hướng dẫn kiểm tra Contents hoặc Actions. Khi khảo sát repo, công cụ hướng dẫn đọc danh sách thư mục trước và dùng đường dẫn thật.

Tài liệu chính thức: [Token người dùng của GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app), [làm mới token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens), [API job và log](https://docs.github.com/en/rest/actions/workflow-jobs).
