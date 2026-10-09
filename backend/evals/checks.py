"""Phép kiểm tra hẹp, không dùng đếm từ để thay cho chấm chất lượng."""
from __future__ import annotations

import re


def evaluate(checks: list[dict], raw: str, visible: str) -> list[dict]:
    from features.companion.emotion_tags import EMOTIONS
    rows = []
    for check in checks:
        kind = check['kind']
        if kind in {'match', 'avoid'}:
            matched = bool(re.search(check['value'], visible, re.IGNORECASE | re.MULTILINE))
            passed = matched if kind == 'match' else not matched
        elif kind == 'max_chars':
            passed = len(visible) <= check['value']
        elif kind == 'emotion':
            found = re.findall(r'<\|EMOTE_([A-Z]+)\|>', raw)
            passed = len(found) == 1 and found[0].lower() in EMOTIONS and raw.lstrip().startswith(f'<|EMOTE_{found[0]}|>')
        elif kind == 'private_hidden':
            secrets = re.findall(r'<private>(.*?)</private>', raw, re.IGNORECASE | re.DOTALL)
            passed = '<private' not in visible.lower() and '<|' not in visible and all(
                not secret.strip() or secret.strip() not in visible for secret in secrets)
        else:
            # Chỉ phát hiện ký hiệu rõ ràng; ngôn ngữ và sự tự nhiên vẫn do người chấm.
            passed = not re.search(r'```|(?m:^\s*#{1,6}\s)|\*\*|<\||[\U0001F300-\U0001FAFF]', visible)
        rows.append({'kind': kind, 'label': check['label'], 'critical': check.get('critical', False), 'passed': passed})
    return rows
