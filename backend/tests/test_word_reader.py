"""Đọc Word: công thức (OMML → LaTeX), số thứ tự Word tự đánh, phông Symbol, hình và công thức MathType."""
import io
import json
import zipfile

import pytest

from features.documents import reader
from features.documents.math.omml_in import omml_to_latex
from features.documents.word_reader import format_number, parse

NAMESPACES = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
              'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
              'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
              'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
              'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
              'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
              'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
              'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def word(body: str, numbering: str | None = None, styles: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", f"<w:document {NAMESPACES}><w:body>{body}</w:body></w:document>")
        if numbering is not None:
            archive.writestr("word/numbering.xml", f"<w:numbering {NAMESPACES}>{numbering}</w:numbering>")
        if styles is not None:
            archive.writestr("word/styles.xml", f"<w:styles {NAMESPACES}>{styles}</w:styles>")
    return output.getvalue()


def read(body: str, **parts) -> dict:
    return reader.extract_document(word(body, **parts), reader.DOCX_MIME, 80_000, 100)


def latex(omml: str) -> str:
    return omml_to_latex(parse(f"<m:oMath {NAMESPACES}>{omml}</m:oMath>".encode()))


def run(text: str, plain: bool = False) -> str:
    style = '<m:rPr><m:sty m:val="p"/></m:rPr>' if plain else ""
    return f"<m:r>{style}<m:t>{text}</m:t></m:r>"


FRACTION = (run("A=") + "<m:f><m:fPr><m:ctrlPr/></m:fPr><m:num>" + run("x+1") + "</m:num><m:den>"
            "<m:sSup><m:sSupPr><m:ctrlPr/></m:sSupPr><m:e>" + run("x") + "</m:e><m:sup>" + run("2") + "</m:sup></m:sSup>"
            + run("-1") + "</m:den></m:f>")


@pytest.mark.parametrize("omml,expected", [
    (FRACTION, r"A=\frac{x+1}{x^{2}-1}"),
    ('<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>' + run("x") + '</m:e></m:rad>', r"\sqrt{x}"),
    ('<m:rad><m:deg>' + run("3") + '</m:deg><m:e>' + run("x+1") + '</m:e></m:rad>', r"\sqrt[3]{x+1}"),
    ('<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr><m:sub>' + run("i=1")
     + '</m:sub><m:sup>' + run("n") + '</m:sup><m:e><m:sSup><m:e>' + run("i") + '</m:e><m:sup>' + run("2")
     + '</m:sup></m:sSup></m:e></m:nary>', r"\sum_{i=1}^{n} i^{2}"),
    ('<m:nary><m:naryPr><m:limLoc m:val="subSup"/></m:naryPr><m:sub>' + run("0") + '</m:sub><m:sup>' + run("1")
     + '</m:sup><m:e>' + run("x dx") + '</m:e></m:nary>', r"\int_{0}^{1} x dx"),
    ('<m:func><m:fName><m:limLow><m:e>' + run("lim", plain=True) + '</m:e><m:lim>' + run("x→0") + '</m:lim>'
     '</m:limLow></m:fName><m:e><m:f><m:num><m:func><m:fName>' + run("sin", plain=True) + '</m:fName><m:e>'
     + run("x") + '</m:e></m:func></m:num><m:den>' + run("x") + '</m:den></m:f></m:e></m:func>',
     r"\lim_{x\to0} \frac{\sin x}{x}"),
    ('<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e><m:m><m:mr><m:e>' + run("1")
     + '</m:e><m:e>' + run("2") + '</m:e></m:mr><m:mr><m:e>' + run("3") + '</m:e><m:e>' + run("4")
     + '</m:e></m:mr></m:m></m:e></m:d>', r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}"),
    ('<m:d><m:dPr><m:begChr m:val="{"/><m:endChr m:val=""/></m:dPr><m:e><m:eqArr><m:e>' + run("x+y=3")
     + '</m:e><m:e>' + run("x-y=1") + '</m:e></m:eqArr></m:e></m:d>',
     r"\begin{cases} x+y=3 \\ x-y=1 \end{cases}"),
    ('<m:bar><m:barPr><m:pos m:val="top"/></m:barPr><m:e>' + run("x") + '</m:e></m:bar>' + run("y")
     + '<m:bar><m:barPr><m:pos m:val="top"/></m:barPr><m:e>' + run("z") + '</m:e></m:bar>',
     r"\overline{x}y\overline{z}"),
    ('<m:acc><m:accPr><m:chr m:val="⃗"/></m:accPr><m:e>' + run("AB") + '</m:e></m:acc>', r"\overrightarrow{AB}"),
    ('<m:d><m:e>' + FRACTION + '</m:e></m:d>', r"\left( A=\frac{x+1}{x^{2}-1} \right)"),
    ('<m:sSup><m:e><m:d><m:e>' + run("a+b") + '</m:e></m:d></m:e><m:sup>' + run("2") + '</m:sup></m:sSup>',
     r"(a+b)^{2}"),
    ('<m:d><m:e><m:f><m:fPr><m:type m:val="noBar"/></m:fPr><m:num>' + run("n") + '</m:num><m:den>' + run("k")
     + '</m:den></m:f></m:e></m:d>', r"\binom{n}{k}"),
    (run("𝑥") + run("∈") + run("ℝ"), r"x\in\mathbb{R}"),
    (run("α+β≤π"), r"\alpha+\beta\le\pi"),
    ('<m:r><m:rPr><m:nor/></m:rPr><m:t> với mọi </m:t></m:r>' + run("x"), r"\text{ với mọi }x"),
    ('<m:sSubSup><m:e>' + run("x") + '</m:e><m:sub>' + run("i") + '</m:sub><m:sup>' + run("2")
     + '</m:sup></m:sSubSup>', r"x_{i}^{2}"),
    ('<m:eqArr><m:e>' + run("x&amp;=1") + '</m:e><m:e>' + run("y&amp;=2") + '</m:e></m:eqArr>',
     r"\begin{aligned} x&=1 \\ y&=2 \end{aligned}"),
    ('<m:f><m:fPr><m:type m:val="lin"/></m:fPr><m:num>' + run("a+b") + '</m:num><m:den>' + run("2")
     + '</m:den></m:f>', r"{a+b}/2"),
    (run("50%"), r"50\%"),
])
def test_word_equations_become_latex(omml, expected):
    assert latex(omml) == expected


def test_equations_reach_peto_inline_and_display():
    body = (f'<w:p><w:r><w:t xml:space="preserve">Câu 1. Rút gọn </w:t></w:r><m:oMath>{FRACTION}</m:oMath></w:p>'
            f'<w:p><m:oMathPara><m:oMath>{run("y=2x")}</m:oMath></m:oMathPara></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><m:oMath>' + run("x") + '</m:oMath></w:p></w:tc><w:tc><w:p><w:r><w:t>1</w:t>'
            '</w:r></w:p></w:tc></w:tr></w:tbl>')
    document = read(body)
    assert document["status"] == "ready"
    assert "[Đoạn 1]\nCâu 1. Rút gọn $A=\\frac{x+1}{x^{2}-1}$" in document["text"]
    assert "[Đoạn 2]\n$$y=2x$$" in document["text"]
    assert "[Bảng 1]\n$x$ | 1" in document["text"]
    assert document["formulas"] == 3
    assert "3 công thức" in document["notice"]
    assert document["word_format"] == reader.WORD_FORMAT


NUMBERING = """
<w:abstractNum w:abstractNumId="0">
  <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1)"/></w:lvl>
  <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2."/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="1">
  <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="upperRoman"/><w:lvlText w:val="%1."/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="2">
  <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val=""/></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="0"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>
<w:num w:numId="3"><w:abstractNumId w:val="1"/></w:num>
<w:num w:numId="4"><w:abstractNumId w:val="2"/></w:num>
"""
STYLES = """
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:basedOn w:val="Normal"/><w:pPr><w:numPr><w:numId w:val="3"/></w:numPr></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1Sub"><w:basedOn w:val="Heading1"/></w:style>
"""


def numbered(text: str, num: int | None = None, level: int = 0, style: str | None = None) -> str:
    properties = f'<w:pStyle w:val="{style}"/>' if style else ""
    if num is not None:
        properties += f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{num}"/></w:numPr>'
    return f"<w:p><w:pPr>{properties}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"


def test_word_numbering_labels_match_word():
    body = "".join([
        numbered("Mở bài", style="Heading1"),
        numbered("Lập bảng", 1), numbered("Viết công thức", 1), numbered("Ý con", 1, 1), numbered("Ý con nữa", 1, 1),
        numbered("Rút gọn", 1),
        numbered("Danh sách mới", 2), numbered("Tiếp", 2),
        numbered("Thân bài", style="Heading1Sub"),
        numbered("Gạch đầu dòng", 4),
        numbered("Bỏ số", 0),
    ])
    text = read(body, numbering=NUMBERING, styles=STYLES)["text"]
    for line in ["I. Mở bài", "a) Lập bảng", "b) Viết công thức", "b.1. Ý con", "b.2. Ý con nữa", "c) Rút gọn",
                 "a) Danh sách mới", "b) Tiếp", "II. Thân bài", "• Gạch đầu dòng", "[Đoạn 11]\nBỏ số"]:
        assert line in text, line


def test_empty_numbered_paragraph_still_counts():
    body = numbered("Một", 1) + '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr></w:p>' \
        + numbered("Ba", 1)
    assert "c) Ba" in read(body, numbering=NUMBERING)["text"]


@pytest.mark.parametrize("number,kind,expected", [
    (1, "lowerLetter", "a"), (27, "lowerLetter", "aa"), (4, "upperRoman", "IV"), (9, "lowerRoman", "ix"),
    (7, "decimalZero", "07"), (3, "decimalEnclosedCircle", "③"), (5, "none", ""), (12, "decimal", "12"),
])
def test_number_formats(number, kind, expected):
    assert format_number(number, kind) == expected


def test_symbol_font_and_symbol_characters():
    body = ('<w:p><w:r><w:t xml:space="preserve">x </w:t></w:r>'
            '<w:r><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:rPr><w:t>Î</w:t></w:r>'
            '<w:r><w:t xml:space="preserve"> A, góc </w:t></w:r>'
            '<w:r><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:rPr><w:t>a</w:t></w:r>'
            '<w:r><w:t xml:space="preserve"> </w:t></w:r><w:r><w:sym w:font="Symbol" w:char="F0B9"/></w:r>'
            '<w:r><w:t xml:space="preserve"> 90°</w:t></w:r></w:p>')
    assert "x ∈ A, góc α ≠ 90°" in read(body)["text"]


def test_pictures_mathtype_and_text_boxes_are_marked_once():
    picture = ('<w:r><w:drawing><wp:inline><a:graphic><a:graphicData '
               'uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic/></a:graphicData></a:graphic>'
               '</wp:inline></w:drawing></w:r>')
    mathtype = ('<w:r><w:object><v:shape><v:imagedata r:id="rId9"/></v:shape>'
                '<o:OLEObject Type="Embed" ProgID="Equation.DSMT4" r:id="rId10"/></w:object></w:r>')
    box = ('<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wp:anchor><a:graphic><a:graphicData '
           'uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"><wps:wsp><wps:txbx><w:txbxContent>'
           '<w:p><w:r><w:t>Hộp chữ</w:t></w:r></w:p></w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic>'
           '</wp:anchor></w:drawing></mc:Choice><mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent><w:p><w:r>'
           '<w:t>Hộp chữ</w:t></w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback>'
           '</mc:AlternateContent></w:r>')
    body = (f'<w:p><w:r><w:t xml:space="preserve">Câu 2. Xem hình </w:t></w:r>{picture}</w:p>'
            f'<w:p><w:r><w:t xml:space="preserve">Câu 3. Tính </w:t></w:r>{mathtype}</w:p>'
            f'<w:p><w:r><w:t>Câu 4.</w:t></w:r>{box}</w:p>')
    document = read(body)
    text = document["text"]
    assert "Câu 2. Xem hình [Hình 1 trong tệp]" in text
    assert "Câu 3. Tính [Công thức MathType 1: Peto không đọc được]" in text
    assert text.count("Hộp chữ") == 1 and "[Hình 2" not in text
    assert document["status"] == "partial" and document["truncated"] is False
    assert document["formulas_unread"] == 1 and document["images"] == 1
    assert "MathType" in document["notice"] and "1 hình" in document["notice"]


def test_tracked_deletions_are_not_read():
    body = ('<w:p><w:r><w:t xml:space="preserve">Giữ </w:t></w:r><w:del><w:r><w:delText>xóa</w:delText></w:r></w:del>'
            '<w:ins><w:r><w:t>chèn</w:t></w:r></w:ins></w:p>')
    assert "[Đoạn 1]\nGiữ chèn" in read(body)["text"]


def test_old_word_reads_are_read_again_but_still_shown():
    old = {"version": reader.VERSION, "status": "ready", "notice": "Đã đọc phần thân văn bản và bảng biểu trong Word.",
           "text": "[Đoạn 1]\nCâu 1", "characters": 15}
    assert reader.cached_document(json.dumps(old)) is None
    assert reader.public_document(json.dumps(old))["status"] == "ready"
    text_file = {"version": reader.VERSION, "status": "ready", "notice": "Đã đọc tệp chữ.", "text": "Word", "characters": 4}
    assert reader.cached_document(json.dumps(text_file)) == text_file
    fresh = read(numbered("Một", None))
    assert reader.cached_document(json.dumps(fresh)) == fresh
    assert reader.public_document(json.dumps(fresh)).get("formulas") == 0
