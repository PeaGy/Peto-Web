"""Tin Companion trả lời một tin cũ (Reply của AIRI, chủ web chọn đưa về 26/10/2026).

Tin người dùng lưu ``quote_id``. Mỗi lượt, phần lịch sử gửi model thêm một dòng ``[Replying to: …]`` vào đầu tin đó,
như ``formatReplyPromptPrefix`` trong chat-orchestrator-runtime.ts của AIRI (commit 74ddd90): tin được trích vẫn nằm
trong lịch sử nên chỉ cần đủ chữ để nhận ra (480 ký tự). Dòng này không lưu vào tin nhắn, trí nhớ và bản tóm tắt không
thấy nó. Tin được trích đã bị xóa thì bỏ dòng, như AIRI.
"""

from __future__ import annotations

import aiosqlite

from features.companion import emotion_tags, private_notes
from storage import connection

# AIRI: REPLY_PROMPT_REFERENCE_CHARACTER_LIMIT.
QUOTE_LIMIT = 480


def visible(row: dict) -> str:
    """Chữ người dùng thấy của tin được trích: câu trả lời bỏ ghi chú riêng và thẻ cảm xúc của Peto."""
    text = str(row.get('content') or '')
    if row.get('role') == 'assistant':
        text = emotion_tags.strip(private_notes.strip(text))
    return text


def prefix(target: dict | None, quote_id: int) -> str:
    """Dòng đứng trước tin trả lời. Tin được trích không có chữ (chỉ có ảnh) thì ghi mã tin như AIRI."""
    if target is None:
        return ''
    text = ' '.join(visible(target).split())
    if len(text) > QUOTE_LIMIT:
        text = text[:QUOTE_LIMIT - 1].rstrip() + '…'
    return f'[Replying to: {text}]\n' if text else f'[Replying to message: {quote_id}]\n'


async def with_quotes(owner: str, conversation_id: str, rows: list[dict]) -> list[dict]:
    """Bản sao ``rows`` có dòng trích ở đầu những tin trả lời. Tin được trích nằm ngoài cửa sổ lịch sử thì đọc thêm,
    lọc theo chủ tài khoản và đúng hội thoại."""
    wanted = {row['quote_id'] for row in rows if row.get('quote_id')}
    if not wanted:
        return rows
    targets = {row['id']: row for row in rows if row.get('id') in wanted}
    missing = sorted(wanted - targets.keys())
    if missing:
        marks = ','.join('?' * len(missing))
        async with connection.connect() as db:
            db.row_factory = aiosqlite.Row
            found = await (await db.execute(
                f'''SELECT m.id, m.role, m.content FROM messages m JOIN conversations c ON c.id = m.conversation_id
                    WHERE m.id IN ({marks}) AND m.conversation_id = ? AND c.owner = ?''',
                (*missing, conversation_id, owner))).fetchall()
        targets.update({row['id']: dict(row) for row in found})
    result = []
    for row in rows:
        quote_id = row.get('quote_id')
        line = prefix(targets.get(quote_id), quote_id) if quote_id and row.get('role') == 'user' else ''
        result.append({**row, 'content': line + str(row.get('content') or '')} if line else row)
    return result
