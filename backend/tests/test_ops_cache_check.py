"""ops.cache_check: đọc usage_events chỉ đọc, đánh dấu lần gọi có phần đầu đổi, không in chữ người dùng (G1.1b)."""
import sqlite3
import time
from contextlib import closing
from zoneinfo import ZoneInfo

from ops import cache_check


def make_db(path, with_hash=True):
    with closing(sqlite3.connect(path)) as db:
        extra = ', prefix_hash TEXT' if with_hash else ''
        db.execute('CREATE TABLE usage_events (at REAL, kind TEXT, surface TEXT, purpose TEXT, model TEXT, effort TEXT, '
                   f'input_tokens INTEGER, cached_tokens INTEGER, cache_write_tokens INTEGER{extra})')
        now = time.time()
        values = [
            (now - 300, 'call', 'chat', 'chat', 'haiku', 'medium', 25236, 0, 19181, 'aaaa1111'),
            (now - 280, 'call', 'chat', 'side', 'haiku', 'low', 300, 0, 0, 'ffff0000'),
            (now - 260, 'call', 'chat', 'chat', 'haiku', 'medium', 26046, 19181, 5419, 'aaaa1111'),
            (now - 240, 'call', 'chat', 'chat', 'luna', 'low', 16240, 0, 15365, 'bbbb2222'),
            (now - 200, 'call', 'chat', 'chat', 'haiku', 'medium', 35436, 0, 34000, 'cccc3333'),
            (now - 99999, 'call', 'chat', 'chat', 'haiku', 'medium', 1, 0, 0, 'dddd4444'),
        ]
        if not with_hash:
            values = [row[:-1] for row in values]
        db.executemany(f'INSERT INTO usage_events VALUES ({", ".join("?" * len(values[0]))})', values)
        db.commit()


def test_marks_the_call_whose_prefix_changed(tmp_path, capsys):
    path = tmp_path / 'peto.db'
    make_db(path)
    items = cache_check.annotate(cache_check.rows(path, 6))
    assert [item['model'] for item in items] == ['haiku', 'haiku', 'luna', 'haiku']
    assert [item['note'] for item in items] == ['', '', '', 'phần đầu đổi']
    assert [item['ratio'] for item in items] == ['0%', '74%', '0%', '0%']
    assert 'dddd4444' not in cache_check.table(items, ZoneInfo('UTC'))
    assert cache_check.main(['--db', str(path), '--hours', '1', '--timezone', 'Asia/Ho_Chi_Minh']) == 0
    out = capsys.readouterr().out
    assert 'phần đầu đổi' in out and 'cccc3333' in out


def test_old_tables_without_the_fingerprint_still_read(tmp_path, capsys):
    path = tmp_path / 'old.db'
    make_db(path, with_hash=False)
    items = cache_check.annotate(cache_check.rows(path, 6))
    assert len(items) == 4 and all(item['prefix_hash'] is None and item['note'] == '' for item in items)
    assert cache_check.main(['--db', str(tmp_path / 'missing.db')]) == 1
    assert 'Không đọc được' in capsys.readouterr().err
    assert not (tmp_path / 'missing.db').exists()
