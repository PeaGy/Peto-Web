# Kế hoạch Peto Agent / CLI

Cập nhật: 11/09/2026, sau khi người dùng làm rõ nơi thực thi công việc.
Trạng thái: lập kế hoạch; chưa triển khai CLI, bộ điều phối agent hoặc Docker.
Tài liệu ghi lại định hướng, không phải yêu cầu tự động triển khai hay thay đổi VPS.

## Hướng hiện hành

Người dùng muốn mở Peto CLI trên Windows và nhờ Peto sửa trực tiếp dự án trên
máy mình, trong khi dịch vụ Peto vẫn được triển khai trên VPS.

**VPS điều phối; Windows thực thi.** Hướng này thay thế phương án Work thực thi
trong Docker trên VPS được ghi trước đó do hiểu nhầm yêu cầu.

## Những quyết định đã làm rõ

- Ưu tiên agent hỗ trợ viết code, thao tác trình duyệt rồi mở rộng sang ứng dụng.
- Peto CLI trên Windows nhận yêu cầu, hiển thị tiến trình, thực thi công cụ trong
  phạm vi được cho phép và trình bày phần thay đổi cùng kết quả kiểm tra.
- VPS phục vụ tài khoản, gọi mô hình AI và điều phối vòng làm việc. Chưa chốt
  đổi nhà cung cấp hoặc chạy mô hình trực tiếp trên VPS.
- Tận dụng dự án Peto-Web hiện tại. Cách tổ chức package/thư mục CLI sẽ chốt khi
  triển khai; không cần clone nguyên một dự án mẫu để thay Peto.
- Chat và tạo ảnh trên web vẫn được giữ. Work trên web là khả năng mở rộng sau
  này, không còn là giao diện bắt buộc cho bản agent đầu.
- Không cần desktop app có giao diện đồ họa. CLI là chương trình kết nối và
  thực thi trên máy Windows, không phải chỉ là màn hình nhập lệnh từ xa.
- Docker không bắt buộc cho bản đầu. Nếu dùng Docker để cách ly công việc cục bộ,
  Docker chạy trên Windows. Đóng gói backend trên VPS là một quyết định riêng.

## Kiến trúc dự kiến

```text
Windows của người dùng
└── Peto CLI, mở trong thư mục dự án được chọn
    ├── Nhận yêu cầu và hiển thị tiến trình
    ├── Kiểm tra quyền dùng công cụ tại máy người dùng
    ├── Đọc/sửa tệp, chạy lệnh và kiểm tra code
    ├── Điều khiển trình duyệt cục bộ khi đã bổ sung công cụ
    └── Gửi kết quả công cụ về VPS
               ↕ Kết nối có xác thực
VPS
└── Dịch vụ Peto
    ├── Tài khoản và Peto Web hiện tại
    ├── Gọi mô hình AI
    ├── Điều phối bước tiếp theo và lưu trạng thái tác vụ
    └── Gửi yêu cầu dùng công cụ xuống đúng phiên CLI
```

Ví dụ: mở CLI trong C:\Projects\website-a, yêu cầu sửa lỗi đăng nhập. Peto
điều phối trên VPS; CLI đọc/sửa tệp và chạy kiểm tra ngay trong website-a trên
Windows. Kết quả công cụ được trả về để mô hình tiếp tục hoặc báo hoàn tất.

Không cần tải toàn bộ repository lên VPS trước. Tuy nhiên, nội dung tệp, đoạn
code và kết quả lệnh cần cho suy luận có thể đi qua VPS tới nhà cung cấp AI.
Không mô tả kiến trúc này là xử lý hoàn toàn offline hoặc code không rời máy.
Phạm vi ngữ cảnh gửi đi và xử lý thông tin nhạy cảm cần được thiết kế rõ.

## Phạm vi bản thử đầu

1. Kết nối/đăng nhập CLI với dịch vụ trên VPS và chọn thư mục dự án.
2. Đọc, tìm kiếm, sửa tệp và chạy kiểm tra phù hợp trên Windows.
3. Quan sát kết quả công cụ, điều chỉnh khi lỗi và trình bày phần thay đổi.
4. Hiện tiến trình, cho dừng và lưu kết quả cục bộ.
5. Bổ sung chạy website thử và kiểm tra bằng trình duyệt cục bộ.

Bài thử đầu: mở CLI trong dự án thử trên Windows → giao một lỗi nhỏ → Peto sửa
code tại máy → chạy kiểm tra → trình bày phần thay đổi và kết quả. Khi công cụ
trình duyệt đã có, thêm bước kiểm tra giao diện website thử.

Giữ tính cách Peto. Thành công phải dựa trên kết quả công cụ, không chỉ lời mô hình.
Không mang trở lại giới hạn ký tự hoặc cơ chế quyền riêng của Discord.

## Quyền thực thi, dữ liệu và gián đoạn

- CLI kiểm tra quyền cục bộ trước khi thực thi yêu cầu từ VPS. VPS không mặc
  nhiên có quyền đọc toàn bộ máy hoặc chạy mọi lệnh.
- Kiểm soát đường dẫn, phạm vi thư mục, quyền chạy lệnh và hành động ra bên ngoài.
  Giới hạn thư mục trong công cụ đọc tệp không tự cách ly lệnh shell tùy ý;
  cách kiểm soát shell/sandbox cần được chốt và kiểm tra khi triển khai.
- Bảo toàn thay đổi có sẵn của người dùng; không tự ghi đè, reset hoặc xóa công việc.
  Nếu sửa Peto-Web thì sửa checkout cục bộ, không sửa bản đang chạy trên VPS.
- Code và tệp đầu ra nằm tại dự án/vùng làm việc cục bộ. Mất kết nối không được
  tự xóa kết quả hoặc tự phát lại lệnh có tác dụng phụ.
- Phiên đăng nhập, tác vụ, thiết bị và kết quả công cụ phải gắn đúng chủ sở hữu.
- Có giới hạn thời gian/số bước và cơ chế dừng tiến trình đang chạy, không chỉ
  ngừng hiển thị câu trả lời. Mức giới hạn cụ thể chưa chốt.
- Chỉ dẫn trong tài liệu, trang web hay kho mã không tự cấp thêm quyền cho agent.
- Trình duyệt cục bộ dự kiến dùng phiên riêng; dùng phiên đăng nhập có sẵn cần
  lựa chọn và cấp quyền rõ ràng.
- Khi CLI đóng, máy ngủ hoặc mất mạng, VPS không thể tiếp tục thực thi công cụ
  trên Windows. Chạy nền, kết nối lại và khôi phục tiến độ cần được xây riêng.

## Vai trò VPS và tài nguyên

Số liệu người dùng cung cấp ngày 11/09/2026: 2 vCPU; RAM tổng 3,7 GiB, khả dụng
2,6 GiB tại thời điểm đo; ổ chính còn khoảng 28 GB; chưa có swap. Máy đang chạy
Peto Web, bot Discord, bgutil-pot, cloudflared, warp-svc và các dịch vụ hệ thống.

Theo kiến trúc mới, build code và trình duyệt chạy trên Windows. Không dùng số
liệu VPS để suy ra sức chứa tác vụ cục bộ. VPS vẫn cần đo tải cho kết nối,
điều phối, lưu trạng thái và dịch vụ web. Chưa đo cấu hình Windows, chưa chốt
số tác vụ đồng thời, chưa cần quyết định nâng cấp VPS hay cài Docker để bắt đầu CLI.

## Những lựa chọn còn mở

- Ngôn ngữ/package CLI, cách cài đặt và cập nhật trên Windows.
- Giao thức kết nối, xác thực thiết bị và quản lý phiên CLI với VPS.
- Framework agent hoặc cách mở rộng vòng công cụ hiện có; chưa cần nhiều agent.
- Chính sách quyền shell, cách ly và Docker cục bộ nếu cần.
- Lưu tiến độ, hủy tác vụ, khôi phục kết nối và chống thực thi lặp.
- Công cụ trình duyệt, ứng dụng Windows và phạm vi quyền cụ thể.
- Work trên web hoặc desktop GUI sau này; không bắt buộc trong bản đầu.

## Nguồn tham khảo

- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling?api-mode=responses)
- [xAI Function Calling](https://docs.x.ai/developers/tools/function-calling)
- [Hugging Face Agents Course](https://huggingface.co/learn/agents-course/en/unit0/introduction)
- [GenAI Agents](https://github.com/NirDiamant/GenAI_Agents)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Docker Security](https://docs.docker.com/engine/security/) — khi chọn cách ly bằng Docker.
