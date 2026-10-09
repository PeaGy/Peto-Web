"""CLI nội bộ; chạy mock mặc định, API thật luôn cần lựa chọn rõ ràng."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import logging
import os
from pathlib import Path
import sys
import tempfile
import uuid


def parser():
    cli = argparse.ArgumentParser(description='Peto Brain Benchmark v1 — dữ liệu giả, không đổi model đang chạy.')
    commands = cli.add_subparsers(dest='command', required=True)
    for name in ('list', 'plan', 'run'):
        command = commands.add_parser(name, help={'list': 'Xem bài và model.', 'plan': 'Xem kế hoạch, không gọi API.', 'run': 'Chạy bộ bài.'}[name])
        command.add_argument('--dataset', type=Path, default=Path(__file__).with_name('cases.json'))
        command.add_argument('--persona', choices=('all', 'chat', 'companion', 'roleplay'), default='all')
        command.add_argument('--group', choices=('all', 'identity', 'conversation', 'memory', 'reasoning', 'truth', 'protocol'), default='all')
        command.add_argument('--cases', nargs='+')
        command.add_argument('--models', nargs='+', default=['peto'])
        command.add_argument('--effort', default='low')
        command.add_argument('--mode', choices=('mock', 'live'), default='mock')
        command.add_argument('--allow-paid', action='store_true', help='Chấp nhận API trả phí cho đúng lần run này.')
        command.add_argument('--repeat', type=int, default=1)
        command.add_argument('--concurrency', type=int, default=1)
        command.add_argument('--timeout', type=float, default=90)
        command.add_argument('--max-calls', type=int, default=60)
        command.add_argument('--max-output-tokens', type=int, default=1024)
        command.add_argument('--max-input-chars', type=int, default=60_000)
        command.add_argument('--clock', help='Mốc ISO có múi giờ để so sánh prompt giữa các lần chạy.')
        if name == 'run':
            command.add_argument('--output', type=Path)
            command.add_argument('--rates', type=Path)
    report = commands.add_parser('report', help='Xuất lại báo cáo và nhận điểm người chấm.')
    report.add_argument('directory', type=Path)
    report.add_argument('--rates', type=Path)
    report.add_argument('--ratings', type=Path)
    compare = commands.add_parser('compare', help='Đối chiếu số đo nhiều lần chạy.')
    compare.add_argument('directories', nargs='+', type=Path)
    compare.add_argument('--output', type=Path, required=True)
    return cli


def configure(mode: str, temporary: str):
    # Chỉ thay môi trường của tiến trình CLI. Không ghi .env hoặc sửa cấu hình máy chủ.
    if mode != 'live':
        os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        for name in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'XAI_API_KEY'):
            os.environ.pop(name, None)
        os.environ['PETO_XAI_TOKEN_PATH'] = str(Path(temporary) / 'fake-xai.json')
    os.environ['PETO_AI_PROVIDER'] = 'mock' if mode != 'live' else 'xai'
    os.environ['PETO_WEB_DB'] = str(Path(temporary) / 'unused.db')
    os.environ['PETO_UPLOAD_DIR'] = str(Path(temporary) / 'unused-uploads')
    os.environ['PETO_MEMORY_GATEWAY_URL'] = ''
    os.environ['PETO_MEMORY_GATEWAY_TOKEN'] = ''
    # SDK/HTTP và provider có thể đưa nội dung lỗi vào log; CLI chỉ xuất kết quả đã chọn.
    logging.disable(logging.CRITICAL)


def execute(args) -> int:
    from .schema import EvalError, load_cases, read_json, Settings
    from .report import compare, load_rates, load_ratings, write_report
    if args.command == 'report':
        result = read_json(args.directory / 'results.json', limit=100_000_000)
        rates = load_rates(args.rates) if args.rates else result.get('rates', {})
        write_report(result, args.directory, rates, load_ratings(result, args.ratings))
        print(f'Đã xuất báo cáo: {args.directory / "report.md"}')
        return 0
    if args.command == 'compare':
        results = [read_json(directory / 'results.json', limit=100_000_000) for directory in args.directories]
        summaries = [read_json(directory / 'summary.json') if (directory / 'summary.json').exists()
                     else None for directory in args.directories]
        if any(summary is None for summary in summaries):
            from .report import summarize
            summaries = [summary or summarize(result, result.get('rates')) for summary, result in zip(summaries, results)]
        if args.output.exists():
            raise EvalError('Tệp so sánh đã tồn tại; chọn đường dẫn mới để tránh ghi đè.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(compare(results, summaries), encoding='utf-8')
        print(f'Đã xuất so sánh: {args.output}')
        return 0
    from ai.models import MODELS, supported_efforts
    all_cases = load_cases(args.dataset)
    if args.cases and set(args.cases) - {case.id for case in all_cases}:
        raise EvalError('Có mã bài không tồn tại trong dataset.')
    cases = [case for case in all_cases if (args.persona == 'all' or case.persona == args.persona)
             and (args.group == 'all' or case.group == args.group) and (not args.cases or case.id in args.cases)]
    if args.command == 'list':
        for model in MODELS.values():
            if model.web:
                print(f'{model.key}: {model.label}; effort: {", ".join(supported_efforts(model.key))}')
        for case in cases:
            print(f'{case.id}: {case.persona}/{case.group}, {len(case.turns)} lượt — {case.title}')
        return 0
    settings = Settings(args.mode, tuple(args.models), args.effort, args.repeat, args.concurrency,
                        args.timeout, args.max_calls, args.max_output_tokens, args.max_input_chars, args.allow_paid)
    # plan chỉ đọc: không đòi đồng ý trả phí và không kiểm/gọi credential.
    planned = replace(settings, allow_paid=True).validate(cases) if args.command == 'plan' else settings.validate(cases)
    print(f'Kế hoạch: {len(cases)} bài, {planned} lượt, model {", ".join(settings.models)}, effort {settings.effort}.')
    print(f'Giới hạn: {settings.max_calls} request, {settings.max_output_tokens} token đầu ra/request, '
          f'{settings.max_input_chars} ký tự đầu vào/request, {settings.timeout:g} giây/lượt, '
          f'{settings.concurrency} hội thoại đồng thời.')
    print('Tắt công cụ/tìm web, không retry SDK, không ghi nhớ nền hoặc tạo tiêu đề.')
    if args.command == 'plan':
        print('Chưa gọi API. Khi chạy LIVE, phí thuộc billing của khóa trên máy chạy lệnh; không có trần USD tuyệt đối.')
        return 0
    rates = load_rates(args.rates)
    clock = datetime.fromisoformat(args.clock) if args.clock else None
    if clock is not None and clock.tzinfo is None:
        raise EvalError('--clock cần có múi giờ, ví dụ 2026-10-09T00:00:00+00:00.')
    if settings.mode == 'live':
        from .adapter import ensure_credentials
        ensure_credentials(settings.models)
        print('LIVE: lệnh này gọi API thật và tính phí; số đo không bao gồm chi phí TTS/công cụ.')
    else:
        print('MOCK: không gọi API, không tốn tiền, kết quả không đánh giá chất lượng model.')
    directory = args.output or Path(__file__).resolve().parents[2] / 'benchmark-output' / (
        datetime.now(UTC).strftime('%Y%m%d-%H%M%S') + '-' + settings.mode + '-' + uuid.uuid4().hex[:8])
    from .runner import run, save_json
    result = asyncio.run(run(cases, settings, args.dataset, directory, clock=clock,
                            progress=lambda model, case_id, repeat: print(f'Đã chạy {model}/{case_id}, lần {repeat}.')))
    result['rates'] = rates
    save_json(directory / 'results.json', result)
    write_report(result, directory, rates)
    print(f'Kết quả: {directory / "report.md"}; phiếu chấm: {directory / "review.json"}')
    failed = any(turn['status'] != 'complete' or any(c['critical'] and not c['passed'] for c in turn['checks'])
                 for sample in result['samples'] for turn in sample['turns'])
    return 1 if settings.mode == 'live' and failed else 0


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    # Chặn trước mọi import config/.env/provider; không có flag thì không thể chạy thật.
    if args.command == 'run' and args.mode == 'live' and not args.allow_paid:
        print('Chạy thật cần --mode live và --allow-paid. Chưa gọi API nào.', file=sys.stderr)
        return 2
    try:
        # Các đường dẫn DB/upload/token giả không được dùng; không cần tạo hoặc xóa thư mục tạm.
        temporary = str(Path(tempfile.gettempdir()) / ('peto-brain-' + uuid.uuid4().hex))
        configure(getattr(args, 'mode', 'mock'), temporary)
        return execute(args)
    except KeyboardInterrupt:
        print('Đã ngắt bài thi; kết quả đã hoàn thành được giữ trong results.json.', file=sys.stderr)
        return 130
    except Exception as err:
        from .schema import EvalError
        if isinstance(err, EvalError):
            print(str(err), file=sys.stderr)
        else:
            print('Không thể chạy bộ đánh giá. Kiểm tra thư viện backend, JSON và đường dẫn đầu ra; chưa tự thử lại.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
