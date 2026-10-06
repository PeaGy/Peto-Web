"""Đọc Markdown giới hạn của create_document thành các khối, rồi dựng DOCX/PDF theo kiểu trình bày; không chạy HTML,
không tải gì từ ngoài. Bản Word ở docx_out.py, bản PDF ở pdf_out.py; phần chung (khối, công thức, ô ảnh) ở đây."""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from html import escape
from urllib.parse import unquote

from markdown_it import MarkdownIt

from core.config import BASE_DIR
from features.documents.cover import Cover, split_cover
from features.documents.math import latex as math_latex
from features.documents.math import markdown as math_markdown

MAX_CONTENT = 60000
# Công thức trong một tài liệu ($…$, $$…$$); mỗi công thức dựng thành công thức Word thật và hình vẽ trong PDF.
MAX_FORMULAS = 600
MATH_SLOT = BASE_DIR / "assets" / "math-slot.png"
# Bảng chân trị 4 biến có 9 cột (x, y, z, w, bốn hạng tử, F), nên giới hạn cũ 8 cột không đủ (6/10/2026).
MAX_TABLE_COLUMNS = 12
# Bảng tối đa chừng này hàng (gồm hàng tiêu đề) không tách sang hai trang, ở cả bản Word lẫn PDF.
SHORT_TABLE_ROWS = 12
# Ảnh trong một tài liệu: chỉ ảnh người dùng đã gửi trong hội thoại (document_images.py), không bao giờ ảnh từ web.
MAX_IMAGES = 12
MAX_SLOTS = 30
FONT_DIR = BASE_DIR / "assets" / "fonts"
_font_lock = threading.Lock()
# ![chú thích](anh-2) là Ảnh 2 của hội thoại, đúng số trong nhãn "[Ảnh 2: …]" model thấy cạnh ảnh.
IMAGE_REF = re.compile(r"#?(?:anh|ảnh)[-_: ]?(\d{1,3})", re.IGNORECASE)
# ![chú thích](khung-anh) là khung chừa chỗ cho người dùng dán ảnh chụp màn hình sau.
SLOT_REF = re.compile(r"#?(?:khung[-_ ]?(?:anh|ảnh)|slot|placeholder|cho[-_ ]?anh|chỗ[-_ ]?ảnh)", re.IGNORECASE)
# Một đoạn ngay trên bảng bắt đầu bằng "Bảng:" (hay "Bảng 2.") là chú thích của bảng, đánh số tự động.
TABLE_CAPTION = re.compile(r"^(?:Bảng|Table)\s*(?:\d+(?:\.\d+)*)?\s*[.:–—-]?\s+(.+)$", re.IGNORECASE)
FIGURE_LABEL = re.compile(r"^(?:Hình|Figure|Ảnh)\s*\d", re.IGNORECASE)
# Một dòng riêng "[TOC]" hoặc "[Mục lục]" là chỗ đặt mục lục, gồm các đề mục cấp 1–3.
TOC_MARKERS = {"[toc]", "[mục lục]"}
TOC_LEVELS = 3
# Danh sách lồng nhau: số 1. → a. → i., dấu đầu dòng • → –. Word và PDF dùng chung để hai bản giống nhau.
ORDERED_STYLES = ("decimal", "lowerLetter", "lowerRoman")
BULLETS = ("•", "–")


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False
    # Công thức trong dòng: text là mã LaTeX.
    math: bool = False


@dataclass
class ListInfo:
    """Một danh sách Markdown. Mỗi danh sách, kể cả danh sách lồng, là một danh sách riêng trong Word nên tự đánh số từ đầu."""
    id: int
    ordered: bool
    depth: int
    style: str
    marker: str
    start: int


@dataclass
class Block:
    kind: str
    runs: list[Run] = field(default_factory=list)
    level: int = 0
    rows: list[list[list[Run]]] = field(default_factory=list)
    # Đoạn thuộc một mục danh sách: ``number`` là số của mục ở đoạn đầu tiên, None ở các đoạn sau của cùng mục.
    list_info: ListInfo | None = None
    number: int | None = None
    image: int = 0
    caption: str = ""
    # Công thức dòng riêng (kind "math"): mã LaTeX.
    math: str = ""


@dataclass
class DocImage:
    """Ảnh đã thu nhỏ để nhúng (document_images.prepare); kích thước tính bằng điểm ảnh."""
    data: bytes
    width: int
    height: int


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff￾￿]", "", value).strip()


def _source(token) -> str:
    return unicodedata.normalize("NFC", unquote(token.attrGet("src") or "")).strip()


def _image_number(token) -> int:
    """Số ảnh của hội thoại khi ``src`` là anh-N, ngược lại 0: ảnh ở địa chỉ khác chỉ hiện thành chữ, không được tải."""
    match = IMAGE_REF.fullmatch(_source(token))
    return int(match.group(1)) if match and int(match.group(1)) > 0 else 0


def _is_slot(token) -> bool:
    return token.type == "image" and bool(SLOT_REF.fullmatch(_source(token)))


def _alt(token) -> str:
    return " ".join((token.content or "").split())


def inline_runs(tokens, formulas: list | None = None) -> list[Run]:
    runs, bold, italic, strike = [], 0, 0, 0
    links = []
    for token in tokens or []:
        if token.type == "text" and formulas and math_markdown.PLACEHOLDER.search(token.content):
            # Công thức (kể cả dòng riêng nằm trong đề mục hay ô bảng) thành công thức trong dòng.
            for part in math_markdown.split(token.content, formulas):
                if isinstance(part, tuple):
                    runs.append(Run(part[0], math=True))
                elif part:
                    runs.append(Run(part, bool(bold), bool(italic), bool(strike)))
            continue
        if token.type == "strong_open": bold += 1
        elif token.type == "strong_close": bold -= 1
        elif token.type == "em_open": italic += 1
        elif token.type == "em_close": italic -= 1
        elif token.type == "s_open": strike += 1
        elif token.type == "s_close": strike -= 1
        elif token.type in {"text", "code_inline", "softbreak", "hardbreak", "image"}:
            text = token.content
            if token.type in {"softbreak", "hardbreak"}: text = "\n"
            if token.type == "image":
                number = _image_number(token)
                text = f"[Ảnh {number}: {_alt(token) or 'không có mô tả'}]" if number else f"[Ảnh: {token.content or 'không có mô tả'}]"
            runs.append(Run(text, bool(bold), bool(italic), bool(strike), token.type == "code_inline"))
        elif token.type == "link_close":
            if links:
                url, start = links.pop()
                label = ''.join(run.text for run in runs[start:])
                if url and url != label:
                    runs.append(Run(f' ({url})'))
        elif token.type == "link_open":
            # Keep the source address in downloads without fetching or executing it.
            links.append((token.attrGet('href'), len(runs)))
    return runs


def _trim(runs: list[Run]) -> list[Run]:
    """Bỏ phần chỉ có khoảng trắng hoặc xuống dòng ở hai đầu, còn lại khi một ảnh tách đoạn văn làm đôi."""
    while runs and not runs[0].text.strip() and not runs[0].math: runs.pop(0)
    while runs and not runs[-1].text.strip() and not runs[-1].math: runs.pop()
    if runs:
        if not runs[0].math: runs[0].text = runs[0].text.lstrip()
        if not runs[-1].math: runs[-1].text = runs[-1].text.rstrip()
    return runs


def inline_parts(tokens, formulas: list | None = None) -> list:
    """Như inline_runs, nhưng ảnh của hội thoại (anh-N) thành phần riêng ``(số, chú thích)``, khung chừa ảnh thành
    ``("slot", chú thích)`` và công thức dòng riêng thành ``("math", LaTeX)``, để dựng thành khối riêng."""
    parts, segment = [], []
    for token in tokens or []:
        number = _image_number(token) if token.type == "image" else 0
        if number:
            parts.extend([_trim(inline_runs(segment, formulas)), (number, _alt(token))])
            segment = []
        elif _is_slot(token):
            parts.extend([_trim(inline_runs(segment, formulas)), ("slot", _alt(token))])
            segment = []
        elif token.type == "text" and formulas and math_markdown.DISPLAY_OPEN in token.content:
            pieces = math_markdown.PLACEHOLDER.split(token.content)
            # split với nhóm bắt: [chữ, dấu mở, số, chữ, dấu mở, số, …]
            for position in range(0, len(pieces), 3):
                if pieces[position]:
                    segment.append(token.copy(content=pieces[position]))
                if position + 2 < len(pieces):
                    opener, number = pieces[position + 1], int(pieces[position + 2])
                    latex, display = formulas[number]
                    if opener == math_markdown.DISPLAY_OPEN:
                        parts.extend([_trim(inline_runs(segment, formulas)), ("math", latex)])
                        segment = []
                    else:
                        segment.append(token.copy(content=f"{math_markdown.INLINE_OPEN}{number}{math_markdown.INLINE_CLOSE}"))
        else:
            segment.append(token)
    parts.append(_trim(inline_runs(segment, formulas)))
    return parts


def _formula_error(latex: str, error: Exception) -> ValueError:
    short = " ".join(latex.split())
    short = short if len(short) <= 60 else short[:57] + "…"
    return ValueError(f'Công thức "{short}" chưa dựng được: {error} Sửa công thức rồi gọi lại công cụ.')


def parse_document(content: str) -> tuple[Cover | None, list[Block]]:
    """(Trang bìa nếu nội dung mở đầu bằng khối --- … ---, các khối của phần thân)."""
    if not content.strip() or len(content) > MAX_CONTENT:
        raise ValueError("Nội dung cần có từ 1 đến 60.000 ký tự.")
    cover, content = split_cover(content)
    content, formulas = math_markdown.extract(content)
    if len(formulas) > MAX_FORMULAS:
        raise ValueError(f"Mỗi tài liệu có tối đa {MAX_FORMULAS} công thức. Hãy chia thành nhiều tài liệu.")
    for latex, display in formulas:
        try:
            math_latex.parse(latex, display)
        except math_latex.MathError as error:
            raise _formula_error(latex, error) from None
    tokens = MarkdownIt("commonmark", {"html": False, "maxNesting": 20}).enable(["table", "strikethrough"]).parse(content)
    if len(tokens) > 12000:
        raise ValueError("Tài liệu có quá nhiều mục. Hãy chia thành các tài liệu nhỏ hơn.")
    blocks: list[Block] = []
    if cover is not None and cover.logo:
        # Logo trên bìa là một ảnh của hội thoại: khối "logo" để image_numbers tải nó, phần thân bỏ qua khối này.
        blocks.append(Block("logo", image=cover.logo))
    lists: list[ListInfo] = []
    counters: list[int] = []
    items: list[list] = []  # [danh sách, số của mục, đã gắn số vào đoạn nào chưa]
    index, quote_depth, list_count, has_toc = 0, 0, 0, False
    while index < len(tokens):
        token = tokens[index]
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            ordered = token.type == "ordered_list_open"
            same = sum(item.ordered == ordered for item in lists)
            start = min(max(int(token.attrGet("start") or 1), 0), 99999) if ordered else 1
            list_count += 1
            lists.append(ListInfo(list_count, ordered, min(len(lists), 8), ORDERED_STYLES[same % 3] if ordered else "bullet",
                                  "" if ordered else BULLETS[same % 2], start))
            counters.append(start)
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop(); counters.pop()
        elif token.type == "list_item_open":
            items.append([lists[-1], counters[-1], False])
            counters[-1] += 1
        elif token.type == "list_item_close": items.pop()
        elif token.type == "blockquote_open": quote_depth += 1
        elif token.type == "blockquote_close": quote_depth -= 1
        elif token.type == "heading_open":
            blocks.append(Block("heading", inline_runs(tokens[index + 1].children, formulas), int(token.tag[1:])))
        elif token.type == "paragraph_open":
            parts = inline_parts(tokens[index + 1].children, formulas)
            marker = len(parts) == 1 and "".join(run.text for run in parts[0]).strip().casefold() in TOC_MARKERS
            if marker and not items and not quote_depth:
                if not has_toc: blocks.append(Block("toc"))
                has_toc = True
            else:
                for part in parts:
                    if isinstance(part, tuple) and part[0] == "math":
                        blocks.append(Block("math", math=part[1]))
                    elif isinstance(part, tuple) and part[0] == "slot":
                        blocks.append(Block("slot", caption=part[1]))
                    elif isinstance(part, tuple):
                        blocks.append(Block("image", image=part[0], caption=part[1]))
                    elif part:
                        block = Block("quote" if quote_depth else "paragraph", part, min(len(lists), 6))
                        if items and not quote_depth:
                            item = items[-1]
                            block.list_info = item[0]
                            if not item[2]: block.number, item[2] = item[1], True
                        blocks.append(block)
        elif token.type in {"fence", "code_block"}:
            for line in math_markdown.restore(token.content, formulas).rstrip("\n").split("\n"):
                blocks.append(Block("code", [Run(line or " ", code=True)]))
        elif token.type == "hr": blocks.append(Block("rule"))
        elif token.type == "table_open":
            rows, row = [], []
            index += 1
            while index < len(tokens) and tokens[index].type != "table_close":
                cell = tokens[index]
                if cell.type == "tr_open": row = []
                elif cell.type == "inline": row.append(inline_runs(cell.children, formulas))
                elif cell.type == "tr_close": rows.append(row)
                index += 1
            if len(rows) > 100 or any(len(row) > MAX_TABLE_COLUMNS for row in rows):
                raise ValueError(f"Mỗi bảng hỗ trợ tối đa 100 dòng và {MAX_TABLE_COLUMNS} cột. Hãy chia bảng lớn trước khi xuất.")
            blocks.append(Block("table", rows=rows))
        index += 1
    if sum(block.kind == "image" for block in blocks) > MAX_IMAGES:
        raise ValueError(f"Mỗi tài liệu chèn tối đa {MAX_IMAGES} ảnh. Hãy bớt ảnh hoặc chia thành nhiều tài liệu.")
    if sum(block.kind == "slot" for block in blocks) > MAX_SLOTS:
        raise ValueError(f"Mỗi tài liệu chừa tối đa {MAX_SLOTS} khung ảnh.")
    if len(blocks) > 1200:
        raise ValueError("Tài liệu có quá nhiều đoạn. Hãy chia nhỏ trước khi xuất.")
    return cover, blocks


def parse_blocks(content: str) -> list[Block]:
    return parse_document(content)[1]


def image_numbers(blocks: list[Block]) -> set[int]:
    """Các số ảnh (Ảnh N của hội thoại) tài liệu chèn, kể cả logo trên bìa."""
    return {block.image for block in blocks if block.kind in {"image", "logo"} and block.image}


def list_indent(depth: int) -> tuple[int, int]:
    """Chỗ đặt số hoặc dấu đầu dòng và chỗ bắt đầu chữ (point), thụt treo như Word; mỗi cấp lồng thụt thêm 18 pt."""
    return 18 + 18 * depth, 36 + 18 * depth


def list_label(info: ListInfo, number: int) -> str:
    """Nhãn của một mục trong bản PDF, cùng kiểu Word dựng từ định nghĩa đánh số (numbering_level)."""
    if not info.ordered:
        return info.marker
    if info.style == "lowerLetter":  # như Word: y, z, aa, bb
        return chr(ord("a") + (max(number, 1) - 1) % 26) * ((max(number, 1) - 1) // 26 + 1) + "."
    if info.style == "lowerRoman":
        return _roman(max(number, 1)) + "."
    return f"{number}."


def _roman(number: int) -> str:
    result = ""
    for value, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
                           (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        count, number = divmod(number, value)
        result += letters * count
    return result


def numbering_level(level: int, info: ListInfo) -> str:
    """Một cấp trong định nghĩa đánh số của Word (numbering.xml), cùng nhãn và vị trí với bản PDF."""
    number_x, text_x = list_indent(level)
    kind, text = (info.style, f"%{level + 1}.") if info.ordered else ("bullet", info.marker)
    return (f'<w:lvl w:ilvl="{level}"><w:start w:val="{info.start}"/><w:numFmt w:val="{kind}"/>'
            f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
            f'<w:pPr><w:ind w:left="{text_x * 20}" w:hanging="{(text_x - number_x) * 20}"/></w:pPr></w:lvl>')


def fit(image: DocImage, width: float, height: float) -> tuple[float, float]:
    """Kích thước (point) để ảnh vừa khổ chữ: ảnh tính 96 dpi, không phóng to ảnh nhỏ, không cao quá ``height``."""
    natural_width, natural_height = image.width * .75, image.height * .75
    scale = min(1, width / natural_width, height / natural_height)
    return natural_width * scale, natural_height * scale


def placeholder(block: Block) -> str:
    return f"[Ảnh {block.image}: {block.caption}]" if block.caption else f"[Ảnh {block.image}]"


def plain(runs: list[Run]) -> str:
    return " ".join("".join(run.text for run in runs).split())


def body_blocks(title: str, blocks: list[Block]) -> tuple[str, list[Block]]:
    """(Tên in ở đầu tài liệu, phần thân để dựng).

    Đề mục mở đầu là tên bài (trùng tên tài liệu, hoặc không đề mục nào khác cùng cấp hay cao hơn, như "# Lời giải bài
    tập 5: Đại số Bool" rồi các "## Bài 1") thì thành phần tên ở đầu trang thay vì in hai lần. Đề mục cao nhất còn lại về
    cấp 1 ("##" là đề mục cấp 1 của kiểu trình bày), tối đa cấp 4. Khối logo chỉ dùng cho bìa."""
    blocks = [block for block in blocks if block.kind != "logo"]
    shown = " ".join(title.split())
    if blocks and blocks[0].kind == "heading":
        first = blocks[0]
        same = plain(first.runs).casefold() == shown.casefold()
        alone = not any(block.kind == "heading" and block.level <= first.level for block in blocks[1:])
        if same or alone:
            shown = shown if same or any(run.math for run in first.runs) else plain(first.runs)
            blocks = blocks[1:]
    levels = [block.level for block in blocks if block.kind == "heading"]
    top = min(levels, default=1)
    for block in blocks:
        if block.kind == "heading":
            block.level = min(block.level - top + 1, 4)
    return shown, blocks


def contents(blocks: list[Block]) -> list[Block]:
    """Đề mục vào mục lục (cấp 1–3)."""
    return [block for block in blocks if block.kind == "heading" and block.level <= TOC_LEVELS]


def table_caption(block: Block, following: Block | None) -> str | None:
    """Chữ chú thích nếu ``block`` là đoạn "Bảng: …" đứng ngay trên một bảng."""
    if block.kind != "paragraph" or block.list_info or following is None or following.kind != "table":
        return None
    match = TABLE_CAPTION.match(plain(block.runs))
    return match.group(1).strip() if match else None


def figure_caption(text: str) -> str:
    """Chú thích hình không kèm số: "Hình 2. …" đã có số thì giữ nguyên chữ sau số."""
    return re.sub(r"^(?:Hình|Figure|Ảnh)\s*\d+(?:\.\d+)*\s*[.:–—-]?\s*", "", text, flags=re.IGNORECASE).strip()


def running_title(title: str) -> str:
    title = " ".join(title.split())
    return title if len(title) <= 70 else title[:67] + "…"


def visible(runs: list[Run]) -> str:
    """Chữ hiện ra của một ô: công thức tính theo ký hiệu nhìn thấy (\\bar{x} là một chữ), không theo mã LaTeX."""
    text = "".join(re.sub(r"\\[A-Za-z]+|[{}^_\\$]", "", run.text) if run.math else run.text for run in runs)
    return " ".join(text.split())


def column_widths(rows: list[list[list[Run]]], total: float) -> list[float]:
    """Bề rộng cột (point), tổng bằng ``total``: cột nào cũng đủ rộng cho từ dài nhất của nó (không bẻ "AppLocker"
    thành hai dòng), phần còn lại chia theo độ dài chữ, nên cột số ngắn hẹp, cột chữ dài rộng."""
    columns = max((len(row) for row in rows), default=1)
    character = 6.3  # bề rộng trung bình một chữ Times New Roman 12 pt, có tính chữ đậm ở hàng đầu
    minimum, desired = [], []
    for column in range(columns):
        texts = [visible(row[column]) for row in rows if column < len(row)]
        word = max((len(piece) for text in texts for piece in text.split()), default=1)
        longest = max((len(text) for text in texts), default=1)
        minimum.append(word * character + 12)
        desired.append(max(min(longest, 45), word) * character + 12)
    if sum(desired) <= total:
        return [width * total / sum(desired) for width in desired]
    if sum(minimum) >= total:
        return [width * total / sum(minimum) for width in minimum]
    extra = total - sum(minimum)
    slack = [want - least for want, least in zip(desired, minimum)]
    return [least + extra * room / (sum(slack) or 1) for least, room in zip(minimum, slack)]


def centered_columns(rows: list[list[list[Run]]]) -> set[int]:
    """Cột chỉ toàn ô ngắn (số, 0/1 của bảng chân trị, ký hiệu) thì căn giữa."""
    columns = max((len(row) for row in rows), default=0)
    out = set()
    for column in range(columns):
        cells = [plain(row[column]) for row in rows[1:] if column < len(row)]
        if cells and all(len(cell) <= 6 for cell in cells):
            out.add(column)
    return out


# ---------- Công thức trong DOCX/PDF ----------
def omml(latex: str, display: bool, text_font: str):
    """Phần tử công thức Word (m:oMath hoặc m:oMathPara) dựng từ mã LaTeX đã kiểm ở parse_document."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    from features.documents.math.omml_out import to_omml
    xml = to_omml(math_latex.parse(latex, display), text_font)
    tag = 'm:oMathPara' if display else 'm:oMath'
    return parse_xml(xml.replace(f'<{tag}>', f'<{tag} {nsdecls("m", "w")}>', 1))


def register_fonts() -> None:
    """Phông cho bản PDF: Tinos (cùng bề rộng chữ với Times New Roman của bản Word), Cousine cho mã, STIX Two Math cho
    công thức và ký hiệu toán gõ thẳng trong chữ thường mà Tinos không có."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    from features.documents.math.layout import MATH_FONT, glyphs
    with _font_lock:
        if 'PetoTimes' not in pdfmetrics.getRegisteredFontNames():
            for suffix, style in [('', 'Regular'), ('-Bold', 'Bold'), ('-Italic', 'Italic'), ('-BoldItalic', 'BoldItalic')]:
                pdfmetrics.registerFont(TTFont('PetoTimes' + suffix, str(FONT_DIR / f'Tinos-{style}.ttf')))
            pdfmetrics.registerFontFamily('PetoTimes', normal='PetoTimes', bold='PetoTimes-Bold',
                                          italic='PetoTimes-Italic', boldItalic='PetoTimes-BoldItalic')
        if 'PetoMono' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('PetoMono', str(FONT_DIR / 'Cousine-Regular.ttf')))
            pdfmetrics.registerFontFamily('PetoMono', normal='PetoMono', bold='PetoMono', italic='PetoMono',
                                          boldItalic='PetoMono')
    glyphs()
    with _font_lock:
        # Phông toán chỉ có một kiểu; <b>, <i> quanh nó vẫn dùng chính nó thay vì báo lỗi thiếu kiểu đậm/nghiêng.
        pdfmetrics.registerFontFamily(MATH_FONT, normal=MATH_FONT, bold=MATH_FONT, italic=MATH_FONT, boldItalic=MATH_FONT)


def fallback(text: str, body: dict, math: dict, math_font: str) -> str:
    """Bọc các ký tự phông chữ thiếu mà phông toán có (≤, ∈, →…) trong <font> của phông toán."""
    out, run = [], []
    for char in text:
        missing = ord(char) not in body and ord(char) in math
        if missing:
            run.append(char)
            continue
        if run:
            out.append(f'<font face="{math_font}">{"".join(run)}</font>')
            run = []
        out.append(char)
    if run:
        out.append(f'<font face="{math_font}">{"".join(run)}</font>')
    return ''.join(out)


def math_slot(latex: str, size: float, text_fonts, slots: list) -> str:
    """Ô ảnh rỗng đúng cỡ công thức trong dòng; attach_math gắn hình công thức vào ô, MathCanvas vẽ nó."""
    from features.documents.math.layout import layout
    box = layout(math_latex.parse(latex, False), size, text_fonts)
    slots.append(box)
    height = max(box.height + box.depth, 0.1)
    return (f'<img src="{escape(str(MATH_SLOT))}" width="{box.width:.2f}" height="{height:.2f}" '
            f'valign="{-box.depth:.2f}"/>')


def attach_math(paragraph, boxes: list) -> None:
    if not boxes:
        return
    remaining = iter(boxes)
    for fragment in getattr(paragraph, 'frags', []):
        definition = getattr(fragment, 'cbDefn', None)
        if definition is not None and getattr(definition, 'kind', None) == 'img':
            box = next(remaining, None)
            if box is None:
                break
            definition.image.peto_math = box


_canvas_cache: list = []


def _canvas_class():
    if _canvas_cache:
        return _canvas_cache[0]
    from reportlab.pdfgen.canvas import Canvas

    from features.documents.math.layout import draw

    class MathCanvas(Canvas):
        """Canvas vẽ công thức vào ô ảnh giữ chỗ thay cho ảnh rỗng (nét vector, chữ chọn được)."""

        def drawImage(self, image, x, y, width=None, height=None, mask=None, *args, **kwargs):
            box = getattr(image, 'peto_math', None)
            if box is None:
                return super().drawImage(image, x, y, width, height, mask, *args, **kwargs)
            self.saveState()
            self.setFillColorRGB(0, 0, 0)
            self.setStrokeColorRGB(0, 0, 0)
            draw(self, box, x, y + box.depth)
            self.restoreState()
            return (width, height)

    _canvas_cache.append(MathCanvas)
    return MathCanvas


def math_canvas(*args, **kwargs):
    return _canvas_class()(*args, **kwargs)


def math_block(latex: str, size: float, text_fonts):
    """Công thức dòng riêng trong PDF: căn giữa, thu nhỏ nếu rộng hơn khổ chữ; số hiệu \\tag ở lề phải."""
    from reportlab.platypus import Flowable

    from features.documents.math.layout import draw, layout

    formula = math_latex.parse(latex, True)
    box = layout(formula, size, text_fonts)
    tag = layout(math_latex.Formula([math_latex.Text(f'({formula.tag})')]), size, text_fonts) if formula.tag else None

    class MathBlock(Flowable):
        def wrap(self, available_width, available_height):
            self.available = available_width
            reserved = (tag.width + size * 1.5) * 2 if tag else 0
            self.scale = min(1.0, (available_width - reserved) / box.width) if box.width else 1.0
            self.height = (box.height + box.depth) * self.scale + size * 0.9
            return available_width, self.height

        def draw(self):
            canvas = self.canv
            canvas.saveState()
            canvas.setFillColorRGB(0, 0, 0)
            canvas.setStrokeColorRGB(0, 0, 0)
            baseline = size * 0.45 + box.depth * self.scale
            left = (self.available - box.width * self.scale) / 2
            canvas.translate(left, baseline)
            canvas.scale(self.scale, self.scale)
            draw(canvas, box, 0, 0)
            canvas.restoreState()
            if tag:
                canvas.saveState()
                canvas.setFillColorRGB(0, 0, 0)
                draw(canvas, tag, self.available - tag.width, baseline)
                canvas.restoreState()

    block = MathBlock()
    block.spaceBefore, block.spaceAfter = 2, 6
    return block


# ---------- Dựng tệp ----------
def render_docx(title: str, content: str, layout: str = 'classic', images: dict[int, DocImage] | None = None,
                toc_pages: list | None = None) -> bytes:
    from features.documents.docx_out import render
    return render(title, content, layout, images, toc_pages)


def render_pdf(title: str, content: str, layout: str = 'classic', images: dict[int, DocImage] | None = None,
               toc_out: list | None = None) -> bytes:
    from features.documents.pdf_out import render
    return render(title, content, layout, images, toc_out)
