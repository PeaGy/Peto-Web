# Kiểm tra giao diện và phục hồi kết nối

Bộ kiểm tra dùng Chromium thật, component/CSS của sản phẩm và API giả. Không cần backend, tài khoản hay khóa AI;
không gọi AI và không đọc dữ liệu chạy. Các bài kiểm tra bố cục thay renderer Live2D/VRM bằng component rỗng để
chuyển động và WebGL không làm ảnh đối chiếu thay đổi. Riêng `companion-presence.spec.ts` dùng renderer Live2D
thật để kiểm tra loading chờ nhân vật và bong bóng đang nghĩ bám theo đầu nhân vật.

## Chạy tại máy

Từ thư mục `frontend`, dùng Node 24:

```powershell
npm ci
npx playwright install chromium
npm run test:browser
```

Playwright tự mở Vite ở cổng 5179 và đóng khi xong; không dùng server/backend đang chạy của người dùng.
Trong môi trường sandbox Windows, bước đóng tiến trình con có thể cần chạy ngoài sandbox.
Ảnh chuẩn hiện được tạo trên Windows (`*-win32.png`). Máy chạy Linux/macOS cần bộ ảnh chuẩn riêng vì font khác;
không dùng ảnh của hệ điều hành khác để kết luận giao diện lỗi.

## Những gì được kiểm tra

- Routing: `/` → `/companion` → `/imagine` → Back → Back → Forward, giữ lịch sử và bản nháp, không remount tab,
  bấm lại tab không thêm history. Kiểm tra F5, tab mới, query và URL hash cũ, lịch sử phiên bản ảnh.
  `npm run build` rồi `npm run test:browser -- --config playwright.routing.config.ts` chạy riêng phần này trên bản build
  do FastAPI phục vụ bằng fallback thật. Server kiểm thử chỉ nghe loopback, không đọc database hay gọi AI.
  URL `/chat/<id>`: đổi giữa hội thoại và chat mới, giữ nháp khi quay từ Imagine, bookmark ngoài danh sách gần đây,
  chat đã lưu trữ, F5/tab mới, cấp ID tin đầu không tải lại tin, quyền truy cập và quay lại URL sau đăng nhập.

- PC 1440×900 và mobile 390×844: sidebar, nút tùy chọn, menu hội thoại, bảng, giá tiền, công thức và trình sửa tin.
- Chat dài: giữ ô nhập, không cuộn ngang toàn trang, vị trí nút xuống cuối khi nhấn giữ.
- Companion: khoảng cách bóng chat trên mobile; chat/Companion thu khung xuống 390×500 để mô phỏng chỗ bàn phím.
  Cần kiểm tra thêm trên Android/iOS thật để xác nhận hành vi bàn phím và thanh địa chỉ của từng trình duyệt.
- Luồng trả lời bị ngắt, chuyển ngoại tuyến rồi có mạng lại: chỉ đọc lịch sử đúng lượt đã xác nhận, giữ bản nháp mới,
  không gửi lại tin và không gọi AI thêm. Đồng bộ không tự phát giọng nói.
- Companion bật/tắt nghe nhiều phiên, xuống nền giữ chữ chưa chốt và không tự mở micro khi quay về. Mỗi cấu hình
  PC/mobile còn mở/đóng capture thật 30 lần để kiểm tra mọi track kết thúc và mọi AudioContext đóng. Dịch vụ nhận
  giọng dùng bản giả; sự kiện xuống nền được mô phỏng, chưa thay cho khóa màn hình trên Android/iOS thật.
- Vitest kiểm tra thêm kết quả đến muộn, đổi hội thoại/tài khoản, tab ẩn, lưu chậm, hết phiên, giới hạn thời gian đọc
  và phân biệt thao tác Dừng với mất mạng.

Ảnh khác ảnh chuẩn làm kiểm tra thất bại. Ảnh mới/ảnh so sánh và trace nằm ở `test-results/`;
báo cáo nằm ở `playwright-report/`. Các thư mục kết quả này không đưa vào Git.

Chỉ cập nhật ảnh chuẩn khi đã xem và chấp nhận thay đổi giao diện:

```powershell
npm run test:browser:update
```

Ảnh chuẩn trong `*-snapshots/` cần đưa vào cùng commit sửa giao diện. Không cập nhật ảnh để che lỗi kiểm tra.

## Tự kiểm tra khi cập nhật mã

`.github/workflows/frontend-checks.yml` chạy kiểm tra logic, build và so sánh ảnh trên Windows khi push hoặc mở PR
có sửa frontend. Workflow không triển khai web. Lần chạy trên GitHub cần xem thêm báo cáo nếu font của runner khác
máy tạo ảnh chuẩn; kết quả chạy local không xác nhận lần chạy GitHub đã đạt.
Cấu hình dựa trên [hướng dẫn CI của Playwright](https://playwright.dev/docs/ci-intro).

CI chạy một worker và dùng SwiftShader để vẽ WebGL bằng phần mềm; các bài kiểm tra sân khấu trong
`companion-presence.spec.ts` vẫn tải model Live2D thật. Khi một bài thất bại, CI thử lại đúng một lần;
Playwright khởi động worker và trình duyệt mới, rồi chạy lại toàn bộ bài. Chạy local mặc định không thử lại.
Lần đầu lỗi nhưng lần sau qua được ghi là `flaky`, không phải đạt ngay lần đầu. Lỗi lặp lại vẫn làm workflow
thất bại. Cơ chế này xử lý lỗi tài nguyên tạm thời như `net::ERR_NO_BUFFER_SPACE`; không bỏ bước kiểm tra
hay tự cập nhật ảnh chuẩn. Không dùng kết quả flaky để kết luận lỗi ứng dụng đã được sửa.

Mỗi lượt CI giữ gói `ket-qua-frontend` trong bảy ngày, kể cả khi qua sau lần thử lại. Xem báo cáo HTML và
`playwright-report/results.json` để phân biệt đạt, flaky và thất bại; các trace lỗi nằm trong `test-results/`.
Cách chạy lại dựa trên [cơ chế retry của Playwright](https://playwright.dev/docs/test-retries).

## Giới hạn phục hồi

Chỉ phục hồi lượt đã nhận `meta` kèm mã tin nhắn từ máy chủ. Nếu mất mạng trước bước đó, bản nháp vẫn được giữ và
người dùng cần kiểm tra lịch sử trước khi gửi lại. Câu trả lời trên máy chủ chưa hoàn tất được hiển thị là chưa hoàn
tất; không tự tạo tiếp nội dung. Mỗi lần kết nối lại chỉ đọc tối đa ba lần, mỗi lần tối đa năm giây.
