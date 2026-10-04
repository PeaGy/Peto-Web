"""Request-scoped creation of real, private chat artifacts. No model-supplied paths."""
from contextvars import ContextVar
from typing import Literal
import logging
import unicodedata

import anyio
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
from storage import documents as document_store

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


class DocumentSession:
    def __init__(self, owner, conversation_id):
        self.owner, self.conversation_id = owner, conversation_id
        self.created = []
        self._completed = {}

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
