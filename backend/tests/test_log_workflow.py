"""Quy trình đọc log/crash report (P1 của khảo sát công cụ, 21/10/2026): phần đọc sẵn giữ dòng nêu tên mod gây lỗi,
khối hướng dẫn chỉ đi kèm khi hội thoại có tệp chữ, công cụ tìm trả đúng số dòng của chuỗi nguyên nhân.

Log ở đây là dữ liệu giả (examplemod, othermod); không dùng crash report thật của ai."""
import base64
import re

from conftest import TEST_OWNER, read_events
from features.chat import service as chat_service
from features.chat.prompt_context import _build_system_prompt, has_text_files
from features.documents import reader
from prompts import LOG_PROMPT
from shared import attachment_tools
from test_attachment_tools import args, attached

GUIDE = '## Logs, crash reports and stack traces'
MIXIN = ('[12:02:00] [main/ERROR]: Mixin apply for mod examplemod failed examplemod.mixins.json:MixinFoo from mod '
         'examplemod -> net.minecraft.client.Foo: org.spongepowered.asm.mixin.injection.throwables.'
         'InvalidInjectionException: @Inject annotation on onRender could not find any targets matching render')
CAUSE = ('Caused by: org.spongepowered.asm.mixin.throwables.MixinApplyError: Mixin [examplemod.mixins.json:MixinFoo] '
         'from phase [DEFAULT] in config [examplemod.mixins.json] FAILED during APPLY')


def _name(index: int, size: int = 4) -> str:
    """Tên chỉ có chữ cái, khác nhau theo từng số: dòng không bị gộp thành "cùng dạng" như khi chỉ khác chữ số."""
    return ''.join(chr(97 + (index // 26 ** place) % 26) for place in range(size))


def modpack_log(noise_errors: int = 100) -> tuple[list[str], int, int]:
    lines = [f'[12:00:{i % 60:02d}] [main/INFO]: Loading mod pack{chr(65 + i % 20)} step {i}' for i in range(300)]
    for i in range(noise_errors):
        lines.append(f'[12:01:00] [Worker-Main-{i % 8}/ERROR]: Failed to load texture {_name(i)}:item/{_name(i)}_icon')
        lines.append(f'[12:01:00] [Worker-Main-{i % 8}/WARN]: Recipe {_name(i)}:craft has unknown ingredient')
    mixin = len(lines)
    lines.append(MIXIN)
    lines += [f'\tat org.spongepowered.asm.mixin.Frame{k}.apply(Frame{k}.java:{k})' for k in range(30)]
    lines.append('\tat othermod.compat.Hook.run(Hook.java:42)')
    lines += [f'[12:03:{i % 60:02d}] [Render thread/INFO]: Registered model {_name(i * 5, 7)}:block/{_name(i * 3, 5)}'
              for i in range(400)]
    cause = len(lines)
    lines.append(CAUSE)
    lines += [f'\tat cpw.mods.Loader{k}.load(Loader{k}.java:{k})' for k in range(40)]
    lines += [f'[12:04:{i % 60:02d}] [main/INFO]: Stopping service {_name(i * 11, 8)} cleanly' for i in range(600)]
    return lines, mixin, cause


def test_mixin_failure_naming_the_mod_survives_hundreds_of_earlier_errors():
    # Trước khi có mẫu mixin trong ROOT_SIGNAL, 100 lỗi texture khác dạng đứng trước đã chiếm hết phần dành cho lỗi.
    lines, mixin, cause = modpack_log(100)
    document = reader.extract_document('\n'.join(lines).encode(), 'text/plain', 20_000, 100)
    assert document['status'] == 'partial' and len(document['text']) <= 20_000
    assert MIXIN in document['text'] and CAUSE in document['text']
    # Khối giữ số dòng thật để đọc tiếp bằng read_attachment_lines.
    blocks = [(int(a.replace('.', '')), int(b.replace('.', '')))
              for a, b in re.findall(r'\[Dòng ([\d.]+)–([\d.]+) · có lỗi hoặc cảnh báo\]', document['text'])]
    assert any(first <= mixin + 1 <= last for first, last in blocks)
    assert 0 < mixin < cause


def test_mixin_pattern_does_not_promote_config_names_or_unrelated_warnings():
    for line in ('[main/INFO]: Loaded examplemod.mixins.json with 4 mixins',
                 '[mixin/WARN]: Error loading class: optional/Compat (skipped)'):
        assert not reader.ROOT_SIGNAL.search(line)
    for line in (MIXIN, CAUSE, 'org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError: An error'):
        assert reader.ROOT_SIGNAL.search(line)


def test_text_file_detection_reads_stored_metadata_not_user_words():
    assert has_text_files([{'kind': 'file', 'mime': 'text/plain', 'filename': 'latest.log'}])
    assert has_text_files([{'kind': 'file', 'mime': 'text/x-python', 'filename': 'main.py'}])
    assert not has_text_files([])
    assert not has_text_files([{'kind': 'file', 'mime': 'application/pdf', 'filename': 'crash.pdf'}])
    assert not has_text_files([{'kind': 'image', 'mime': 'image/png', 'filename': 'crash.png'}])
    # Mục tài liệu Peto tự tạo trong danh mục không có kind/mime của tệp gửi lên.
    assert not has_text_files([{'id': 'doc', 'version': 1, 'style': 'classic', 'filename': 'baocao.docx'}])


async def test_log_guide_is_chat_only_and_follows_the_text_file_flag(client):
    with_files = await _build_system_prompt(TEST_OWNER, model='haiku', text_files=True)
    assert GUIDE in with_files and LOG_PROMPT in with_files
    # Đứng trước khối người dùng: hồ sơ/trí nhớ đổi thì phần phía trên, kể cả khối này, vẫn nằm trong tiền tố cache.
    assert with_files.index('## Context boundaries') < with_files.index(GUIDE) < with_files.index('## Current user')
    assert GUIDE not in await _build_system_prompt(TEST_OWNER, model='haiku')
    # "log" trong lời người dùng không tự gắn khối này: chỉ tệp đã lưu mới quyết định.
    assert GUIDE not in await _build_system_prompt(TEST_OWNER, agent_question='Đọc log crash giúp mình')
    assert GUIDE not in await _build_system_prompt(TEST_OWNER, 'companion', text_files=True)


async def test_chat_turn_with_uploaded_log_carries_the_guide_into_follow_ups(client, monkeypatch):
    prompts = []

    class Provider:
        async def stream(self, **kwargs):
            prompts.append(kwargs['system_prompt'])
            yield 'Đã đọc log.'

    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Provider())
    lines, _, _ = modpack_log(10)
    upload = {'name': 'latest.log', 'mime': 'text/plain', 'data': base64.b64encode('\n'.join(lines).encode()).decode()}
    first = await read_events(await client.post('/api/chat', json={'message': 'Vì sao game crash?', 'attachments': [upload]}))
    assert first[-1]['type'] == 'done', first
    conversation = next(event['conversation_id'] for event in first if event['type'] == 'meta')
    later = await read_events(await client.post('/api/chat', json={'message': 'Thử gỡ mod nào trước?',
                                                                   'conversation_id': conversation}))
    assert later[-1]['type'] == 'done'
    plain = await read_events(await client.post('/api/chat', json={'message': 'Log là gì?'}))
    assert plain[-1]['type'] == 'done'
    assert GUIDE in prompts[0] and GUIDE in prompts[1]
    assert GUIDE not in prompts[2]


async def test_search_finds_the_cause_chain_with_true_line_numbers(tmp_path):
    lines, mixin, cause = modpack_log(100)
    rows = await attached(tmp_path, 'latest.log', '\n'.join(lines).encode(), 'text/plain')
    files = attachment_tools.AttachmentFiles(rows)
    assert 'Caused by | Description:' in attachment_tools.SEARCH_SCHEMA['description']
    found = await files.run('search_attachment', args(file='latest.log', query='Caused by | Mixin apply', context_lines=0))
    assert found['matches'] == 2 and found['lines_total'] == len(lines)
    number = reader.number
    assert f'{number(mixin + 1)}: {MIXIN}' in found['text'] and f'{number(cause + 1)}: {CAUSE}' in found['text']
    # Frame của othermod nằm 31 dòng sau lỗi mixin: đọc đúng chỗ đó để xem nó chỉ là một frame.
    frames = await files.run('read_attachment_lines', args(file='latest.log', start_line=mixin + 31, end_line=mixin + 32))
    assert frames['text'] == f'{number(mixin + 31)}: {lines[mixin + 30]}\n{number(mixin + 32)}: {lines[mixin + 31]}'
    assert 'othermod' in lines[mixin + 31]
