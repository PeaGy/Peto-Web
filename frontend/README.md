# Cấu trúc

`src/main.tsx` chọn ứng dụng chính hoặc Docs theo URL. Mỗi mục có thư mục riêng:

```text
src/
  app/                         Khung ứng dụng, sidebar, đăng nhập, tài khoản
  features/
    chat/                      Tin nhắn, Markdown, ô soạn, tệp đính kèm
    companion/
      characters/              Live2D, VRM, nhập model, biểu cảm, chuyển động
      speech/                  Giọng nói, micro, nhận diện tiếng nói, worklet
    imagine/                   Tạo ảnh và thư viện
    projects/                  Thư mục dự án, tên dự án trên chat, chuyển chat
    documents/                 Tài liệu, bản xem trước, chỉnh sửa, xuất tệp
    connectors/                Cài đặt kết nối GitHub, cấp quyền và quản lý repo
    diagrams/                  Sơ đồ Mermaid và bảng sơ đồ
    docs/                      Trang hướng dẫn công khai
    settings/                  Hộp cài đặt và các mục tài khoản, Agent, trí nhớ
  shared/
    api/                       Hợp đồng dữ liệu và kết nối backend
    markdown/                  Plugin Markdown, công thức, tô màu mã
    ui/                        Thành phần UI dùng chung
    styles/                    Nền, màu, tương tác và điểm nhập CSS
```

## Đặt mã mới ở đâu

- Mã chỉ phục vụ một tính năng nằm trong thư mục tính năng đó, cạnh CSS liên quan. Ví dụ giới hạn tệp của chat nằm ở `features/chat/attachments.ts`; preset biểu cảm nằm ở `features/companion/characters/`.
- Chỉ chuyển vào `shared/` khi nhiều phần thực sự dùng cùng một chức năng. Feature không import từ `app/`; khung ứng dụng truyền dữ liệu và callback xuống.
- `app/App.tsx` điều phối đăng nhập, phiên chat, gửi/dừng, điều hướng và các bảng. `app/Sidebar.tsx` dựng thanh bên; `features/chat/ChatMessage.tsx` dựng tin nhắn và giữ memoization; `app/LoginScreen.tsx` dựng màn đăng nhập.
- Import trực tiếp module cần dùng. Tránh một `index.ts` xuất toàn bộ các feature: nó dễ kéo cả Live2D, VRM hoặc Mermaid vào lần mở chat đầu tiên.

## CSS và tải riêng

`shared/styles/styles.css` là danh sách import có thứ tự, dùng bởi App và các trang kiểm tra giao diện. CSS từng phần nằm cạnh tính năng. Thứ tự này giữ nguyên cách áp dụng quy tắc của giao diện cũ, kể cả quy tắc trên điện thoại và các thành phần dùng chung giữa Chat và Companion. Đừng đổi thứ tự hoặc import lại từng tệp từ component nếu chưa kiểm tra ảnh hưởng.

Một vài tệp trong `app/`, như `mobileShell.css` và `conversationControls.css`, nối nhiều thành phần của khung ứng dụng. Quy tắc khoảng trống cho nút sửa phải có phạm vi `.chat .bubble.user`; áp dụng lên `.bubble.user` chung sẽ tạo khoảng trống trong Companion. Bong bóng và composer chung vẫn được Companion tùy biến bên trong `.companion`.

Docs có điểm nhập CSS riêng trong `features/docs/docs.css`. CSS bảng tài liệu và bảng sơ đồ tiếp tục được import từ module tương ứng. Imagine, Companion, các mục Settings, bộ tô màu mã, công thức, Mermaid và bộ dựng nhân vật tiếp tục tải qua dynamic import. Worklet nghe nằm cùng `hearingCapture.ts`; giữ hậu tố `?url&no-inline` để Vite xuất thành tệp riêng.

## Kiểm tra

Từ thư mục `frontend/`:

```sh
npm test
npm run build
npm run dev
```

Test ở `tests/`, các trang kiểm tra trình duyệt ở `tests/fixtures/`; các trang này không nằm trong bản build sản xuất. Khi chuyển module, cập nhật cả import của source, test, mock và fixture. Kiểm tra thêm Chat, Tạo ảnh, Companion và Docs ở PC/điện thoại nếu thay đổi CSS hoặc cách tải module.
