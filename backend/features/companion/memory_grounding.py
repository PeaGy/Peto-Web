"""Fail-closed checks for automatic memory proposals, not a semantic truth verifier.

Only new, complete user messages can support a new fact. Existing facts stay untouched unless a user-backed
correction/removal is proposed. The small VI/EN vetoes are conservative warning signals, never proof of ownership.
"""
import re
import unicodedata

MESSAGE_CHARS = 1500


def normalized(text):
    return ' '.join(text.split()) if isinstance(text, str) else ''


def _fold(text):
    text = unicodedata.normalize('NFD', text.replace('đ', 'd').replace('Đ', 'D'))
    return ''.join(char for char in text if not unicodedata.combining(char)).casefold()


UNCERTAIN = re.compile(r'\b(?:co le|hinh nhu|chua chac|khong chac|gia su|gia du|tuong tuong|nhap vai|nhan vat|'
                       r'trong truyen|hay dich|dich cau|maybe|perhaps|suppose|imagine|fictional|roleplay|translate)\b')
THIRD_PARTY = re.compile(r'\b(?:nguoi khac|cua ban|ban (?:toi|minh|to|em)|anh ay|co ay|chi ay|ho noi|'
                         r'someone else|my friend|their cat|their dog|his cat|her cat|he said|she said)\b')
TRANSIENT = re.compile(r'\b(?:(?:mat|that lac|khong tim thay) (?:anh|hinh|file|tep)|'
                       r'(?:lost|missing|cannot find) (?:a |the |my )?(?:photo|picture|file))\b')
NAMED_OWNER = re.compile(r'\b(?:của|cua|belongs to)\s+([A-ZĐÀ-Ỹ][^\W\d_]*)')
NEGATED_OWNERSHIP = re.compile(r"\b(?:(?:khong|chua|chang) (?:he |phai |co )?(?:nuoi|so huu|cua|thu cung)|"
                               r"(?:do not|don't|never) (?:own|have)|not mine|not my (?:cat|dog|pet))\b")
FORGET_REQUEST = re.compile(r'\b(?:quen|xoa|bo (?:y|muc|ghi nho)|dung nho|forget|delete|remove|stop remembering)\b')


def conversation_records(rows):
    """JSON roles/IDs cannot be forged by a 'User:' string embedded in a message."""
    return [{'message_id': row['id'], 'conversation_id': row.get('conversation_id'), 'role': row['role'],
             'text': normalized(row['content'])[:MESSAGE_CHARS],
             'truncated': len(normalized(row['content'])) > MESSAGE_CHARS} for row in rows]


def filter_changes(data, existing, source_rows, *, slot_for, max_chars):
    known = {entry['id']: entry for entry in existing}
    sources = {row['id']: row for row in source_rows if row['role'] == 'user'
               and len(normalized(row['content'])) <= MESSAGE_CHARS}

    def evidence(value):
        if not isinstance(value, dict) or type(value.get('message_id')) is not int:
            return ''
        row = sources.get(value['message_id'])
        quote = normalized(value.get('quote'))
        # Full visible utterance is required: do not accept a clipped 'I have a cat' from a third-party quotation.
        return quote if row and quote and quote == normalized(row['content']) else ''

    changes, removals = [], []
    seen = set()
    items = data.get('entries') if isinstance(data.get('entries'), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        memory_id = item.get('id')
        if memory_id is not None and (type(memory_id) is not int or memory_id not in known):
            continue
        entry = known.get(memory_id)
        slot = entry.get('slot') if entry else slot_for(item.get('title')) if item.get('section') == 'you' else ''
        if not entry:
            if item.get('section') not in ('you', 'topic', 'area') or not isinstance(item.get('title'), str):
                continue
            entry = next((old for old in existing if (slot and old.get('slot') == slot)
                          or (not slot and old['section'] == item.get('section') and old['title'] == item.get('title'))), None)
            memory_id = entry['id'] if entry else None
        identity = memory_id if entry else (item.get('section'), normalized(item.get('title')))
        if identity in seen:
            continue
        seen.add(identity)
        old = list(entry['details']) if entry else []
        accepted = []
        details = item.get('details') if isinstance(item.get('details'), list) else []
        for fact in details:
            if not isinstance(fact, dict):
                continue  # Old strings are already retained below; new ungrounded strings are never accepted.
            text, quote = normalized(fact.get('text')), evidence(fact.get('evidence'))
            if (not text or len(text) > max_chars or not quote or fact.get('subject') != 'user'
                    or fact.get('certainty') != 'explicit' or fact.get('retention') != 'lasting'):
                continue
            signal = _fold(quote)
            named_other = any(_fold(match[1]) not in {'toi', 'minh', 'to', 'em', 'anh', 'chi', 'me', 'us'}
                              for match in NAMED_OWNER.finditer(quote))
            if (UNCERTAIN.search(signal) or TRANSIENT.search(signal) or THIRD_PARTY.search(signal)
                    or NEGATED_OWNERSHIP.search(signal) or named_other):
                continue
            accepted.append(text)
        forgotten = set()
        forget = item.get('forget') if isinstance(item.get('forget'), list) else []
        for change in forget:
            proof = evidence(change.get('evidence')) if isinstance(change, dict) else ''
            if (isinstance(change, dict) and change.get('text') in old
                    and proof and (change.get('reason') == 'correction'
                                   or (change.get('reason') == 'user_request' and FORGET_REQUEST.search(_fold(proof))))):
                forgotten.add(change['text'])
        if not accepted and not forgotten:
            continue
        lines = list(dict.fromkeys([text for text in old if text not in forgotten] + accepted))
        if entry:
            # Do not allow unevidenced model title/summary prose to smuggle rejected facts back into the prompt.
            patch = {'id': memory_id, 'details': lines}
            if forgotten and lines:
                patch['summary'] = ('Cách bạn muốn Peto trả lời' if slot == 'style' else 'Bạn là ai'
                                    if slot == 'profile' else lines[0])
            changes.append(patch)
        else:
            section, title = item.get('section'), item.get('title')
            summary = 'Cách bạn muốn Peto trả lời' if slot == 'style' else 'Bạn là ai' if slot == 'profile' else lines[0]
            changes.append({'section': section, 'title': title, 'summary': summary, 'details': lines})

    for item in data.get('remove', []) if isinstance(data.get('remove'), list) else []:
        if (isinstance(item, dict) and type(item.get('id')) is int and item['id'] in known
                and item.get('reason') == 'user_request' and FORGET_REQUEST.search(_fold(evidence(item.get('evidence'))))):
            removals.append(item['id'])
    return {'entries': changes, 'remove': removals}
