"""Bounded, display-only provenance for Web Chat's sources panel.

This catalogue is separate from the 30-source prompt/citation compatibility list.
Only producer-proven call IDs and memberships are retained; no query is inferred.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

from shared.web_search import normalize_sources

MAX_DISPLAY_SOURCES = 200
MAX_WEB_CALLS = 40
MAX_WEB_BYTES = 256 * 1024
MAX_CALL_ID = 128
MAX_QUERIES = 8
MAX_QUERY_CHARS = 500
MAX_SNIPPET_CHARS = 320
MAX_CALL_URLS = 200
MAX_INPUT_SOURCES = 1000
_CALL_ID = re.compile(r'[A-Za-z0-9_.:-]{1,128}')
_OPERATIONS = {'search', 'fetch', 'open_page', 'find_in_page'}
_STATES = {'live', 'done', 'failed', 'stopped'}


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ''
    # A malformed JSON escape must not make UTF-8 budget accounting/history rendering crash.
    return re.sub(r'[\ud800-\udfff]', '\ufffd', ' '.join(value.split())[:limit])


def display_sources(value: object) -> list[dict]:
    """Sanitize individual records without applying the prompt's global 30-source cap."""
    if not isinstance(value, (list, tuple)):
        return []
    found: dict[str, dict] = {}
    for raw in value[:MAX_INPUT_SOURCES]:
        normalized = normalize_sources([raw])
        if not normalized:
            continue
        source = normalized[0]
        if any(0xd800 <= ord(char) <= 0xdfff for char in source['url']):
            continue
        source['title'] = _text(source['title'], 200)
        # Only explicit public plaintext excerpts, never encrypted/native replay bodies.
        snippet = next((_text(raw.get(key), MAX_SNIPPET_CHARS) for key in ('snippet', 'description', 'cited_text')
                        if _text(raw.get(key), MAX_SNIPPET_CHARS)), '')
        old = found.get(source['url'])
        if old:
            source = normalize_sources([old, source])[0]
            snippet = snippet or old.get('snippet', '')
        if snippet:
            source['snippet'] = snippet
        found[source['url']] = source
    return list(found.values())


def _safe_url(value: object) -> str | None:
    if isinstance(value, str) and any(0xd800 <= ord(char) <= 0xdfff for char in value):
        return None
    sources = normalize_sources([{'url': value}])
    return sources[0]['url'] if sources else None


class SourceActivity:
    def __init__(self):
        self._sources: dict[str, dict] = {}
        self._calls: dict[str, dict] = {}
        self._truncated = False

    def _payload(self) -> dict | None:
        if not self._sources and not self._calls and not self._truncated:
            return None
        result = {'version': 1, 'sources': list(self._sources.values()), 'calls': list(self._calls.values())}
        if self._truncated:
            result['truncated'] = True
        return result

    def snapshot(self) -> dict | None:
        return deepcopy(self._payload())

    def _prune(self):
        # Favor explicitly cited sources without reordering the stable first-seen display list.
        ordered = list(self._sources.values())
        retained = sorted(ordered, key=lambda source: source.get('kind') != 'citation')[:MAX_DISPLAY_SOURCES]
        keep = {source['url'] for source in retained}
        if len(ordered) > len(keep):
            self._truncated = True
        self._sources = {url: source for url, source in self._sources.items() if url in keep}

        def remove_unknown_refs():
            for call in self._calls.values():
                call['source_urls'] = [url for url in call['source_urls'] if url in self._sources]

        remove_unknown_refs()
        # At most 200 records are removed, even for pathological URL lengths/many memberships.
        while len(json.dumps(self._payload(), ensure_ascii=False).encode('utf-8')) > MAX_WEB_BYTES:
            self._truncated = True
            if not self._sources:
                # Bounded calls/queries/targets alone fit this budget. Defensive fallback for future fields.
                if not self._calls:
                    break
                self._calls.pop(next(reversed(self._calls)))
            else:
                victim = next((url for url in reversed(self._sources) if self._sources[url].get('kind') != 'citation'),
                              next(reversed(self._sources)))
                del self._sources[victim]
                remove_unknown_refs()

    def _apply(self, info: object):
        if not isinstance(info, dict):
            return
        raw_call = info.get('call')
        failed = isinstance(raw_call, dict) and isinstance(raw_call.get('state'), str) and raw_call['state'] in {'failed', 'stopped'}
        raw_sources = info.get('sources')
        if isinstance(raw_sources, (list, tuple)) and len(raw_sources) > MAX_INPUT_SOURCES:
            self._truncated = True
        if not failed:
            for source in display_sources(raw_sources):
                old = self._sources.get(source['url'])
                self._sources[source['url']] = display_sources([old, source] if old else [source])[0]
        if isinstance(raw_call, dict):
            ident = raw_call.get('id')
            kind, state = raw_call.get('kind'), raw_call.get('state')
            if (isinstance(ident, str) and _CALL_ID.fullmatch(ident) and isinstance(kind, str) and kind in {'search', 'page'}
                    and isinstance(state, str) and state in _STATES):
                old = self._calls.get(ident)
                if old and old['kind'] != kind:
                    return  # Conflicting identity cannot move proven membership to another operation kind.
                if old or len(self._calls) < MAX_WEB_CALLS:
                    call = deepcopy(old) if old else {'id': ident, 'kind': kind, 'queries': [], 'state': state, 'source_urls': []}
                    # Repeated native completion/final snapshots must not reopen a terminal call.
                    if not old or old['state'] == 'live':
                        call['state'] = state
                    operation = raw_call.get('operation')
                    if isinstance(operation, str) and operation in _OPERATIONS and (kind == 'search') == (operation == 'search'):
                        call['operation'] = operation
                    query_values = raw_call.get('queries')
                    if isinstance(query_values, list):
                        queries = list(dict.fromkeys(value for query in query_values[:MAX_QUERIES]
                                                     if (value := _text(query, MAX_QUERY_CHARS))))
                        if queries:
                            call['queries'] = queries
                    target = _safe_url(raw_call.get('url'))
                    if target:
                        call['url'] = target
                    refs = raw_call.get('source_urls')
                    if not failed and isinstance(refs, list):
                        call['source_urls'] = list(dict.fromkeys([*call['source_urls'],
                            *(url for raw in refs[:MAX_CALL_URLS] if (url := _safe_url(raw)) and url in self._sources)]))[:MAX_CALL_URLS]
                    self._calls[ident] = call
                else:
                    self._truncated = True

    def update(self, info: object) -> dict | None:
        if not isinstance(info, dict):
            return None
        before = self.snapshot()
        self._apply(info)
        self._prune()
        after = self.snapshot()
        return after if after != before else None

    def close(self, complete: bool) -> dict | None:
        for call in self._calls.values():
            if call['state'] == 'live':
                call['state'] = 'done' if complete else 'stopped'
        self._prune()
        return self.snapshot()


def normalize_web(value: object) -> dict | None:
    """Read legacy/untrusted JSON safely; future versions fall back to the flat source list."""
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        return None
    activity = SourceActivity()
    # Bulk history restore avoids 40 repeated deepcopy/serialization passes over the same registry.
    activity._apply({'sources': value.get('sources')})
    calls = value.get('calls')
    if isinstance(calls, list):
        for call in calls[:MAX_WEB_CALLS]:
            # Snapshot source membership was already validated when persisted. Failed/stopped calls can
            # retain their prior successful links; unlike new failed updates, this does not add sources.
            previous_state = call.get('state') if isinstance(call, dict) else None
            replay = {**call, 'state': 'live'} if isinstance(previous_state, str) and previous_state in {'failed', 'stopped'} else call
            activity._apply({'call': replay})
            if isinstance(previous_state, str) and previous_state in {'failed', 'stopped'} and isinstance(call.get('id'), str) and call['id'] in activity._calls:
                activity._calls[call['id']]['state'] = previous_state
        if len(calls) > MAX_WEB_CALLS:
            activity._truncated = True
    if value.get('truncated') is True:
        activity._truncated = True
    activity._prune()
    return activity.snapshot()


def stop_web(value: object) -> dict | None:
    result = normalize_web(value)
    if result:
        for call in result['calls']:
            if call['state'] == 'live':
                call['state'] = 'stopped'
    # The longer terminal state strings must still fit the persisted byte budget.
    return normalize_web(result) if result else None
