"""Bản đọc lại cấu trúc (trường check) trong kết quả create_document và create_presentation: P2 của khảo sát công cụ."""
import json
from types import SimpleNamespace

import storage as db
from ai.base import ChatMessage
from conftest import TEST_OWNER
from features.documents import tools as document_tools
from features.documents.readback import deck_check, document_check
from features.documents.slides.spec import DeckInput, normalize
from features.documents.tools import DocumentSession, current_session
from test_presentations import slide

REPORT = r"""---
trường: Trường Đại học Thử Nghiệm
loại: Báo cáo môn học
thành viên:
- Nguyễn Văn B | 124001022
---
# Báo cáo mạng máy tính

[TOC]

## Chương 1. Mở đầu
Đoạn mở đầu có công thức $x^2 + 1$.

### 1.1 Mục tiêu
- Ý một
- Ý hai

Bảng: Kết quả đo
| Chỉ số | Giá trị |
|---|---|
| Độ trễ | $\alpha$ |

$$\int_0^1 x\,dx$$

![Sơ đồ mạng](khung-anh)

## Chương 2. Kết luận
Kết thúc.
"""


def test_document_check_matches_the_built_structure():
    check = document_check('Báo cáo mạng máy tính', REPORT, 3)
    # Đề mục trùng tên tài liệu thành tên ở đầu trang, không tính là chương; "##" là cấp 1 của kiểu trình bày.
    assert check['title'] == 'Báo cáo mạng máy tính'
    assert check['headings'] == [[1, 'Chương 1. Mở đầu'], [2, '1.1 Mục tiêu'], [1, 'Chương 2. Kết luận']]
    assert (check['tables'], check['formulas'], check['images'], check['image_slots']) == (1, 3, 0, 1)
    assert check['toc'] is True and check['pages'] == 3 and check['words'] > 20
    # Trường, thành viên đã có; khoa và giảng viên sẽ in dòng chấm.
    assert check['cover'] == {'blank': ['khoa', 'giảng viên']}


def test_document_check_is_bounded_and_has_no_cover_without_a_cover_block():
    content = '\n\n'.join(f'## Chương {index} ' + 'rất dài ' * 40 + f'\n\nĐoạn {index}.' for index in range(1, 31))
    check = document_check('Tài liệu dài', content, 12)
    assert len(check['headings']) == 20 and check['headings_omitted'] == 10
    assert all(len(text) <= 60 for _, text in check['headings'])
    assert 'cover' not in check and check['toc'] is False
    assert len(json.dumps(check, ensure_ascii=False)) < 2000


async def test_create_document_returns_check_with_a_comparison_note(client):
    conversation = await db.create_conversation(TEST_OWNER, 'Báo cáo')
    session = DocumentSession(TEST_OWNER, conversation)
    content = '---\nloại: Báo cáo thực hành\n---\n# Báo cáo\n\n## Mở đầu\nNội dung.'
    args = json.dumps({'title': 'Báo cáo thực hành', 'content': content, 'format': 'docx', 'style': 'classic'},
                      ensure_ascii=False)
    result = await session.create(args)
    assert result['ok'], result
    assert result['check']['cover'] == {'blank': ['trường', 'khoa', 'giảng viên', 'thành viên']}
    assert result['check']['pages'] == result['artifact']['pages']
    assert document_tools.DOCUMENT_CHECK_NOTE in result['instruction']
    assert await session.create(args) == result and len(session.created) == 1


async def test_a_failed_readback_keeps_the_created_file(client, monkeypatch):
    def broken(*args):
        raise RuntimeError('lỗi giả')
    monkeypatch.setattr(document_tools, 'document_check', broken)
    session = DocumentSession(TEST_OWNER, await db.create_conversation(TEST_OWNER, 'Lỗi đọc lại'))
    result = await session.create(json.dumps({'title': 'Ghi chú', 'content': '# Ghi chú\n\nMột dòng.', 'format': 'pdf',
                                              'style': 'minimal'}, ensure_ascii=False))
    assert result['ok'] and 'check' not in result
    assert document_tools.DOCUMENT_CHECK_NOTE not in result['instruction']
    assert len(session.created) == 1


def deck(notes: list[str], titles: list[str] | None = None) -> str:
    titles = titles or [f'Slide số {index}' for index in range(1, len(notes) + 1)]
    slides = [slide('cover', titles[0], notes[0], subtitle='Đồ án môn học')]
    slides += [slide('bullets', title, note, bullets=['Ý chính một', 'Ý chính hai']) for title, note in zip(titles[1:], notes[1:])]
    return json.dumps({'title': 'Bài thuyết trình thử', 'theme': 'clean', 'slides': slides}, ensure_ascii=False)


async def test_presentation_check_lists_slides_and_reports_missing_notes(client):
    session = DocumentSession(TEST_OWNER, await db.create_conversation(TEST_OWNER, 'Slide'))
    result = await session.present(deck(['Chào hỏi.', '', 'Kết luận.']))
    assert result['ok'], result
    assert result['check']['slides'] == [[1, 'cover', 'Slide số 1'], [2, 'bullets', 'Slide số 2'],
                                         [3, 'bullets', 'Slide số 3']]
    assert result['check']['without_notes'] == [2]
    assert 'Slide 2 chưa có ghi chú' in result['instruction']
    # Câu dặn cũ luôn nói mọi slide có ghi chú, kể cả khi sai.
    assert 'mỗi slide có ghi chú' not in result['instruction']
    full = await session.present(deck(['Chào hỏi.', 'Nói ý chính.']))
    assert full['check']['without_notes'] == [] and 'Mọi slide đều có ghi chú' in full['instruction']


def test_deck_check_is_bounded_for_the_largest_deck():
    # Tiêu đề slide dài nhất normalize nhận là 100 ký tự; check chỉ giữ 40.
    titles = [f'{index} ' + 'tiêu đề rất dài ' * 6 for index in range(1, 26)]
    data = json.loads(deck(['Ghi chú.'] * 25, titles))
    check = deck_check(normalize(DeckInput.model_validate_json(json.dumps(data, ensure_ascii=False))))
    assert len(check['slides']) == 25 and all(len(title) <= 40 for _, _, title in check['slides'])
    assert len(json.dumps(check, ensure_ascii=False)) < 2000


async def test_model_receives_the_check_in_the_tool_result(client, monkeypatch):
    from test_clock_tools import FakeStream, call, done, fake_provider
    args = json.dumps({'title': 'Báo cáo mạng máy tính', 'content': REPORT, 'format': 'docx', 'style': 'band'},
                      ensure_ascii=False)
    first = FakeStream([done(call('create_document', args))])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã tạo tệp.'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    token = current_session.set(DocumentSession(TEST_OWNER, await db.create_conversation(TEST_OWNER, 'Vòng công cụ')))
    try:
        _ = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Tạo báo cáo')])]
    finally:
        current_session.reset(token)
    result = json.loads(requests[1]['input'][-1]['output'])
    assert result['ok'] and result['check']['tables'] == 1 and result['check']['cover']['blank'] == ['khoa', 'giảng viên']
