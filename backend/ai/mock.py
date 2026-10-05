"""Nhà cung cấp giả — không gọi mạng, không cần credential.

Dùng để dựng và kiểm thử toàn bộ luồng chat (stream, lưu lịch sử, giới hạn
tải, báo lỗi) trước khi chốt nhà cung cấp AI thật.

Hai từ khóa dành riêng cho kiểm thử:
- ``__error__`` trong tin nhắn -> giả lập lỗi nhà cung cấp.
- ``__slow__`` trong tin nhắn -> trả lời rất chậm để thử timeout/hủy.
"""

from __future__ import annotations

import asyncio
import random
import json
import re
from collections.abc import AsyncIterator

from .base import ChatMessage, ChatProvider, ProviderError, StreamChunk
from shared.time_tools import execute_tool
from shared.attachment_tools import current_files
from features.documents.tools import current_session

DOCUMENT_SAMPLE = '''# Giữ sự tử tế trong xã hội số

Trong một thế giới mà mỗi người có thể gửi đi hàng trăm tin nhắn mỗi ngày, sự tử tế không còn chỉ thể hiện ở những cuộc gặp trực tiếp. Nó còn nằm trong cách chúng ta đọc một lời tâm sự, phản hồi một ý kiến khác biệt và dừng lại trước khi chia sẻ điều chưa được kiểm chứng. Không gian số giúp con người đến gần nhau, nhưng khoảng cách phía sau màn hình cũng có thể khiến ta quên rằng bên kia là một con người có cảm xúc.

Sự tử tế là thái độ tôn trọng, biết quan tâm và có trách nhiệm với hành động của mình. Trên mạng, điều ấy bắt đầu từ những việc rất nhỏ: không chế giễu một người chỉ vì họ mắc lỗi, không biến nỗi đau của người khác thành trò vui, không dùng những lời cay nghiệt để giành phần thắng. Tử tế không có nghĩa là đồng ý với mọi quan điểm. Ta hoàn toàn có thể phản biện thẳng thắn mà vẫn giữ sự công bằng và tôn trọng đối phương.

Thực tế cho thấy nhiều người sẵn sàng giúp đỡ nhau qua những nhóm học tập, chia sẻ kiến thức và kết nối cộng đồng. Một lời động viên đúng lúc có thể giúp ai đó vượt qua ngày khó khăn. Tuy vậy, cũng có những cuộc tranh luận nhanh chóng trở thành công kích cá nhân. Khi số lượt thích được xem như thước đo duy nhất, con người dễ chạy theo những phát ngôn gây chú ý mà bỏ qua hậu quả của chúng.

Nguyên nhân không chỉ đến từ tính ẩn danh. Nhịp thông tin quá nhanh khiến chúng ta phản ứng trước khi suy nghĩ, trong khi những mẩu chuyện bị tách khỏi bối cảnh lại dễ tạo ra hiểu lầm. Vì vậy, trách nhiệm của người sử dụng mạng không dừng ở việc tránh nói lời xúc phạm. Mỗi người còn cần học cách kiểm tra thông tin, lắng nghe nhiều phía và thừa nhận khi mình sai.

Để giữ sự tử tế, trước hết hãy tạo một khoảng dừng trước khi bình luận hoặc chia sẻ. Tự hỏi lời nói của mình có đúng sự thật, có cần thiết và có giúp ích hay không. Gia đình và nhà trường cũng cần tạo cơ hội để người trẻ thực hành tranh luận văn minh, thay vì chỉ yêu cầu im lặng trước bất đồng. Các nền tảng trực tuyến cần có cách tiếp nhận phản ánh rõ ràng và hỗ trợ người bị quấy rối.

Xã hội số trở nên đáng sống hơn khi mỗi người nhìn thấy con người phía sau tài khoản. Một hành động nhỏ không thể giải quyết mọi vấn đề, nhưng nhiều lựa chọn có trách nhiệm sẽ tạo nên thói quen chung. Giữ sự tử tế vì thế là việc có thể bắt đầu ngay hôm nay, từ chính lời nói tiếp theo mà chúng ta gửi đi.
'''

# "__sodo__": câu trả lời có sơ đồ lớp, tuần tự, hoạt động và hoạt động có làn, để bản chạy thử xem được thẻ sơ đồ và
# bảng bên phải.
DIAGRAM_SAMPLE = """Đây là bốn sơ đồ cho hệ thống thư viện:

```mermaid
---
title: Sơ đồ lớp hệ thống thư viện
---
classDiagram
    direction LR
    class NguoiDung {
        <<abstract>>
        -int id
        -String hoTen
        +dangNhap(email, matKhau) bool
    }
    class DocGia {
        -String maThe
        +muonSach(sach) PhieuMuon
    }
    class ThuThu {
        +duyetPhieu(phieu) void
    }
    class PhieuMuon {
        -Date ngayMuon
        -Date hanTra
    }
    class Sach {
        -String isbn
        -String tenSach
    }
    NguoiDung <|-- DocGia
    NguoiDung <|-- ThuThu
    DocGia "1" --> "0..*" PhieuMuon : lập
    PhieuMuon "*" o-- "1..*" Sach : gồm
    ThuThu ..> PhieuMuon : duyệt
```

```mermaid
---
title: Đăng nhập
---
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant W as Trang web
    participant S as Máy chủ
    U->>W: Nhập email, mật khẩu
    W->>S: POST /login
    alt Mật khẩu đúng
        S-->>W: 200 và token
    else Sai mật khẩu
        S-->>W: 401
    end
```

```mermaid
---
title: "Sơ đồ hoạt động: Mượn sách"
---
stateDiagram-v2
    state KiemTra <<choice>>
    [*] --> ChonSach
    ChonSach: Chọn sách
    ChonSach --> KiemTra
    KiemTra --> TaoPhieu: Còn sách
    KiemTra --> [*]: Hết sách
    TaoPhieu: Tạo phiếu mượn
    TaoPhieu --> [*]
```

```mermaid
---
title: "Sơ đồ hoạt động: Mượn sách theo làn"
---
swimlane-beta
    subgraph DG["Độc giả"]
        S@{ shape: sm-circ } --> A(Chọn sách)
        A --> B(Gửi yêu cầu mượn)
        G(Nhận sách) --> X@{ shape: fr-circ }
    end
    subgraph TT["Thủ thư"]
        C{"Còn sách?"}
        D(Tạo phiếu mượn)
        E(Báo hết sách) --> Y@{ shape: fr-circ }
    end
    subgraph HT["Hệ thống"]
        F(Cập nhật số lượng)
    end
    B --> C
    C -->|Còn| D
    C -->|Hết| E
    D --> F
    F --> G
```

Bấm vào từng thẻ để xem lớn, tải PNG, SVG, PDF hoặc mở bằng draw.io."""

# "__bang__": bảng nhiều cột có ghi chú dài, để xem bảng trên điện thoại (cuộn ngang, không bẻ chữ giữa từ).
TABLE_SAMPLE = """Giá tham khảo, đơn vị USD cho 1 triệu token:

| Model | Nhà cung cấp | Input | Output | Cache hit | Ghi chú |
|---|---|---|---|---|---|
| Qwen3.7 Flash | Alibaba | $0.03 | $0.13 | — | Rẻ nhất trong bảng xếp hạng ngày 28/9/2026 |
| Llama 3.1 8B Instant | Groq | $0.05 | $0.08 | — | Model nhỏ, rất nhanh, yếu ở việc khó |
| DeepSeek V4.1 Flash | DeepSeek | $0.15 | $0.60 | $0.003 | Giờ cao điểm gấp đôi. Context 1M |

Bảng trên điện thoại cuộn ngang được."""



def slide_sample(theme: str) -> dict:
    """Bài thuyết trình mẫu cho "__slide__": đủ các khuôn không cần ảnh."""
    empty = dict.fromkeys(('subtitle', 'meta', 'section', 'bullets', 'left_title', 'left_bullets', 'right_title',
                           'right_bullets', 'image', 'caption', 'table_columns', 'table_rows', 'chart_type',
                           'chart_categories', 'chart_series', 'chart_unit'))

    def slide(layout, title, notes, **fields):
        return {**empty, 'layout': layout, 'title': title, 'notes': notes, **fields}

    return {'title': 'Hệ thống quản lý thư viện số', 'theme': theme, 'slides': [
        slide('cover', 'Hệ thống quản lý thư viện số', 'Chào thầy cô và các bạn, giới thiệu tên nhóm.',
              subtitle='Đồ án môn Công nghệ phần mềm', meta='Nhóm 5 · Lớp KTPM2024\nTháng 10/2026'),
        slide('agenda', 'Nội dung', 'Đi nhanh qua mục lục.', bullets=['Bài toán và mục tiêu', 'Phân tích yêu cầu',
                                                                     'Kết quả thử nghiệm', 'Kết luận']),
        slide('bullets', 'Bài toán đặt ra', 'Mở đầu bằng con số 5–7 phút.', section='1 · Bài toán và mục tiêu',
              bullets=['Mượn trả ghi sổ tay, mỗi lượt mất 5–7 phút', 'Không biết sách còn trên kệ hay đã có người mượn',
                       'Độc giả quên hạn trả, phí phạt khó đối chiếu']),
        slide('two_columns', 'Trước và sau khi có hệ thống', 'Cột phải là phần nhóm đã làm xong.',
              left_title='Hiện tại', left_bullets=['Ghi sổ, tra cứu bằng tủ phiếu', 'Báo cáo tháng làm thủ công'],
              right_title='Hệ thống mới', right_bullets=['Quét mã vạch, cập nhật ngay', 'Báo cáo tự động mỗi tuần']),
        slide('table', 'Kết quả thử nghiệm', 'Báo cáo tháng giảm nhiều nhất.', caption='Đo trên 120 lượt, tháng 9/2026',
              table_columns=['Thao tác', 'Trước', 'Sau'],
              table_rows=[['Mượn sách', '6,5 phút', '1,2 phút'], ['Trả sách', '4,0 phút', '0,8 phút']]),
        slide('chart', 'Lượt mượn theo tháng', 'Tháng 9 tăng vì đầu năm học.', chart_type='column', chart_unit='lượt',
              chart_categories=['T7', 'T8', 'T9'], chart_series=[{'name': 'Năm 2025', 'values': [190, 240, 410]},
                                                                 {'name': 'Năm 2026', 'values': [210, 260, 640]}]),
    ]}


# "__suynghi__": tóm tắt suy nghĩ nhiều đoạn, đúng kiểu Grok thật gửi về khi sửa tệp Excel thử ngày 5/10/2026 (mỗi đoạn
# một hai câu tiếng Việt), để xem khối "Đang làm" chỉ hiện một dòng mà không cần gọi AI thật.
THINKING_SAMPLE = [
    'Đang phân tích tệp Excel để xác định lỗi. Sẽ sửa các vấn đề và trả lại file đã chỉnh sửa.',
    'Đang liệt kê các quy tắc kiểm tra trên trang tính Bang_luong để xác định lỗi. Các điều kiện cần đối chiếu với trang '
    'Nhan_su và kiểm tra công thức tính ngày công, phụ cấp, tổng thu nhập và BHXH.',
    'Đang kiểm tra từng dòng nhân viên trên trang tính Bang_luong. Các công thức ở cột H đến M đều đúng theo quy tắc, trừ '
    'dòng 6 và dòng 11.',
    'Dòng 7 NV003 đang ghi mã NV003 trong khi trang Nhan_su chỉ có NV-003. Cần đối chiếu với trang Nhan_su để chọn cách sửa.',
    'Đã quyết định sửa mã nhân viên ở dòng 8 thành NV004 vì Phạm Minh Dũng đang dùng trùng mã NV003.',
    'Đang soạn danh sách thay đổi: sửa mã, sửa công thức BHXH và thuế, nới dòng tổng cộng cho đủ 8 nhân viên.',
]


def _tool_result(tool: str, result: dict) -> StreamChunk:
    """Kết quả gọn cho nhật ký "Đang làm", như provider thật (bỏ "_ui" khỏi kết quả, phần đó không dành cho mô hình)."""
    ui = result.pop('_ui', None) or {}
    return StreamChunk('tool_result', info={'tool': tool, 'ok': bool(result.get('ok')), 'error': result.get('error'), **ui})


async def edit_sample(session, name: str) -> list[dict]:
    """Thay đổi mẫu cho "__suaexcel__": thêm cột "Ghi chú Peto" ngay sau vùng dữ liệu của trang đầu, theo định dạng cột
    bên trái, rồi tô hàng đầu."""
    from features.documents.workbook_edit.book import Book
    from features.documents.workbook_edit.sheetxml import address, column_letter
    source = await session._workbook(name)
    book = Book(source['data'])
    info = book.data_sheets()[0]
    top, left, bottom, right = book.worksheet(info).bounds() or (0, 0, 0, 0)
    blank = dict(range=None, values=None, value=None, format_from=None, bold=None, italic=None, font_color=None,
                 fill_color=None, number_format=None, decimals=None, align=None, new_name=None)
    col = column_letter(right + 1)
    changes = [{**blank, 'action': 'set', 'sheet': info.name, 'range': address(top, right + 1), 'values': [['Ghi chú Peto']],
                'format_from': address(top, right)}]
    if bottom > top:
        changes.append({**blank, 'action': 'fill', 'sheet': info.name, 'range': f'{col}{top + 2}:{col}{bottom + 1}',
                        'value': 'Đã kiểm tra', 'format_from': f'{column_letter(right)}{top + 2}'})
    changes.append({**blank, 'action': 'format', 'sheet': info.name, 'range': f'{address(top, left)}:{address(top, right + 1)}',
                    'bold': True, 'fill_color': '#FFF2CC'})
    return changes


def sheet_sample(kind: str = 'diem') -> dict:
    """Bảng tính mẫu cho "__excel__" (bảng điểm có thống kê) và "__excel__:chitieu" (chi tiêu: tiền, ngày, phần trăm)."""
    if kind == 'chitieu':
        spend = "'Chi tiêu tháng 10'"
        items = [('2026-10-01', 'Tiền nhà tháng 10', 'Nhà ở', '3500000'), ('2026-10-02', 'Đi chợ', 'Ăn uống', '420000'),
                 ('2026-10-03', 'Xăng xe', 'Đi lại', '150000'), ('2026-10-05', 'Cà phê với bạn', 'Ăn uống', '90000'),
                 ('2026-10-07', 'Điện nước', 'Nhà ở', '620000'), ('2026-10-08', 'Sách tham khảo', 'Học tập', '280000'),
                 ('2026-10-10', 'Đi chợ', 'Ăn uống', '510000'), ('2026-10-12', 'Vé xe buýt tháng', 'Đi lại', '200000')]
        groups = ['Nhà ở', 'Ăn uống', 'Đi lại', 'Học tập']
        return {'title': 'Chi tiêu tháng 10', 'sheets': [
            {'name': 'Chi tiêu tháng 10', 'title': 'Chi tiêu cá nhân tháng 10/2026',
             'columns': [{'header': 'Ngày', 'format': 'date', 'decimals': None},
                         {'header': 'Khoản chi', 'format': 'text', 'decimals': None},
                         {'header': 'Nhóm', 'format': 'text', 'decimals': None},
                         {'header': 'Số tiền', 'format': 'vnd', 'decimals': None}],
             'rows': [list(item) for item in items], 'total_row': ['', 'Tổng cộng', '', '=SUM(D2:D9)'], 'charts': []},
            {'name': 'Theo nhóm', 'title': None,
             'columns': [{'header': 'Nhóm', 'format': 'text', 'decimals': None},
                         {'header': 'Số tiền', 'format': 'vnd', 'decimals': None},
                         {'header': 'Tỉ lệ', 'format': 'percent', 'decimals': 1}],
             'rows': [[group, f'=SUMIF({spend}!C$2:C$9,A{row},{spend}!D$2:D$9)', f'=B{row}/B$6']
                      for row, group in enumerate(groups, start=2)],
             'total_row': ['Tổng', '=SUM(B2:B5)', '=SUM(C2:C5)'],
             'charts': [{'type': 'pie', 'title': 'Chi tiêu theo nhóm', 'category_column': 'A', 'value_columns': ['B']}]},
        ]}
    students = [('Nguyễn Minh Anh', '8', '7.5', '8'), ('Trần Gia Bảo', '9', '8.5', '9'), ('Lê Thu Hà', '6.5', '7', '6'),
                ('Phạm Quốc Huy', '7', '6', '5.5'), ('Hoàng Ngọc Lan', '10', '9', '9.5'), ('Vũ Đức Minh', '5', '4.5', '4'),
                ('Đặng Bảo Ngọc', '8.5', '8', '7.5'), ('Bùi Thanh Phong', '7.5', '7', '7'), ('Đỗ Khánh Linh', '9', '9', '8.5'),
                ('Ngô Hải Nam', '6', '5.5', '6.5')]
    score = {'format': 'number', 'decimals': 1}
    rows = [[str(index), name, a, b, c, f'=ROUND((C{row}+D{row}*2+E{row}*3)/6,1)',
             f'=IF(F{row}>=8,"Giỏi",IF(F{row}>=6.5,"Khá",IF(F{row}>=5,"Trung bình","Yếu")))']
            for index, (row, (name, a, b, c)) in enumerate(enumerate(students, start=2), start=1)]
    return {'title': 'Bảng điểm lớp 10A1 - Học kỳ I', 'sheets': [
        {'name': 'Bảng điểm', 'title': 'Bảng điểm lớp 10A1 - Học kỳ I',
         'columns': [{'header': 'STT', 'format': 'number', 'decimals': 0}, {'header': 'Họ và tên', 'format': 'text', 'decimals': None},
                     {'header': 'Điểm 15 phút', **score}, {'header': 'Điểm 1 tiết', **score},
                     {'header': 'Điểm thi HK', **score}, {'header': 'Điểm TB', **score},
                     {'header': 'Xếp loại', 'format': 'text', 'decimals': None}],
         'rows': rows, 'total_row': ['', 'Trung bình lớp', '=AVERAGE(C2:C11)', '=AVERAGE(D2:D11)', '=AVERAGE(E2:E11)',
                                     '=AVERAGE(F2:F11)', ''], 'charts': []},
        {'name': 'Thống kê', 'title': 'Thống kê xếp loại lớp 10A1',
         'columns': [{'header': 'Xếp loại', 'format': 'text', 'decimals': None},
                     {'header': 'Số học sinh', 'format': 'number', 'decimals': 0},
                     {'header': 'Tỉ lệ', 'format': 'percent', 'decimals': 0}],
         'rows': [[level, f"=COUNTIF('Bảng điểm'!G$2:G$11,A{row})", f'=B{row}/B$6']
                  for row, level in enumerate(['Giỏi', 'Khá', 'Trung bình', 'Yếu'], start=2)],
         'total_row': ['Tổng', '=SUM(B2:B5)', '=SUM(C2:C5)'],
         'charts': [{'type': 'column', 'title': 'Số học sinh theo xếp loại', 'category_column': 'A', 'value_columns': ['B']},
                    {'type': 'pie', 'title': 'Tỉ lệ xếp loại', 'category_column': 'A', 'value_columns': ['B']}]},
    ]}


_CHUNK_DELAY = 0.035

_GREETING = (
    "Chào bạn! Hôm nay mình giúp gì được cho bạn?",
    "Chào bạn, bạn cần mình hỗ trợ việc gì?",
)

_TOOL_REFUSAL = (
    "Web này chưa có công cụ cho việc đó nên mình chưa làm được. "
    "Nếu bạn muốn, mình có thể giúp theo cách khác."
)

_IMAGE_REFUSAL = (
    "Muốn tạo ảnh thì bạn mở tab Tạo ảnh rồi nhập mô tả nhé. "
    "Còn sửa ảnh thì bấm Thêm ảnh, chọn ảnh gốc, nhập điều muốn thay đổi "
    "rồi bấm Sửa ảnh."
)

_MATH = (
    "Bài này cần tính cẩn thận. Hiện Peto đang chạy bằng phản hồi giả nên chưa "
    "giải thật được; khi nối nhà cung cấp AI, mình sẽ giải từng bước."
)

_DEFAULT = (
    "Mình đã nhận tin nhắn. Hiện Peto đang chạy bằng phản hồi giả để thử giao "
    "diện, nên câu trả lời này chưa phải của AI thật. Luồng chat, lưu lịch sử và "
    "hiển thị chữ chảy dần đang hoạt động bình thường."
)

_IMAGE_WORDS = ("vẽ", "tạo ảnh", "vẽ ảnh", "sửa ảnh", "chỉnh ảnh", "chỉnh sửa ảnh", "generate image", "edit image")
_TOOL_WORDS = (
    "phát nhạc", "mở bài", "mở nhạc", "tìm ảnh",
    "search", "tìm kiếm", "tra web",
)


def _pick_reply(user_text: str, timezone: str | None = None) -> str:
    lowered = user_text.casefold().strip()
    if not lowered:
        return "Tin nhắn đang trống. Bạn nhập nội dung rồi gửi lại nhé."
    if lowered in {"chào", "hi", "hello", "hey", "alo", "chao"}:
        return random.choice(_GREETING)
    if any(marker in lowered for marker in (
        "mấy giờ", "may gio", "ngày mấy", "ngay may", "ngày bao nhiêu", "thứ mấy",
        "hôm nay ngày", "hôm nay là ngày", "ngày giờ hiện tại", "current time", "what time",
    )):
        clock = execute_tool("get_current_datetime", "{}", timezone=timezone)
        if "error" in clock:
            return "Chưa xác định được múi giờ. Bạn cho mình biết múi giờ muốn xem nhé."
        year, month, day = clock["date"].split("-")
        return (
            f"Bây giờ là {clock['time']}, {clock['weekday']}, ngày {day}/{month}/{year} "
            f"({clock['timezone']}, {clock['utc_offset']})."
        )
    if any(word in lowered for word in _IMAGE_WORDS):
        return _IMAGE_REFUSAL
    if any(word in lowered for word in _TOOL_WORDS):
        return _TOOL_REFUSAL
    from .routing import looks_like_math

    if looks_like_math(lowered):
        return _MATH
    return _DEFAULT


class MockProvider(ChatProvider):
    name = "mock"

    def __init__(self, model: str = "peto") -> None:
        # Model người dùng chọn; phản hồi giả không đổi theo model, nhưng test đọc được lượt nào đi vào model nào.
        self.model = model

    async def stream(
        self,
        *,
        system_prompt: str,
        messages: list[ChatMessage],
        effort: str = "low",
        timezone: str | None = None,
        web_search: str = "auto",
        tools_enabled: bool = True,
    ) -> AsyncIterator[str | StreamChunk]:
        last = next((m for m in reversed(messages) if m.role == "user"), None)
        last_user = last.content if last else ""
        names = [item.name for item in last.attachments] if last else []

        # Lượt đặt tên hội thoại: trả về tên gọn lấy từ chính tin nhắn, để bản
        # chạy thử vẫn thấy đúng kiểu web thật đặt tên.
        from features.chat.titles import TITLE_MARKER  # import muộn cho khỏi vòng import

        if TITLE_MARKER in system_prompt:
            title = " ".join(last_user.split()[:6]) or "Trò chuyện mới"
            yield title[:1].upper() + title[1:]
            return

        # Lượt ghi nhớ Companion: chỉ đổi khi lời người dùng có từ khóa thử, để test và bản chạy thử đoán trước được.
        # __nho__:<câu> thêm, __sua__:<id>:<câu> sửa, __quen__:<id> xóa một ghi nhớ.
        from features.companion.memory import MEMORY_MARKER, SUMMARY_MARKER

        if SUMMARY_MARKER in system_prompt:
            # Tóm tắt giả: giữ bản cũ rồi nối lời người dùng trong đoạn vừa trôi ra, để test lần ra được từng tin.
            old, _, talk = last_user.partition("Đoạn hội thoại vừa trôi khỏi lịch sử:")
            old = old.replace("Bản tóm tắt hiện có:", "").strip()
            said = [line.split(":", 1)[1].strip() for line in talk.splitlines() if line.startswith("Người dùng:")]
            yield " ".join(part for part in ("" if old == "(chưa có)" else old, "Người dùng kể: " + "; ".join(said)) if part)
            return

        if MEMORY_MARKER in system_prompt:
            talk = last_user.split("Đoạn hội thoại mới:", 1)[-1]
            said = "\n".join(line for line in talk.splitlines() if line.startswith("Người dùng:"))
            yield json.dumps({
                "add": [text.strip() for text in re.findall(r"__nho__:([^_\n]+)", said)],
                "update": [{"id": int(key), "text": text.strip()} for key, text in re.findall(r"__sua__:(\d+):([^_\n]+)", said)],
                "remove": [int(key) for key in re.findall(r"__quen__:(\d+)", said)],
            }, ensure_ascii=False)
            return

        if "__error__" in last_user:
            raise ProviderError(
                "Nhà cung cấp AI đang lỗi (giả lập). Thử lại sau nhé.",
                retryable=True,
            )
        if "__slow__" in last_user:
            await asyncio.sleep(3600)

        if not last_user.strip() and names:
            last_user = f"[đính kèm {', '.join(names)}]"
        if tools_enabled:
            # Như provider thật: mỗi lần gọi mô hình mở một bước "Đang suy nghĩ…" trong nhật ký.
            yield StreamChunk("round")

        reply = _pick_reply(last_user, timezone)
        if "__sodo__" in last_user:
            reply = DIAGRAM_SAMPLE
        if "__bang__" in last_user:
            reply = TABLE_SAMPLE
        # Ghi chú riêng của Companion (private_notes.py): "__bimat__:x" giấu x giữa câu trả lời; "__doan__" đọc lại ghi
        # chú mới nhất trong lịch sử, để test thấy model nhận lại ghi chú ở lượt sau.
        secret = re.search(r"__bimat__:([^_\n]+)", last_user)
        if secret:
            reply = f"Mình chọn xong rồi. <private>{secret.group(1).strip()}</private> Đoán đi!"
        if "__doan__" in last_user:
            notes = [note for message in messages if message.role == "assistant"
                     for note in re.findall(r"<private>(.*?)</private>", message.content, re.S)]
            reply = f"Ghi chú riêng của mình: {notes[-1].strip()}" if notes else "Mình không có ghi chú riêng nào."
        # Thẻ cảm xúc Companion (emotion_tags.py): "__camxuc__:happy" mở đầu câu trả lời bằng <|EMOTE_HAPPY|>.
        emotion = re.search(r"__camxuc__:([a-zA-Z]+)", last_user)
        if emotion:
            reply = f"<|EMOTE_{emotion.group(1).upper()}|> {reply}"
        session = current_session.get()
        # "__slide__" hay "__slide__:academic": tạo bài thuyết trình mẫu bằng create_presentation, để chạy thử thẻ slide.
        slide = re.search(r'__slide__(?::(clean|academic|bold))?', last_user)
        if session and slide:
            yield StreamChunk('tool', 'create_presentation')
            yield StreamChunk('document_status', 'Đang dàn trang slide…')
            result = await session.present(json.dumps(slide_sample(slide.group(1) or 'clean'), ensure_ascii=False))
            if result.get('ok'):
                yield StreamChunk('artifact', artifact=result['artifact'])
            yield _tool_result('create_presentation', result)
            yield StreamChunk('document_status', '')
            if result.get('ok'):
                yield 'Đã tạo bài thuyết trình mẫu **Hệ thống quản lý thư viện số**, mỗi slide có ghi chú cho người thuyết trình.'
            else:
                yield 'Chưa tạo được bài thuyết trình: ' + result['error']
            return
        # "__excel__" hay "__excel__:chitieu": tạo bảng tính mẫu bằng create_spreadsheet, để chạy thử lưới xem.
        workbook = re.search(r'__excel__(?::(diem|chitieu))?', last_user)
        if session and workbook:
            sample = sheet_sample(workbook.group(1) or 'diem')
            yield StreamChunk('tool', 'create_spreadsheet')
            yield StreamChunk('document_status', 'Đang tính bảng tính…')
            result = await session.tabulate(json.dumps(sample, ensure_ascii=False))
            if result.get('ok'):
                yield StreamChunk('artifact', artifact=result['artifact'])
            yield _tool_result('create_spreadsheet', result)
            yield StreamChunk('document_status', '')
            if result.get('ok'):
                yield f'Đã tạo bảng tính mẫu **{sample["title"]}** với công thức thật và biểu đồ.'
            else:
                yield 'Chưa tạo được bảng tính: ' + result['error']
            return
        # "__suaexcel__": sửa tệp Excel mới nhất của hội thoại bằng edit_spreadsheet, để chạy thử thẻ và lưới xem tệp đã sửa.
        if session and '__suaexcel__' in last_user:
            if not session.workbooks:
                yield 'Hội thoại chưa có tệp Excel nào để sửa.'
                return
            name = session.workbooks[-1]['name']
            # Như Grok thật: một câu dẫn rồi mới viết lệnh sửa; câu dẫn vào nhật ký "Đang làm", không vào câu trả lời.
            yield 'Mình thêm cột "Ghi chú Peto" ngay sau vùng dữ liệu của trang đầu.'
            yield StreamChunk('note')
            yield StreamChunk('tool', 'edit_spreadsheet')
            yield StreamChunk('document_status', 'Đang sửa tệp Excel…')
            changes = await edit_sample(session, name)
            result = await session.edit(json.dumps({'file': name, 'changes': changes}, ensure_ascii=False))
            if result.get('ok'):
                yield StreamChunk('artifact', artifact=result['artifact'])
            yield _tool_result('edit_spreadsheet', result)
            yield StreamChunk('document_status', '')
            # "__suaexcel__:2": sửa tiếp cùng tệp trong lượt này (chèn một hàng ở đầu) như Grok sửa nhiều đợt: trả lời
            # chỉ còn một thẻ, là bản cuối kể đủ cả hai lần.
            if result.get('ok') and '__suaexcel__:2' in last_user:
                sheet = changes[0]['sheet']
                yield StreamChunk('round')
                yield StreamChunk('tool', 'edit_spreadsheet')
                yield StreamChunk('document_status', 'Đang sửa tệp Excel…')
                more = await session.edit(json.dumps({'file': name, 'changes': [
                    {'action': 'insert_rows', 'sheet': sheet, 'range': '1'},
                    {'action': 'set', 'sheet': sheet, 'range': 'A1', 'values': [['Bản đã rà soát']], 'bold': True}]},
                    ensure_ascii=False))
                if more.get('ok'):
                    yield StreamChunk('artifact', artifact=more['artifact'])
                yield _tool_result('edit_spreadsheet', more)
                yield StreamChunk('document_status', '')
            yield StreamChunk('round')
            if result.get('ok'):
                yield f'Đã sửa tệp **{name}**: ' + '; '.join(line.strip() for line in result['changes']) + '.'
            else:
                yield 'Chưa sửa được tệp: ' + result['error']
            return
        lowered = last_user.casefold()
        # Only the offline mock uses keyword routing. The real provider chooses its tool.
        create_requested = '[PETO_DOCUMENT_CREATE]' in system_prompt or (
            any(word in lowered for word in ('tạo', 'xuất', 'create', 'generate')) and
            any(word in lowered for word in ('docx', 'pdf', 'word', 'tài liệu', 'file')))
        if session and create_requested:
            format = 'pdf' if 'pdf' in lowered and 'docx' not in lowered else 'docx'
            yield StreamChunk('tool', 'create_document')
            yield StreamChunk('document_status', 'Đang soạn và dàn trang tài liệu…')
            result = await session.create(json.dumps({'title': 'Giữ sự tử tế trong xã hội số', 'content': DOCUMENT_SAMPLE,
                'format': format, 'style': 'essay'}, ensure_ascii=False))
            if result.get('ok'):
                yield StreamChunk('artifact', artifact=result['artifact'])
                yield _tool_result('create_document', result)
                yield StreamChunk('document_status', '')
                yield 'Đã tạo tệp mẫu chứa bài nghị luận **Giữ sự tử tế trong xã hội số**.\n\nBạn có thể xem từng trang và tải tệp bên dưới. Đây là nội dung mẫu của chế độ kiểm thử, chưa dùng AI thật.'
            else:
                yield _tool_result('create_document', result)
                yield StreamChunk('document_status', '')
                yield 'Chưa tạo được tệp: ' + result['error']
            return
        # Tìm trong tệp đã gửi (attachment_tools): "__timtep__:ERROR | Exception" tìm trong tệp gửi sau cùng, để bản chạy thử
        # và test thấy được bước "Đang tìm … trong tệp" mà không cần model thật tự gọi công cụ.
        files = current_files.get()
        lookup = re.search(r"__timtep__:([^\n]+)", last_user)
        if files and files.files and lookup:
            arguments = json.dumps({"file": files.files[-1]["filename"], "query": lookup.group(1).strip(),
                                    "context_lines": 1}, ensure_ascii=False)
            yield StreamChunk("file_lookup", files.label("search_attachment", arguments))
            result = await files.run("search_attachment", arguments)
            yield StreamChunk("file_lookup_done", files.label("search_attachment", arguments, result))
            yield (f"Tìm thấy {result['matches']} dòng khớp trong {result['file']}:\n\n```text\n{result['text']}\n```"
                   if "error" not in result else f"Chưa tìm được: {result['error']}")
            return
        search_requested = web_search == "on" or any(word in last_user.casefold() for word in ("tìm kiếm", "tìm web", "tra web", "tra cứu", "mới nhất", "search"))
        if search_requested:
            reply = (
                "Tìm web đang tắt cho lượt này. Peto chưa xác minh thông tin mới."
                if web_search == "off" else
                "Peto đang chạy bằng phản hồi giả nên chưa tìm web thật và chưa có nguồn đã xác minh. "
                "Khi kết nối AI thật, Peto sẽ tra cứu và hiện nguồn ngay dưới câu trả lời."
            )
        if names:
            reply = (
                f"Mình thấy bạn gửi kèm {', '.join(names)}. "
                "Bộ đọc xử lý tệp riêng; đang chạy phản hồi giả nên mình chưa phân tích nội dung bằng AI thật. "
            ) + reply

        if "__suynghi__" in last_user:
            for paragraph in THINKING_SAMPLE:
                await asyncio.sleep(0.8)
                yield StreamChunk("thinking", paragraph + "\n\n")
            reply = "Mình đã nghĩ xong. Đây là câu trả lời mẫu sau một lượt suy nghĩ dài, chưa dùng AI thật."
        else:
            await asyncio.sleep(_CHUNK_DELAY)
            yield StreamChunk("thinking", "Đọc tin nhắn rồi nghĩ cách trả lời…")

        # Cắt theo từ để giống nhịp stream thật. Mỗi mảnh mang theo khoảng trắng đứng trước nó, nên ghép lại đúng nguyên
        # văn, kể cả thụt lề trong khối code (trước đây dấu cách liền nhau sau mỗi lần xả bị mất).
        buffer = ""
        for piece in re.findall(r"\s*\S+|\s+$", reply):
            buffer += piece
            if len(buffer) >= 12:
                await asyncio.sleep(_CHUNK_DELAY)
                yield buffer
                buffer = ""
        if buffer:
            await asyncio.sleep(_CHUNK_DELAY)
            yield buffer
