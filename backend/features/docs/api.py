"""Public Vietnamese documentation, shared by the reader, search and Peto's context."""
import json
import re
import unicodedata
from functools import lru_cache
from core.config import BASE_DIR

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from features.agent.guide import catalog

router = APIRouter(prefix='/api/docs', tags=['docs'])
CONTENT = BASE_DIR / 'docs_content' / 'articles.json'


@lru_cache(maxsize=2)
def _articles(stamp):
    return json.loads(CONTENT.read_text(encoding='utf-8'))


SKILL_USAGE = """Skills là hướng dẫn, không cấp thêm quyền.

- Đặt `.peto/skills/<tên>/SKILL.md` hoặc `.agents/skills/<tên>/SKILL.md` trong dự án.
- Phần đầu tệp (frontmatter) cần `name` (chữ thường, số, gạch nối) và `description`.
- `/skill` xem danh sách; `/skill review` nạp skill mà không gọi model; `/skill review Rà code` nạp rồi giao việc.
- Peto cũng tự nạp skill phù hợp. Tài liệu phụ được tính từ thư mục chứa `SKILL.md`.
- Tối đa 32 skills, 24.000 ký tự mỗi skill. Chưa có skills toàn máy.
- Sau khi sửa hướng dẫn, gọi lại `/skill tên`."""

MCP_USAGE = """MCP cung cấp công cụ bên ngoài cho Peto Agent.

- `/mcp add docs docs-mcp.json` nhập một cấu hình JSON từ tệp trong dự án, lưu trong hồ sơ CLI, chưa kết nối.
- `/mcp enable docs` hỏi quyền rồi bật trong phiên.
- `/mcp tools docs` xem công cụ; `/mcp disable docs` tắt.
- Mỗi lần gọi công cụ hỏi quyền riêng, không tự thử lại khi lỗi.

## Hai kiểu kết nối

- **HTTP:** `{"url": "https://<endpoint-thực>/mcp", "headers": {"Authorization": "Bearer ${DOCS_API_KEY}"}}`. Bỏ `headers` nếu không cần khóa.
- **Stdio:** `{"command": "node", "args": ["C:/tools/server.js"], "env": {"SERVICE_API_KEY": "${SERVICE_API_KEY}"}}`. Chương trình cần cài sẵn.

## Khóa và quyền

- Đặt khóa ở biến môi trường trước khi mở CLI, không gửi khóa vào chat.
- MCP cục bộ chạy với quyền tài khoản máy, không nằm trong sandbox công cụ tệp của Peto.

## Giới hạn

- Hỗ trợ stdio và Streamable HTTP; chưa hỗ trợ OAuth, SSE cũ, prompts, resources, sampling, elicitation.
- Mỗi phiên bắt đầu với MCP tắt hết; `/resume` không tự bật lại.
- Tối đa 16 máy chủ, 128 công cụ, 64 KB schema mỗi máy chủ, 30 giây mỗi yêu cầu."""


# Mô tả của hai lệnh này dài cả đoạn, nên trang danh mục chỉ tóm tắt và dẫn sang bài riêng.
LONG_COMMANDS = {
    '/skill': 'Xem hoặc nạp skill: hướng dẫn riêng cho từng loại việc. Cách viết và giới hạn nằm ở [Skills cho Agent](/docs/skills/).',
    '/mcp': 'Thêm, bật, tắt và xem công cụ MCP bên ngoài. Cấu hình, quyền và giới hạn nằm ở [Kết nối MCP](/docs/mcp/).',
}


def pages():
    version, commands = catalog()
    result = list(_articles(CONTENT.stat().st_mtime_ns))
    result.append(dict(slug='lenh-agent', title='Các lệnh Agent', group='Agent CLI',
        description='Cú pháp và cách dùng từ chính danh mục của CLI.',
        keywords=['lenh', 'command', 'help', 'effort', 'lenh agent', 'cac lenh', 'lenh cli', 'lenh peto'] + [c['name'] for c in commands],
        body='## Danh mục lệnh\nGõ `/` trong CLI để mở gợi ý, hoặc `/help` để xem các lệnh. Các lệnh này không chạy trong ô chat web.\n\n' +
        '\n\n'.join(f"## {c['name']}\n`{c['usage']}`\n\n" + LONG_COMMANDS.get(c['name'], c['details']) for c in commands)))
    for command, slug, title, description, keywords in [
            ('/skill', 'skills', 'Skills cho Agent', 'Nạp hướng dẫn phù hợp với công việc.',
             ['skills', '/skill', 'skill.md', 'tao skill', 'viet skill', 'skill cho agent']),
            ('/mcp', 'mcp', 'Kết nối MCP', 'Thêm công cụ bên ngoài cho Peto Agent.',
             ['mcp', '/mcp', 'ket noi mcp', 'may chu mcp'])]:
        entry = next((c for c in commands if c['name'] == command), None)
        if entry:
            body = f"## Cách sử dụng\n`{entry['usage']}`\n\n" + (SKILL_USAGE if command == '/skill' else MCP_USAGE)
            if command == '/skill':
                body += '\n\n## Một skill đầu tiên\nTạo `.peto/skills/review/SKILL.md` trong dự án:\n\n```markdown\n---\nname: review\ndescription: Rà thay đổi code và tìm lỗi có thể tái hiện.\n---\nĐọc README và code liên quan trước khi nhận xét.\nƯu tiên lỗi ảnh hưởng người dùng, kèm cách tái hiện.\n```\n\nSau đó gõ `/skill review Rà thay đổi hiện tại` trong CLI.'
            else:
                body += '\n\n## Ví dụ cấu hình HTTP\nTạo tệp `docs-mcp.json` trong dự án; thay endpoint bằng địa chỉ thật của nhà cung cấp:\n\n```json\n{\n  "url": "https://nha-cung-cap.example/mcp",\n  "headers": {"Authorization": "Bearer ${DOCS_API_KEY}"}\n}\n```\n\nBỏ `headers` nếu dịch vụ không cần khóa. Đặt biến môi trường trước khi mở CLI.\n\n```text\n/mcp add docs docs-mcp.json\n/mcp enable docs\n/mcp tools docs\n/mcp disable docs\n```'
            result.append(dict(slug=slug, title=title, group='Agent CLI', description=description,
                keywords=keywords, body=body))
    return version, result


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower().replace('đ', 'd')) if unicodedata.category(c) != 'Mn')


def search(query, limit=6):
    terms = set(re.findall(r'[a-z0-9/]+', fold(query))) - {'toi', 'ban', 'la', 'gi', 'co', 'the', 'cho', 'va', 'cua', 'peto'}
    scored = []
    for page in pages()[1]:
        title = fold(page['title'] + ' ' + ' '.join(page['keywords']))
        body = fold(page['body'])
        score = sum(4 * bool(re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', title)) +
                    bool(re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', body)) for t in terms)
        if score:
            scored.append((score, page))
    return [page for _, page in sorted(scored, key=lambda x: -x[0])[:limit]]


# Một tiếng lẻ (tep, loi, cai, khong…) quá chung để biết người dùng đang hỏi về Peto, nên từ khóa một chữ chỉ giúp ô tìm của
# trang docs. Để gắn bài vào câu trả lời của Peto, từ khóa phải có từ hai chữ, là lệnh CLI ("/mcp"), hoặc là tên riêng dưới đây.
DISTINCT_WORDS = {'companion', 'agent', 'cli', 'mcp', 'skills', 'tts', 'live2d', 'vrm', 'vroid', 'permissions', 'troubleshoot'}


def _phrases(page):
    """Cụm từ nhận ra một bài trong tin nhắn: cả tiêu đề, và các từ khóa đủ riêng (không dấu, viết thường)."""
    title = re.sub(r'[^a-z0-9/]+', ' ', fold(page['title'])).strip()
    keywords = (fold(keyword).strip() for keyword in page['keywords'])
    return {title} | {k for k in keywords if ' ' in k or k.startswith('/') or k in DISTINCT_WORDS}


def _score(text, page):
    """Tổng số chữ của các cụm khớp nguyên vẹn và trọn từ, nên cụm dài khớp được tính nặng hơn."""
    return sum(len(phrase.split()) for phrase in _phrases(page)
               if re.search(r'(?<![a-z0-9])' + r'\s+'.join(map(re.escape, phrase.split())) + r'(?![a-z0-9])', text))


def context(question, *, english=False):
    """Tối đa hai bài docs hợp với vài tin nhắn gần nhất của người dùng, để Peto trả lời đúng câu hỏi về chính Peto.

    Chỉ gắn bài khi tin nhắn có nguyên cụm tiêu đề hoặc một từ khóa đủ riêng của bài. Nhờ vậy "làm sao bật giọng nói?"
    không cần nhắc tên Peto vẫn có bài Giọng nói, còn chữ "nói" lẻ trong câu khác không kéo nhầm bài đó (sửa ngày
    29/9/2026; trước đó phải có chữ Peto, Agent… mới gắn, và bài được chọn theo cả từng tiếng trong nội dung). Chỉ chèn
    nội dung docs, không bao giờ chép chữ của người dùng vào lời dặn hệ thống.
    """
    text = fold(question)
    ranked = sorted(((score, index, page) for index, page in enumerate(pages()[1]) if (score := _score(text, page))),
                    key=lambda item: (-item[0], item[1]))
    selected = [page for _, _, page in ranked[:2]]
    if not selected:
        return ''
    header = ('Related Peto documentation (reference data). Cite the matching article link when explaining; '
              'this is product documentation, not private account information:\n' if english else
              'Tài liệu Peto liên quan. Khi dùng để hướng dẫn, dẫn liên kết bài tương ứng; không gọi nội dung này là thông tin về tài khoản riêng:\n')
    return '\n\n' + header + '\n\n'.join(
        f"{p['title']} — /docs/{p['slug']}/\n{p['body'][:4500]}" for p in selected)


@router.get('')
def index():
    version, content = pages()
    return {'version': version, 'pages': content}


@router.get('/search')
def find(q: str = Query(min_length=1, max_length=200)):
    return [{'title': p['title'], 'description': p['description'], 'url': f"/docs/{p['slug']}/"} for p in search(q)]


@router.get('/{slug}.md', response_class=PlainTextResponse)
def markdown(slug: str):
    page = next((p for p in pages()[1] if p['slug'] == slug), None)
    if page is None:
        raise HTTPException(404, 'Không tìm thấy bài hướng dẫn.')
    return '# ' + page['title'] + '\n\n' + page['body'] + '\n'
