"""Phông của slide: PPTX ghi tên Arial / Times New Roman (máy nào cũng có, đủ dấu tiếng Việt), còn bản xem trước và việc đo
chữ dùng Liberation Sans / Serif đi kèm, có cùng độ rộng từng chữ với hai phông đó. Nhờ vậy chữ xuống dòng giống PowerPoint.
"""
import threading

from features.documents.export import FONT_DIR

SANS, SERIF = 'Arial', 'Times New Roman'
_FILES = {
    (SANS, False, False): ('PetoSlideSans', 'LiberationSans-Regular.ttf'),
    (SANS, True, False): ('PetoSlideSans-Bold', 'LiberationSans-Bold.ttf'),
    (SANS, False, True): ('PetoSlideSans-Italic', 'LiberationSans-Italic.ttf'),
    (SANS, True, True): ('PetoSlideSans-BoldItalic', 'LiberationSans-BoldItalic.ttf'),
    (SERIF, False, False): ('PetoSlideSerif', 'LiberationSerif-Regular.ttf'),
    (SERIF, True, False): ('PetoSlideSerif-Bold', 'LiberationSerif-Bold.ttf'),
}
_lock = threading.Lock()
_ready = False


def register():
    global _ready
    if _ready:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _lock:
        if not _ready:
            names = set(pdfmetrics.getRegisteredFontNames())
            for name, filename in _FILES.values():
                if name not in names:
                    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
            _ready = True


def font_name(family: str, bold: bool = False, italic: bool = False) -> str:
    """Tên phông ReportLab đã đăng ký. Serif không có bản nghiêng: slide chỉ dùng Serif cho tiêu đề đậm."""
    register()
    key = (family, bold, italic if family == SANS else False)
    return _FILES.get(key, _FILES[(family, bold, False)])[0]


def width(text: str, family: str, size: float, bold: bool = False, italic: bool = False, spacing: float = 0) -> float:
    from reportlab.pdfbase import pdfmetrics
    return pdfmetrics.stringWidth(text, font_name(family, bold, italic), size) + spacing * len(text)


def descent(family: str, size: float, bold: bool = False) -> float:
    """Khoảng từ đường chân chữ xuống đáy chữ (dương), để đặt dòng chữ trong ô cao cố định."""
    from reportlab.pdfbase import pdfmetrics
    return -pdfmetrics.getDescent(font_name(family, bold), size)


def wrap(text: str, family: str, size: float, limit: float, bold: bool = False, italic: bool = False,
         spacing: float = 0) -> list[str]:
    """Ngắt dòng theo từ như PowerPoint; một từ dài hơn cả dòng thì cắt theo ký tự."""
    lines: list[str] = []
    for paragraph in text.split('\n'):
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
        current = ''
        for word in words:
            candidate = f'{current} {word}' if current else word
            if width(candidate, family, size, bold, italic, spacing) <= limit:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = ''
            while width(word, family, size, bold, italic, spacing) > limit and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and width(word[:cut], family, size, bold, italic, spacing) > limit:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def balanced(text: str, family: str, size: float, limit: float, bold: bool = False, spacing: float = 0) -> float:
    """Bề rộng hẹp nhất vẫn giữ nguyên số dòng, để tiêu đề nhiều dòng chia đều thay vì để một chữ lẻ ở dòng cuối."""
    count = len(wrap(text, family, size, limit, bold, spacing=spacing))
    if count < 2:
        return limit
    low, high = limit / count, limit
    for _ in range(18):
        middle = (low + high) / 2
        if len(wrap(text, family, size, middle, bold, spacing=spacing)) > count:
            low = middle
        else:
            high = middle
    return min(limit, high + 2)
