"""Phép thử thực thi mã phía nhà cung cấp (khảo sát công cụ 21/10/2026, phần 3a).

Mặc định chạy khô: phản hồi giả dựng theo tài liệu, không gọi mạng, không tốn tiền; bằng chứng ghi ``mode: dry_run``
và không phải bằng chứng về nhà cung cấp. Chỉ khi có ``--allow-paid`` mới gọi API thật bằng thông tin xác thực của máy
đang chạy lệnh (giống backend):

- ``haiku``: Messages API, model Haiku của registry, ``code_execution_20260521``, suy nghĩ adaptive mức low như Chat.
  Tối đa 2 request (1 lần tiếp ``pause_turn``). Tệp ra được tải về để kiểm rồi xóa khỏi Files API.
- ``xai``: Responses API, ``XAI_MODEL``, đúng đường xác thực của web (token OAuth Grok CLI đã lưu, dự phòng
  ``XAI_API_KEY``) nhưng không bao giờ refresh token, ``store: false``, công cụ ``code_interpreter``. Request 2 gửi
  lại item của request 1 làm input để xem có được nhận.

Dữ liệu là bảng giả. Bằng chứng chỉ ghi loại sự kiện/block, usage, mã lỗi, chữ mã đã in và câu trả lời ngắn; không ghi
khóa, token hay header. Chạy từ ``backend/``::

    ../.venv/Scripts/python.exe -X utf8 -m ops.code_execution_probe haiku
    ../.venv/Scripts/python.exe -X utf8 -m ops.code_execution_probe haiku --allow-paid
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
from time import perf_counter

import httpx

ROOT = Path(__file__).resolve().parents[2]
ANTHROPIC_BASE = 'https://api.anthropic.com'
TOOL_VERSION = 'code_execution_20260521'
MAX_OUTPUT_TOKENS = 2048
TIMEOUT = httpx.Timeout(180.0, connect=15.0)
CLIP = 2000

MONTHS = list(range(1, 21))
REVENUE = [120, 135, 128, 142, 150, 138, 161, 155, 149, 170, 165, 158, 172, 180, 176, 169, 185, 190, 182, 195]
EXPECTED = {'mean': round(float(statistics.mean(REVENUE)), 2), 'stdev': round(statistics.stdev(REVENUE), 2),
            'median': round(float(statistics.median(REVENUE)), 2)}
CSV = 'thang,doanh_thu\n' + '\n'.join(f'{month},{value}' for month, value in zip(MONTHS, REVENUE))
INTRO = f'Dữ liệu giả để thử công cụ, không phải dữ liệu thật:\n{CSV}\n\n'
PROMPT_HAIKU = INTRO + (
    'Hãy dùng công cụ chạy mã: tính trung bình và độ lệch chuẩn mẫu của cột doanh_thu (làm tròn 2 chữ số), vẽ biểu đồ '
    'cột doanh_thu theo tháng, lưu thành chart.png trong $OUTPUT_DIR và liệt kê thư mục đó trong cùng lệnh. '
    'Trả lời ngắn hai con số.')
PROMPT_XAI = INTRO + ('Hãy dùng công cụ chạy mã Python tính trung bình và độ lệch chuẩn mẫu của cột doanh_thu '
                      '(làm tròn 2 chữ số) và in kết quả. Trả lời ngắn hai con số.')
FOLLOW_UP_XAI = 'Giờ dùng công cụ chạy mã tính trung vị của cột doanh_thu. Trả lời ngắn.'
# Giá và giới hạn theo tài liệu đọc ngày 21/10/2026 (xem features/chat/docs/tools-survey-2026-10-21.md), không phải hóa đơn.
COST_NOTES = {
    'haiku': 'Token Haiku cộng thời gian chạy mã: tối thiểu 5 phút mỗi lần, 1.550 giờ miễn phí mỗi tổ chức/tháng, '
             'sau đó $0,05/giờ/container. Files API miễn phí.',
    'xai': 'Token grok cộng $5/1.000 lượt gọi code execution nếu tính theo API key; tính theo gói OAuth chưa có tài liệu.',
}


def _clip(value, limit: int = CLIP) -> str:
    text = str(value or '')
    return text if len(text) <= limit else text[:limit] + f'…[cắt {len(text) - limit} ký tự]'


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _seen(text: str, number: float) -> bool:
    """Con số có trong chữ, viết dấu chấm hay dấu phẩy thập phân, đủ hai chữ số lẻ hoặc gọn như Python in ("163.0").
    Lần chạy thật ngày 21/10/2026, Grok trả "163.0" đúng mà bản chỉ tìm "163.00" báo là không thấy."""
    forms = {f'{number:.2f}', f'{number:.1f}'} | ({str(int(number))} if number == int(number) else set())
    pattern = '|'.join(re.escape(form).replace(r'\.', '[.,]') for form in sorted(forms, key=len, reverse=True))
    return re.search(rf'(?<![\d.,])(?:{pattern})(?![\d]|[.,]\d)', text) is not None


async def _events(response: httpx.Response):
    """Đọc SSE: (tên sự kiện, dữ liệu JSON). Dòng data không phải JSON (như [DONE]) được bỏ qua."""
    name, data = None, []

    def flush():
        if not data:
            return None
        try:
            return name, json.loads('\n'.join(data))
        except ValueError:
            return None

    async for line in response.aiter_lines():
        if not line:
            item = flush()
            if item:
                yield item
            name, data = None, []
        elif line.startswith('event:'):
            name = line[6:].strip()
        elif line.startswith('data:'):
            data.append(line[5:].strip())
    item = flush()
    if item:
        yield item


def _failure(response: httpx.Response, body: bytes) -> dict:
    try:
        error = json.loads(body).get('error') or {}
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict):
        error = {'message': error}
    return {'http_status': response.status_code, 'error_type': _clip(error.get('type') or error.get('code'), 120),
            'error_message': _clip(error.get('message') or body.decode(errors='replace'), 400)}


# ---------- A: Haiku ----------

def _block_summary(block: dict) -> dict:
    kind = block.get('type')
    summary = {'type': kind}
    if block.get('name'):
        summary['name'] = block['name']
    if kind == 'text':
        summary['text'] = _clip(block.get('text'), 800)
    elif kind in {'thinking', 'redacted_thinking'}:
        summary['chars'] = len(block.get('thinking') or block.get('data') or '')
    elif kind == 'server_tool_use':
        summary['input_keys'] = sorted((block.get('input') or {}).keys())
        summary['command'] = _clip((block.get('input') or {}).get('command'), 600)
    elif isinstance(block.get('content'), dict):
        content = block['content']
        summary.update(result_type=content.get('type'), return_code=content.get('return_code'),
                       error_code=content.get('error_code'), stdout=_clip(content.get('stdout')),
                       stderr=_clip(content.get('stderr'), 800),
                       files=[_digest(file_id) for file_id in _file_ids(block)])
    return summary


def _file_ids(block: dict) -> list[str]:
    content = block.get('content')
    return [item['file_id'] for item in (content.get('content') or [] if isinstance(content, dict) else [])
            if isinstance(item, dict) and item.get('file_id')]


async def _haiku_message(client: httpx.AsyncClient, headers: dict, body: dict) -> dict:
    started = perf_counter()
    record = {'events': Counter(), 'blocks': [], 'containers': []}
    blocks, partial = {}, {}
    async with client.stream('POST', f'{ANTHROPIC_BASE}/v1/messages', headers=headers, json=body) as response:
        if response.status_code >= 400:
            return {**_failure(response, await response.aread()), 'elapsed_ms': round((perf_counter() - started) * 1000)}
        usage = {}
        async for name, data in _events(response):
            kind = data.get('type') or name
            record['events'][kind] += 1
            if kind == 'message_start':
                message = data.get('message') or {}
                usage.update(message.get('usage') or {})
                if message.get('container'):
                    record['containers'].append(('message_start', message['container']))
            elif kind == 'content_block_start':
                blocks[data['index']] = dict(data.get('content_block') or {})
            elif kind == 'content_block_delta':
                delta, block = data.get('delta') or {}, blocks.setdefault(data['index'], {})
                if delta.get('type') == 'text_delta':
                    block['text'] = block.get('text', '') + delta.get('text', '')
                elif delta.get('type') == 'input_json_delta':
                    partial[data['index']] = partial.get(data['index'], '') + delta.get('partial_json', '')
                elif delta.get('type') == 'thinking_delta':
                    block['thinking'] = block.get('thinking', '') + delta.get('thinking', '')
                elif delta.get('type') == 'signature_delta':
                    block['signature'] = delta.get('signature', '')
            elif kind == 'content_block_stop' and data.get('index') in partial:
                raw = partial.pop(data['index'])
                blocks[data['index']]['input'] = json.loads(raw) if raw else {}
            elif kind == 'message_delta':
                record['stop_reason'] = (data.get('delta') or {}).get('stop_reason')
                usage.update(data.get('usage') or {})
                container = (data.get('delta') or {}).get('container') or data.get('container')
                if container:
                    record['containers'].append(('message_delta', container))
            elif kind == 'error':
                record['stream_error'] = _clip(json.dumps(data.get('error'), ensure_ascii=False), 400)
    record['content'] = [blocks[index] for index in sorted(blocks)]
    record['blocks'] = [_block_summary(block) for block in record['content']]
    record['usage'] = usage
    record['events'] = dict(record['events'])
    record['elapsed_ms'] = round((perf_counter() - started) * 1000)
    return record


async def _haiku_file(client: httpx.AsyncClient, headers: dict, file_id: str) -> dict:
    url = f'{ANTHROPIC_BASE}/v1/files/{file_id}'
    found = {'file': _digest(file_id)}
    meta = await client.get(url, headers=headers)
    found['metadata_status'] = meta.status_code
    if meta.status_code == 200:
        data = meta.json()
        found['metadata'] = {key: data.get(key) for key in ('filename', 'mime_type', 'size_bytes', 'downloadable', 'expires_at')}
    content = await client.get(url + '/content', headers=headers)
    found['download_status'] = content.status_code
    if content.status_code == 200:
        found['bytes'] = len(content.content)
        found['png'] = content.content[:8] == b'\x89PNG\r\n\x1a\n'
    deleted = await client.delete(url, headers=headers)
    found['delete_status'] = deleted.status_code
    found['after_delete_status'] = (await client.get(url, headers=headers)).status_code
    return found


async def probe_haiku(client: httpx.AsyncClient, key: str, model: str) -> dict:
    headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
    body = {'model': model, 'max_tokens': MAX_OUTPUT_TOKENS, 'stream': True,
            'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'low'},
            'tools': [{'type': TOOL_VERSION, 'name': 'code_execution'}],
            'messages': [{'role': 'user', 'content': PROMPT_HAIKU}]}
    evidence = {'provider': 'anthropic', 'model': model, 'tool': TOOL_VERSION, 'requests': []}
    file_ids = []
    for attempt in range(2):
        record = await _haiku_message(client, headers, body)
        content = record.pop('content', [])
        evidence['requests'].append(record)
        if 'http_status' in record:
            break
        for block in content:
            file_ids += _file_ids(block)
        if record.get('stop_reason') != 'pause_turn' or attempt:
            break
        # Tiếp lượt bị tạm dừng đúng như tài liệu: gửi lại nội dung và container của request trước.
        body['messages'].append({'role': 'assistant', 'content': content})
        if record['containers']:
            body['container'] = record['containers'][-1][1].get('id')
    for record in evidence['requests']:
        record['containers'] = [{'from': where, 'id': _digest(str(value.get('id'))), 'expires_at': value.get('expires_at')}
                                for where, value in record.get('containers', [])]
    texts = ' '.join(block.get('stdout') or block.get('text') or ''
                     for record in evidence['requests'] for block in record.get('blocks', []))
    evidence['files'] = [await _haiku_file(client, headers, file_id) for file_id in dict.fromkeys(file_ids)]
    evidence['check'] = {'mean_seen': _seen(texts, EXPECTED['mean']), 'stdev_seen': _seen(texts, EXPECTED['stdev']),
                         'png_returned': any(item.get('png') for item in evidence['files']),
                         'files_deleted': all(item.get('after_delete_status') == 404 for item in evidence['files'])}
    return evidence


# ---------- B: xAI ----------

def _item_summary(item: dict) -> dict:
    summary = {'type': item.get('type'), 'status': item.get('status'), 'keys': sorted(item)}
    if item.get('type') == 'code_interpreter_call':
        summary['code'] = _clip(item.get('code'), 1200)
        summary['outputs'] = _clip(json.dumps(item.get('outputs'), ensure_ascii=False), 1500)
    elif item.get('type') == 'message':
        summary['text'] = _clip(' '.join(part.get('text', '') for part in item.get('content') or []
                                         if isinstance(part, dict)), 800)
    return summary


async def _xai_response(client: httpx.AsyncClient, base: str, token: str, body: dict) -> tuple[dict, list]:
    started = perf_counter()
    record, output = {'events': Counter()}, []
    headers = {'Authorization': f'Bearer {token}'}
    async with client.stream('POST', f'{base}/responses', headers=headers, json=body) as response:
        if response.status_code >= 400:
            return {**_failure(response, await response.aread()), 'elapsed_ms': round((perf_counter() - started) * 1000)}, []
        async for name, data in _events(response):
            kind = data.get('type') or name
            record['events'][kind] += 1
            if kind == 'response.completed':
                final = data.get('response') or {}
                output = final.get('output') or []
                record['status'] = final.get('status')
                record['usage'] = final.get('usage')
                for key in ('server_side_tool_usage', 'tool_calls'):
                    if key in final:
                        record[key] = final[key]
            elif kind in {'response.failed', 'response.incomplete', 'error'}:
                record['failure'] = _clip(json.dumps(data, ensure_ascii=False), 600)
    record['events'] = dict(record['events'])
    record['items'] = [_item_summary(item) for item in output]
    record['elapsed_ms'] = round((perf_counter() - started) * 1000)
    return record, output


async def probe_xai(client: httpx.AsyncClient, base: str, token: str, model: str, auth_mode: str) -> dict:
    question = [{'role': 'user', 'content': [{'type': 'input_text', 'text': PROMPT_XAI}]}]
    body = {'model': model, 'input': question, 'tools': [{'type': 'code_interpreter'}], 'stream': True, 'store': False,
            'include': ['reasoning.encrypted_content'], 'reasoning': {'effort': 'low'},
            'max_output_tokens': MAX_OUTPUT_TOKENS}
    evidence = {'provider': 'xai', 'model': model, 'auth_mode': auth_mode, 'requests': []}
    first, output = await _xai_response(client, base, token, body)
    evidence['requests'].append(first)
    if output:
        # store=false: lượt sau phải tự gửi lại item cũ, như vòng công cụ của Peto.
        body['input'] = [*question, *output, {'role': 'user', 'content': [{'type': 'input_text', 'text': FOLLOW_UP_XAI}]}]
        second, _ = await _xai_response(client, base, token, body)
        evidence['requests'].append(second)
    texts = json.dumps(evidence['requests'], ensure_ascii=False)
    evidence['check'] = {'mean_seen': _seen(texts, EXPECTED['mean']), 'stdev_seen': _seen(texts, EXPECTED['stdev']),
                         'median_seen': _seen(texts, EXPECTED['median']),
                         'code_items': sum(item['type'] == 'code_interpreter_call'
                                           for record in evidence['requests'] for item in record.get('items', [])),
                         'follow_up_accepted': len(evidence['requests']) == 2 and 'http_status' not in evidence['requests'][1]}
    return evidence


# ---------- Chạy khô: phản hồi giả theo tài liệu ----------

def _sse(events: list[dict]) -> bytes:
    return ''.join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()


def fake_transport() -> httpx.MockTransport:
    """Phản hồi giả dựng theo tài liệu đã đọc, để kiểm phần đọc và ghi bằng chứng; không phải hành vi thật."""
    mean, stdev, median = EXPECTED['mean'], EXPECTED['stdev'], EXPECTED['median']
    deleted = set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == '/v1/messages':
            tool = {'type': 'server_tool_use', 'id': 'srvtoolu_fake', 'name': 'bash_code_execution', 'input': {}}
            result = {'type': 'bash_code_execution_tool_result', 'tool_use_id': 'srvtoolu_fake', 'content': {
                'type': 'bash_code_execution_result', 'stdout': f'mean={mean:.2f} stdev={stdev:.2f}\nchart.png', 'stderr': '',
                'return_code': 0, 'content': [{'type': 'bash_code_execution_output', 'file_id': 'file_fake_chart'}]}}
            return httpx.Response(200, content=_sse([
                {'type': 'message_start', 'message': {'usage': {'input_tokens': 900, 'output_tokens': 1}}},
                {'type': 'content_block_start', 'index': 0, 'content_block': tool},
                {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta',
                                                                      'partial_json': '{"command": "python a.py"}'}},
                {'type': 'content_block_stop', 'index': 0},
                {'type': 'content_block_start', 'index': 1, 'content_block': result},
                {'type': 'content_block_stop', 'index': 1},
                {'type': 'content_block_start', 'index': 2, 'content_block': {'type': 'text', 'text': ''}},
                {'type': 'content_block_delta', 'index': 2, 'delta': {'type': 'text_delta', 'text': f'TB {mean:.2f}'}},
                {'type': 'content_block_stop', 'index': 2},
                {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'container': {
                    'id': 'container_fake', 'expires_at': '2026-10-21T12:00:00Z'}},
                 'usage': {'output_tokens': 120, 'server_tool_use': {'code_execution_requests': 1}}},
                {'type': 'message_stop'}]), headers={'content-type': 'text/event-stream'})
        if path.startswith('/v1/files/file_fake_chart'):
            if request.method == 'DELETE':
                deleted.add(path)
                return httpx.Response(200, json={'id': 'file_fake_chart', 'type': 'file_deleted'})
            if '/v1/files/file_fake_chart' in deleted:
                return httpx.Response(404, json={'error': {'type': 'not_found_error', 'message': 'File not found.'}})
            if path.endswith('/content'):
                return httpx.Response(200, content=b'\x89PNG\r\n\x1a\n' + b'0' * 64)
            return httpx.Response(200, json={'filename': 'chart.png', 'mime_type': 'image/png', 'size_bytes': 72,
                                             'downloadable': True, 'expires_at': None})
        if path.endswith('/responses'):
            follow_up = FOLLOW_UP_XAI in request.content.decode()
            code = {'type': 'code_interpreter_call', 'id': 'ci_fake', 'status': 'completed',
                    'code': 'print(statistics.median(x))' if follow_up else 'print(mean, stdev)',
                    'outputs': [{'type': 'logs', 'logs': f'{median:.2f}' if follow_up else f'{mean:.2f} {stdev:.2f}'}]}
            message = {'type': 'message', 'role': 'assistant', 'status': 'completed',
                       'content': [{'type': 'output_text', 'text': 'Xong.'}]}
            return httpx.Response(200, content=_sse([
                {'type': 'response.created'},
                {'type': 'response.output_item.done', 'item': code},
                {'type': 'response.completed', 'response': {'status': 'completed', 'output': [code, message],
                 'usage': {'input_tokens': 800, 'output_tokens': 60},
                 'server_side_tool_usage': {'SERVER_SIDE_TOOL_CODE_EXECUTION': 1}}}]),
                headers={'content-type': 'text/event-stream'})
        return httpx.Response(404, json={'error': {'message': 'không có trong phản hồi giả'}})

    return httpx.MockTransport(handler)


# ---------- Lệnh ----------

def scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, '[ẩn]')
    return text


def _xai_credential() -> tuple[str, str]:
    """Token OAuth đang lưu của web, hoặc XAI_API_KEY. Không bao giờ refresh: backend đang chạy giữ refresh token trong bộ
    nhớ, phép thử refresh hộ có thể làm token đó mất hiệu lực và Peto không trả lời được tới khi đăng nhập lại."""
    import os
    from ai.xai_auth import load_tokens
    from core import config
    bundle = load_tokens(config.XAI_TOKEN_PATH)
    if bundle is not None:
        if bundle.is_expired():
            raise SystemExit('Token xAI đã lưu đã hết hạn; phép thử không tự refresh. Gửi một tin chat bằng Peto để backend '
                             'refresh token rồi chạy lại ngay.')
        return bundle.access_token, 'oauth'
    key = (os.getenv('XAI_API_KEY') or '').strip()
    if key:
        return key, 'api_key'
    raise SystemExit('Máy này chưa đăng nhập xAI và chưa có XAI_API_KEY; không gọi gì.')


async def run(provider: str, paid: bool, transport: httpx.AsyncBaseTransport | None = None) -> tuple[dict, list[str]]:
    from ai.models import MODELS
    from core import config
    if not paid:
        transport = transport or fake_transport()
    async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT, follow_redirects=False) as client:
        if provider == 'haiku':
            key = config.ANTHROPIC_API_KEY if paid else 'sk-ant-dry-run-placeholder'
            if not key:
                raise SystemExit('Máy này chưa có ANTHROPIC_API_KEY; không gọi gì.')
            return await probe_haiku(client, key, MODELS['haiku'].slug), [key]
        token, mode = 'xai-dry-run-placeholder', 'dry_run'
        if paid:
            token, mode = _xai_credential()
        base = config.XAI_API_BASE if paid else 'https://api.x.ai/v1'
        return await probe_xai(client, base.rstrip('/'), token, config.XAI_MODEL, mode), [token]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Phép thử thực thi mã phía nhà cung cấp; mặc định chạy khô.')
    parser.add_argument('provider', choices=['haiku', 'xai'])
    parser.add_argument('--allow-paid', action='store_true', help='Gọi API thật, có tính phí.')
    parser.add_argument('--out', type=Path, help='Tệp JSON bằng chứng (mặc định .runtime/probes/ ở gốc repo).')
    args = parser.parse_args(argv)
    print(f"{'GỌI API THẬT, có tính phí' if args.allow_paid else 'CHẠY KHÔ: phản hồi giả, không gọi mạng'}: "
          f'{args.provider}. Giới hạn 2 request, {MAX_OUTPUT_TOKENS} token đầu ra mỗi request. {COST_NOTES[args.provider]}')
    evidence, secrets = asyncio.run(run(args.provider, args.allow_paid))
    evidence = {'mode': 'paid' if args.allow_paid else 'dry_run', 'time': datetime.now().astimezone().isoformat(),
                'expected': EXPECTED, 'cost_notes': COST_NOTES[args.provider], **evidence}
    text = scrub(json.dumps(evidence, ensure_ascii=False, indent=2), secrets)
    out = args.out or ROOT / '.runtime' / 'probes' / (
        f"{datetime.now():%Y%m%d-%H%M%S}-{args.provider}{'' if args.allow_paid else '-dry'}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf-8')
    print(json.dumps({'check': evidence['check'],
                      'requests': [{key: record.get(key) for key in ('http_status', 'stop_reason', 'status', 'elapsed_ms')}
                                   for record in evidence['requests']]}, ensure_ascii=False))
    print(f'Bằng chứng: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
