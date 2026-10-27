# Ghi nhớ tự động: đúng chủ thể, có căn cứ, có giá trị lâu dài

Triển khai ngày 27/10/2026 sau báo cáo mèo Blue của người khác bị đưa vào Hồ sơ tài khoản.
Chưa có hội thoại gốc/log extractor của sự cố nên không khẳng định một nguyên nhân duy nhất.

## Các điểm quan sát được trong mã cũ

- `SYSTEM_PROMPT` yêu cầu chi tiết không có chủ ngữ; ví dụ là “Nuôi một con mèo tên Mơ”.
- Bộ trích chỉ thấy các tin mới, không có vài tin trước đó để giải đại từ/quan hệ sở hữu.
- Hội thoại được ghép thành dòng `User:`/`Peto:` không có ID. `parse_changes` chấp nhận câu tự do của model,
  không yêu cầu chỉ ra lời người dùng hỗ trợ một dữ kiện mới; rewrite cả mục có thể bỏ những ý không được lặp lại.

## Luồng mới

1. Vẫn một lượt `_ask` chạy nền sau Chat/Companion đủ điều kiện; không thêm model kiểm duyệt hay dịch vụ ngoài.
2. Giữ nguyên cửa sổ 12 tin mới. Đọc tối đa 4 tin trước đó mỗi mạch, trả tổng tối đa 12 tin ngữ cảnh, theo đúng owner,
   chế độ, thẻ Peto gốc, provider và ranh giới bật/tắt/xóa trí nhớ. Không đọc lịch sử tùy ý.
3. Gửi JSON phân biệt `context_only`/`new_messages`; mỗi tin có ID, conversation, role, text và cờ truncated.
   Mỗi text tối đa 1.500 ký tự. Tin bị cắt và tin cũ chỉ giúp hiểu bối cảnh, không cấp căn cứ lưu dữ kiện mới.
4. `AUTO_SYSTEM_PROMPT` yêu cầu chủ thể, độ chắc chắn, tính lâu dài và bằng chứng cho mỗi ý mới. Chỉ nhận
   `subject=user`, `certainty=explicit`, `retention=lasting` cùng ID của tin người dùng **mới** và toàn bộ lời gốc đã
   chuẩn hóa khoảng trắng. Không nhận ID assistant, ID bịa, trích đoạn bỏ mất các từ xác định chủ thể hay nguồn bị cắt.
5. `memory_grounding.filter_changes` bỏ câu chuỗi tự do thiếu bằng chứng và đề xuất về người khác/suy đoán/tạm thời.
   Một số dấu hiệu VI/EN về người khác, sở hữu bị phủ định, giả định, dịch câu hoặc mất ảnh/tệp cũng khiến ý mới bị bỏ,
   kể cả model gắn nhãn chắc chắn sai. Không có ngoại lệ hard-code riêng tên Blue.
6. Giữ nguyên các ý cũ mặc định. Thêm ý không được xóa tuổi/nghề/sở thích chỉ vì lần này model không nhắc lại.
   Tiêu đề/tóm tắt model của mục cũ không được dùng để đưa lại ý bị từ chối; tóm tắt mục mới lấy từ nội dung được nhận
   hoặc mô tả cố định của Hồ sơ/Cách trả lời.
7. Đính chính/bỏ từng ý cần `forget` với nguyên văn ý cũ và căn cứ lời người dùng mới. Xóa cả mục cần yêu cầu quên
   rõ ràng. Khi thực sự bỏ ý, reset tóm tắt của mục còn lại và xóa summary Companion trong **cùng transaction**.
   Kết quả cũ bị từ chối không được xóa summary hay đẩy cursor. Xóa/quên cũng dời ranh giới context để tin cũ không bị
   đọc lại làm tham chiếu. Mục người dùng vừa sửa tay được bảo vệ bằng revision/updated_at.

Ví dụ output tự động:

```json
{
  "entries": [{
    "section": "you", "title": "Hồ sơ",
    "details": [{
      "text": "Người dùng nuôi mèo tên Mơ",
      "subject": "user", "certainty": "explicit", "retention": "lasting",
      "evidence": {"message_id": 123, "quote": "Mình nuôi mèo tên Mơ."}
    }]
  }],
  "remove": []
}
```

## Tương thích và giới hạn

- Mục Trí nhớ vẫn nhận chuỗi chi tiết như trước; API sửa tay, Hoàn tác và “Bảo Peto…” không đổi schema.
  Lời nhắc chung giữ rõ chủ thể cho cả thao tác trên trang Trí nhớ và xếp ghi nhớ legacy.
- Thông tin của người khác không tự thêm vào trí nhớ cá nhân; khi cần nhớ một quan hệ/câu chuyện cụ thể, người dùng
  có thể bảo lưu rõ ràng trên trang Trí nhớ. Các câu chuyện còn trong lịch sử/tóm tắt theo mạch; summary được nhắc giữ
  chủ sở hữu và không biến nội dung giả định thành tiểu sử người dùng.
- Không tự quét/sửa/xóa hàng loạt ghi nhớ đã lưu. Muốn sửa trường hợp Blue trên VPS, người dùng đính chính sau deploy
  hoặc sửa/xóa các ý đó trong Cài đặt. Không có migration dữ liệu cũ hoặc ghi ngược vào bot Discord.
- Bằng chứng xác nhận **nguồn và cách trích**, không chứng minh model diễn giải đúng mọi ngữ nghĩa. Nhãn chủ thể/
  độ chắc chắn vẫn do model đánh giá; các veto VI/EN là kiểm tra bảo thủ, không phải NLP đa ngôn ngữ hoàn chỉnh.
  Có thể bỏ sót dữ kiện đúng khi lời gốc dài, có nhiều chủ thể hoặc dùng lối nói chưa nhận diện. Không tuyên bố hết
  mọi hallucination hay đã đo chất lượng provider thật.
- Số lượt model không tăng; JSON, bằng chứng và bối cảnh bổ sung có thể tăng token so với trước. Không lưu/log nguyên
  hội thoại hoặc quote vào log chẩn đoán. Metadata bằng chứng chỉ dùng để kiểm tra trước lưu, chưa có UI xem nguồn.
- Không thay UI, `.env`, dependency hoặc schema SQLite. Deploy chỉ cập nhật/restart backend.

## Kiểm thử

`tests/test_memory_grounding.py` dùng phản hồi model cố ý sai và dữ liệu giả: mèo của bạn/Người khác/Nam,
nguồn bị trích thiếu/giả/assistant/truncated, suy đoán/giả định/dịch câu, mất ảnh, phủ định sở hữu, câu tự xác nhận,
bảo toàn ý cũ, tóm tắt không lọt dữ kiện bị từ chối, đính chính từng ý, owner/cursor/context/xóa/race với sửa tay.

Kiểm hồi quy cùng `test_companion_memory`, `test_memory_scope`, `test_discord_memory`,
`test_discord_memory_settings`, `test_companion_cards`, `test_byok`. Tất cả SQLite/model/gateway giả; không gọi paid API.
Kết quả cuối: **149 passed** trong một lần chạy chung bảy tệp trên; `git diff --check` không có lỗi khoảng trắng.
