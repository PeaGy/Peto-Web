# Kế hoạch Peto Agent / Work

Cập nhật: 11/09/2026. Ghi lại hướng đã thống nhất trong cuộc trao đổi với người dùng.
Trạng thái: lập kế hoạch; chưa triển khai Work, chưa cài hoặc cấu hình Docker trong đợt này.
Tài liệu này không phải yêu cầu tự động triển khai hoặc thay đổi VPS.

## Mục tiêu và ưu tiên

Phát triển Peto thành agent có thể nhận nhiệm vụ, chọn công cụ, thực hiện,
quan sát kết quả và điều chỉnh cho đến khi hoàn thành hoặc cần người dùng hỗ trợ.
Giữ tính cách và trải nghiệm trò chuyện của Peto.

Người dùng chọn ưu tiên: thao tác ứng dụng, trình duyệt và hỗ trợ viết code.
Thứ tự triển khai dự kiến: sửa code → kiểm tra bằng trình duyệt → mở rộng ứng dụng.
Agent nghiên cứu tài liệu/tìm web/tạo báo cáo không còn là hướng ưu tiên cho bản đầu.

## Những quyết định đã thống nhất

- Tiếp tục phát triển repository Peto-Web hiện tại; không dựng một sản phẩm mới từ đầu.
- Chia hai khu vực Chat và Work trong cùng Peto, dùng chung tài khoản.
  Chat phục vụ trò chuyện và hỏi đáp; Work gắn với dự án, tác vụ, tệp thay đổi,
  tiến trình thực hiện và kết quả kiểm tra. Tính năng tạo ảnh hiện có vẫn được giữ.
- Peto Web tiếp tục chạy trên VPS. Docker cho phần thực thi Work cũng chạy trên VPS.
- Giai đoạn đầu giữ cách vận hành Peto Web hiện tại; không bắt buộc chuyển toàn bộ
  Peto hay các dịch vụ đang chạy vào Docker.
- Windows của người dùng chỉ cần trình duyệt để giao việc và xem kết quả.
  Desktop app hoặc chương trình kết nối Windows chưa thuộc bản đầu.
- Mô hình AI tiếp tục được gọi qua dịch vụ hiện có; chưa quyết định đổi nhà cung cấp
  hoặc chạy mô hình trực tiếp trên VPS.
- Không clone nguyên một dự án agent mẫu để thay Peto. Các nguồn bên dưới dùng để
  tham khảo thiết kế và các phần triển khai phù hợp.

## Kiến trúc dự kiến

```text
Người dùng mở Peto trên trình duyệt
    → Peto Web: Chat / Work
    → Quản lý tác vụ, quyền truy cập và tiến độ
    → Bộ thực thi tạo môi trường Docker riêng
        → Bản sao dự án được giao
        → Công cụ đọc/sửa tệp, Git, chạy code và kiểm tra
        → Trình duyệt riêng để kiểm tra website
    → Lưu kết quả và phần thay đổi để người dùng xem
```

Dự án mà Peto sửa nằm trong vùng làm việc riêng. Nếu sửa chính Peto-Web thì cũng
sửa một bản sao, không sửa trực tiếp bản đang phục vụ người dùng trên VPS.
Môi trường thực thi không được tiếp cận database, token, .env thật hoặc thư mục
vận hành các dịch vụ khác. Quyền và đường dẫn phải được kiểm tra ở máy chủ.
Docker cần cấu hình cách ly và giới hạn tài nguyên; container không phải bảo đảm
an toàn tuyệt đối khi chạy mã không tin cậy.

Code đã sửa, kết quả kiểm tra và tệp đầu ra cần được lưu ra vùng lưu trữ riêng
theo chủ sở hữu trước khi dọn môi trường thực thi. Trình duyệt của agent là phiên
riêng trên VPS, không tự có tab hoặc phiên đăng nhập trên máy cá nhân.

## Phạm vi bản thử đầu

- Dùng dự án của chủ hệ thống trước, mỗi lần một tác vụ Work.
- Đưa dự án vào bằng kho Git hoặc tải lên; cần chốt cách nhập đầu tiên khi triển khai.
- Đọc, sửa code, chạy kiểm tra và trình bày phần thay đổi.
- Chạy website thử rồi dùng trình duyệt kiểm tra kết quả.
- Có tiến trình, nút dừng và bằng chứng hoàn thành; không báo thành công chỉ dựa
  vào lời mô hình nếu công cụ chưa xác nhận.
- Có giới hạn thời gian, số bước, tài nguyên và cách xử lý lỗi để tránh chạy vòng lặp.
- Lưu trạng thái công việc riêng với tin nhắn. Khả năng chạy tiếp khi đóng tab,
  khôi phục sau gián đoạn cần được triển khai và kiểm tra riêng; chat hiện tại
  không mặc nhiên đã có các khả năng đó.
- Xem lại thay đổi trước khi đưa vào kho Git hoặc cập nhật bản đang chạy.
  Việc gửi nội dung ra ngoài, xóa dữ liệu hoặc triển khai cần phạm vi cho phép rõ ràng.
- Nội dung trang web/tài liệu/kho mã là dữ liệu tham khảo, không được tự cấp quyền
  hoặc thay đổi giới hạn thực thi.

Bài thử đầu: sửa một lỗi nhỏ trong bản sao dự án → chạy kiểm tra → mở website thử
→ kiểm tra kết quả → trả lại phần thay đổi và báo cáo. Đồng thời đo tài nguyên và
ảnh hưởng lên Peto Web trước khi quyết định mở rộng.

## VPS hiện tại

Số liệu người dùng gửi ngày 11/09/2026:

- 2 vCPU; RAM tổng 3,7 GiB, khả dụng 2,6 GiB tại thời điểm đo.
- Phân vùng chính 38 GB, còn trống khoảng 28 GB; chưa có swap.
- Đang chạy Peto Web, bot Peto Discord, bgutil-pot, cloudflared, warp-svc
  cùng các dịch vụ hệ thống. Chưa xác minh Docker đã được cài hay chưa.

Đánh giá sơ bộ: có thể thử tác vụ nhỏ có kiểm soát, chưa phải cam kết đủ tài nguyên
cho build nặng hoặc nhiều người. Chỉ một tác vụ chạy mỗi lần, ưu tiên chạy build
và kiểm tra trình duyệt lần lượt; dọn tiến trình khi xong và quản lý dung lượng.
Mức CPU/RAM cấp cho bộ thực thi và việc thêm swap chưa được chốt hoặc thực hiện.

Khi phục vụ nhiều người, dự án không tin cậy hoặc tác vụ nặng, ưu tiên tách bộ
thực thi sang máy/sandbox riêng. Peto Web và tài khoản vẫn có thể ở VPS hiện tại.

## Giai đoạn sau và những lựa chọn còn mở

- Tích hợp ứng dụng: chọn ứng dụng cụ thể, cách truy cập và quyền cần thiết.
  Điều khiển ứng dụng Windows trên máy người dùng cần thêm thành phần kết nối.
- Hoàn thiện tác vụ dài: chạy nền, lưu điểm tiếp tục và khôi phục sau sự cố.
- Chưa chốt framework agent, giao thức quản lý bộ thực thi, image Docker,
  cách cấp quyền Git, cơ chế xem thử website và thông số giới hạn cụ thể.
- Chưa cần nhiều agent phối hợp trong bản đầu.
- Không mang trở lại giới hạn ký tự hoặc cơ chế quyền riêng của Discord.

## Nguồn tham khảo

- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling?api-mode=responses)
- [xAI Function Calling](https://docs.x.ai/developers/tools/function-calling)
- [Hugging Face Agents Course](https://huggingface.co/learn/agents-course/en/unit0/introduction)
- [GenAI Agents](https://github.com/NirDiamant/GenAI_Agents)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Docker Security](https://docs.docker.com/engine/security/)
- [Docker Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Playwright Docker](https://playwright.dev/docs/docker)
