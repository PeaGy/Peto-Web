# Sửa phát tiếp sau F5 (24/10/2026)

Owner đã commit/deploy giai đoạn 2 ở `03a184f`. Bản lưu khôi phục được queue, vị trí, volume và chế độ,
nhưng bấm Phát lại chạy từ đầu. Đợt sửa này chưa commit/deploy, chỉ frontend; không đổi dữ liệu lưu, backend,
persona, DB, key, dependency hoặc bước tiếp theo của kế hoạch.

## Nguyên nhân và sửa

Vị trí nghe thường có phần thập phân. Code cũ đưa thẳng giá trị đó vào `playerVars.start`, trong khi tham số
embed này yêu cầu số nguyên. Trước khi phát, helper hiển thị mốc đã lưu khi native báo unstarted/time=0;
vì vậy thanh thời lượng đúng chưa chứng minh video sẽ phát đúng mốc. Mock trước cũng nhận mọi số thập phân trong
constructor và ca F5 chỉ kiểm `play.ok`, chưa đối chiếu vị trí sau khi thực sự playing.

- Constructor gửi `start` số nguyên. Khi khởi tạo một nguồn dừng có mốc > 0, chủ động `cueVideoById` với
  `startSeconds` đã lưu; API này nhận cả số thập phân. Cả nút Peto lẫn nút bên trong iframe dùng cùng nguồn đã cue.
- Không gọi seek/play khi restore; vẫn chờ thao tác người dùng. Không thêm iframe. Nguồn autoplay/đổi bài đang
  dùng đường cũ, không cue lại sau mỗi lần bấm Phát hoặc mỗi sự kiện playing.
- Seek về 0, pause/play về sau vẫn giữ lựa chọn mới, không bị ép quay về mốc restore. Restart/loop vẫn dùng start gốc.
- Mock constructor được sửa để chỉ nhận `start` nguyên. Ca F5 kiểm vị trí lúc playing qua cả nút native và Peto,
  gồm một lần F5 nữa giữa hai cách phát; không dùng vị trí hiển thị ở trạng thái ready làm bằng chứng.

Tài liệu chính thức đã đối chiếu:
[tham số start](https://developers.google.com/youtube/player_parameters#start),
[cueVideoById/startSeconds](https://developers.google.com/youtube/iframe_api_reference#cueVideoById).

## Bằng chứng

Đã chạy Chrome desktop với **iframe/video YouTube thật** (`Soy4jGPHr3g`), tài khoản/backend/metadata Peto giả,
profile trình duyệt riêng, volume=0. Không gửi chat/gọi AI/TTS hoặc YouTube Data API. Seed mốc 45,75 giây, F5,
đợi trạng thái dừng rồi bấm Phát. Một phép đối chứng chỉ thay JS được trả cho browser để phục hồi hai chỗ gọi cũ,
không ghi đè source trên đĩa.

| Trường hợp | Vị trí sau khi thực sự playing |
| --- | --- |
| Cách gọi cũ: start thập phân, không cue rõ mốc | 0 giây — tái hiện lỗi. |
| Bản sửa, nút Phát của Peto | Khoảng 46 giây. |
| Bản sửa, nút Phát trong YouTube | Khoảng 46 giây. |

Giá trị trên đọc từ slider ứng dụng bước 1 giây **sau** trạng thái native playing; không phải phép đo chính xác
đến từng phần thập phân. Đã xem ảnh video thật ở khoảng 0:45. Không suy kết quả một video/máy thành bảo đảm mọi
video hoặc Android thật. YouTube có thể bắt đầu gần mốc theo keyframe như tài liệu của họ.

| Kiểm tra | Kết quả |
| --- | --- |
| Unit | 57 ca đạt / 3 tệp useYouTubePlayer, playerSession, usePlayerLibrary. |
| Browser giả Chrome/Edge | Mỗi browser 2 ca F5 desktop/mobile mô phỏng đạt, không retry/flaky. |
| YouTube thật, Chrome desktop | 3 phép kiểm đạt: đối chứng cũ + hai nút ở bản sửa. |
| Build và TypeScript browser tests | Đạt; còn cảnh báo chunk lớn đã có. |

Không chạy lại toàn bộ backend hoặc bộ 48 ca browser; đây là sửa nhỏ ở khởi tạo nguồn có mốc khác 0.
Lần kiểm native thật đầu dùng selector CSS cũ không còn trong YouTube hiện tại nên không bấm được nút;
đã đổi sang nút có tên truy cập “Phát video”, chạy lại cả ba phép kiểm đều đạt. Không coi timeout selector là
lỗi phát video. Bộ mới không dùng retry ngầm để biến lỗi thành pass.

Raw Git-ignored: `.runtime/player-resume-fix/`, `.runtime/player-resume-real-results.json` và
`.runtime/player-resume-real-artifacts/`. Script/config kiểm thật cũng chỉ ở `.runtime/`, không vào CI mặc định.

## Deploy và thử lại

Chỉ rebuild/deploy frontend. Tab đang mở cần tải lại để nhận bundle mới. Dữ liệu session cũ vẫn đọc được;
không xóa queue/yêu thích để sửa lỗi. Nếu đã phát về 0 với bản cũ, mốc mới có thể đã được lưu lại gần 0;
tua lại tới giữa bài rồi F5 → mở Player → thử nút Phát Peto và nút Phát trong video. Kiểm cả sau pause/seek về 0.
Chưa nghiệm thu riêng trên Android thật hoặc trên tài khoản production của owner.
