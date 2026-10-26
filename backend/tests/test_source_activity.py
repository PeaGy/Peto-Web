"""Display provenance is bounded independently from the model's compatibility sources."""
import json

import pytest

from shared.source_activity import SourceActivity, display_sources, normalize_web, stop_web, MAX_WEB_BYTES
from shared.web_search import normalize_sources


def source(index=0, **extra):
    return {'url': f'https://example.com/{index}', 'title': f'Source {index}', **extra}


def call(ident='xai:0:call-1', **extra):
    return {'id': ident, 'kind': 'search', 'operation': 'search', 'queries': ['monitor'],
            'state': 'done', 'source_urls': [source()['url']], **extra}


@pytest.mark.parametrize('value', [None, [], {'version': 2}, {'version': True}, {'version': 1}, {'version': 1, 'calls': [None, {'id': [], 'kind': {}, 'state': []}]}])
def test_unsupported_or_invalid_web_data_has_no_invented_activity(value):
    assert normalize_web(value) is None


def test_duplicate_updates_late_metadata_and_shared_sources_keep_proven_membership():
    activity = SourceActivity()
    assert activity.update({'call': call(state='live', queries=[], source_urls=[])})
    result = activity.update({'sources': [source()], 'call': call(queries=['monitor', 'IPS'])})
    assert result['calls'][0]['queries'] == ['monitor', 'IPS']
    assert activity.update({'sources': [source()], 'call': call(queries=['monitor', 'IPS'])}) is None
    activity.update({'call': call(state='live', queries=[], source_urls=[])})
    assert activity.snapshot()['calls'][0]['state'] == 'done'
    activity.update({'call': call('xai:1:call-1')})
    assert len(activity.snapshot()['calls']) == 2
    assert activity.snapshot()['calls'][0]['source_urls'] == activity.snapshot()['calls'][1]['source_urls']
    assert len(activity.snapshot()['sources']) == 1


def test_failed_update_does_not_introduce_sources_but_keeps_prior_successful_refs():
    activity = SourceActivity()
    activity.update({'sources': [source()], 'call': call(state='live')})
    failed = activity.update({'sources': [source(1)], 'call': call(state='failed', source_urls=[source(1)['url']])})
    assert failed['calls'][0]['state'] == 'failed'
    assert failed['calls'][0]['source_urls'] == [source()['url']]
    assert failed['sources'] == [source()]
    assert normalize_web(failed) == failed
    assert activity.update({'call': call(state='live')}) is None


def test_unknown_sources_and_bad_urls_cannot_be_attached_to_a_call():
    activity = SourceActivity()
    activity.update({'sources': [source(), source(1, url='javascript:alert(1)'), source(2, url='https://u:p@example.org/private')],
                     'call': call(source_urls=[source()['url'], source(9)['url'], 'javascript:alert(1)'])})
    result = activity.snapshot()
    assert result['sources'] == [source()]
    assert result['calls'][0]['source_urls'] == [source()['url']]


def test_plaintext_snippets_are_optional_and_private_native_payload_is_never_exposed():
    rows = display_sources([source(encrypted_content='SECRET', encrypted_index='SECRET'),
                            source(1, description='  public\n excerpt '), source(2, snippet='a' * 600)])
    assert 'snippet' not in rows[0]
    assert rows[1]['snippet'] == 'public excerpt'
    assert len(rows[2]['snippet']) == 320
    assert 'SECRET' not in json.dumps(rows)


def test_invalid_unicode_cannot_break_utf8_budget_or_turn_into_a_different_url():
    activity = SourceActivity()
    result = activity.update({'sources': [source(title='Bad\ud800 title', snippet='Bad\udfff excerpt'),
                                          source(1, url='https://example.org/\ud800')],
                              'call': call(queries=['Bad\ud800 query'])})
    assert len(result['sources']) == 1
    assert '\ufffd' in result['sources'][0]['title'] and '\ufffd' in result['calls'][0]['queries'][0]
    assert json.dumps(result, ensure_ascii=False).encode('utf8')


def test_display_registry_keeps_105_sources_without_increasing_prompt_limit_and_unions_aliases():
    rows = [source(index) for index in range(105)]
    activity = SourceActivity()
    activity.update({'sources': rows, 'call': call(source_urls=[row['url'] for row in rows])})
    assert len(activity.snapshot()['sources']) == 105
    assert len(activity.snapshot()['calls'][0]['source_urls']) == 105
    assert len(normalize_sources(rows)) == 30
    activity.update({'sources': [source(citation_ids=['web:21'], kind='citation')]})
    activity.update({'sources': [source(citation_ids=['web:26'])]})
    assert activity.snapshot()['sources'][0]['citation_ids'] == ['web:21', 'web:26']


def test_source_and_call_caps_favor_citations_and_mark_partial_catalogue():
    activity = SourceActivity()
    rows = [source(index) for index in range(205)]
    activity.update({'sources': rows})
    activity.update({'sources': [source(204, kind='citation')]})
    for index in range(45):
        activity.update({'call': call(f'xai:0:call-{index}', queries=['x' * 900] * 20)})
    result = activity.snapshot()
    assert len(result['sources']) == 200 and len(result['calls']) == 40
    assert any(item['url'] == source(204)['url'] and item['kind'] == 'citation' for item in result['sources'])
    assert result['truncated'] is True
    assert len(result['calls'][0]['queries'][0]) == 500


def test_global_byte_budget_bounds_long_urls_repeated_across_calls():
    rows = [source(index, url=f'https://example.com/{index}/' + 'z' * 1900, snippet='文' * 320) for index in range(200)]
    activity = SourceActivity()
    activity.update({'sources': rows})
    for index in range(40):
        activity.update({'call': call(f'xai:0:{index}', source_urls=[row['url'] for row in rows], queries=['文' * 500] * 8)})
    result = activity.snapshot()
    assert result['truncated'] is True
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= MAX_WEB_BYTES
    known = {item['url'] for item in result['sources']}
    assert all(set(item['source_urls']) <= known for item in result['calls'])


def test_close_and_restart_only_finalize_live_calls_and_snapshots_are_isolated():
    activity = SourceActivity()
    activity.update({'sources': [source()], 'call': call()})
    activity.update({'call': call('xai:0:live', state='live')})
    snapshot = activity.snapshot()
    snapshot['sources'].clear()
    assert activity.snapshot()['sources']
    result = stop_web(activity.snapshot())
    assert [item['state'] for item in result['calls']] == ['done', 'stopped']
    assert activity.close(True)['calls'][1]['state'] == 'done'


@pytest.mark.parametrize('bad', [None, [], {'call': []}, {'call': {'id': 'bad', 'kind': {}, 'state': []}},
                              {'call': {'id': 'bad', 'kind': 'search', 'state': 'live', 'operation': {}}},
                              {'call': {'id': 'x' * 129, 'kind': 'search', 'state': 'done'}}, {'sources': {}}])
def test_malformed_incremental_data_never_crashes(bad):
    activity = SourceActivity()
    activity.update(bad)
    normalize_web({'version': 1, 'sources': [], 'calls': [bad]})
