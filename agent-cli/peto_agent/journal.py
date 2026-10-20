"""Nhật ký giao dịch và projection cục bộ; lời gọi dở không được tự phát lại.

Theo ranh giới Core/Inbox/Step của OpenCode 22e771f: SQLite là nguồn phục hồi,
JSON phiên cũ là bản xuất tương thích. Không lưu header/token hoặc quyền thực thi.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid


class DurabilityError(RuntimeError):
    """Không được chuyển lỗi lưu trữ thành lỗi công cụ rồi tiếp tục gây tác dụng phụ."""


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Journal:
    def __init__(self, root: Path, server: str, session_id: str):
        from .history import _folder
        key = hashlib.sha256((server + '\0' + session_id).encode()).hexdigest()
        self.path = _folder(root) / 'runtime' / (key + '.sqlite3')
        self.identity = {'root': os.path.normcase(str(root)), 'server': server, 'id': session_id}
        self.lease = None

    @contextlib.contextmanager
    def transaction(self):
        db = None
        try:
            if self.deleted():
                raise DurabilityError('Phiên đã bị xóa; runtime không tạo lại dữ liệu cũ.')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            if db.execute('PRAGMA user_version').fetchone()[0] not in {0, 1}:
                raise DurabilityError('Journal được tạo bởi CLI mới hơn; cập nhật CLI trước khi mở phiên.')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                    kind TEXT NOT NULL, entity TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, purpose TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS steps (id TEXT PRIMARY KEY, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calls (step TEXT NOT NULL, ordinal INTEGER NOT NULL, call_id TEXT NOT NULL,
                    name TEXT NOT NULL, status TEXT NOT NULL, output TEXT, PRIMARY KEY(step,ordinal));
                CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, position INTEGER NOT NULL, delivery TEXT NOT NULL,
                    status TEXT NOT NULL, data TEXT NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA user_version=1')
            yield db
            db.commit()
        except (sqlite3.Error, OSError) as error:
            if db is not None:
                db.rollback()
            raise DurabilityError('Không lưu được runtime. Peto dừng trước bước tiếp theo; kiểm tra dung lượng/quyền ghi.') from error
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def event(db, kind, entity, data):
        db.execute('INSERT INTO events(at,kind,entity,data) VALUES(?,?,?,?)', (time.time(), kind, entity, encode(data)))

    def _snapshot(self, db, data):
        data = {**data, **self.identity}
        old = db.execute('SELECT data FROM snapshot WHERE id=1').fetchone()
        if old and (title := json.loads(old['data']).get('title')):
            data['title'] = title
        db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?)', (encode(data),))

    def deleted(self):
        return self.path.with_suffix('.deleted').is_file()

    def purge(self):
        from .atomic_file import write_text
        write_text(self.path.with_suffix('.deleted'), 'deleted')
        for suffix in ('', '-wal', '-shm'):
            Path(str(self.path) + suffix).unlink(missing_ok=True)

    def rename(self, title):
        if not self.path.is_file():
            return
        with self.transaction() as db:
            old = db.execute('SELECT data FROM snapshot WHERE id=1').fetchone()
            if old:
                data = {**json.loads(old['data']), 'title': title}
                db.execute('UPDATE snapshot SET data=? WHERE id=1', (encode(data),))
                self.event(db, 'session.renamed', self.identity['id'], {'title': title})

    def snapshot(self, data):
        with self.transaction() as db:
            self._snapshot(db, data)
            self.event(db, 'session.checkpoint', self.identity['id'], {'items': len(data.get('items', []))})

    def read(self):
        if self.deleted() or not self.path.is_file():
            return None
        with self.transaction() as db:
            row = db.execute('SELECT data FROM snapshot WHERE id=1').fetchone()
            data = json.loads(row['data']) if row else None
            if data and (any(data.get(key) != self.identity[key] for key in ('server', 'id'))
                         or os.path.normcase(data.get('root', '')) != self.identity['root']):
                raise DurabilityError('Dữ liệu runtime không thuộc đúng phiên/máy chủ/dự án.')
            return data

    def claim(self):
        if self.lease is not None:
            raise DurabilityError('Phiên này đã có vòng thực thi đang chạy.')
        handle = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.with_suffix('.lock').open('a+b')
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lease = handle
        except OSError as error:
            if handle:
                handle.close()
            raise DurabilityError('Phiên đang được Peto khác sử dụng hoặc chưa khóa được runtime.') from error

    def release(self):
        if self.lease is not None:
            self.lease.close()
            self.lease = None

    def request_started(self, body, *, private=False, logical_step=None, source=None):
        request_id = uuid.uuid4().hex
        purpose = str(body.get('context', {}).get('purpose') or 'work')
        with self.transaction() as db:
            db.execute('INSERT INTO requests VALUES(?,?,?)', (request_id, purpose, 'running'))
            self.event(db, 'model.started', request_id,
                       {'purpose': purpose, 'model': body.get('model'), 'effort': body.get('effort'),
                        **({'source': source} if source else {}),
                        'logical_step': logical_step or uuid.uuid4().hex,
                        **({} if private else {'request': body})})
        return request_id

    def execution_started(self):
        execution_id = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute('INSERT INTO executions VALUES(?,?)', (execution_id, 'running'))
            self.event(db, 'execution.started', execution_id, {})
        return execution_id

    def execution_finished(self, execution_id, outcome):
        with self.transaction() as db:
            db.execute('UPDATE executions SET status=? WHERE id=?', (outcome, execution_id))
            self.event(db, 'execution.ended', execution_id, {'outcome': outcome})

    def request_finished(self, request_id, status, result=None):
        with self.transaction() as db:
            db.execute('UPDATE requests SET status=? WHERE id=?', (status, request_id))
            self.event(db, 'model.' + status, request_id, result or {})

    def publish_step(self, step, calls, data, *, request_id=None, response=None):
        with self.transaction() as db:
            if request_id:
                db.execute("UPDATE requests SET status='completed' WHERE id=?", (request_id,))
                self.event(db, 'model.completed', request_id, response or {})
            db.execute('INSERT INTO steps VALUES(?,?)', (step, 'running' if calls else 'completed'))
            for ordinal, call in enumerate(calls):
                db.execute('INSERT INTO calls VALUES(?,?,?,?,?,NULL)',
                           (step, ordinal, str(call.get('call_id', '')), str(call.get('name', '')), 'pending'))
                self.event(db, 'tool.called', f'{step}:{ordinal}', call)
            self._snapshot(db, data)
            self.event(db, 'step.published', step, {'calls': len(calls), 'request_id': request_id})

    def child_step(self, step, calls, request_id=None):
        with self.transaction() as db:
            db.execute('INSERT INTO steps VALUES(?,?)', (step, 'running' if calls else 'completed'))
            self.event(db, 'step.published', step, {'scope': 'explore', 'calls': len(calls), 'request_id': request_id})
            for ordinal, call in enumerate(calls):
                db.execute('INSERT INTO calls VALUES(?,?,?,?,?,NULL)',
                           (step, ordinal, str(call.get('call_id', '')), str(call.get('name', '')), 'pending'))
                self.event(db, 'tool.called', f'{step}:{ordinal}', call)

    def child_finished(self, step, ordinal, result):
        with self.transaction() as db:
            if db.execute("UPDATE calls SET status=?,output=? WHERE step=? AND ordinal=? AND status IN ('pending','running')",
                          ('failed' if result.get('error') else 'completed', encode(result), step, ordinal)).rowcount != 1:
                raise DurabilityError('Kết quả agent con đã được ghi hoặc chưa có lời gọi.')
            self.event(db, 'tool.finished', f'{step}:{ordinal}', {'result': result, 'scope': 'explore'})
            if not db.execute("SELECT 1 FROM calls WHERE step=? AND status IN ('pending','running')", (step,)).fetchone():
                db.execute("UPDATE steps SET status='completed' WHERE id=?", (step,))

    def tool_started(self, step, ordinal):
        with self.transaction() as db:
            changed = db.execute("UPDATE calls SET status='running' WHERE step=? AND ordinal=? AND status='pending'",
                                 (step, ordinal)).rowcount
            if changed != 1:
                raise DurabilityError('Công cụ đã được nhận chạy hoặc chưa được lưu; không phát lại.')
            self.event(db, 'tool.started', f'{step}:{ordinal}', {})

    def tool_finished(self, step, ordinal, output, data, *, task_state):
        with self.transaction() as db:
            changed = db.execute("UPDATE calls SET status=?,output=? WHERE step=? AND ordinal=? AND status IN ('pending','running')",
                                 ('failed' if output.get('error') else 'completed', encode(output), step, ordinal)).rowcount
            if changed != 1:
                raise DurabilityError('Kết quả công cụ đã được ghi hoặc không thuộc bước này.')
            self._snapshot(db, {**data, 'task_state': task_state})
            self.event(db, 'tool.finished', f'{step}:{ordinal}', {'result': output, 'task_state': task_state})
            if not db.execute("SELECT 1 FROM calls WHERE step=? AND status IN ('pending','running')", (step,)).fetchone():
                db.execute("UPDATE steps SET status='completed' WHERE id=?", (step,))

    def enqueue(self, data, delivery='steer', item_id=None):
        if delivery not in {'input', 'steer', 'queue'}:
            raise ValueError('Cách nhận tin không hợp lệ.')
        item_id = item_id or uuid.uuid4().hex
        with self.transaction() as db:
            old = db.execute('SELECT * FROM inbox WHERE id=?', (item_id,)).fetchone()
            if old:
                if old['delivery'] != delivery:
                    raise DurabilityError('Mã tin nhắn đã được dùng cho loại đầu vào khác.')
                return item_id
            position = db.execute('SELECT COALESCE(MAX(position),0)+1 FROM inbox').fetchone()[0]
            db.execute('INSERT INTO inbox VALUES(?,?,?,?,?)', (item_id, position, delivery, 'pending', encode(data)))
            self.event(db, 'inbox.enqueued', item_id, {'delivery': delivery, **data})
        return item_id

    def pending(self, delivery=None):
        with self.transaction() as db:
            query, params = "SELECT * FROM inbox WHERE status='pending'", []
            if delivery:
                query += ' AND delivery=?'; params.append(delivery)
            return [{**dict(row), 'data': json.loads(row['data'])} for row in
                    db.execute(query + ' ORDER BY position', params)]

    def deliver(self, ids, data):
        with self.transaction() as db:
            for item_id in ids:
                if db.execute("UPDATE inbox SET status='delivered' WHERE id=? AND status='pending'", (item_id,)).rowcount != 1:
                    raise DurabilityError('Tin nhắn đã được nhận; không chèn trùng.')
                self.event(db, 'inbox.delivered', item_id, {})
            self._snapshot(db, data)

    def cancel_input(self, item_id):
        with self.transaction() as db:
            if db.execute("UPDATE inbox SET status='cancelled' WHERE id=? AND status='pending'", (item_id,)).rowcount != 1:
                raise DurabilityError('Tin không còn chờ; chưa xóa gì.')
            self.event(db, 'inbox.cancelled', item_id, {})

    def recover(self):
        """Gọi khi đã giữ lease; không thực thi công cụ/model hoặc xóa tin chưa nhận."""
        from .session_protocol import interrupted_items
        with self.transaction() as db:
            executions = db.execute("SELECT id FROM executions WHERE status='running'").fetchall()
            for row in executions:
                db.execute("UPDATE executions SET status='interrupted' WHERE id=?", (row['id'],))
                self.event(db, 'execution.interrupted', row['id'], {})
            for row in db.execute("SELECT id FROM requests WHERE status='running'").fetchall():
                db.execute("UPDATE requests SET status='unknown' WHERE id=?", (row['id'],))
                self.event(db, 'model.unknown', row['id'], {'reason': 'interrupted'})
            for row in db.execute("SELECT step,ordinal,status FROM calls WHERE status IN ('pending','running')").fetchall():
                db.execute("UPDATE calls SET status='interrupted' WHERE step=? AND ordinal=?", (row['step'], row['ordinal']))
                self.event(db, 'tool.interrupted', f"{row['step']}:{row['ordinal']}", {'may_have_executed': row['status'] == 'running'})
            db.execute("UPDATE steps SET status='interrupted' WHERE status='running'")
            row = db.execute('SELECT data FROM snapshot WHERE id=1').fetchone()
            if row:
                data = json.loads(row['data'])
                items, count = interrupted_items(data['items'])
                pending_images = data.get('pending_images')
                if pending_images and pending_images not in items[-1:]:
                    items.append(pending_images)
                if count or executions or pending_images:
                    self._snapshot(db, {**data, 'items': items, 'pending_images': None,
                                        'retryable': False, 'interrupted': True})

    def events(self, after=0):
        with self.transaction() as db:
            return [{**dict(row), 'data': json.loads(row['data'])} for row in
                    db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq', (after,))]
