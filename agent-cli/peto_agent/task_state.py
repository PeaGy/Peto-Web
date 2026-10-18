"""Projection công việc và bằng chứng; mã thoát 0 không tự trở thành nghiệm thu ứng dụng."""
from __future__ import annotations

import copy
import hashlib
import json
from .workspace import WorkspaceError

MUTATIONS = {'write_file', 'edit_file', 'delete_file', 'move_file', 'apply_patch'}
CHECKS = {'read_file', 'run_command', 'run_python', 'read_command_output', 'read_output', 'browser_read',
          'browser_screenshot', 'browser_open', 'browser_click', 'browser_type', 'browser_press', 'mcp_call_tool'}


class TaskState:
    def __init__(self, workspace, data=None):
        self.workspace = workspace
        self.data = copy.deepcopy(data) if isinstance(data, dict) and data.get('version') == 1 else {
            'version': 1, 'goal': '', 'revision': 0, 'plan': [], 'artifacts': {}, 'evidence': [], 'acceptance': []}

    def artifact(self, path):
        try:
            file = self.workspace.resolve(path, must_exist=False)
            if not file.exists():
                return {'status': 'deleted'}
            if not file.is_file() or file.is_symlink():
                return {'status': 'unreadable'}
            with file.open('rb') as handle:
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
            return {'status': 'present', 'sha256': digest, 'bytes': file.stat().st_size}
        except (OSError, ValueError, RuntimeError, WorkspaceError):
            return {'status': 'unreadable'}

    def record(self, evidence_id, name, args, result):
        paths = []
        if not result.get('error') and name in MUTATIONS:
            paths += [result.get('path'), result.get('moved_from')]
            for row in result.get('files', []) if isinstance(result.get('files'), list) else []:
                if isinstance(row, dict):
                    paths += [row.get('path'), row.get('new_path')]
        paths += result.get('files_changed', []) if isinstance(result.get('files_changed'), list) else []
        paths = list(dict.fromkeys(path for path in paths if isinstance(path, str)))
        # Đọc/kiểm lại sau khi người dùng sửa bên ngoài: bằng chứng phải thuộc phiên bản tệp mới.
        observed = {path: self.artifact(path) for path in self.data['artifacts']} if name in CHECKS else {}
        changed = {path: value for path, value in observed.items() if value != self.data['artifacts'][path]}
        if paths or name in MUTATIONS or changed:
            self.data['revision'] += 1
            self.data['artifacts'].update(changed)
            for path in paths:
                self.data['artifacts'][path] = self.artifact(path)
            for row in self.data['acceptance']:
                row['status'] = 'stale'
        if name == 'update_plan' and result.get('ok'):
            self.data['plan'] = [{'title': str(row.get('title', ''))[:160], 'status': row.get('status')}
                                 for row in args.get('steps', [])[:10] if isinstance(row, dict)]
        observation = {'id': evidence_id, 'tool': name, 'revision': self.data['revision'],
                       'arguments': {key: str(args[key])[:600] for key in ('path', 'command', 'cwd', 'url', 'code') if key in args},
                       'result': {key: result[key] if type(result[key]) in {int, bool} else str(result[key])[:1800]
                                  for key in ('ok', 'error', 'exit_code', 'classification', 'output', 'path', 'output_id') if key in result}}
        self.data['evidence'] = (self.data['evidence'] + [observation])[-100:]

    def accept(self, criterion, status, evidence_ids, note):
        if not isinstance(criterion, str) or not criterion.strip() or len(criterion) > 300:
            raise ValueError('Tiêu chí cần có nội dung, tối đa 300 ký tự.')
        if status not in {'passed', 'failed', 'unverified'} or not isinstance(evidence_ids, list) or len(evidence_ids) > 12:
            raise ValueError('Trạng thái hoặc danh sách bằng chứng không hợp lệ.')
        evidence = {row['id']: row for row in self.data['evidence']}
        if any(not isinstance(key, str) or key not in evidence for key in evidence_ids):
            raise ValueError('Bằng chứng phải là evidence_id do runtime trả về trong phiên này.')
        if status in {'passed', 'failed'} and not evidence_ids:
            raise ValueError('Cần bằng chứng thực tế trước khi đánh dấu đạt hoặc không đạt.')
        if not isinstance(note, str) or not note.strip():
            raise ValueError('Ghi rõ phạm vi đã kiểm hoặc lý do chưa xác minh trong note.')
        if status == 'passed':
            for key in evidence_ids:
                row = evidence[key]
                result = row['result']
                if (row['tool'] not in CHECKS or row['revision'] != self.data['revision']
                        or result.get('error') or result.get('exit_code', 0) != 0):
                    raise ValueError('Bằng chứng lỗi hoặc thuộc bản sửa cũ; chưa thể đánh dấu đạt.')
            for path, observed in self.data['artifacts'].items():
                if self.artifact(path) != observed:
                    raise ValueError('Tệp đã đổi ngoài runtime; đọc và kiểm tra lại trước khi nghiệm thu.')
        row = {'criterion': criterion.strip(), 'status': status, 'evidence_ids': list(dict.fromkeys(evidence_ids)),
               'revision': self.data['revision'], 'note': str(note or '')[:1200], 'reported_by': 'agent'}
        previous = [old for old in self.data['acceptance'] if old['criterion'] != row['criterion']]
        if len(previous) >= 30:
            raise ValueError('Tối đa 30 tiêu chí; cập nhật tiêu chí đã có thay vì thêm nữa.')
        self.data['acceptance'] = previous + [row]
        return {'ok': True, 'acceptance': row}

    def view(self):
        # Projection cho model có ngân sách riêng; dữ liệu đầy đủ vẫn ở journal và read_history.
        criteria = sorted(self.data['acceptance'], key=lambda row: row['status'] == 'passed')
        result = {'version': 1, 'goal': self.data['goal'][:1600], 'revision': self.data['revision'],
                  'plan': copy.deepcopy(self.data['plan'][:10]),
                  'acceptance': [{**copy.deepcopy(row), 'criterion': row['criterion'][:200], 'note': row['note'][:300],
                                  'evidence_ids': row['evidence_ids'][:4]} for row in criteria[:12]],
                  'artifacts': [(path[:180], value) for path, value in list(self.data['artifacts'].items())[-12:]],
                  'evidence': copy.deepcopy(self.data['evidence'][-8:])}
        for row in result['evidence']:
            row['arguments'] = {key: value[:180] for key, value in row['arguments'].items()}
            row['result'] = {key: value[:400] if isinstance(value, str) else value for key, value in row['result'].items()}
        for key in ('evidence', 'artifacts', 'acceptance'):
            while len(json.dumps(result, ensure_ascii=False)) > 14000 and len(result[key]) > 1:
                result[key].pop()
        result['omitted'] = {key: len(self.data[key]) - len(result[key]) for key in ('evidence', 'artifacts', 'acceptance')}
        return result

    def accepted(self):
        rows = self.data['acceptance']
        if any(self.artifact(path) != observed for path, observed in self.data['artifacts'].items()):
            for row in rows:
                row['status'] = 'stale'
        return bool(rows) and all(row['status'] == 'passed' and row['revision'] == self.data['revision'] for row in rows)
