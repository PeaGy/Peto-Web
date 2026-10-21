"""Chỉ số Web Chat có mẫu và phạm vi rõ; không chấm nội dung hoặc tính chi phí lần hai."""
from collections import Counter
from ai.models import MODELS


def summarize(rows, percentile):
    events = [row for row in rows if row.get('kind') == 'chat_event' and row.get('surface') == 'chat']
    summary = [row for row in events if row.get('purpose') == 'summary']
    summary_calls = [row for row in rows if row.get('kind') == 'call' and row.get('surface') == 'chat'
                     and row.get('purpose') == 'summary']
    summary_times = [row['elapsed_ms'] for row in summary if row.get('elapsed_ms') is not None]
    recoveries = Counter(row.get('outcome') for row in events if row.get('purpose') == 'recovery')
    tools = [row for row in events if row.get('purpose') == 'tool']
    groups, legacy = {}, 0
    for row in rows:
        if row.get('kind') != 'turn' or row.get('surface') != 'chat':
            continue
        effort = row.get('effort') or 'unknown'
        legacy += effort == 'unknown'
        key = (row.get('model') or 'unknown', row.get('slug') or '', effort)
        group = groups.setdefault(key, {'turns': 0, 'complete': 0, 'times': [], 'firsts': []})
        group['turns'] += 1
        if row.get('outcome') == 'complete' and row.get('complete'):
            group['complete'] += 1
            if row.get('elapsed_ms') is not None:
                group['times'].append(row['elapsed_ms'])
        if row.get('first_text_ms') is not None:
            group['firsts'].append(row['first_text_ms'])
    configs = []
    for (model, slug, effort), group in sorted(groups.items()):
        info = MODELS.get(model)
        configs.append({'model': model, 'slug': slug or None, 'label': info.label if info else model, 'effort': effort,
            'turns': group['turns'], 'complete': group['complete'], 'total_samples': len(group['times']),
            'first_samples': len(group['firsts']), 'p50_ms': percentile(group['times'], .5),
            'p95_ms': percentile(group['times'], .95), 'first_p50_ms': percentile(group['firsts'], .5),
            'first_p95_ms': percentile(group['firsts'], .95)})
    states = Counter(row.get('outcome') for row in summary)
    return {'configs': configs, 'legacy_turns': legacy,
        'summary': {'attempts': len(summary), 'complete': states['complete'], 'source_changed': states['source_changed'],
            'errors': sum(states[key] for key in ('error', 'timeout', 'overflow')), 'cancelled': states['cancelled'],
            'sdk_calls': len(summary_calls), 'usage_calls': sum(row.get('input_tokens') is not None and
                row.get('output_tokens') is not None for row in summary_calls), 'latency_samples': len(summary_times),
            'p50_ms': percentile(summary_times, .5), 'p95_ms': percentile(summary_times, .95)},
        'tools': {'results': len(tools), 'errors': sum(row.get('outcome') == 'error' for row in tools),
                  'web_errors': sum(row.get('purpose') == 'web' and row.get('outcome') == 'error' for row in events)},
        'context_overflows': sum(row.get('purpose') == 'context' and row.get('outcome') == 'overflow' for row in events),
        'recovery': {'checks': sum(recoveries.values()), **{key: recoveries[key] for key in ('complete', 'partial', 'pending', 'missing')}}}
