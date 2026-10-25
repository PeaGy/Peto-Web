"""Thẻ nhân vật Companion theo thẻ AIRI (chủ web chốt 25/10/2026): người dùng tự viết persona, xem được toàn bộ prompt.

Prompt của thẻ ghép như ``resolveSystemPrompt`` của AIRI (packages/stage-ui/src/stores/modules/airi-card.ts): system
prompt, mô tả, tính cách, bối cảnh, bỏ trường trống, nối bằng một dòng trống. Khác AIRI:
- máy chủ ghép prompt (trí nhớ, bộ lọc thẻ cảm xúc và ``<private>`` vẫn chạy ở đây);
- "hướng dẫn sau lịch sử" được dùng, đặt cuối prompt; câu chào thành tin nhắn đầu của mạch mới;
- ``{{char}}`` và ``{{user}}`` của thẻ cộng đồng được thay bằng tên nhân vật và tên người dùng;
- một quy tắc cố định về người dưới 18 tuổi luôn được gắn, thẻ không sửa được.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from prompts import COMPANION_SYSTEM_PROMPT
from storage import cards as store
from storage.cards import DEFAULT_CARD

MAX_CARDS = 50
LIMITS = {
    'name': 60, 'nickname': 60, 'version': 20, 'description': 20000, 'notes': 4000, 'personality': 8000,
    'scenario': 8000, 'system_prompt': 20000, 'post_history': 4000, 'display_model': 100,
}
PROMPT_FIELDS = ('system_prompt', 'description', 'personality', 'scenario')
MAX_PROMPT_CHARS = 40000
MAX_GREETINGS = 10
MAX_GREETING_CHARS = 4000
MODULE_KEYS = {'brain': ('provider', 'model'), 'voice': ('source', 'provider', 'model', 'voice')}
LABELS = {
    'name': 'Tên', 'nickname': 'Biệt danh', 'version': 'Phiên bản', 'description': 'Mô tả', 'notes': 'Ghi chú',
    'personality': 'Tính cách', 'scenario': 'Bối cảnh', 'system_prompt': 'System prompt',
    'post_history': 'Hướng dẫn sau lịch sử', 'display_model': 'Model hiển thị',
}
CARD_ID = re.compile(rf'^(?:{DEFAULT_CARD}|[0-9a-f]{{32}})$')

# Giá trị gốc của thẻ mặc định; cột NULL trong bảng là dùng các giá trị này.
BUILTIN = {
    'name': 'Peto', 'nickname': '', 'version': '1.0.0', 'description': '', 'notes': '', 'personality': '',
    'scenario': '', 'system_prompt': COMPANION_SYSTEM_PROMPT, 'post_history': '', 'display_model': 'hiyori',
    'greetings': [], 'modules': {},
}
EMPTY = {**{name: '' for name in LIMITS}, 'version': '1.0.0', 'greetings': [], 'modules': {}}

_CHAR = re.compile(r'\{\{\s*char\s*\}\}', re.IGNORECASE)
_USER = re.compile(r'\{\{\s*user\s*\}\}', re.IGNORECASE)


def check_id(card_id: str) -> str:
    if not CARD_ID.match(card_id):
        raise HTTPException(404, 'Không tìm thấy thẻ nhân vật')
    return card_id


def effective(card: dict) -> dict:
    """Thẻ với giá trị thật: thẻ mặc định lấy giá trị gốc cho cột còn trống."""
    fallback = BUILTIN if card['id'] == DEFAULT_CARD else EMPTY
    values = {name: card.get(name) if card.get(name) is not None else fallback[name] for name in store.FIELDS}
    return {**values, 'id': card['id']}


def public(card: dict) -> dict:
    values = effective(card)
    is_default = card['id'] == DEFAULT_CARD
    return {
        **values,
        'is_default': is_default,
        # Thẻ mặc định có chỗ nào khác bản gốc thì trang thẻ hiện nút "Khôi phục bản gốc".
        'modified': is_default and any(card.get(name) is not None for name in store.FIELDS),
        'created_at': card['created_at'], 'updated_at': card['updated_at'],
    }


def _text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise HTTPException(400, f'{LABELS[name]} phải là chữ.')
    value = value.replace('\r\n', '\n').replace('\x00', '')
    if name in ('name', 'nickname', 'version', 'display_model'):
        value = ' '.join(value.split())
    if len(value) > LIMITS[name]:
        raise HTTPException(400, f'{LABELS[name]} dài quá {LIMITS[name]:,} ký tự.'.replace(',', '.'))
    return value


def _greetings(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(400, 'Câu chào phải là danh sách chữ.')
    items = [item.replace('\r\n', '\n').strip() for item in value]
    items = [item for item in items if item]
    if len(items) > MAX_GREETINGS:
        raise HTTPException(400, f'Mỗi thẻ có tối đa {MAX_GREETINGS} câu chào.')
    if any(len(item) > MAX_GREETING_CHARS for item in items):
        raise HTTPException(400, f'Mỗi câu chào dài tối đa {MAX_GREETING_CHARS:,} ký tự.'.replace(',', '.'))
    return items


def _modules(value: object) -> dict:
    """Bộ não và giọng riêng của thẻ (AIRI: Modules); để trống là theo cài đặt chung. Máy chủ chỉ lưu, trình duyệt áp."""
    if not isinstance(value, dict) or set(value) - set(MODULE_KEYS):
        raise HTTPException(400, 'Mô-đun của thẻ không hợp lệ.')
    clean: dict = {}
    for module, choice in value.items():
        if choice is None:
            continue
        if not isinstance(choice, dict) or set(choice) - set(MODULE_KEYS[module]):
            raise HTTPException(400, 'Mô-đun của thẻ không hợp lệ.')
        if any(not isinstance(item, str) or len(item) > 100 for item in choice.values()):
            raise HTTPException(400, 'Mô-đun của thẻ không hợp lệ.')
        picked = {key: item.strip() for key, item in choice.items() if item.strip()}
        if picked:
            clean[module] = picked
    return clean


def clean(fields: dict, card_id: str | None) -> dict:
    """Kiểm từng trường gửi lên. Với thẻ mặc định, giá trị trùng bản gốc lưu thành NULL để còn theo bản gốc về sau."""
    values: dict = {}
    for name, value in fields.items():
        if name == 'greetings':
            values[name] = _greetings(value)
        elif name == 'modules':
            values[name] = _modules(value)
        else:
            values[name] = _text(name, value)
    if 'name' in values and not values['name']:
        raise HTTPException(400, 'Thẻ cần có tên.')
    if 'version' in values and not values['version']:
        values['version'] = '1.0.0'
    if card_id == DEFAULT_CARD:
        values = {name: None if value == BUILTIN[name] else value for name, value in values.items()}
    return values


def check_size(card: dict) -> None:
    total = sum(len(card[name]) for name in (*PROMPT_FIELDS, 'post_history'))
    if total > MAX_PROMPT_CHARS:
        raise HTTPException(400, f'Phần prompt của thẻ dài quá {MAX_PROMPT_CHARS:,} ký tự cộng lại.'.replace(',', '.'))


def check_name(name: str, cards: list[dict], except_id: str | None) -> None:
    """Không cho hai thẻ trùng tên (như ô "Save as New Profile" của AIRI)."""
    if any(effective(card)['name'] == name and card['id'] != except_id for card in cards):
        raise HTTPException(409, f'Đã có thẻ tên "{name}". Đặt tên khác nhé.')


def _fill(text: str, character: str, user: str) -> str:
    return _USER.sub(lambda _: user, _CHAR.sub(lambda _: character, text))


def character_name(card: dict) -> str:
    return card['nickname'] or card['name'] or 'Peto'


def prompt_parts(card: dict, user: str) -> tuple[str, str]:
    """(phần đầu prompt, hướng dẫn sau lịch sử) của thẻ đã ``effective``."""
    character = character_name(card)
    head = '\n\n'.join(_fill(card[name].strip(), character, user) for name in PROMPT_FIELDS if card[name].strip())
    return head, _fill(card['post_history'].strip(), character, user)


def greeting(card: dict, user: str) -> str:
    """Câu chào đầu tiên của thẻ, mở đầu mỗi mạch mới."""
    return _fill(card['greetings'][0], character_name(card), user) if card['greetings'] else ''


async def resolve(owner: str, card_id: str | None) -> dict:
    """Thẻ đã ``effective`` theo id (None là thẻ đang dùng); 404 khi không phải của tài khoản."""
    if card_id is None:
        card_id, _ = await store.list_cards(owner)
    card = await store.get_card(owner, check_id(card_id))
    if card is None:
        raise HTTPException(404, 'Không tìm thấy thẻ nhân vật')
    return effective(card)


async def user_name(owner: str) -> str:
    """Tên thay cho ``{{user}}``: tên gọi trong Hồ sơ, rồi tên tài khoản."""
    import storage as db

    user = await db.get_user(owner) or {}
    profile = await db.get_profile(owner) if user else {}
    return profile.get('nickname') or user.get('display_name') or user.get('username') or 'User'


async def open_conversation(owner: str, card: dict, conversation_id: str) -> None:
    """Mạch vừa tạo của thẻ: thành mạch đang mở của thẻ, thẻ thành thẻ đang dùng, và có câu chào đầu nếu thẻ có."""
    import storage as db

    text = greeting(card, await user_name(owner))
    if text:
        await db.add_message(conversation_id, 'assistant', text)
    await store.set_active_card(owner, card['id'], conversation_id)


def remembers(card_id: str) -> bool:
    """Trí nhớ chung (với tab Trò chuyện) chỉ dành cho thẻ Peto mặc định; thẻ khác chưa đọc, chưa ghi trí nhớ."""
    return card_id == DEFAULT_CARD
