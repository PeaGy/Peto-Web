# Phục hồi lượt Chat và phạm vi dữ liệu — giai đoạn 3, 21/10/2026

Phạm vi: Web Chat và hàng rào ghi của trí nhớ cá nhân dùng chung Chat/Companion. Giữ nguyên model, bộ công cụ,
persona, thuật toán tóm tắt Companion và runtime Agent. Không chạy lại công cụ khi khôi phục lịch sử.

## Ranh giới hoàn tất

- `chat_turns.bind` ghi tin người dùng mới và liên kết request trong cùng `BEGIN IMMEDIATE`. Nếu giao dịch hỏng,
  không để lại tin người dùng đã nhận nhưng không gắn request. Retry/fork dùng ID tin đã có.
- `chat_turns.persist` chốt nội dung assistant, status, citations, work log, liên kết artifact đã kiểm owner/chat/version
  và trạng thái request trong cùng giao dịch. Chỉ sau commit thành công mới phát `done` và bật ghi nhớ nền.
- `complete` đã chốt là bất biến: mất ACK hoặc lưu lại cùng request không sinh thêm reply. Request ID đã nhận bị từ
  chối nếu gửi lại; nút Thử lại là một lần thử mới có ID riêng. Không cho sửa/thử lại tại chỗ khi lần cũ vẫn chạy.
- Nếu ghi cuối lỗi, không báo thành công; giữ checkpoint có trước, đánh dấu interrupted nếu DB còn ghi được và báo
  cần kiểm tra lịch sử. Nếu chính SQLite/ổ đĩa không còn ghi được, không bảo đảm lưu cả nhãn lỗi đó.
- Stop thắng khi đã ghi trạng thái dưới write lock trước lần chốt. Kết quả tới muộn không biến Stop thành complete.
  Nếu complete commit trước thì Stop không đổi nó thành stopped.
- Mỗi lần checkpoint/finalize kiểm lại owner, chat, project, archived và digest tin nguồn. Chat bị xóa không được tái
  tạo; đổi project/lưu trữ/sửa nguồn làm ngắt lượt. Đây là chặn ghi muộn, không thu hồi dữ liệu đã gửi provider trước đó.

## Checkpoint và phục hồi

Chat checkpoint khi nhận chunk sau ít nhất 1 giây hoặc thêm 2.048 ký tự, và buộc lưu khi có artifact, tool result,
note hoặc replace. Bản nháp bị thay/xóa phải thay cả checkpoint, không nối vào chữ cũ. Work log được chụp mà không
đóng các bước của luồng đang chạy. Checkpoint giới hạn 200.000 ký tự và có ghi chú nếu bị cắt; lần chốt bình thường
lưu toàn bộ phản hồi theo giới hạn provider hiện hành. Không thêm checkpoint theo từng token cho Companion.

Mất kết nối/đóng stream dùng `interrupted / stream_interrupted`; Stop dùng `stopped / user_stopped`; timeout có
trạng thái riêng. Khi tiến trình khởi động, lượt còn running trở thành `interrupted / process_restarted`, đóng các
bước work log còn live, giữ reply/artifact đã commit, hoặc tạo placeholder rỗng để giao diện nhận biết lượt bị ngắt.
Không phục hồi checkpoint của một attempt cũ đã được thay bằng attempt mới cùng tin nguồn.

Trình duyệt chỉ đọc lịch sử sau gián đoạn, không POST lại hoặc chạy lại model. Nó bỏ qua checkpoint còn running,
thử đọc có giới hạn, rồi yêu cầu người dùng xem lịch sử nếu chưa chốt được. UI phân biệt đang chạy, timeout, restart
và Stop. Mất mạng của máy khách không chứng minh provider đã ngừng hoặc chưa tính phí.

**Giới hạn:** hard kill có thể mất chữ sau checkpoint gần nhất. Tạo tài liệu/công cụ có giao dịch riêng; có thể bị
ngắt giữa việc tạo artifact và nhận chunk để gắn nó vào reply. Không có distributed transaction hoặc exactly-once
cho tác dụng phụ bên ngoài. Phục hồi không tự replay bất kỳ tool call nào; Thử lại do người dùng chọn có thể làm lại
công việc. Không hỗ trợ nhiều worker cùng tự nhận quyền phục hồi running; triển khai hiện tại dùng một tiến trình.

## Lượt lỗi trong ngữ cảnh

Câu hỏi của lượt error/timeout/interrupted được đưa lại như tham khảo lịch sử ở vai assistant, có nhãn không phải
việc đang chờ. Không bỏ mất phần reply đã có hoặc tệp nguồn; ảnh vẫn giữ vai user với nhãn tham khảo để tương thích
vision. Stop giữ hành vi đã có: lượt rỗng không tự sống lại, phần trả lời dở chỉ tiếp tục khi câu mới yêu cầu.
Lượt running cũ khi có câu hỏi mới cũng chỉ là tham khảo. Agent guidance chỉ đọc câu user còn hiệu lực.

Summary, first-user anchor và `read_chat_history` mang trạng thái nguồn và cùng quy tắc không tự làm lại yêu cầu cũ.
Đổi trạng thái turn vô hiệu summary đã phủ nguồn đó. Migration một lần bỏ cache v1 đã phủ lượt lỗi/running trước khi
có quy tắc mới; lịch sử gốc được giữ. Đặt tiêu đề và trích trí nhớ chỉ dùng Chat complete hoặc lịch sử legacy hợp lệ.
Đây là sửa biểu diễn context; không bảo đảm model luôn hiểu đúng chỉ nhờ một nhãn.

## Hợp đồng dữ liệu hiện hành

| Dữ liệu | Đọc/ghi | Khi xóa hoặc đổi phạm vi |
|---|---|---|
| Lịch sử, upload, reply/checkpoint, artifact của Chat | Theo owner và conversation; công cụ lịch sử không nhận ID chat khác từ model | Xóa chat xóa lịch sử, upload, context và các liên kết của chat theo cơ chế hiện có. Không tái tạo bằng kết quả tới muộn. |
| Rolling summary Chat | Chỉ một owner/chat/project, không phụ thuộc công tắc trí nhớ cá nhân | Sửa/xóa nguồn đã phủ, đổi project hoặc trạng thái lượt làm mất hiệu lực cache; fork không chép summary cũ. |
| Dự án | Hướng dẫn và tệp được chọn của đúng dự án có quyền | Chuyển chat không đem summary cũ sang. Chưa có kho project memory do model tự học riêng. |
| Trí nhớ cá nhân đã lưu | Sở thích/hồ sơ/chủ đề ngắn dùng chung Chat thường và Companion trong cùng tài khoản, kể cả khi đổi project; không dùng chat nhập vai cũ hoặc BYOK Companion | Xóa một chat **không tự xóa** mục cá nhân đã trích. Muốn quên phải xóa/sửa trong Trí nhớ. Không coi mục “Lĩnh vực” là kho memory cách ly theo project. |
| Summary Companion | Riêng mạch Companion, điều khiển bởi công tắc trí nhớ hiện hành | Xóa mạch hoặc quên trí nhớ vô hiệu summary theo watermark; không dùng trong Web Chat. |
| Chat tạm/retention/export và tìm nhiều chat | Chưa triển khai trong giai đoạn này | API từ chối các cờ `temporary`, `temporary_chat`, `retention`, `memory_scope` thay vì lặng lẽ lưu như chat thường. Không mở retrieval xuyên chat. |

**Memory OFF không phải Chat tạm:** ngừng dùng/trích saved personal memory theo cơ chế hiện có, không xóa lịch sử,
upload hay rolling summary cần cho chat đang mở. Bật lại bắt đầu từ mốc hiện tại, không học ngược tin trong thời gian
tắt. Nội dung đã gửi tới provider trước khi tắt không thể bị thu hồi bởi công tắc này.

## Không ghi lại dữ liệu đã quên từ tác vụ nền cũ

`companion_memory_state.revision` tăng khi sửa/xóa mục, quên summary hoặc đổi công tắc, kể cả OFF rồi ON rất nhanh.
Trước khi lưu kết quả model, transaction kiểm enabled + revision + nội dung/owner/chat/project/trạng thái của các
tin nguồn. Nguồn bị xóa/sửa/chuyển hoặc revision đổi thì bỏ cả kết quả và không dời cursor từ snapshot lỗi thời.
Kiểm tra này áp dụng cho ghi nhớ nền, xếp ghi nhớ cũ, “Bảo Peto…” và lưu summary Companion; không đổi persona của nó.

Khi xóa/quên trí nhớ, cursor được dời qua các tin đang có để lượt nền sau không đọc lại cùng nguồn chưa xử lý rồi
học lại điều vừa xóa. Summary Companion cũng được bỏ như trước. Nguồn chat vẫn còn có thể được đọc như lịch sử của
chat đó; lời nhắc mới của người dùng có thể tạo một ghi nhớ mới. Không cam kết xóa khỏi mọi bản sao/provider.
Nếu chat khác còn running, trích trí nhớ chưa dời cursor vượt qua lượt đó, tránh bỏ mất user/checkpoint có ID cũ
khi nó hoàn tất sau một chat khác.

## Triển khai và kiểm định

Migration SQLite tự chạy khi khởi động: thêm cột/trigger, giữ lịch sử và mục cá nhân hiện có. Không cần `.env` mới
hoặc cập nhật CLI. Frontend có thay đổi kiểu dữ liệu/nhãn và recovery, nên cần build lại trước khi restart backend.

Kiểm thử dùng SQLite tạm và model giả: rollback user/link, lỗi giữa reply và terminal state, ACK mất sau commit,
checkpoint/replace/truncation/restart, final persist lỗi, Stop, owner/project/delete/edit, tệp đúng phạm vi, cache
summary cũ, yêu cầu mới sau lỗi rỗng, OFF→ON/sửa/xóa trí nhớ và nguồn trong lúc tác vụ nền đang chạy. Không gọi API
trả phí hoặc phá tiến trình production để kiểm thử. Kết quả tự động không chứng minh chất lượng model thật.

Kết quả cuối ngày 21/10: backend **1.518 đạt, 1 bỏ qua** (350 giây). Nhóm phục hồi/trí nhớ/ghi chú riêng **91 đạt**,
component **23 đạt**, trình duyệt Chromium desktop và mobile giả lập **6 đạt**; build frontend và diff check đạt.
Lần hồi quy trước phát hiện Companion chỉ có private note bị lưu thành bubble rỗng; đã sửa giữ hành vi không lưu
bubble đó và chạy lại toàn backend. Bản kiểm thử trình duyệt dùng API giả, không đại diện điện thoại thật hoặc VPS.

Sau deploy, thử giới hạn một chat mới: Stop rồi hỏi câu khác, reload sau gián đoạn, kiểm tra không có reply trùng;
thử lại Haiku sau lỗi và câu hỏi mới. Hard restart chỉ thử trong môi trường giả có thể dừng được, không chủ động
restart production đang có người dùng chỉ để tạo lỗi. Giai đoạn 4 chờ nghiệm thu giai đoạn 3.
