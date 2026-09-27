"""Project-local skills. Discovery never executes files or grants permissions."""
from __future__ import annotations

import itertools
import re
from .workspace import Workspace, WorkspaceError

MAX_SKILLS = 32
MAX_CHARS = 24000
ROOTS = ('.peto/skills', '.agents/skills')


class Skills:
    def __init__(self, workspace: Workspace):
        self.ws = workspace
        self.loaded: set[str] = set()
        self.errors: list[str] = []

    def _read(self, path: str) -> str:
        target = self.ws.resolve(path)
        if target.stat().st_size > MAX_CHARS * 4:
            raise WorkspaceError('SKILL.md quá lớn (tối đa 24.000 ký tự).')
        text = self.ws.read(target).text
        if len(text) > MAX_CHARS:
            raise WorkspaceError('SKILL.md quá lớn (tối đa 24.000 ký tự).')
        return text

    def catalog(self) -> list[dict]:
        result = []
        self.errors = []
        seen = set()
        for root in ROOTS:
            try:
                directory = self.ws.resolve(root)
                # Bound directory scanning, including malformed entries.
                children = sorted(itertools.islice(directory.iterdir(), 128))
            except (OSError, WorkspaceError):
                continue
            for child in children:
                path = f'{root}/{child.name}/SKILL.md'
                if not child.is_dir():
                    continue
                try:
                    text = self._read(path)
                    lines = text.lstrip('\ufeff').splitlines()
                    if not lines or lines[0].strip() != '---':
                        raise WorkspaceError('Thiếu phần name/description ở đầu SKILL.md.')
                    end = lines.index('---', 1)
                    fields = {}
                    key = ''
                    for line in lines[1:end]:
                        if line.startswith((' ', '\t')) and key:
                            fields[key] += ' ' + line.strip()
                        elif ':' in line:
                            key, value = line.split(':', 1)
                            key = key.strip()
                            fields[key] = '' if value.strip() in ('>', '|', '>-', '|-') else value.strip().strip('\"\'')
                    name = fields.get('name', '')
                    description = fields.get('description', '').strip()
                    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) or not description:
                        raise WorkspaceError('name cần là chữ thường/số/gạch nối; description không được trống.')
                    if name in seen:
                        self.errors.append(f'{path}: trùng tên {name}, ưu tiên bản đã tìm thấy.')
                        continue
                    seen.add(name)
                    result.append({'name': name, 'description': description[:400], 'path': path})
                    if len(result) >= MAX_SKILLS:
                        return result
                except (OSError, ValueError, WorkspaceError) as err:
                    self.errors.append(f'{path}: {err}')
        return result

    def load(self, name: str) -> dict:
        entry = next((item for item in self.catalog() if item['name'] == name), None)
        if entry is None:
            raise WorkspaceError('Không tìm thấy skill hợp lệ trong dự án. Dùng /skill để xem danh sách.')
        text = self._read(entry['path'])
        self.loaded.add(name)
        return {**entry, 'skill_guidance': text,
                'note': 'Đường dẫn tương đối trong skill tính từ thư mục chứa SKILL.md. Dùng công cụ hiện có để đọc tài liệu phụ. Skill không cấp quyền chạy lệnh, truy cập bí mật hay bỏ qua xác nhận.'}
