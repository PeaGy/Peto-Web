# Player — giảm nhạc khi trò chuyện, giai đoạn 4 (24/10/2026)

## Phạm vi

Bản đối chiếu `ed499ba`. Owner đã commit/deploy giai đoạn 3 và xác nhận kiểm chứng thành công, yêu cầu bước tiếp.
Đợt này thêm ducking cho Player đang có. Chưa commit/deploy; giai đoạn 5 nghiệm thu tích hợp vẫn là bước sau.
Peto nghe/nhìn nội dung video vẫn tạm gác.

## Hành vi

- Khi Companion đang ở trước và Peto **thực sự phát lời đọc**, người dùng đang giữ để nói hoặc bộ nghe báo có
  lời nói, âm lượng YouTube tạm còn **20% mức đã chọn** (60 → 12; mức dương rất thấp giữ tối thiểu 1).
- Bật micro nhưng chờ im lặng, gõ chat, chép tiếng thành chữ, AI suy nghĩ hoặc tải giọng lần đầu không giảm nhạc.
  Giọng nghe thử trong Cài đặt và micro test không thuộc cuộc trò chuyện Companion.
- Sau khi hết lời nói chờ **350 ms** rồi trả về mức đã chọn. Khoảng nghỉ ngắn giữa các mẩu giọng không làm âm
  lượng bật lên xuống liên tục; buffer dài thì nhạc về bình thường, phát lời đọc tiếp mới hạ lại.
- Thanh âm lượng giữ **mức người dùng chọn**. Chỉnh thanh, dùng nút mute hoặc nhờ Peto chỉnh trong lúc ducking
  vẫn được: kết thúc lời nói trả về mức mới, không ghi đè bằng mức cũ và không tự bật tiếng nếu đã mute.
- Controls native YouTube được nhận qua poll/read. Nếu đổi âm lượng native khi đang ducking, coi con số mới là
  mức chọn rồi áp dụng hệ số tạm; mute/unmute native vẫn giữ được mức có tiếng trước đó. API có thể phản hồi trễ,
  nên những giá trị cũ đang chờ xác nhận không được ghi ngược thành lựa chọn mới.
- IFrame API thật có lúc tạm trả `undefined` cho `isMuted`/`getVolume` khi cue video, dù đã onReady. Xem đó là
  dữ liệu chưa có, không ép thành 0 rồi mute hoặc lưu đè mức chọn. Quan sát chưa đầy đủ cũng không cấp proof native.
- Ẩn Player bằng `_`/mũi tên vẫn theo giọng nói khi Companion còn hoạt động. Desktop rời Companion/ẩn tab tiếp
  tục nhạc ở mức thường theo lifecycle cũ; mobile vẫn dừng/giải phóng khi rời hoặc ẩn trang. X/Clear All/logout/
  pagehide/unmount hủy iframe; thay đổi ducking đến sau không tạo player, phát lại hay gửi lệnh tới iframe đã hủy.
- Đổi bài dùng cùng iframe; iframe mới khi đang ducking nhận mức đã hạ trước khi được phát. Không tạo audio
  analyser, lấy tiếng từ iframe hoặc thêm tính năng nghe/nhìn video cho AI.

## Cấu trúc và tương thích

`usePlayerDucking.ts` chỉ tính tín hiệu từ trạng thái hearing/TTS và foreground. `playerVolume.ts` quản lý mức
chọn, mức native và hệ số tạm; `useYouTubePlayer` vẫn sở hữu một iframe. Không đổi ASR/TTS pipeline, renderer,
phím Space, bố cục hoặc thêm chữ/nút vào Player. Không thêm dependency, key hoặc cấu hình server.

Checkpoint lưu **mức chọn**, gồm flush trước dispose khi F5; không lưu mức đã hạ hoặc trạng thái ducking. Schema
phiên nghe/history không đổi, khôi phục vẫn stopped. Clear Queue/All/Undo/history/favorites giữ ngữ nghĩa cũ.

Chat vẫn capability v5 và các action cũ. Receipt có thêm hai field tùy chọn: `effective_volume` là mức native quan
sát được (0 nếu mute), `ducked` cho biết đang áp dụng ducking; `volume` là mức chọn. Backend nhận các field này và
vẫn chấp nhận receipt tab cũ thiếu chúng. Prompt khả năng chỉ giải thích ý nghĩa hai mức khi có field; không đổi
persona/examples hoặc ép mẫu xác nhận. `set_volume`/mute/unmute phải chờ cả mức chọn và mức native thực tế phù
hợp hệ số hiện tại; gọi hàm không được coi là thành công. Proof phát đúng video/state1 và guard lời đáp giữ nguyên.

## Kiểm chứng

| Phần | Kết quả |
| --- | --- |
| Backend | 296 ca / 12 tệp đạt, gồm schema ducking tùy chọn và tương thích receipt cũ. |
| Frontend | 276 ca / 14 tệp Player/Companion/Hearing/speech đạt trên bản sửa cache cuối. |
| Chrome desktop/mobile mô phỏng | Hồi quy đầy đủ: 53 đạt, 1 lỗi phép chờ release của test, 4 skip theo thiết bị. Đã sửa test; nhóm voice cuối sau sửa cache 5 đạt / 1 skip. |
| Edge desktop/mobile mô phỏng | Nhóm voice 5 ca đạt / 1 skip theo thiết bị, gồm PCM/Live2D, micro, chat volume, mute, đổi bài và F5. |
| YouTube thật / Chrome desktop | 1 ca đạt với Tetris: 30 → 6; chỉnh native 50 → 10; hết nói về 50; F5 lưu và cue stopped ở mức 50. |
| Build frontend + TypeScript browser tests | Đạt; cảnh báo chunk lớn đã có. |

Browser hồi quy dùng backend/YouTube/ASR giả; ca giọng đọc dùng Audio/PCM tổng hợp và renderer Live2D thật.
Ca iframe thật dùng profile riêng, backend/tài khoản Peto và ASR giả, tắt tiếng đầu ra của browser; quan sát IFrame
API, không chứng minh âm lượng cảm nhận ở loa hoặc Peto hiểu tiếng nhạc. Không gọi AI/TTS/catalogue trả phí,
không dùng tài khoản production. Android thật chưa thử bản mới.

Giữ báo cáo các lượt kiểm tra lỗi: lần kiểm lại đầu còn một ca bị quá hạn tải Companion 8s lúc khởi động lạnh;
đã cho phần tải ban đầu cùng hạn 30s như ca renderer và chạy nhóm voice tuần tự đạt. Không gọi những lượt đó là
hoàn toàn xanh. Lượt native đầu chỉ ra cache thiếu bị ép thành 0/mute; đã thêm kiểm kiểu và hai ca unit cho đúng
tình huống này. Sau sửa, iframe thật chạy ngay ở mức 30, không cần thao tác bật tiếng để né lỗi; giữ đúng 50 sau F5.
Kết quả hồi quy + nhóm kiểm lại bao phủ 54 ca Chrome khác nhau; không chạy lại toàn bộ suite sau sửa cache, kiểm
lại nhóm voice/F5 bị tác động và unit liên quan. Không retry tự động.

Bằng chứng cục bộ Git-ignored: `.runtime/player-session-stage4/`, các JSON `chrome-results`, `chrome-verified-results`,
`chrome-final-results`, `chrome-cache-final-results`, `msedge-results`, `real-youtube-results`, trace và log build. Harness native nằm trong
`.runtime/player-ducking-real.spec.ts`/`.config.ts`; chỉ thêm quan sát vào instance thật, không thay API/player/logic volume.

## Deploy và thử thật

Rebuild frontend và restart backend, **backend trước hoặc cùng frontend** vì receipt mới có hai field tùy chọn.
Tab cũ vẫn dùng được; tải lại sau phiên nghe để nhận bundle mới. Không migration hoặc thay key.

Checklist desktop và Xiaomi/Android 13/Chrome của owner:

1. Phát nhạc ở 60, nhờ Peto đọc một câu: nghe nhạc nhỏ đi, hết câu trở lại 60. Chỉ gõ/chờ trả lời không giảm.
2. Giữ để nói rồi thả/hủy; thử Luôn nghe lúc im lặng và lúc nói. Tắt nghe hoặc ngắt Peto đều trả nhạc về thường.
3. Trong lúc đọc, chỉnh mức xuống 35 rồi dừng giọng: nhạc trở lại 35. Mute rồi dừng giọng vẫn im; unmute được.
4. Nhờ Peto chỉnh âm lượng khi đang nghe; so với controls và trạng thái thật, không yêu cầu câu xác nhận cố định.
5. Đổi bài, ẩn Player/mở lại, X/Clear All và F5 khi đang ducking: không tự phát lại, không nhân iframe; F5 giữ
   mức chọn và phát tiếp đúng mốc sau thao tác Phát. Rời/ẩn trang desktop/mobile theo vòng đời đã chốt.

Nghiệm thu micro/loa/Android thật của bản mới vẫn cần owner thử sau deploy; mô phỏng không thay thiết bị thật.
