"""Hướng dẫn sơ đồ; chỉ thêm khi câu hỏi cần tính năng này."""

from __future__ import annotations
import re
import unicodedata


DIAGRAM_PROMPT = """
## Vẽ sơ đồ bằng Mermaid
Web tự vẽ khối ```mermaid thành sơ đồ (thẻ trong chat, bấm vào mở lớn ở bảng bên phải).
- Mỗi sơ đồ một khối ```mermaid riêng. Viết một câu dẫn trước khối, giải thích ngắn sau khối.
- Đặt tên sơ đồ bằng phần đầu khối: dòng `---`, dòng `title: Tên sơ đồ`, dòng `---`. Sơ đồ hoạt động và use
  case thì tên bắt đầu bằng "Sơ đồ hoạt động: " hoặc "Sơ đồ use case: " để web ghi đúng loại.
- ID chỉ gồm chữ không dấu, số và gạch dưới (DocGia, B2). Chữ có dấu, dấu ngoặc tròn, dấu hai chấm
  hay dấu phẩy đặt trong nhãn có ngoặc kép, ví dụ B["Gọi API (POST /login)"]: ngoặc tròn trong [ ] mà
  không có ngoặc kép là lỗi cú pháp. Không dùng end, class, subgraph làm ID.
- Sơ đồ lớp (UML class): classDiagram. Thuộc tính và phương thức có + - # ~; <<interface>>,
  <<abstract>> trong khối class. Quan hệ: <|-- kế thừa, ..|> hiện thực, *-- hợp thành, o-- tụ hợp,
  --> kết hợp, ..> phụ thuộc; bội số trong ngoặc kép, ví dụ DocGia "1" --> "0..*" PhieuMuon : lập.
- Sơ đồ tuần tự (sequence): sequenceDiagram; actor cho người dùng, participant cho hệ thống; ->> là
  gọi, -->> là trả về; activate/deactivate; khung alt/else, opt, loop, par; autonumber khi cần đánh số.
- Sơ đồ hoạt động (activity) không có làn: Mermaid không có loại riêng; dùng stateDiagram-v2 cho đúng
  ký hiệu UML: [*] là điểm bắt đầu và kết thúc, hành động viết ID: Nhãn. Khai báo các nút state X <<choice>>,
  state Y <<fork>>, state Z <<join>> ở ĐẦU sơ đồ, trước dòng đầu tiên dùng tới chúng; khai báo sau
  thì nút rẽ nhánh thành hình chữ nhật.
- Sơ đồ hoạt động có làn (swimlane, phân làn theo người hay bộ phận): dùng swimlane-beta và để làn dọc
  mặc định (không thêm LR: làn ngang nối mũi tên vòng rất rối). Mỗi làn là subgraph ID["Tên làn"] … end.
  Mọi nút khai báo bên trong làn của nó, kể cả điểm bắt đầu và kết thúc: nút nằm ngoài mọi làn sinh ra
  một làn trống không tên. Mũi tên nối sang làn khác viết sau khi đã đóng hết các làn; viết sớm hơn thì
  nút bị kéo sang làn sai. Bắt đầu S@{ shape: sm-circ }, kết thúc X@{ shape: fr-circ } (luồng kết thúc ở
  làn khác thì thêm một điểm kết thúc trong làn đó), hành động A(Tên), rẽ nhánh C{"Câu hỏi?"} với nhãn
  trên mũi tên -->|Có|, tách và gộp luồng J@{ shape: fork }.
- Sơ đồ use case: Mermaid chưa có loại này. Vẽ gần đúng bằng flowchart LR (tác nhân dạng ((Tên)),
  ca sử dụng dạng (["Tên"]), hệ thống là một subgraph), và nói rõ đây là bản gần đúng.
- ERD dùng erDiagram, lưu đồ dùng flowchart TD, trạng thái dùng stateDiagram-v2.
- Không dùng HTML trong nhãn, lệnh click, %%{init}%% hay tự đổi màu nếu người dùng không nhờ.
""".strip()


_DIAGRAM_WORDS = re.compile(
    r"(?<![a-z0-9])(so do|luu do|bieu do|diagram|uml|erd|flowchart|mermaid|activity|sequence|use ?case|swimlane"
    r"|draw\.?io|gantt|mindmap)(?![a-z0-9])"
)


def build_diagram_guide(question: str, *, english: bool = False) -> str:
    """Hướng dẫn vẽ sơ đồ khi vài tin nhắn gần đây nói tới sơ đồ; không thì chuỗi rỗng."""
    folded = unicodedata.normalize("NFD", question.lower().replace("đ", "d"))
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    if not _DIAGRAM_WORDS.search(folded):
        return ""
    if english:
        from .english import DIAGRAM_PROMPT as english_prompt
        return "\n\n" + english_prompt
    return "\n\n" + DIAGRAM_PROMPT
