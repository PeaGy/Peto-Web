"""Request-scoped creation of real, private chat artifacts. No model-supplied paths."""
from contextvars import ContextVar
from pathlib import Path
from typing import Literal
import logging
import re
import unicodedata

import anyio
from anyio import to_process
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from features.documents.export import TOC_LEVELS, clean_text, image_numbers, MAX_CONTENT, parse_blocks
from features.documents.jobs import (TOOL_WAIT, RenderBusy, build_files, build_presentation, build_spreadsheet,
                                     document_filename, render_queue, sheet_today)
from features.documents import images as document_images
from features.documents.sheets import spec as sheet_spec
from features.documents.sheets.spec import SCHEMA as SPREADSHEET_SCHEMA
from features.documents.sheets.view import summary as sheet_summary
from features.documents.slides.spec import SCHEMA as PRESENTATION_SCHEMA, DeckInput, image_numbers as slide_images, normalize, plain_text
from features.documents.workbook_edit.ops import SCHEMA as EDIT_SCHEMA, EditInput, changed_line, run as run_edit
from features.documents.workbook_reader import SPREADSHEET_MIMES
from storage import documents as document_store

# Sửa tệp Excel: chờ tối đa (giây) trong tiến trình riêng; phần chữ của tệp mới lưu kèm để Peto đọc ở lượt sau.
EDIT_TIMEOUT = 45
EDIT_EXCERPT_CHARS = 40_000
MAX_EDITS_PER_TURN = 4
CHANGED_PREFIX = 'Ô đã sửa: '
# Lời nhờ sửa trong tin nhắn (có dấu, không phân biệt hoa thường). Chỉ để nhà cung cấp AI biết có nên nhắc Grok làm tiếp
# khi nó báo sắp sửa rồi dừng (ai/xai.py, FOLLOW_UP); không quyết định công cụ nào được dùng.
_EDIT_WORDS = re.compile(r'(?<!\w)(sửa|chỉnh|điền|thêm|xóa|xoá|đổi|gộp|tô màu|định dạng|cập nhật|làm lại|fix|edit)(?!\w)',
                         re.IGNORECASE)


def asks_edit(text: str) -> bool:
    return bool(_EDIT_WORDS.search(unicodedata.normalize('NFC', text or '')))

logger = logging.getLogger('peto_web.documents')
current_session = ContextVar('document_session', default=None)

_VIETNAMESE_MARKERS = (
    'nghi luan', 'xa hoi', 'trach nhiem', 'dat van de', 'mo bai', 'than bai',
    'ket bai', 'noi dung', 'tai lieu', 'ke hoach', 'gioi tre', 'doc sach',
    'thoi dai', 'nguyen nhan', 'giai phap', 'mang xa hoi', 'su tu te',
)


def _looks_like_unaccented_vietnamese(title: str, content: str) -> bool:
    """Catch an obvious ASCII-only Vietnamese draft before it becomes an artifact.

    This intentionally recognizes only a conservative set of common phrases. It
    never tries to restore accents because guessing them can change meaning.
    """
    text = f'{title}\n{content}'
    if any(unicodedata.combining(char) or char in 'đĐ' for char in text):
        return False
    folded = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('ascii').casefold()
    return sum(marker in folded for marker in _VIETNAMESE_MARKERS) >= 2

def _has_contents(blocks) -> bool:
    """Tài liệu có mục lục thật: có dòng [TOC] và có đề mục để đưa vào."""
    return any(block.kind == 'toc' for block in blocks) and any(
        block.kind == 'heading' and block.level <= TOC_LEVELS for block in blocks)


SCHEMA = {
    'type': 'function', 'name': 'create_document', 'strict': True,
    'description': 'Tạo tệp Word DOCX hoặc PDF thật, lưu riêng theo tài khoản và hiện thẻ xem trước/tải ngay trong chat. Gọi khi người dùng yêu cầu tạo/xuất/gửi file; không chỉ dán nội dung vào lời nhắn. Không dùng chỉ để đọc, tóm tắt hay giải thích cách tạo file. Giữ đúng ngôn ngữ người dùng; nếu là tiếng Việt, title và content bắt buộc dùng Unicode tiếng Việt đầy đủ dấu, tuyệt đối không viết tiếng Việt không dấu.',
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'title': {'type': 'string', 'description': 'Tên tài liệu ngắn, không có phần mở rộng. Giữ nguyên ngôn ngữ yêu cầu; tiếng Việt phải có đầy đủ dấu (ă â ê ô ơ ư đ và dấu thanh), không phiên âm ASCII.'},
            'content': {'type': 'string', 'description': 'Toàn bộ nội dung tài liệu dạng Markdown, bắt đầu bằng tiêu đề. Giữ đúng ngôn ngữ người dùng; nếu viết tiếng Việt phải dùng đầy đủ dấu Unicode trong toàn bộ title, heading và đoạn văn, không viết không dấu. Không chứa lời chào, hướng dẫn bấm nút, thông báo tạo xong hay code fence bọc toàn bài. Có thể dùng bảng tối đa 8 cột. Chèn ảnh người dùng đã gửi trong hội thoại bằng một dòng riêng ![chú thích](anh-N), N là số trong nhãn [Ảnh N: …]; chú thích hiện dưới ảnh; tối đa 12 ảnh; không dùng ảnh từ web. Muốn có mục lục thì đặt một dòng [TOC] ngay sau đoạn mở đầu (mục lục gồm đề mục ##, ###). Chưa hỗ trợ LaTeX, emoji.'},
            'format': {'type': 'string', 'enum': ['docx', 'pdf']},
            'style': {'type': 'string', 'enum': ['report', 'essay'], 'description': 'essay cho bài nghị luận: A4, Times New Roman trong DOCX, căn đều, đầu/chân trang và số trang. report cho báo cáo, kế hoạch, bảng biểu.'},
        }, 'required': ['title', 'content', 'format', 'style'],
    },
}


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=MAX_CONTENT)
    format: Literal['docx', 'pdf']
    style: Literal['report', 'essay']


def conversation_workbooks(rows) -> list[dict]:
    """Tệp Excel sửa được của hội thoại, cũ trước mới sau: tệp người dùng gửi (đường dẫn đã lưu, lọc theo chủ tài khoản
    trong SQL) và các bản Peto đã sửa (tài liệu kiểu 'workbook')."""
    found = []
    for row in rows or []:
        for item in row.get('attachments') or []:
            if item.get('kind') == 'file' and item.get('mime') in SPREADSHEET_MIMES and item.get('path'):
                found.append({'name': item['filename'], 'kind': 'upload', 'path': item['path'], 'mime': item['mime']})
        for artifact in row.get('artifacts') or []:
            if isinstance(artifact, dict) and artifact.get('style') == 'workbook' and artifact.get('id'):
                found.append({'name': artifact.get('filename', ''), 'kind': 'document', 'id': artifact['id']})
    return found


class DocumentSession:
    def __init__(self, owner, conversation_id, rows=None):
        self.owner, self.conversation_id = owner, conversation_id
        self.created = []
        self._completed = {}
        self.workbooks = conversation_workbooks(rows)
        # Tin nhắn của lượt này nhờ sửa (asks_edit): phía chat đặt sau khi tạo phiên.
        self.edit_request = False
        # Tệp Excel đã sửa trong lượt này, theo mã tài liệu: dòng thay đổi, ô đã sửa và chỗ thẻ của nó trong ``created``.
        # Sửa tiếp cùng tệp thì bản mới kể cả các thay đổi trước và thay thẻ cũ: một lượt chỉ để lại một thẻ cho mỗi tệp.
        self._turn_edits: dict[str, dict] = {}
        self.edits = 0

    async def create(self, arguments: str):
        try:
            if not isinstance(arguments, str) or len(arguments) > MAX_CONTENT * 7:
                raise ValueError('Tham số tạo tài liệu quá lớn.')
            spec = DocumentInput.model_validate_json(arguments)
            title = ' '.join(clean_text(spec.title).split())
            content = clean_text(spec.content)
            if not title: raise ValueError('Tên tài liệu trống.')
            if _looks_like_unaccented_vietnamese(title, content):
                raise ValueError('Nội dung tiếng Việt đang bị gửi không dấu. Hãy gọi lại create_document với title và content dùng Unicode tiếng Việt đầy đủ dấu; không tự đoán hoặc bỏ qua lỗi này.')
            blocks = parse_blocks(content)
            key = (title, content, spec.format, spec.style)
            if key in self._completed: return self._completed[key]
            if len(self.created) >= 2: raise ValueError('Mỗi lượt chỉ tạo tối đa hai tài liệu.')
            raw_images = await document_images.load(self.owner, self.conversation_id, image_numbers(blocks), strict=True)
            try:
                async with render_queue.slot(TOOL_WAIT):
                    files = await anyio.to_thread.run_sync(build_files, title, content, spec.style, spec.format, raw_images)
                    # Once rendering succeeds, commit the draft and all bytes atomically.
                    # A disconnect can recover this document from its conversation shelf.
                    with anyio.CancelScope(shield=True):
                        draft = await document_store.save_document(self.owner, self.conversation_id, title, content, style=spec.style, assets=files)
                        artifact = {k: draft[k] for k in ('id', 'title', 'version', 'style')}
                        artifact.update(format=spec.format, filename=document_filename(title, spec.format), pages=files['pages'])
                        self.created.append(artifact)
                        instruction = 'Tệp đã tạo và thẻ tài liệu tự hiển thị. Trả lời ngắn về nội dung/định dạng. Không chép lại toàn bộ bài, không yêu cầu bấm Tạo tài liệu, không tự viết đường dẫn.'
                        if spec.format == 'docx' and _has_contents(blocks):
                            instruction += ' Tài liệu có mục lục: dặn ngắn rằng khi mở bằng Word, chọn Có (Yes) lúc Word hỏi cập nhật các trường thì mục lục mới có số trang.'
                        result = {'ok': True, 'artifact': artifact, 'instruction': instruction}
                        self._completed[key] = result
                        return result
            except RenderBusy:
                raise ValueError('Peto đang xuất tài liệu khác. Hãy báo người dùng thử lại sau vài giây.') from None
        except ValidationError:
            return {'error': 'Đầu vào cần title, content (tối đa 60.000 ký tự), format docx/pdf, style report/essay. Sửa tham số rồi gọi lại.'}
        except (ValueError, HTTPException) as error:
            return {'error': str(error.detail) if isinstance(error, HTTPException) else str(error)}
        except Exception:
            logger.exception('Không tạo được tài liệu')
            return {'error': 'Chưa tạo được tệp. Không nói đã tạo xong; báo người dùng thử lại.'}

    async def present(self, arguments: str):
        """Công cụ create_presentation: kiểm tra, dàn trang, lưu PPTX cùng bản PDF xem trước như một tài liệu của hội thoại."""
        try:
            if not isinstance(arguments, str) or len(arguments) > 250_000:
                raise ValueError('Tham số tạo bài thuyết trình quá lớn.')
            deck = normalize(DeckInput.model_validate_json(arguments))
            if _looks_like_unaccented_vietnamese(deck.title, plain_text(deck)):
                raise ValueError('Nội dung tiếng Việt đang bị gửi không dấu. Hãy gọi lại create_presentation với chữ tiếng Việt '
                                 'đầy đủ dấu; không tự đoán hoặc bỏ qua lỗi này.')
            content = deck.to_json()
            key = ('pptx', content)
            if key in self._completed: return self._completed[key]
            if len(self.created) >= 2: raise ValueError('Mỗi lượt chỉ tạo tối đa hai tài liệu.')
            raw_images = await document_images.load(self.owner, self.conversation_id, slide_images(deck), strict=True,
                                                    tool='create_presentation')
            try:
                async with render_queue.slot(TOOL_WAIT):
                    files = await anyio.to_thread.run_sync(build_presentation, content, raw_images)
                    with anyio.CancelScope(shield=True):
                        draft = await document_store.save_document(self.owner, self.conversation_id, deck.title, content,
                                                                   style=deck.theme, assets=files)
                        artifact = {k: draft[k] for k in ('id', 'title', 'version', 'style')}
                        artifact.update(format='pptx', filename=document_filename(deck.title, 'pptx'), pages=files['pages'])
                        self.created.append(artifact)
                        result = {'ok': True, 'artifact': artifact, 'instruction': (
                            'Bài thuyết trình đã tạo và thẻ xem trước tự hiển thị. Trả lời ngắn: số slide, phong cách, ý chính; '
                            'nói rằng mỗi slide có ghi chú cho người thuyết trình và tải được PPTX hoặc PDF. Không chép lại '
                            'toàn bộ slide, không tự viết đường dẫn.')}
                        self._completed[key] = result
                        return result
            except RenderBusy:
                raise ValueError('Peto đang xuất tài liệu khác. Hãy báo người dùng thử lại sau vài giây.') from None
        except ValidationError as error:
            details = '; '.join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()[:4])
            return {'error': f'Tham số chưa đúng lược đồ ({details}). Sửa rồi gọi lại create_presentation.'}
        except (ValueError, HTTPException) as error:
            return {'error': str(error.detail) if isinstance(error, HTTPException) else str(error)}
        except Exception:
            logger.exception('Không tạo được bài thuyết trình')
            return {'error': 'Chưa tạo được tệp. Không nói đã tạo xong; báo người dùng thử lại.'}

    async def tabulate(self, arguments: str):
        """Công cụ create_spreadsheet: kiểm tra từng ô, tính công thức, ghi XLSX và lưu như một tài liệu của hội thoại."""
        try:
            if not isinstance(arguments, str) or len(arguments) > 300_000:
                raise ValueError('Tham số tạo bảng tính quá lớn.')
            book = sheet_spec.normalize(sheet_spec.WorkbookInput.model_validate_json(arguments))
            if _looks_like_unaccented_vietnamese(book.title, sheet_spec.plain_text(book)):
                raise ValueError('Nội dung tiếng Việt đang bị gửi không dấu. Hãy gọi lại create_spreadsheet với chữ tiếng Việt '
                                 'đầy đủ dấu; không tự đoán hoặc bỏ qua lỗi này.')
            content = book.to_json()
            key = ('xlsx', content)
            if key in self._completed: return self._completed[key]
            if len(self.created) >= 2: raise ValueError('Mỗi lượt chỉ tạo tối đa hai tài liệu.')

            def build():
                prepared = sheet_spec.prepare(book, sheet_today())
                return build_spreadsheet(content, prepared), sheet_summary(prepared)

            try:
                async with render_queue.slot(TOOL_WAIT):
                    files, results = await anyio.to_thread.run_sync(build)
                    with anyio.CancelScope(shield=True):
                        draft = await document_store.save_document(self.owner, self.conversation_id, book.title, content,
                                                                   style='sheet', assets=files)
                        artifact = {k: draft[k] for k in ('id', 'title', 'version', 'style')}
                        artifact.update(format='xlsx', filename=document_filename(book.title, 'xlsx'), pages=files['pages'])
                        self.created.append(artifact)
                        result = {'ok': True, 'artifact': artifact, 'instruction': (
                            'Bảng tính đã tạo và lưới xem tự hiển thị trong chat. Trả lời ngắn: các trang tính, cột nào tính bằng '
                            'công thức gì, biểu đồ gì; số liệu nêu ra lấy từ results. Không chép lại cả bảng, không tự viết '
                            'đường dẫn.')}
                        if results:
                            result['results'] = results
                        self._completed[key] = result
                        return result
            except RenderBusy:
                raise ValueError('Peto đang xuất tài liệu khác. Hãy báo người dùng thử lại sau vài giây.') from None
        except ValidationError as error:
            details = '; '.join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()[:4])
            return {'error': f'Tham số chưa đúng lược đồ ({details}). Sửa rồi gọi lại create_spreadsheet.'}
        except (ValueError, HTTPException) as error:
            return {'error': str(error.detail) if isinstance(error, HTTPException) else str(error)}
        except Exception:
            logger.exception('Không tạo được bảng tính')
            return {'error': 'Chưa tạo được tệp. Không nói đã tạo xong; báo người dùng thử lại.'}

    async def _workbook(self, name: str) -> dict:
        """Bản mới nhất của tệp Excel tên ``name`` trong hội thoại: bytes, tên tệp và tài liệu (nếu là bản Peto đã sửa)."""
        wanted = ' '.join(str(name or '').split())
        matches = [item for item in self.workbooks if item['name'] == wanted] or [
            item for item in self.workbooks if item['name'].casefold() == wanted.casefold()]
        if not matches:
            names = ', '.join(dict.fromkeys(f'"{item["name"]}"' for item in self.workbooks)) or 'chưa có'
            raise ValueError(f'Không có tệp Excel "{wanted[:80]}" trong hội thoại. Tệp sửa được: {names}.')
        latest = matches[-1]
        if latest['kind'] == 'upload':
            try:
                data = await anyio.to_thread.run_sync(Path(latest['path']).read_bytes)
            except OSError:
                raise ValueError('Không mở được tệp đã lưu. Nhờ người dùng gửi lại tệp Excel.') from None
            return {'data': data, 'filename': latest['name'], 'document_id': None, 'version': None}
        document = await document_store.get_document(self.owner, latest['id'])
        assets = await document_store.get_assets(self.owner, latest['id'], document['version'])
        if not assets or not assets.get('xlsx'):
            raise ValueError('Bản Excel Peto đã sửa không còn tệp. Nhờ người dùng gửi lại tệp gốc.')
        return {'data': assets['xlsx'], 'filename': latest['name'], 'document_id': latest['id'],
                'version': document['version']}

    async def edit(self, arguments: str):
        """Công cụ edit_spreadsheet: sửa thẳng tệp Excel của hội thoại trong tiến trình riêng, lưu bản mới như một phiên
        bản tài liệu (tệp gửi lên lần đầu thì thành tài liệu mới)."""
        try:
            if not isinstance(arguments, str) or len(arguments) > 400_000:
                raise ValueError('Tham số sửa bảng tính quá lớn. Chia thành nhiều lần sửa.')
            spec = EditInput.model_validate_json(arguments)
            written = '\n'.join(text for change in spec.changes
                                for text in [change.value or '', change.new_name or '',
                                             *(cell or '' for row in change.values or [] for cell in row)])
            if _looks_like_unaccented_vietnamese('', written):
                raise ValueError('Chữ tiếng Việt đang bị gửi không dấu. Hãy gọi lại edit_spreadsheet với chữ tiếng Việt đầy '
                                 'đủ dấu; không tự đoán hoặc bỏ qua lỗi này.')
            key = ('edit', arguments)
            if key in self._completed: return self._completed[key]
            # Sửa một bảng nhiều lỗi có thể cần vài lần gọi (40 thay đổi mỗi lần), mỗi lần thành một bản mới.
            if self.edits >= MAX_EDITS_PER_TURN:
                raise ValueError(f'Mỗi lượt chỉ lưu tối đa {MAX_EDITS_PER_TURN} bản sửa. Báo người dùng phần đã sửa; '
                                 'phần còn lại làm ở lượt sau.')
            source = await self._workbook(spec.file)
            changes = [change.model_dump() for change in spec.changes]
            # Tệp này đã sửa ở lần gọi trước trong lượt: bản mới mang theo thay đổi của lần đó.
            earlier = self._turn_edits.get(source['document_id']) if source['document_id'] else None
            carried = {'lines': earlier['lines'], 'changed': earlier['changed']} if earlier else None
            try:
                async with render_queue.slot(TOOL_WAIT):
                    with anyio.fail_after(EDIT_TIMEOUT):
                        outcome = await to_process.run_sync(run_edit, source['data'], changes, sheet_today().isoformat(),
                                                            EDIT_EXCERPT_CHARS, carried, cancellable=True)
            except RenderBusy:
                raise ValueError('Peto đang xuất tài liệu khác. Hãy báo người dùng thử lại sau vài giây.') from None
            except TimeoutError:
                raise ValueError('Tệp lớn quá nên sửa mất quá lâu. Báo người dùng chia nhỏ tệp hoặc sửa ít ô hơn mỗi lần.') from None
            if 'error' in outcome:
                if outcome.get('internal'):
                    logger.warning('Bộ sửa Excel lỗi: %s', outcome['internal'])
                # Nhật ký chỉ kể lỗi; dòng dặn mô hình cách sửa ("Sửa công thức, hoặc bọc IFERROR…") không phải lỗi.
                problems = [line for line in outcome['error'].splitlines()
                            if line.startswith(('Thay đổi ', 'Công thức mới ', '(và '))] or [outcome['error']]
                return {'error': outcome['error'] + '\nChưa ghi gì vào tệp, kể cả các thay đổi không lỗi. Sửa hết các lỗi '
                        'trên rồi gọi lại edit_spreadsheet với đủ danh sách thay đổi.',
                        '_ui': {'label': 'Sửa tệp bị từ chối, chưa ghi gì', 'problems': problems}}
            filename = source['filename']
            title = filename.rsplit('.', 1)[0].strip() or 'Bảng tính'
            content = workbook_content(filename, outcome)
            files = {'docx': b'', 'pdf': b'', 'preview': b'', 'xlsx': outcome['data'], 'pages': len(outcome['sheets']),
                     'format': 'xlsx'}
            with anyio.CancelScope(shield=True):
                if source['document_id'] and source['version'] < document_store.MAX_VERSIONS:
                    draft = await document_store.save_document(self.owner, None, title, content, source['document_id'],
                                                               source['version'], style='workbook', assets=files)
                else:
                    draft = await document_store.save_document(self.owner, self.conversation_id, title, content,
                                                               style='workbook', assets=files)
                artifact = {k: draft[k] for k in ('id', 'title', 'version', 'style')}
                # Thẻ trong chat hiện danh sách thay đổi ngay, không phải tải cả lưới; ``lines`` gồm cả các lần sửa trước
                # của tệp này trong lượt, ``change_count`` là tổng số dòng (thẻ chỉ mang 20 dòng đầu).
                artifact.update(format='xlsx', filename=filename, pages=files['pages'], changes=outcome['lines'][:20],
                                change_count=len(outcome['lines']))
                if earlier is not None:
                    # Cùng một lượt: thẻ của bản trước nhường chỗ cho bản mới, nên trả lời chỉ có một thẻ cho tệp này.
                    index = earlier['index']
                    self.created[index] = artifact
                    self._turn_edits.pop(source['document_id'], None)
                else:
                    index = len(self.created)
                    self.created.append(artifact)
                self._turn_edits[draft['id']] = {'lines': outcome['lines'], 'changed': outcome['changed'], 'index': index}
                self.edits += 1
                self.workbooks.append({'name': filename, 'kind': 'document', 'id': draft['id']})
                result = {'ok': True, 'artifact': artifact, 'changes': outcome.get('new_lines', outcome['lines']), 'instruction': (
                    'Tệp đã sửa, giữ nguyên định dạng và các phần khác; thẻ xem tự hiển thị trong chat (ô đã sửa được tô '
                    'nổi). Trả lời ngắn: đã sửa gì, ở đâu; số liệu nêu ra lấy từ results. Nếu có notes thì nói ngắn phần '
                    'cần biết. Không chép lại cả bảng, không tự viết đường dẫn.')}
                if outcome['results']:
                    result['results'] = outcome['results']
                if outcome['notes']:
                    result['notes'] = outcome['notes']
                summary = f'{len(spec.changes)} thay đổi'
                if outcome.get('computed'):
                    summary += f' · tính lại {outcome["computed"]} công thức'
                result['_ui'] = {'label': f'Đã sửa {filename}', 'detail': summary}
                self._completed[key] = result
                return result
        except ValidationError as error:
            details = '; '.join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()[:4])
            return {'error': f'Tham số chưa đúng lược đồ ({details}). Sửa rồi gọi lại edit_spreadsheet.'}
        except (ValueError, HTTPException) as error:
            return {'error': str(error.detail) if isinstance(error, HTTPException) else str(error)}
        except Exception:
            logger.exception('Không sửa được tệp Excel')
            return {'error': 'Chưa sửa được tệp. Không nói đã sửa xong; báo người dùng thử lại.'}


_CHANGE = re.compile(r"^- '((?:[^']|'')+)'(?:!([A-Z]{1,3}\d+(?::[A-Z]{1,3}\d+)?|\d+:\d+|[A-Z]{1,3}:[A-Z]{1,3}))?: (.+)$")


def parse_changes(content: str) -> list[dict]:
    """Các dòng dưới "Thay đổi:" của bản Excel đã sửa, tách thành trang, vùng (A9:F9, 9:10, G:H hoặc trống) và chữ, cho
    danh sách thay đổi trong lưới xem."""
    out, started = [], False
    for line in content.splitlines():
        if line == 'Thay đổi:':
            started = True
            continue
        if not started:
            continue
        if not line.startswith('- '):
            break
        match = _CHANGE.match(line)
        if match:
            out.append({'sheet': match.group(1).replace("''", "'"), 'where': match.group(2) or '', 'text': match.group(3)})
        else:
            out.append({'sheet': '', 'where': '', 'text': line[2:]})
    return out


def workbook_content(filename: str, outcome: dict) -> str:
    """Nội dung lưu của bản Excel đã sửa, cũng là chữ Peto đọc ở lượt sau: thay đổi, ô đã sửa, rồi dữ liệu của tệp mới."""
    lines = [f'[Bản Peto đã sửa của tệp "{filename}". Định dạng, công thức khác, biểu đồ và mọi phần khác giữ như tệp '
             'trước. Sửa tiếp thì gọi edit_spreadsheet với đúng tên tệp này.]', 'Thay đổi:']
    lines.extend(f'- {line.strip()}' for line in outcome['lines'])
    changed = changed_line(outcome['changed'])
    if changed:
        lines.append(f'{CHANGED_PREFIX}{changed}')
    for note in outcome['notes']:
        lines.append(f'Lưu ý: {note}')
    lines.append('')
    lines.append(outcome['readout'])
    return '\n'.join(lines)
