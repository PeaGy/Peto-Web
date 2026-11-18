"""G2.2: mức suy nghĩ "Tự động" khớp theo trọn từ và có tín hiệu không phụ thuộc từ khóa.

Bảng ví dụ lấy từ mục 3 #8 của bản audit 10/11/2026: trước đây khớp chuỗi con nên câu cần nghĩ bị xếp thấp, câu thường
bị xếp vừa."""
import pytest

from ai.routing import choose_effort, looks_like_math


@pytest.mark.parametrize(('text', 'expected'), [
    # Bảng #8 của bản audit.
    ('viết bài luận 1500 chữ phân tích Truyện Kiều', 'medium'),
    ('so sánh ưu nhược hai phương án kinh doanh', 'medium'),
    ('review hợp đồng thuê nhà', 'medium'),
    ('thanh toán hóa đơn', 'low'),
    ('rapid prototyping', 'low'),
    # Chuỗi con khác từng bị nhầm.
    ('kế toán cuối năm cần chuẩn bị gì', 'low'),
    ('mình muốn đi du lịch Đà Lạt', 'low'),
    ('gửi giúp cái happy birthday', 'low'),
    # Những gì vẫn phải lên mức.
    ('giải phương trình bậc hai giúp tao', 'medium'),
    ('bài toán này giải sao', 'medium'),
    ('tính đạo hàm của x^2 + 3x', 'medium'),
    ('luong giac lop 10 kho qua', 'medium'),
    ('lỗi code python này là gì', 'medium'),
    ('API của OpenRouter có công khai không', 'medium'),
    ('chứng minh giúp tao bất đẳng thức này', 'high'),
    ('write an essay comparing two cities', 'medium'),
    ('viết giúp 300 chữ giới thiệu bản thân', 'low'),
    ('viết bài 2.000 từ về biến đổi khí hậu', 'medium'),
])
def test_effort_follows_whole_words(text, expected):
    assert choose_effort(text) == expected


@pytest.mark.parametrize('text', [
    'chào', 'chào cậu', 'Chào bạn!', 'xin chào Peto', 'hello', 'hi', 'hey peto', 'cảm ơn nha', 'cám ơn bạn', 'oke',
    'thanks!', 'chúc ngủ ngon',
])
def test_greetings_never_go_above_low(text):
    assert choose_effort(text) == 'low'
    # Kể cả khi tab Trò chuyện chưa có tệp nào; có tệp thì đã là một yêu cầu đọc tệp.
    assert choose_effort(text, attachments=1) == 'medium'


def test_signals_that_do_not_depend_on_keywords():
    assert choose_effort('xem giúp tệp này') == 'low'
    assert choose_effort('xem giúp tệp này', attachments=2) == 'medium'
    assert choose_effort('soạn giúp thư mời họp', document=True) == 'medium'
    assert choose_effort('đọc thử đoạn này ' * 50) == 'medium'                  # tin dài
    assert choose_effort('sao chạy không được\n```\nprint(1)\n```') == 'medium'  # khối code
    assert choose_effort('đoạn này sai ở đâu:\n    x = foo()') == 'medium'      # code thụt lề


def test_vietnamese_slash_is_not_a_division():
    assert not looks_like_math('ăn trưa và/hoặc ăn tối')
    assert looks_like_math('tính 3/4 + 1/2')
