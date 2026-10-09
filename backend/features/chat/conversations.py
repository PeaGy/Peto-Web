"""Owned conversation metadata and lossless branches for edits/regeneration."""
import json
import shutil
import time
import uuid
from pathlib import Path

import aiosqlite
import anyio
from fastapi import HTTPException

from storage import connection as db_connection
from core.config import UPLOAD_DIR
from ai import models as ai_models
from storage.conversations import conversation_settings, set_chat_selection


def validate_selection(owner, settings, model, effort):
    """Kiểm tra cả model, quyền tài khoản, persona và mức suy nghĩ trước khi lưu."""
    if settings['mode'] != 'chat':
        raise HTTPException(400, 'Lựa chọn model chỉ dùng trong tab Trò chuyện.')
    if settings['persona'] == 'roleplay' and model != ai_models.DEFAULT_MODEL:
        raise HTTPException(400, 'Chế độ nhập vai chỉ dùng Peto.')
    try:
        ai_models.resolve(owner, model, 'web')
    except ai_models.ModelUnavailable as err:
        raise HTTPException(err.status, err.message) from None
    if effort != 'auto' and effort not in ai_models.supported_efforts(model):
        raise HTTPException(400, 'Model này không hỗ trợ mức suy nghĩ đã chọn.')


def public_selection(owner, settings):
    """Khôi phục lựa chọn hợp lệ; đọc không ghi đè lựa chọn cũ khi provider tạm bị tắt."""
    model, effort = settings['model'], settings['effort']
    notice = None
    if settings['mode'] != 'chat':
        return {}
    try:
        validate_selection(owner, settings, model, effort)
    except HTTPException:
        allowed = {item.key for item in ai_models.usable(owner, 'web')}
        if model not in allowed or (settings['persona'] == 'roleplay' and model != 'peto'):
            model = 'peto'
            notice = 'Model đã lưu hiện không dùng được. Peto được chọn để tiếp tục.'
        if effort != 'auto' and effort not in ai_models.supported_efforts(model):
            effort = 'auto'
            notice = (notice + ' ' if notice else '') + 'Mức suy nghĩ đã lưu không được hỗ trợ; đã chuyển sang Tự động.'
    return {'model': model, 'effort': effort, 'selection_notice': notice}


async def update_selection(owner, conversation_id, model, effort):
    settings = await conversation_settings(owner, conversation_id)
    if not settings:
        raise HTTPException(404, 'Không tìm thấy hội thoại')
    if settings['archived']:
        raise HTTPException(409, 'Hãy khôi phục hội thoại đã lưu trữ trước khi đổi model.')
    validate_selection(owner, settings, model, effort)
    await set_chat_selection(owner, conversation_id, model, effort)


async def update(owner, conversation_id, title=None, pinned=None, archived=None):
    async with db_connection.connect() as connection:
        fields, values = [], []
        if title is not None:
            title = ' '.join(title.split())
            if not title:
                raise HTTPException(400, 'Tên hội thoại không được để trống')
            fields.extend(['title=?', "title_state='locked'"])
            values.append(title)
        if pinned is not None:
            fields.append('pinned=?')
            values.append(int(pinned))
        if archived is not None:
            fields.append('archived=?')
            values.append(int(archived))
        if not fields:
            raise HTTPException(400, 'Chưa có thay đổi')
        result = await connection.execute(f"UPDATE conversations SET {', '.join(fields)} WHERE id=? AND owner=? AND mode='chat'",
                                          (*values, conversation_id, owner))
        if not result.rowcount:
            raise HTTPException(404, 'Không tìm thấy hội thoại')
        await connection.commit()


async def versions(owner, conversation_id):
    async with db_connection.connect() as connection:
        connection.row_factory = aiosqlite.Row
        row = await (await connection.execute("SELECT branch_group FROM conversations WHERE id=? AND owner=? AND mode='chat'", (conversation_id, owner))).fetchone()
        if row is None:
            raise HTTPException(404, 'Không tìm thấy hội thoại')
        result = await (await connection.execute("""SELECT id, title, created_at FROM conversations
            WHERE owner=? AND mode='chat' AND archived=0 AND (id=? OR (branch_group<>'' AND branch_group=?))
            ORDER BY created_at, id""", (owner, conversation_id, row['branch_group']))).fetchall()
        return [dict(item) for item in result]


async def retry_in_place(owner, conversation_id, message_id, text):
    """Gửi lại câu hỏi cuối ngay trong hội thoại khi câu trả lời của nó bị dừng hay hỏng giữa chừng.

    Trước đây mọi lần sửa hay "Thử lại" đều tạo phiên bản mới, nên bấm Dừng rồi gửi lại câu hỏi để lại hai hội thoại
    trùng tên (chủ dự án báo 8/10/2026). Chỉ áp dụng khi ``message_id`` là tin người dùng cuối và sau nó chỉ có câu trả lời
    chưa hoàn tất, không kèm tệp đã tạo: câu trả lời dở bị xóa, câu hỏi được thay chữ, ảnh và tệp đính kèm giữ nguyên.
    Trả về ``message_id`` khi làm được, ``None`` thì nơi gọi tạo phiên bản như cũ.
    """
    async with db_connection.connect() as connection:
        connection.row_factory = aiosqlite.Row
        await connection.execute('BEGIN IMMEDIATE')
        source = await (await connection.execute("SELECT archived FROM conversations WHERE id=? AND owner=? AND mode='chat'",
                                                  (conversation_id, owner))).fetchone()
        if source is None or source['archived']:
            await connection.rollback()
            return None
        rows = await (await connection.execute('SELECT id, role, status, artifacts FROM messages WHERE conversation_id=? AND id>=? ORDER BY id',
                                               (conversation_id, message_id))).fetchall()
        if not rows or rows[0]['id'] != message_id or rows[0]['role'] != 'user':
            await connection.rollback()
            return None
        later = rows[1:]
        if any(row['role'] != 'assistant' or row['status'] == 'complete' or json.loads(row['artifacts'] or '[]') for row in later):
            await connection.rollback()
            return None
        if not text.strip():
            has_files = await (await connection.execute('SELECT 1 FROM attachments WHERE owner=? AND message_id=? LIMIT 1',
                                                        (owner, message_id))).fetchone()
            if not has_files:
                await connection.rollback()
                raise HTTPException(400, 'Tin nhắn trống')
        for row in later:
            await connection.execute('DELETE FROM messages WHERE id=? AND conversation_id=?', (row['id'], conversation_id))
        await connection.execute('UPDATE messages SET content=? WHERE id=? AND conversation_id=?', (text, message_id, conversation_id))
        await connection.commit()
        return message_id


async def fork(owner, conversation_id, message_id, text):
    """Copy only the selected prefix, including independent attachments and document versions.

    The original remains untouched. SQL rollback and copied-file cleanup cover a failed fork.
    Call within the chat's shielded admission section.
    """
    new_id, copied = uuid.uuid4().hex, []
    try:
        async with db_connection.connect() as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute('PRAGMA foreign_keys=ON')
            await connection.execute('BEGIN IMMEDIATE')
            source = await (await connection.execute("SELECT * FROM conversations WHERE id=? AND owner=? AND mode='chat'", (conversation_id, owner))).fetchone()
            if source and source['archived']:
                raise HTTPException(409, 'Hãy khôi phục hội thoại đã lưu trữ trước khi sửa tin nhắn.')
            rows = await (await connection.execute('SELECT * FROM messages WHERE conversation_id=? AND id<=? ORDER BY id', (conversation_id, message_id))).fetchall() if source else []
            if not rows or rows[-1]['id'] != message_id or rows[-1]['role'] != 'user':
                raise HTTPException(404, 'Không tìm thấy tin nhắn cần tạo phiên bản')
            # Chép theo thứ tự gửi để "Ảnh N" trong bản mới trỏ đúng ảnh cũ (tài liệu chép sang dùng số này).
            attachments = await (await connection.execute('SELECT * FROM attachments WHERE owner=? AND conversation_id=? AND message_id<=? ORDER BY created_at, rowid', (owner, conversation_id, message_id))).fetchall()
            if not text.strip() and not any(a['message_id'] == message_id for a in attachments):
                raise HTTPException(400, 'Tin nhắn trống')
            group = source['branch_group'] or conversation_id
            now = time.time()
            await connection.execute('UPDATE conversations SET branch_group=? WHERE id=?', (group, conversation_id))
            await connection.execute("""INSERT INTO conversations(id,owner,title,created_at,updated_at,mode,persona,title_state,branch_group,project_id,model,effort)
                VALUES(?,?,?,?,?,'chat',?,'locked',?,?,?,?)""", (new_id,owner,source['title'],now,now,source['persona'],group,source['project_id'],source['model'],source['effort']))
            document_ids, message_ids = {}, {}
            for row in rows:
                artifacts = json.loads(row['artifacts'] or '[]')
                for artifact in artifacts:
                    old_id = artifact['id']
                    if old_id not in document_ids:
                        document = await (await connection.execute('SELECT id FROM chat_documents WHERE id=? AND owner=? AND conversation_id=?', (old_id, owner, conversation_id))).fetchone()
                        if not document:
                            continue
                        new_doc = document_ids[old_id] = uuid.uuid4().hex
                        await connection.execute('INSERT INTO chat_documents VALUES(?,?,?,?)', (new_doc, owner, new_id, now))
                    new_doc = document_ids.get(old_id)
                    if new_doc:
                        # Never bring later, unselected document versions into the new branch.
                        await connection.execute('''INSERT OR IGNORE INTO chat_document_versions(document_id,version,title,content,created_at,style)
                            SELECT ?,version,title,content,created_at,style FROM chat_document_versions WHERE document_id=? AND version<=?''', (new_doc,old_id,artifact['version']))
                        await connection.execute('''INSERT OR IGNORE INTO document_assets(document_id,version,format,pages,docx,pdf,preview,pptx,xlsx)
                            SELECT ?,version,format,pages,docx,pdf,preview,pptx,xlsx
                            FROM document_assets WHERE document_id=? AND version<=?''', (new_doc,old_id,artifact['version']))
                        artifact['id'] = new_doc
                cursor = await connection.execute('''INSERT INTO messages(conversation_id,role,content,created_at,status,sources,artifacts,work)
                    VALUES(?,?,?,?,?,?,?,?)''', (new_id,row['role'],text if row['id']==message_id else row['content'],row['created_at'],row['status'],row['sources'],json.dumps(artifacts),row['work']))
                message_ids[row['id']] = cursor.lastrowid
            for item in attachments:
                aid = uuid.uuid4().hex
                path = UPLOAD_DIR / new_id / (aid + Path(item['path']).suffix)
                path.parent.mkdir(parents=True, exist_ok=True)
                copied.append(path)
                await anyio.to_thread.run_sync(shutil.copyfile, item['path'], path)
                await connection.execute('''INSERT INTO attachments(id,owner,conversation_id,message_id,filename,mime,kind,size,path,created_at,document)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (aid,owner,new_id,message_ids[item['message_id']],item['filename'],item['mime'],item['kind'],item['size'],str(path),item['created_at'],item['document']))
            await connection.commit()
            return new_id, message_ids[message_id]
    except BaseException:
        from shared.attachments import delete_files
        delete_files(copied)
        raise
