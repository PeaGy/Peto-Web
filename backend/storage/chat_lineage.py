"""Explicit Web Chat message origins. Text equality and branch membership never prove sibling replies."""
import aiosqlite

from storage import connection

MAX_QUESTIONS = 200
MAX_VARIANTS = 20


async def init_tables(db):
    # origin_id is intentionally not an FK: an independent fork survives deletion of the original conversation.
    await db.execute('''CREATE TABLE IF NOT EXISTS chat_message_lineage (
        message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
        origin_id INTEGER NOT NULL, question_origin_id INTEGER,
        model TEXT NOT NULL DEFAULT '', effort TEXT NOT NULL DEFAULT '')''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_chat_lineage_question ON chat_message_lineage(question_origin_id,origin_id)')


async def user(db, message_id, origin_id=None):
    await db.execute('INSERT OR IGNORE INTO chat_message_lineage(message_id,origin_id) VALUES(?,?)',
                     (message_id, origin_id or message_id))


async def origin(db, message_id):
    row = await (await db.execute('SELECT origin_id FROM chat_message_lineage WHERE message_id=?', (message_id,))).fetchone()
    return row[0] if row else message_id


async def reply(db, message_id, user_id, model='', effort=''):
    question = await origin(db, user_id)
    await db.execute('''INSERT OR IGNORE INTO chat_message_lineage(message_id,origin_id,question_origin_id,model,effort)
        VALUES(?,?,?,?,?)''', (message_id, message_id, question, model, effort))


async def decorate(owner, conversation_id, rows):
    """Public-history decoration only; this catalogue never expands the model's context.

    Inspect the latest 200 represented questions; cap each family at 20 recent distinct responses, retaining the current
    conversation's response. Prefix copies are deduplicated by response origin, preferring the current copy.
    """
    assistant_ids = [row['id'] for row in rows if row['role'] == 'assistant'][-MAX_QUESTIONS:]
    if not assistant_ids:
        return rows
    async with connection.connect() as db:
        db.row_factory = aiosqlite.Row
        scope = await (await db.execute('''SELECT branch_group,project_id FROM conversations
            WHERE id=? AND owner=? AND mode='chat' AND archived=0''', (conversation_id, owner))).fetchone()
        if not scope or not scope['branch_group']:
            return rows
        marks = ','.join('?' * len(assistant_ids))
        current = await (await db.execute(f'''SELECT message_id,origin_id,question_origin_id FROM chat_message_lineage
            WHERE message_id IN ({marks}) AND question_origin_id IS NOT NULL''', assistant_ids)).fetchall()
        questions = sorted({row['question_origin_id'] for row in current})
        if not questions:
            return rows
        marks = ','.join('?' * len(questions))
        found = await (await db.execute(f'''WITH copies AS (
            SELECT m.id AS message_id,c.id AS conversation_id,l.origin_id,l.question_origin_id,l.model,l.effort,
                m.created_at,c.created_at AS conversation_created,
                ROW_NUMBER() OVER (PARTITION BY l.question_origin_id,l.origin_id
                    ORDER BY CASE WHEN c.id=? THEN 0 ELSE 1 END,c.created_at,c.id,m.id) AS copy_rank
            FROM chat_message_lineage l JOIN messages m ON m.id=l.message_id
            JOIN conversations c ON c.id=m.conversation_id
            WHERE c.owner=? AND c.mode='chat' AND c.persona='assistant' AND c.archived=0
                AND c.project_id IS ? AND c.branch_group=? AND l.question_origin_id IN ({marks})
                AND m.role='assistant' AND (length(trim(m.content))>0 OR m.artifacts NOT IN ('','[]'))
        ), choices AS (
            SELECT *,ROW_NUMBER() OVER (PARTITION BY question_origin_id
                ORDER BY CASE WHEN conversation_id=? THEN 0 ELSE 1 END,conversation_created DESC,conversation_id DESC,message_id DESC) AS family_rank
            FROM copies WHERE copy_rank=1
        ) SELECT * FROM choices WHERE family_rank<=? ORDER BY question_origin_id,created_at,conversation_created,conversation_id,message_id''',
            (conversation_id, owner, scope['project_id'], scope['branch_group'], *questions, conversation_id, MAX_VARIANTS))).fetchall()
    families = {}
    for item in found:
        choice = {'conversation_id': item['conversation_id'], 'message_id': item['message_id']}
        if item['model']:
            choice['model'] = item['model']
        if item['effort']:
            choice['effort'] = item['effort']
        families.setdefault(item['question_origin_id'], []).append((item['origin_id'], choice))
    by_id = {item['message_id']: item for item in current}
    for row in rows:
        lineage = by_id.get(row['id'])
        family = families.get(lineage['question_origin_id'], []) if lineage else []
        if len(family) < 2:
            continue
        index = next((i for i, (origin_id, _) in enumerate(family) if origin_id == lineage['origin_id']), None)
        if index is not None:
            row['reply_variants'] = {'index': index, 'choices': [choice for _, choice in family]}
    return rows
