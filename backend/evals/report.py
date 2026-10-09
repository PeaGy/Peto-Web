"""Báo cáo số đo và phiếu chấm ẩn tên model; không tự gán điểm chất lượng."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math
from pathlib import Path
import random
import re

from .runner import save_json
from .schema import EvalError, read_json, RUBRICS


def load_rates(path: Path | None) -> dict:
    rates = read_json(path) if path else {}
    if not isinstance(rates, dict):
        raise EvalError('Bảng giá phải là đối tượng JSON theo slug model.')
    for slug, rate in rates.items():
        if not isinstance(slug, str) or not isinstance(rate, dict) or set(rate) - {'input', 'output', 'cached_input', 'cache_write'}:
            raise EvalError('Bảng giá chỉ nhận input, output, cached_input, cache_write.')
        if not {'input', 'output', 'cached_input'} <= set(rate):
            raise EvalError('Mỗi giá cần input, output và cached_input, USD trên một triệu token.')
        if any(type(value) not in {int, float} or not math.isfinite(value) or value < 0 for value in rate.values()):
            raise EvalError('Đơn giá phải hữu hạn, không âm.')
    return rates


def call_cost(call: dict, rates: dict) -> float | None:
    usage = call.get('usage')
    rate = rates.get(call.get('actual_model')) or rates.get(call.get('requested_model'))
    if not usage or not rate:
        return None
    fields = (('uncached_input_tokens', 'input'), ('output_tokens', 'output'),
              ('cache_read_tokens', 'cached_input'), ('cache_write_tokens', 'cache_write'))
    cost = 0
    for field, price in fields:
        count = usage.get(field)
        if count is None or (count and price not in rate):
            return None
        cost += count * rate.get(price, 0) / 1_000_000
    return cost


def sample_id(result: dict, sample: dict, turn: dict) -> str:
    key = f"{result['run_id']}|{sample['model']}|{sample['case_id']}|{sample['repeat']}|{turn['turn']}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def review_template(result: dict) -> dict:
    rows = []
    for sample in result['samples']:
        history = []
        private_history = []
        for turn in sample['turns']:
            if turn['status'] == 'complete':
                rows.append({'sample_id': sample_id(result, sample, turn), 'case_id': sample['case_id'],
                             'persona': sample['persona'], 'context': sample.get('context', {}),
                             'history': list(history), 'user': turn['user'],
                             'attachments': turn.get('attachments', []), 'response': turn['visible_response'],
                             'reference_private_notes': list(private_history),
                             'expectation': turn['expectation'], 'scores': {key: None for key in turn['rubric']}, 'comment': ''})
            if sample['persona'] == 'companion':
                private_history.append({'turn': turn['turn'], 'notes': re.findall(
                    r'<private>(.*?)(?:</private>|$)', turn['raw_response'], re.IGNORECASE | re.DOTALL)})
            history += [{'role': 'user', 'content': turn['user']},
                        {'role': 'assistant', 'content': turn['visible_response']}]
    random.Random(result['run_id']).shuffle(rows)
    return {'run_id': result['run_id'], 'mode': result['mode'], 'rubric': RUBRICS,
            'scale': {'1': 'Không đạt mục tiêu hoặc lỗi đáng kể.', '2': 'Đạt một phần, còn thiếu hoặc lệch rõ.',
                      '3': 'Dùng được, còn điểm cần sửa.', '4': 'Tốt, chỉ còn thiếu sót nhỏ.', '5': 'Đáp ứng đầy đủ và phù hợp tình huống.'},
            'instructions': 'Chỉ chấm nội dung theo persona và tiêu chí; để null nếu chưa chấm. reference_private_notes là ghi chú giả của lượt trước để đối chiếu tính liên tục, không phải lời hiển thị. Mock không đo chất lượng model.',
            'samples': rows}


def load_ratings(result: dict, path: Path | None) -> dict:
    if path is None:
        return {}
    raw = read_json(path, limit=100_000_000)
    if not isinstance(raw, dict) or raw.get('run_id') != result['run_id'] or not isinstance(raw.get('samples'), list):
        raise EvalError('Phiếu chấm không thuộc lần chạy này.')
    expected = {row['sample_id']: set(row['scores']) for row in review_template(result)['samples']}
    grades = {}
    for row in raw['samples']:
        key = row.get('sample_id') if isinstance(row, dict) else None
        scores = row.get('scores') if isinstance(row, dict) else None
        if key not in expected or key in grades or not isinstance(scores, dict) or set(scores) != expected[key]:
            raise EvalError('Mã mẫu/tiêu chí bị trùng, sai hoặc thiếu trong phiếu chấm.')
        if any(value is not None and (type(value) is not int or not 1 <= value <= 5) for value in scores.values()):
            raise EvalError('Điểm thủ công chỉ nhận số nguyên 1–5 hoặc null.')
        grades[key] = scores
    return grades


def summarize(result: dict, rates: dict | None = None, ratings: dict | None = None) -> dict:
    from ops.report import distribution
    rates, ratings = rates or {}, ratings or {}
    groups = {}
    for sample in result['samples']:
        key = sample['model'], sample['persona'], sample['group']
        group = groups.setdefault(key, {'model': key[0], 'persona': key[1], 'group': key[2], 'turns': 0,
                                       'outcomes': defaultdict(int), 'check_passed': 0, 'check_total': 0,
                                       'critical_failed_turns': 0, 'latency': [], 'first_visible': [], 'calls': [],
                                       'quality': defaultdict(list), 'quality_pending': 0})
        for turn in sample['turns']:
            group['turns'] += 1
            group['outcomes'][turn['status']] += 1
            # Không gộp timeout hoặc lượt bỏ qua vào thời gian phản hồi thành công.
            if turn['status'] == 'complete':
                group['latency'].append(turn['elapsed_ms'])
                if turn['first_visible_ms'] is not None:
                    group['first_visible'].append(turn['first_visible_ms'])
            group['calls'].extend(turn['calls'])
            group['check_total'] += len(turn['checks'])
            group['check_passed'] += sum(check['passed'] for check in turn['checks'])
            group['critical_failed_turns'] += any(not c['passed'] and c['critical'] for c in turn['checks'])
            if result['mode'] == 'live' and turn['status'] == 'complete':
                scores = ratings.get(sample_id(result, sample, turn), {})
                for criterion in turn['rubric']:
                    value = scores.get(criterion)
                    if value is None:
                        group['quality_pending'] += 1
                    else:
                        group['quality'][criterion].append(value)
    rows = []
    for key in sorted(groups):
        group = groups[key]
        calls = group.pop('calls')
        costs = [call_cost(call, rates) for call in calls]
        usage = [call['usage'] for call in calls if call.get('usage') is not None]
        group['request_count'] = len(calls)
        group['usage_reported_calls'] = len(usage)
        for field in ('input_tokens', 'output_tokens', 'uncached_input_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens'):
            group[field] = sum(u[field] for u in usage) if calls and len(usage) == len(calls) and all(u.get(field) is not None for u in usage) else None
        attempted = group['turns'] - group['outcomes'].get('skipped_dependency', 0)
        group['attempted_turns'] = attempted
        group['error_rate'] = (attempted - group['outcomes'].get('complete', 0)) / attempted if attempted else None
        group['timeout_rate'] = group['outcomes'].get('timeout', 0) / attempted if attempted else None
        group['estimated_usd'] = sum(costs) if costs and all(cost is not None for cost in costs) else None
        group['priced_calls'] = sum(cost is not None for cost in costs)
        group['latency'] = distribution(group['latency'])
        group['first_visible'] = distribution(group['first_visible'])
        group['outcomes'] = dict(group['outcomes'])
        group['quality'] = {name: {'mean': round(sum(values) / len(values), 2), 'samples': len(values)}
                            for name, values in group['quality'].items()}
        rows.append(group)
    return {'run_id': result['run_id'], 'mode': result['mode'], 'finished': result['finished'], 'groups': rows}


def markdown(result: dict, summary: dict) -> str:
    def shown(value):
        return 'chưa có dữ liệu' if value is None else str(round(value, 6) if isinstance(value, float) else value)
    lines = ['# Peto Brain Benchmark v1', '',
             '**MOCK — chỉ kiểm tra công cụ, không dùng để xếp hạng model.**' if result['mode'] == 'mock' else '**LIVE — phản hồi API thật, chất lượng cần người chấm.**', '',
             f"Lần chạy: `{result['run_id']}`. Hoàn tất: {result['finished']}.",
             f"Commit: `{result['manifest']['commit']}`; mã chưa commit: {result['manifest']['dirty']}.",
             f"Dataset: `{result['manifest']['dataset_sha256']}`.", '', result['scope'], '',
             '| Model / persona / nhóm | Hoàn tất / lượt | Phép kiểm tra đạt | Lượt lỗi nghiêm trọng | Chữ hiện đầu p50 / p95 (ms) | Tổng p50 / p95 (ms) | USD ước tính |',
             '|---|---:|---:|---:|---|---|---|']
    for row in summary['groups']:
        first, total = row['first_visible'], row['latency']
        lines.append(f"| {row['model']} / {row['persona']} / {row['group']} | {row['outcomes'].get('complete', 0)}/{row['turns']} | {row['check_passed']}/{row['check_total']} | {row['critical_failed_turns']} | {shown(first['p50_ms'])} / {shown(first['p95_ms'])} | {shown(total['p50_ms'])} / {shown(total['p95_ms'])} | {shown(row['estimated_usd'])} |")
    lines += ['', '## Usage và lỗi lượt', '',
              '| Model / persona / nhóm | Usage / request SDK | Input / output token | Cache đọc / ghi token | Lỗi / timeout |',
              '|---|---:|---|---|---|']
    for row in summary['groups']:
        errors = 'chưa có dữ liệu' if row['error_rate'] is None else f"{row['error_rate']:.1%} / {row['timeout_rate']:.1%}"
        lines.append(f"| {row['model']} / {row['persona']} / {row['group']} | {row['usage_reported_calls']}/{row['request_count']} | {shown(row['input_tokens'])} / {shown(row['output_tokens'])} | {shown(row['cache_read_tokens'])} / {shown(row['cache_write_tokens'])} | {errors} |")
    lines += ['', '## Chất lượng do người chấm', '',
              'Mock không có điểm chất lượng. Với LIVE, điền review.json rồi xuất lại báo cáo. Điểm mỗi tiêu chí 1–5, không quy thành một điểm “bộ não” tổng.']
    for row in summary['groups']:
        if row['quality']:
            lines += ['', f"- {row['model']} / {row['persona']} / {row['group']}: " + '; '.join(
                f"{name}: {grade['mean']}/5 ({grade['samples']} mẫu)" for name, grade in sorted(row['quality'].items()))
                + f"; còn {row['quality_pending']} tiêu chí chưa chấm."]
    lines += ['', '## Lỗi và giới hạn', '']
    for sample in result['samples']:
        if sample.get('setup_failed') or sample.get('cleanup_failed'):
            lines.append(f"- {sample['model']} / {sample['case_id']}: lỗi khởi tạo hoặc đóng provider; xem cờ trong results.json.")
        for turn in sample['turns']:
            failures = [check['kind'] for check in turn['checks'] if not check['passed']]
            if turn['status'] != 'complete' or failures:
                lines.append(f"- {sample['model']} / {sample['case_id']} / lần {sample['repeat']} / lượt {turn['turn']}: {turn['status']}; phép không đạt: {', '.join(failures) or 'không chấm' }.")
    lines += ['', '- Thời gian mock không đại diện độ trễ API. Chỉ thời gian các lượt hoàn tất vào bảng p50/p95; số mẫu nằm trong summary.json.',
              '- Tỷ lệ lỗi/timeout tính các lượt đã thử, bỏ lượt skipped_dependency. Đây là lỗi chạy; lỗi nội dung được kiểm tra/chấm riêng.',
              '- Token/chi phí thiếu dữ liệu là chưa biết, không phải 0. USD cần đơn giá tự cấu hình; không phải hóa đơn.',
              '- Giới hạn request tính cả request tiếp tục của Claude; SDK không tự retry. Giới hạn token áp dụng mỗi request, gồm suy nghĩ nếu nhà cung cấp tính vào ngân sách.',
              '- Không có hạn mức USD tuyệt đối: số request/token và ký tự đầu vào được chặn; đơn giá và cách tính token tùy nhà cung cấp.',
              '- Trí nhớ được cấp bằng fixture. Chưa đo rút/tóm tắt/lưu trí nhớ nền, quyền tài khoản, mạng Web, chạy code, TTS hoặc giao diện.',
              '- Regex kiểm tra dấu hiệu hẹp; đạt regex không chứng minh câu trả lời hoàn toàn đúng. Cần đọc chất lượng và lỗi nghiêm trọng riêng.',
              '- Model/effort/prompt đi thành một cấu hình. Cùng tên effort giữa các hãng không chứng minh cùng mức tính toán.',
              '- Kết quả chỉ áp dụng bộ bài này; chạy lặp, kiểm tra tình huống mới và đánh giá thủ công trước khi đổi cấu hình thật.']
    return '\n'.join(lines) + '\n'


def write_report(result: dict, output: Path, rates: dict | None = None, ratings: dict | None = None):
    summary = summarize(result, rates, ratings)
    save_json(output / 'summary.json', summary)
    (output / 'report.md').write_text(markdown(result, summary), encoding='utf-8')
    # Giữ phiếu người dùng đã chấm; không ghi đè khi xuất lại báo cáo.
    if not (output / 'review.json').exists():
        save_json(output / 'review.json', review_template(result))
    return summary


def compare(results: list[dict], summaries: list[dict] | None = None) -> str:
    summaries = summaries or [summarize(result, result.get('rates')) for result in results]
    if len(summaries) != len(results) or any(summary['run_id'] != result['run_id'] for summary, result in zip(summaries, results)):
        raise EvalError('Báo cáo so sánh không khớp các lần chạy.')
    lines = ['# So sánh các lần Peto Brain Benchmark', '',
             'Đối chiếu từng persona/nhóm. Không xếp hạng chung khi khác dataset, prompt, chế độ hoặc giới hạn đầu ra.', '',
             '| Lần chạy | Chế độ | Effort / token tối đa | Dataset | Model / persona / nhóm | Hoàn tất | Lỗi nghiêm trọng | Chữ đầu p50 (ms) | USD ước tính | Điểm thủ công |',
             '|---|---|---|---|---|---:|---:|---:|---:|---|']
    for result, summary in zip(results, summaries):
        for row in summary['groups']:
            quality = '; '.join(f"{key}: {value['mean']}/5 ({value['samples']})" for key, value in sorted(row['quality'].items())) or 'chưa chấm'
            cost = row['estimated_usd'] if row['estimated_usd'] is not None else 'chưa có dữ liệu'
            first = row['first_visible']['p50_ms']
            lines.append(f"| {result['run_id'][:8]} | {result['mode']} | {result['settings']['effort']} / {result['settings']['max_output_tokens']} | {result['manifest']['dataset_sha256'][:12]} | {row['model']} / {row['persona']} / {row['group']} | {row['outcomes'].get('complete', 0)}/{row['turns']} | {row['critical_failed_turns']} | {first if first is not None else 'chưa có dữ liệu'} | {cost} | {quality} |")
    return '\n'.join(lines) + '\n'
