"""Xem prompt cache của các lượt Chat gần đây từ bảng usage_events; chỉ đọc, không in chữ nào của người dùng.

Mỗi dòng là một lần gọi model của tab Trò chuyện: giờ, model, mức suy nghĩ, token đầu vào, token đọc và ghi cache, và
dấu vân tay phần đầu cố định (``prefix_hash``, G1.1b). Hai lần gọi liền nhau của cùng model mà dấu khác nhau là phần đầu
đã đổi (system prompt, công cụ), nên lần sau không đọc lại được cache; cột ghi chú đánh dấu chỗ đó.

    python -m ops.cache_check                      # 6 giờ gần nhất, database mặc định
    python -m ops.cache_check --hours 1 --db /home/ubuntu/peto-web/backend/data/peto_web.db
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys
import time
from zoneinfo import ZoneInfo

DEFAULT_DB = Path(__file__).resolve().parents[1] / 'data' / 'peto_web.db'


def rows(path: Path, hours: float) -> list[dict]:
    """Các lần gọi Chat trong ``hours`` giờ gần nhất, cũ trước. Database mở chỉ đọc, không tạo tệp mới."""
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        columns = {row[1] for row in db.execute('PRAGMA table_info(usage_events)')}
        fingerprint = 'prefix_hash' if 'prefix_hash' in columns else 'NULL AS prefix_hash'
        return [dict(row) for row in db.execute(
            f"SELECT at, model, effort, input_tokens, cached_tokens, cache_write_tokens, {fingerprint} "
            "FROM usage_events WHERE kind='call' AND surface='chat' AND purpose='chat' AND at >= ? ORDER BY at",
            (time.time() - hours * 3600,))]


def annotate(items: list[dict]) -> list[dict]:
    """Ghi chú từng dòng so với lần gọi trước của cùng model: phần đầu đổi, hay đọc cache được bao nhiêu phần trăm."""
    last: dict[str, str | None] = {}
    for item in items:
        model = item['model'] or '?'
        previous = last.get(model, '')
        current = item['prefix_hash']
        notes = []
        if previous and current and previous != current:
            notes.append('phần đầu đổi')
        cached, total = item['cached_tokens'], item['input_tokens']
        if isinstance(cached, int) and isinstance(total, int) and total > 0:
            item['ratio'] = f'{round(cached * 100 / total)}%'
        else:
            item['ratio'] = '?'
        item['note'] = ', '.join(notes)
        last[model] = current
    return items


def table(items: list[dict], zone: ZoneInfo) -> str:
    header = ('giờ', 'model', 'mức', 'vào', 'đọc', 'ghi', 'tỉ lệ', 'dấu đầu', 'ghi chú')
    lines = [header]
    for item in items:
        lines.append((
            datetime.fromtimestamp(item['at'], zone).strftime('%d/%m %H:%M:%S'), str(item['model'] or '?'),
            str(item['effort'] or '?'), *(str(item[key]) if item[key] is not None else '?' for key in
                                          ('input_tokens', 'cached_tokens', 'cache_write_tokens')),
            item['ratio'], item['prefix_hash'] or '?', item['note']))
    widths = [max(len(line[index]) for line in lines) for index in range(len(header))]
    return '\n'.join('  '.join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip() for line in lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Xem prompt cache của các lượt Chat gần đây (chỉ đọc).')
    parser.add_argument('--db', type=Path, default=Path(os.getenv('PETO_WEB_DB') or DEFAULT_DB))
    parser.add_argument('--hours', type=float, default=6.0)
    parser.add_argument('--timezone', default=os.getenv('PETO_DEFAULT_TIMEZONE') or 'Asia/Ho_Chi_Minh')
    args = parser.parse_args(argv)
    try:
        items = annotate(rows(args.db, max(0.1, min(args.hours, 24 * 90))))
        zone = ZoneInfo(args.timezone)
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        print(f'Không đọc được số liệu cache: {error}', file=sys.stderr)
        return 1
    if not items:
        print('Không có lần gọi Chat nào trong khoảng này.')
        return 0
    print(table(items, zone))
    return 0


if __name__ == '__main__':
    sys.exit(main())
