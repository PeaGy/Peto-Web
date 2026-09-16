"""Request-scoped creation of real, private chat artifacts. No model-supplied paths."""
from contextvars import ContextVar
from typing import Literal
import logging
import unicodedata

import anyio
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from document_export import clean_text, MAX_CONTENT, parse_blocks
from document_jobs import build_files, document_filename, render_lock
import document_store

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

SCHEMA = {
    'type': 'function', 'name': 'create_document', 'strict': True,
    'description': 'Tạo tệp Word DOCX hoặc PDF thật, lưu riêng theo tài khoản và hiện thẻ xem trước/tải ngay trong chat. Gọi khi người dùng yêu cầu tạo/xuất/gửi file; không chỉ dán nội dung vào lời nhắn. Không dùng chỉ để đọc, tóm tắt hay giải thích cách tạo file. Giữ đúng ngôn ngữ người dùng; nếu là tiếng Việt, title và content bắt buộc dùng Unicode tiếng Việt đầy đủ dấu, tuyệt đối không viết tiếng Việt không dấu.',
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'title': {'type': 'string', 'description': 'Tên tài liệu ngắn, không có phần mở rộng. Giữ nguyên ngôn ngữ yêu cầu; tiếng Việt phải có đầy đủ dấu (ă â ê ô ơ ư đ và dấu thanh), không phiên âm ASCII.'},
            'content': {'type': 'string', 'description': 'Toàn bộ nội dung tài liệu dạng Markdown, bắt đầu bằng tiêu đề. Giữ đúng ngôn ngữ người dùng; nếu viết tiếng Việt phải dùng đầy đủ dấu Unicode trong toàn bộ title, heading và đoạn văn, không viết không dấu. Không chứa lời chào, hướng dẫn bấm nút, thông báo tạo xong hay code fence bọc toàn bài. Có thể dùng bảng tối đa 8 cột. Chưa hỗ trợ ảnh, LaTeX, emoji.'},
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
            parse_blocks(content)
            key = (title, content, spec.format, spec.style)
            if key in self._completed: return self._completed[key]
            if len(self.created) >= 2: raise ValueError('Mỗi lượt chỉ tạo tối đa hai tài liệu.')
            if render_lock.locked(): raise ValueError('Peto đang xuất tài liệu khác. Hãy báo người dùng thử lại sau vài giây.')
            async with render_lock:
                files = await anyio.to_thread.run_sync(build_files, title, content, spec.style, spec.format)
                # Once rendering succeeds, commit the draft and all bytes atomically.
                # A disconnect can recover this document from its conversation shelf.
                with anyio.CancelScope(shield=True):
                    draft = await document_store.save_document(self.owner, self.conversation_id, title, content, style=spec.style, assets=files)
                    artifact = {k: draft[k] for k in ('id', 'title', 'version', 'style')}
                    artifact.update(format=spec.format, filename=document_filename(title, spec.format), pages=files['pages'])
                    self.created.append(artifact)
                    result = {'ok': True, 'artifact': artifact, 'instruction': 'Tệp đã tạo và thẻ tài liệu tự hiển thị. Trả lời ngắn về nội dung/định dạng. Không chép lại toàn bộ bài, không yêu cầu bấm Tạo tài liệu, không tự viết đường dẫn.'}
                    self._completed[key] = result
                    return result
        except ValidationError:
            return {'error': 'Đầu vào cần title, content (tối đa 60.000 ký tự), format docx/pdf, style report/essay. Sửa tham số rồi gọi lại.'}
        except (ValueError, HTTPException) as error:
            return {'error': str(error.detail) if isinstance(error, HTTPException) else str(error)}
        except Exception:
            logger.exception('Không tạo được tài liệu')
            return {'error': 'Chưa tạo được tệp. Không nói đã tạo xong; báo người dùng thử lại.'}
