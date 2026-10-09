"""Chạy các hội thoại giả, giữ từng lần chạy và không ghi database."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
import uuid

from .adapter import (BudgetExceeded, CallBudget, Capture, close_provider, ensure_credentials, input_chars,
                      make_provider, prepare_prompts, user_message, VisibleStream)
from .checks import evaluate
from .schema import Case, EvalError, Settings


def manifest(dataset: Path, clock: datetime) -> dict:
    root = Path(__file__).resolve().parents[2]
    def git(*args):
        try:
            result = subprocess.run(['git', *args], cwd=root, capture_output=True, timeout=10)
            return result.stdout.decode('utf-8', errors='replace').strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    status = git('status', '--porcelain')
    versions = {}
    for package in ('openai', 'anthropic', 'python-dotenv'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    sources = [path for folder in ('backend/prompts', 'backend/evals', 'backend/ai')
               for path in (root / folder).glob('*.py')]
    sources += [root / path for path in ('backend/features/chat/prompt_context.py', 'backend/features/chat/history.py',
                                        'backend/features/companion/private_notes.py', 'backend/features/companion/emotion_tags.py',
                                        'backend/shared/time_tools.py', 'backend/shared/web_search.py')]
    return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(status) if status is not None else None,
            'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(), 'clock': clock.isoformat(),
            'code_sha256': {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(sources)},
            'sdk_versions': versions}


def save_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def redact(value):
    """Không để credential thật xuất hiện trong kết quả, kể cả lỗi từ SDK."""
    keys = [os.getenv(name) for name in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'XAI_API_KEY', 'PETO_MEMORY_GATEWAY_TOKEN')]
    if isinstance(value, str):
        for key in keys:
            if key and len(key) >= 8:
                value = value.replace(key, '[đã ẩn credential]')
        return value
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


async def run(cases: list[Case], settings: Settings, dataset: Path, output: Path, *,
              clock: datetime | None = None, factory=make_provider, progress=None) -> dict:
    from ai.base import ChatMessage, ProviderError, StreamChunk
    planned = settings.validate(cases)
    if settings.mode == 'live':
        ensure_credentials(settings.models)
    clock = clock or datetime.now(UTC).replace(microsecond=0)
    if clock.tzinfo is None:
        raise EvalError('Mốc đồng hồ cần có múi giờ.')
    prompts = await prepare_prompts(cases, settings.models, clock)
    # Kiểm tra ngay phần đầu vào đã biết; câu trả lời các lượt trước được kiểm lại lúc chạy.
    for model in settings.models:
        for case in cases:
            for index, turn in enumerate(case.turns):
                if input_chars(prompts[model, case.id, index]['text'], [user_message(turn)]) > settings.max_input_chars:
                    raise EvalError('Một prompt/tệp giả vượt giới hạn đầu vào; chưa gọi API nào.')
    output.mkdir(parents=True, exist_ok=False)
    result = {'version': 1, 'run_id': uuid.uuid4().hex, 'started_at': datetime.now(UTC).isoformat(),
              'mode': settings.mode, 'settings': asdict(settings), 'manifest': manifest(dataset, clock),
              'planned_turns': planned, 'request_count': 0, 'finished': False,
              'scope': 'Prompt và hội thoại có ngữ cảnh giả; không chạy API Web, ghi nhớ nền, công cụ, TTS hoặc Agent.',
              'prompts': [{'model': model, 'case_id': case_id, 'turn': index + 1, **body}
                          for (model, case_id, index), body in prompts.items()], 'samples': []}
    budget, semaphore = CallBudget(settings), asyncio.Semaphore(settings.concurrency)
    save_json(output / 'results.json', redact(result))

    async def one(model: str, case: Case, repeat: int):
        async with semaphore:
            sample = {'model': model, 'case_id': case.id, 'title': case.title, 'persona': case.persona,
                      'group': case.group, 'context': case.context, 'repeat': repeat, 'turns': []}
            history = []
            provider, capture = None, Capture('')
            try:
                provider, capture = factory(model, settings, budget)
            except Exception:
                sample['setup_failed'] = True
            try:
                for index, turn in enumerate(case.turns):
                    prompt = prompts[model, case.id, index]
                    history.append(user_message(turn))
                    row = {'turn': index + 1, 'user': turn['user'], 'attachments': turn.get('attachments', []),
                           'expectation': turn['expectation'], 'rubric': turn['rubric'], 'prompt_sha256': prompt['sha256'],
                           'input_chars': input_chars(prompt['text'], history), 'status': 'complete',
                           'raw_response': '', 'visible_response': '', 'first_text_ms': None, 'first_visible_ms': None,
                           'elapsed_ms': None, 'calls': [], 'checks': []}
                    started, call_start = perf_counter(), len(capture.records)
                    view = VisibleStream(case.persona)
                    pieces, visible, output_chars = [], [], 0
                    iterator = None
                    try:
                        if provider is None:
                            raise ProviderError('Không khởi tạo được provider cho bài này.')
                        if row['input_chars'] > settings.max_input_chars:
                            raise BudgetExceeded('Lịch sử vượt giới hạn đầu vào.')
                        if settings.mode == 'mock':
                            budget.claim({'instructions': prompt['text'], 'input': [asdict(message) for message in history],
                                          'max_output_tokens': settings.max_output_tokens})
                        from shared.web_search import spoken_reply
                        token = spoken_reply.set(case.persona == 'companion')
                        try:
                            async with asyncio.timeout(settings.timeout):
                                iterator = provider.stream(system_prompt=prompt['text'], messages=history, effort=settings.effort,
                                                           timezone='Asia/Ho_Chi_Minh', web_search='off', tools_enabled=False)
                                async for chunk in iterator:
                                    piece = chunk if isinstance(chunk, str) else chunk.text if isinstance(chunk, StreamChunk) and chunk.kind == 'text' else ''
                                    if not piece:
                                        continue
                                    elapsed = round((perf_counter() - started) * 1000, 3)
                                    if row['first_text_ms'] is None:
                                        row['first_text_ms'] = elapsed
                                    pieces.append(piece)
                                    output_chars += len(piece)
                                    public = view.feed(piece)
                                    visible.append(public)
                                    if public.strip() and row['first_visible_ms'] is None:
                                        row['first_visible_ms'] = elapsed
                                    if output_chars > 32_768:
                                        row['status'] = 'output_limit'
                                        break
                        finally:
                            if iterator is not None:
                                await iterator.aclose()
                            spoken_reply.reset(token)
                        tail = view.flush()
                        visible.append(tail)
                        if tail.strip() and row['first_visible_ms'] is None:
                            row['first_visible_ms'] = round((perf_counter() - started) * 1000, 3)
                    except TimeoutError:
                        row['status'] = 'timeout'
                    except BudgetExceeded:
                        row['status'] = 'budget_exceeded'
                    except ProviderError:
                        row['status'] = 'provider_error'
                    except Exception:
                        # Không ghi str(exception) hoặc traceback: SDK có thể kèm credential/body.
                        row['status'] = 'internal_error'
                    row['elapsed_ms'] = round((perf_counter() - started) * 1000, 3)
                    row['raw_response'] = ''.join(pieces)[:32_768]
                    row['visible_response'] = ''.join(visible)[:32_768]
                    row['calls'] = capture.records[call_start:]
                    if row['status'] == 'complete' and not row['visible_response'].strip():
                        row['status'] = 'empty'
                    if row['status'] == 'complete':
                        row['checks'] = evaluate(turn.get('checks', []), row['raw_response'], row['visible_response'])
                    sample['turns'].append(row)
                    if row['status'] != 'complete':
                        for skipped_index, skipped in enumerate(case.turns[index + 1:], index + 2):
                            sample['turns'].append({'turn': skipped_index, 'user': skipped['user'], 'rubric': skipped['rubric'],
                                                    'expectation': skipped['expectation'], 'status': 'skipped_dependency',
                                                    'raw_response': '', 'visible_response': '', 'calls': [], 'checks': [],
                                                    'first_text_ms': None, 'first_visible_ms': None, 'elapsed_ms': None})
                        break
                    history.append(ChatMessage('assistant', row['raw_response']))
            finally:
                try:
                    await close_provider(provider)
                except Exception:
                    sample['cleanup_failed'] = True
                # Khi ngắt, giữ cả các lượt đã xong trong hội thoại đang chạy.
                result['samples'].append(sample)
                result['request_count'] = budget.used
                save_json(output / 'results.json', redact(result))
            if progress:
                progress(model, case.id, repeat)

    tasks = [asyncio.create_task(one(model, case, repeat)) for model in settings.models for case in cases
             for repeat in range(1, settings.repeat + 1)]
    try:
        await asyncio.gather(*tasks)
        result['finished'] = True
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        result['request_count'] = budget.used
        result['finished_at'] = datetime.now(UTC).isoformat()
        result['samples'].sort(key=lambda s: (s['model'], s['case_id'], s['repeat']))
        result = redact(result)
        save_json(output / 'results.json', result)
    return result
