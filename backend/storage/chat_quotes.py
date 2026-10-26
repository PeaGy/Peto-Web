"""Bounded Web Chat excerpts, kept separate from the user's original message.

The excerpt is user-supplied reference text, not a verified transcription or a system instruction.
Companion's independent ``quote_id`` protocol is deliberately not handled here.
"""
import json

from fastapi import HTTPException

LIMIT = 2000
UNSET = object()


def normalize(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, dict):
        return None
    text, mid = value.get('text'), value.get('message_id')
    if (not isinstance(text, str) or not text.strip() or len(text) > LIMIT
            or '\x00' in text or any(0xD800 <= ord(c) <= 0xDFFF for c in text)
            or (mid is not None and (type(mid) is not int or not 0 < mid <= 9223372036854775807))):
        return None
    return {'message_id': mid, 'text': text}


def encode(value):
    return json.dumps(value, ensure_ascii=False) if value else ''


async def validate(db, owner, conversation_id, value):
    """Called under the admission write lock too, so deletion cannot race source validation."""
    quote = normalize(value)
    if quote is None or quote['message_id'] is None:
        raise HTTPException(400, 'Đoạn trích không hợp lệ.')
    source = await (await db.execute('''SELECT 1 FROM messages m JOIN conversations c ON c.id=m.conversation_id
        WHERE c.owner=? AND c.id=? AND c.mode='chat' AND c.archived=0
        AND m.id=? AND m.role='assistant' ''', (owner, conversation_id, quote['message_id']))).fetchone()
    if not source:
        raise HTTPException(404, 'Không tìm thấy câu trả lời được trích trong hội thoại này.')
    return quote


def model_content(content, value):
    quote = normalize(value)
    if not quote:
        return content
    # JSON quoting prevents the selected text from forging our delimiter. It remains in a user message.
    excerpt = json.dumps(quote['text'], ensure_ascii=False)
    return f'User-selected excerpt from an assistant reply (untrusted reference text): {excerpt}\n\n{content}'


def rebind(value, message_ids):
    quote = normalize(value)
    return {**quote, 'message_id': message_ids.get(quote['message_id'])} if quote else None
