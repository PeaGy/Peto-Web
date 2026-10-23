# Player — Yêu thích và hàng đợi, giai đoạn 1

Bản duyệt giao diện riêng, chưa ghép vào Companion đang deploy. Không commit/deploy tự động.

## Mở bản xem thử

Tại `frontend`, chạy `npm run dev -- --host 127.0.0.1 --port 5190 --strictPort`, sau đó mở
<http://127.0.0.1:5190/prototypes/player-library/>. Thu hẹp cửa sổ để xem bố cục mobile.

Đây là dữ liệu minh họa trong bộ nhớ. Không có iframe, audio/video thật, tìm kiếm mạng, tài khoản,
localStorage hoặc API key. Đồng hồ phát chỉ mô phỏng. Reload sẽ đặt lại tim, hàng đợi, loop/shuffle và kết quả.
Các bản cover/live/piano trong kết quả “Tetris” là tên mẫu, không phải kết quả YouTube đã xác minh.

## Hành vi để duyệt

- Tim lưu/bỏ lưu bài hiện tại: desktop trong hàng điều khiển phụ; mobile ở mép phải hàng tên bài dưới video, trên thanh thời lượng,
  thẳng cột với mốc tổng thời lượng ở bên phải và canh giữa hai dòng tên bài/nghệ sĩ.
  File → Yêu thích mở danh sách đã lưu; mobile dùng menu ba chấm.
- Nút danh sách mở/đóng hàng đợi, mặc định đóng. Khung từ 760 px đặt danh sách bên phải; khung hẹp và
  mobile đặt bên dưới. Dùng một vùng danh sách chung cho Hàng đợi, Yêu thích hoặc Kết quả, không thêm tab cố định.
- Khi danh sách mobile mở, vùng minh họa gọn lại, vẫn tối thiểu 200 × 200. Vùng danh sách có scrollbar riêng;
  màn hình ngắn có thể cuộn phần thân Player để đến danh sách. Không tràn sang ô chat.
- File có một ô nhập link hoặc tên. Thử “Tetris” để có năm kết quả, hoặc dùng các nút ví dụ.
  Tìm tên không tự chọn/phát kết quả đầu. Chọn một dòng để mô phỏng phát; dấu cộng thêm vào cuối hàng đợi.
- Thêm bài từ kết quả/yêu thích giữ nguyên nội dung danh sách; nút hàng đợi hiện chấm báo.
  Mở hàng đợi sẽ bỏ chấm. Playlist mẫu thêm ba bài và mở hàng đợi, giữ bài hiện tại.
- Hàng đợi có bài hiện tại và các bài tiếp theo. Kéo tay nắm trên desktop, dùng phím lên/xuống ở tay nắm,
  hoặc menu ba chấm Đưa lên/Đưa xuống/Xóa (dùng được trên cảm ứng).
- Nút kế tiếp và đồng hồ đến cuối bài chuyển sang đầu hàng đợi. Chọn bài trong hàng đợi lấy bài đó khỏi danh sách chờ.
- Hàng điều khiển chính trên desktop/mobile: **Shuffle · Phát lại từ đầu · Phát/Tạm dừng · Bài tiếp theo · Loop**,
  canh giữa theo ảnh chủ web đưa. Âm lượng, tim desktop và nút hàng đợi ở hàng phụ; tim mobile giữ vị trí đã duyệt.
  Shuffle/loop dùng ngay khi hàng đợi đóng; hai nút cạnh “Tiếp theo” trong hàng đợi dùng chung trạng thái.
  Cả hai chế độ đều tắt mặc định.
  Shuffle trộn các bài chờ, giữ bài hiện tại và vị trí phát. Thứ tự danh sách chính là thứ tự sẽ phát.
  Tắt shuffle khôi phục thứ tự thường của các bài còn chờ; kéo/đổi thứ tự bằng tay cũng tắt shuffle và giữ thứ tự vừa chỉnh.
- Loop chuyển **tắt → hàng đợi → một bài → tắt**. Chế độ bật có màu/chấm báo; lặp một bài có số 1.
  Lặp hàng đợi bao gồm bài hiện tại và các bài trong vòng phát, kể cả bài đã nghe trước lúc bật; bài đã xóa không quay lại.
  Lặp một bài quay về đầu khi kết thúc; nút Tiếp theo vẫn bỏ qua sang bài khác. Không bật lặp thì hết hàng đợi sẽ dừng.
  Shuffle kết hợp với lặp hàng đợi trộn lại mỗi vòng, mỗi mục được phát một lần trong vòng và không lặp ngay mục vừa hết
  khi chuyển vòng (trừ khi chỉ có một mục). Những lần thêm cùng video là các mục riêng.
- Desktop `_`, mobile mũi tên xuống và nút mở Player ẩn/hiện toàn bộ frame, giữ đồng hồ; không có mini player.
  X đóng và dừng. Giao diện kéo/resize, menu nổi, âm lượng bên phải loa và quyền phím Space giữ theo bản đã duyệt.
- Esc ưu tiên đóng menu của dòng → âm lượng/menu File → danh sách → Player. Mobile khóa focus trong Player
  khi đang mở; ẩn xong có thể nhập chat mẫu, không gọi AI hoặc micro thật.

## Ranh giới mã

`LibraryPlayerShell.tsx` là bản sao cô lập của shell đã deploy để duyệt bố cục mới; chỉ prototype import nó.
Tái sử dụng hook kéo/resize, hook chọn bố cục và CSS nền của Player, không sửa các file sản phẩm.
`library.tsx` chứa trạng thái/thao tác mẫu và panel; `queuePlayback.ts` xử lý chuyển bài, loop/shuffle trong bộ nhớ;
`data.ts` chứa catalogue mẫu; `library.css` chỉ áp dụng lớp `yl-*`.
HTML này là entry của Vite dev server, không thêm vào entry production. Không để app import prototype/catalogue.

## Các giai đoạn đã thống nhất

1. **Hiện tại:** duyệt UI bằng dữ liệu mẫu tương tác được trên desktop/mobile.
2. Ghép vào Player thật: lưu yêu thích theo tài khoản, hàng đợi thực, phát tiếp, đổi thứ tự, xóa và các chế độ loop/shuffle đã duyệt.
3. Nhập playlist công khai và tìm theo tên với YouTube Data API; giữ kết quả để người dùng chọn, không tự phát bài đầu.
4. Kiểm chứng browser/thiết bị/tài nguyên trước khi hoàn tất. Android/Chrome thật vẫn cần xác nhận riêng.

Tương tác Companion bằng lệnh chat/voice để sau. Giai đoạn 1 không thay đổi backend/schema/cấu hình YouTube.

## Kiểm chứng

Kết quả ngày 23/10/2026 sau bổ sung loop/shuffle: build đạt; 10 ca kiểm tra logic hàng đợi đạt;
18 ca browser của bản này (9 kịch bản × desktop/mobile) đạt. Lượt đối chiếu prototype cũ trước đó:
12 ca đạt, 6 ca bỏ qua theo loại thiết bị.

- `npm run build -- --logLevel error`: TypeScript và build frontend.
- `npm run test -- tests/player-library-playback.test.ts`: hết hàng đợi, ba chế độ lặp, chỉ một bài, shuffle/khôi phục,
  lặp qua nhiều vòng, sửa/xóa, video trùng và action được chạy lại trong Strict Mode.
- `npm run test:browser -- player-library-preview.spec.ts youtube-player-preview.spec.ts`: Chromium desktop
  1440 × 900, mobile mô phỏng 390 × 844, thêm 320 × 640 và 844 × 390; đối chiếu prototype Player cũ.
- Ca mới kiểm tra UI không gọi dịch vụ, một vùng media ổn định, tim/File, dữ liệu phiên, kết quả tìm kiếm,
  chấm báo/playlist, đổi thứ tự/xóa/phát tiếp, loop/shuffle, Space/Esc, ẩn/đóng, cuộn và không tràn ngang.
- Kiểm tra ảnh chụp thật từ trình duyệt kiểm thử cho desktop, mobile dọc/ngang; không coi mock là kiểm chứng
  YouTube thật, Edge thật, Android thật hoặc hiệu năng phát media.
