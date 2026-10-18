# Nhật ký runtime, đầu vào bền vững và nghiệm thu — CLI 0.29.0

Ngày 19/10/2026. Áp dụng cho Peto Agent chạy tại máy người dùng; VPS tiếp tục xác thực, tính bước và gọi model.
Không thay đổi cơ chế cô lập thực thi, quyền shell, quyền sửa tệp hoặc kiến trúc frontend.

## Cơ sở OpenCode

Đối chiếu mã OpenCode **2.0.32**, commit **22e771f5893e255ea78fc10557ed3fb98d3a1072**, giấy phép MIT:

- [runner/step.ts](https://github.com/anomalyco/opencode/blob/22e771f5893e255ea78fc10557ed3fb98d3a1072/packages/core/src/session/runner/step.ts): công bố lời gọi trước khi thực thi.
- [runner/llm.ts](https://github.com/anomalyco/opencode/blob/22e771f5893e255ea78fc10557ed3fb98d3a1072/packages/core/src/session/runner/llm.ts): đối soát lời gọi dở, không tự phát lại thao tác.
- [inbox.ts](https://github.com/anomalyco/opencode/blob/22e771f5893e255ea78fc10557ed3fb98d3a1072/packages/core/src/session/inbox.ts),
  [store.ts](https://github.com/anomalyco/opencode/blob/22e771f5893e255ea78fc10557ed3fb98d3a1072/packages/core/src/session/store.ts),
  [execution.ts](https://github.com/anomalyco/opencode/blob/22e771f5893e255ea78fc10557ed3fb98d3a1072/packages/core/src/session/execution.ts): nhận tin, cập nhật trạng thái và quyền sở hữu vòng chạy.
- [Event stream architecture](https://github.com/anomalyco/opencode/blob/22e771f5893e255ea78fc10557ed3fb98d3a1072/specs/v2/event-stream-architecture.md): dữ liệu runtime và việc hiển thị có trách nhiệm riêng.

Đường dẫn ngoại tuyến nằm trong [bản đồ đọc](opencode-reading-map.md). Không chạy script hay cài OpenCode.
Peto tiếp thu các điều kiện lưu/khôi phục này bằng Python stdlib; không sao chép toàn bộ Core/Server/transport của OpenCode.
Trạng thái nghiệm thu là phần thích nghi cho Peto từ vấn đề kiểm tra sai phạm vi trong bài thử trước, không phải lời
khẳng định OpenCode có cùng một công cụ `record_acceptance`.

## 1. Nhật ký và phục hồi

`journal.py` lưu SQLite riêng cho từng dự án, máy chủ và mã phiên. SQLite dùng WAL, `synchronous=FULL`, giao dịch
ghi tuần tự và phiên bản schema. Một lần gọi model thật có mã request riêng; các lần retry của cùng bước có chung
mã bước logic. Công cụ có danh tính `(step UUID, ordinal)` nên provider tái sử dụng `call_id` không làm ghi đè.

Thứ tự bắt buộc:

1. Ghi ý định request rồi mới mở kết nối model. Có theo dõi cả compaction, tiêu đề, `/btw`, wrapup và agent con.
2. Nhận kết quả model: lưu response, transcript và các lời gọi pending trong cùng giao dịch trước khi chạy tool.
3. Đánh dấu tool running trước khi thực thi. Kiểm tham số/quyền và giới hạn công cụ vẫn áp dụng như trước.
4. Lưu kết quả thật, transcript và trạng thái công việc trong cùng giao dịch, **trước** khi gọi renderer báo kết quả.
5. Lỗi lưu trữ dừng vòng chạy trước công cụ tiếp theo. Không biến lỗi đĩa thành một kết quả tool bình thường rồi chạy tiếp.

Khóa phiên do hệ điều hành giữ ngăn hai CLI chạy đồng thời cùng phiên; tiến trình chết thì khóa tự nhả.
Khóa này bảo vệ vòng điều phối, không phải sandbox hay quyền thực thi.

| Thời điểm bị tắt | Khi mở `/resume` |
|---|---|
| Tin đã nhận nhưng chưa gọi model | Giữ trong `/pending`; chưa tự gửi model |
| Request chưa có kết quả hoàn tất | Đánh dấu chưa rõ kết quả; không tự gửi lại khi mở phiên |
| Tool pending/running chưa có kết quả đã lưu | Đánh dấu bị ngắt; running có thể đã gây tác dụng phụ |
| Kết quả tool đã lưu, renderer chưa vẽ hoặc bị lỗi | Giữ nguyên kết quả đã lưu; không chạy lại tool |

Không thể bảo đảm “exactly once” giữa SQLite và một lệnh shell/dịch vụ bên ngoài: tiến trình có thể chết sau tác dụng
phụ nhưng trước lúc lưu kết quả. Peto ghi nhận sự không chắc chắn và yêu cầu kiểm tra trạng thái thật khi người dùng
chủ động tiếp tục; không suy từ thiếu kết quả rằng thao tác chưa chạy. `/resume` không gọi model hoặc chạy lại tool.
Retry mạng trong một vòng chạy vẫn theo chính sách cũ; journal chỉ ghi rõ từng request, không tự mở thêm retry trả phí.

Agent con khám phá có bước/lời gọi/kết quả riêng trong nhật ký; không ghi đè transcript của agent chính. Khi crash giữa
agent con, thao tác explore của agent chính bị ngắt, không tự chạy lại cả cây. Lệnh nền, trình duyệt và MCP vẫn có vòng
đời tiến trình cũ; không phục hồi hay tự khởi động lại các tiến trình bên ngoài.

## 2. Ranh giới lỗi giao diện

`observer.py` bọc các thông báo quan sát: bắt đầu/kết thúc tool, preview, tiến độ, lời trả lời đang stream, tiêu đề,
kế hoạch và thống kê. Lỗi renderer không được đổi kết quả thành công thành lỗi tool hay khiến model lặp thao tác.
Phương thức quan sát đã lỗi được ngừng gọi; log chỉ có tên phương thức và lớp lỗi, không có nội dung exception.

Các tương tác xin quyền/hỏi người dùng là ranh giới khác: lỗi tương tác trả về từ chối/bỏ qua, không tự cấp quyền.
Các quyền đã được người dùng cho phép qua chính sách vẫn giữ nguyên. `KeyboardInterrupt` không bị nuốt.
Nguồn khôi phục transcript/kết quả là runtime, không phải các khối đã vẽ trong terminal.

Đây là tách trách nhiệm và lỗi trong CLI hiện tại. Lời gọi renderer vẫn đồng bộ: renderer bị treo có thể làm chậm
runtime. Không có daemon hay transport UI độc lập như toàn bộ OpenCode V2; đóng terminal vẫn ngắt runtime cục bộ,
sau đó dùng `/resume`. Việc dựng lại màn hình và các thao tác hiển thị vẫn dùng renderer hiện có.

## 3. Đầu vào bền vững

TerminalUI ghi đầu vào xuống inbox **trước** khi xóa ô nhập hay xác nhận Enter. Nếu lưu thất bại, chữ và ảnh còn trong
ô nhập. Tin có mã admission, thứ tự nhận và kiểu input/steer/queue. Nhận lại cùng admission ID giữ payload đầu tiên.
Tiêu thụ tin và thêm vào transcript là một giao dịch; không có cửa sổ đánh dấu đã nhận nhưng mất tin, hoặc thêm trùng.
Lỗi vẽ khung tin không làm mất receipt đã lưu.

- Tin nhắn thêm khi đang chạy vẫn lái yêu cầu ở ranh giới bước tiếp theo.
- Lệnh `/...` đang xếp hàng không được tự chèn vào prompt hay tự chạy sau crash.
- `/pending` xem tin chưa tiêu thụ: gửi đúng tin và ảnh đã lưu, hoặc xóa tin. Với lệnh điều khiển chỉ điền lại ô nhập;
  người dùng phải bấm Enter để thực thi.
- Mở lại phiên giữ tin chờ và thông báo số lượng; không tự gửi tin nào. Tin cùng chữ nhưng khác ảnh là đầu vào khác.
- Ảnh công cụ đã lưu nhưng chưa kịp chèn vào transcript được đối soát khi mở lại, không chụp lại để lấy ảnh đó.

UI chữ thường không có hàng đợi nhập song song; Session lưu đầu vào khi nhận từ prompt. Bộ tương thích UI cũ chỉ có
thể lưu steer khi được poll; bảo đảm “Enter đã lưu” áp dụng cho TerminalUI mới có callback admission.

## 4. Trạng thái công việc và nghiệm thu

`task_state.py` lưu mục tiêu hiện tại, kế hoạch, phiên bản thay đổi, artifact/hash, các quan sát công cụ và tiêu chí
nghiệm thu. Dữ liệu này không phụ thuộc phần tóm tắt model, nên compaction và `/resume` giữ được các mục đã xác minh,
chưa xác minh và đã lỗi thời. Nó không chứa quyền thực thi; `/resume` vẫn buộc đọc lại trước khi sửa và xóa quyền tạm.

Khi cả CLI và backend thương lượng `task_state`, kết quả tool có `evidence_id` do runtime cấp và model có công cụ
`record_acceptance(criterion, status, evidence_ids, note)`. Các trạng thái: passed, failed, unverified.

- Không chấp nhận ID bịa hoặc ID ngoài phiên. Passed/failed phải có bằng chứng, note phải mô tả phạm vi/lý do.
- Passed chỉ tham chiếu công cụ kiểm tra thật, phiên bản hiện tại, không có lỗi hoặc mã thoát khác 0.
  Ghi tệp, tick kế hoạch và chính lời tự nghiệm thu không được làm bằng chứng kiểm tra.
- Sửa artifact làm tiêu chí cũ thành stale. Hash khác do sửa bên ngoài cũng làm hết hiệu lực; đọc/kiểm lại cập nhật
  phiên bản quan sát để có thể nghiệm thu bản mới.
- `reported_by=agent`: runtime kiểm nguồn bằng chứng và độ mới, không chứng minh nội dung kết luận đúng ngữ nghĩa.
  Đọc được tệp hay script thoát 0 chỉ chứng minh phạm vi đã kiểm, không chứng minh game/ứng dụng dùng được.
- Những tiêu chí chưa đạt được nhắc một lần trước khi kết thúc; nếu không thể kiểm thì phải nêu giới hạn.
  Tiêu chí đã đạt tránh yêu cầu lặp thêm phép kiểm không liên quan chỉ vì vừa sửa tệp.

Trạng thái đầy đủ giữ tối đa 100 bằng chứng gần nhất và 30 tiêu chí; nhật ký và transcript/archive giữ các kết quả
cũ theo giới hạn output hiện có. Projection gửi model khoảng 14.000 ký tự, ưu tiên tiêu chí chưa đạt, kèm số mục bị
lược. `read_history` vẫn tra các kết quả/tiêu chí công cụ trong archive trước compaction. Backend chặn khóa lạ và
projection quá lớn; đây là dữ liệu lịch sử, không phải chỉ dẫn hoặc quyền mới.

## Lưu trữ và tương thích

Trong thư mục phiên của dự án ở `%LOCALAPPDATA%\PetoAgent\sessions\<project hash>\`:

- `<session id>.json`: bản xuất tương thích, có marker `runtime_managed` với phiên mới.
- `runtime/<server + session hash>.sqlite3`: snapshot chuẩn, events, requests, executions, calls và inbox.
- Các tệp `-wal`, `-shm`, `.lock` đi cùng SQLite/khóa. `.deleted` là dấu xóa để chặn callback về muộn làm sống lại phiên.

Nếu đặt `PETO_AGENT_HOME`, các dữ liệu này nằm dưới `sessions` ở nơi đó. Journal chứa nội dung request/tool và ảnh
giống lớp dữ liệu lịch sử cục bộ; không chứa HTTP authorization header hay tự lưu API key. `/btw` chỉ lưu vòng đời,
không lưu câu hỏi/câu trả lời riêng. Nội dung người dùng tự đưa vào tệp/prompt vẫn có thể nằm trong lịch sử.

SQLite thắng JSON cũ hoặc thiếu. Nếu JSON đánh dấu managed nhưng mất journal, hoặc journal hỏng, CLI dừng rõ lỗi;
không âm thầm lấy JSON cũ rồi chạy tiếp. JSON phiên cũ chưa managed vẫn mở được. Schema SQLite mới hơn CLI hiện tại
bị từ chối để tránh sửa dữ liệu không hiểu. Đổi tên chỉ cập nhật metadata, không thay transcript bằng bản cũ.

Xóa và dọn phiên cũ khóa đúng phiên trước; phiên đang thực thi được bỏ qua khi dọn. Chính sách 50 phiên/30 ngày vẫn
áp dụng cho phiên có bản xuất JSON; inbox-only chưa có JSON được giữ để không mất tin chưa chạy, cần xóa chủ động.
Tệp tombstone/lock nhỏ có thể còn sau khi xóa. Journal không giới hạn tổng số event của một phiên; yêu cầu dài có thể
tốn thêm dung lượng do lưu request và trạng thái. Output vẫn chịu giới hạn producer/preview cũ, không phải stdout vô hạn.

Nên đóng CLI rồi sao lưu **cả thư mục phiên**, gồm archive và SQLite. Nếu sao lưu lúc đang chạy cần dùng cơ chế backup
SQLite phù hợp, không chỉ chép `.sqlite3` và bỏ WAL. Không xóa riêng journal rồi trông đợi JSON phục hồi chính xác.
CLI cũ chỉ đọc bản xuất JSON và không có bảo đảm journal/inbox mới; tránh hạ phiên bản để tiếp tục một tác vụ bị ngắt.

## Triển khai và xác minh

Cập nhật backend để quảng bá `task_state`, sau đó cập nhật CLI lên **0.29.0** bằng cách cài/cập nhật hiện có.
Không cần thêm dependency, biến môi trường hoặc migration cơ sở dữ liệu Web. CLI mới dùng journal/UI/inbox với
backend cũ được; công cụ nghiệm thu và projection chỉ bật khi backend quảng bá tính năng tương ứng.

Các kiểm thử dùng model giả, dự án tạm và cả tiến trình con tắt bằng `os._exit` trước/sau lúc lưu kết quả; không gọi
API trả phí. Chạy từ `agent-cli`: `python -m pytest tests -q`; chạy backend các module Agent/API/schema/provider/guide/
installer. Wheel được dựng bằng bộ đóng gói hiện có của backend. Không chạy `pytest` toàn cây eval fixture vì có những
dự án mẫu được cố ý để lỗi phục vụ bài thi.

Kết quả chốt: **656/656 kiểm thử CLI**, **83/83 kiểm thử backend Agent/API/schema/provider/guide/installer** đạt.
Kiểm thử installer đã cài wheel vào thư mục tạm rồi chạy CLI kiểm phiên bản. Gói `peto-0.29.0-py3-none-any.whl`
được dựng riêng ở `.runtime/build/`, mọi module Python trong gói đều biên dịch được. `git diff --check` đạt.

Chưa kiểm thử với provider thật, VPS thật, mất điện vật lý hoặc renderer bị treo vô hạn. Các thay đổi chưa được
commit, triển khai hay cài đè CLI trên máy người dùng trong đợt này.
