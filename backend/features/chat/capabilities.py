"""Một lựa chọn schema cho cả request, manifest và kiểm quyền dispatch của từng vòng."""
from dataclasses import dataclass

from shared.time_tools import TOOL_SCHEMAS
from shared.attachment_tools import SEARCH_SCHEMA, READ_SCHEMA
from shared.chat_history_tools import SCHEMA as HISTORY_SCHEMA
from features.documents.tools import (SCHEMA as DOCUMENT_SCHEMA, PRESENTATION_SCHEMA, SPREADSHEET_SCHEMA,
                                      EDIT_SCHEMA, WORD_EDIT_SCHEMA)
from features.connectors.tools import SCHEMAS as GITHUB_SCHEMAS
from features.companion import player_tools

# Chạy mã phía xAI (thí điểm 21/10/2026): công cụ của dịch vụ, Peto không tự chạy mã nào. Chỉ có chữ in ra, không tệp.
CODE_SCHEMA = {'type': 'code_interpreter'}


@dataclass(frozen=True)
class Capability:
    name: str
    schemas: tuple[dict, ...]
    state: str = 'available'
    reason: str = 'request_scope'
    evidence: dict | None = None


@dataclass(frozen=True)
class ToolPlan:
    capabilities: tuple[Capability, ...]

    @property
    def schemas(self):
        return [schema for item in self.capabilities if item.state == 'available' for schema in item.schemas]

    def allows(self, name):
        return any(schema.get('type') == 'function' and schema.get('name') == name for schema in self.schemas)

    def manifest(self, native_tools=None):
        def names(schemas):
            return [schema.get('name') or schema.get('type') for schema in schemas]
        return [{'name': item.name, 'state': item.state, 'reason': item.reason,
                 'tools': names(native_tools(list(item.schemas)) if native_tools else item.schemas),
                 **({'reader_states': item.evidence} if item.evidence is not None else {})}
                for item in self.capabilities]


def select(*, documents, files, history, github_state, github_reason, search_enabled, web_search,
           tools_enabled, finalizing, required_search, search_fallback=False, code_reason='provider_unsupported'):
    """``code_reason`` None nghĩa là dịch vụ của vòng này chạy mã được; không thì là lý do không có (Luna, Haiku:
    provider_unsupported; công tắc máy chủ tắt: server_disabled)."""
    def entry(name, schemas, enabled, state='unavailable', reason='no_scoped_source'):
        return Capability(name, tuple(schemas), 'available' if enabled else state,
                          'request_scope' if enabled else reason)
    items = [
        entry('clock', TOOL_SCHEMAS, True),
        entry('player', [player_tools.SCHEMA], player_tools.current.get() is not None, reason='companion_browser_only'),
        entry('create_files', [DOCUMENT_SCHEMA, PRESENTATION_SCHEMA, SPREADSHEET_SCHEMA], documents is not None),
        entry('edit_spreadsheet', [EDIT_SCHEMA], bool(documents and documents.workbooks)),
        entry('edit_document', [WORD_EDIT_SCHEMA], bool(documents and getattr(documents, 'word_files', None))),
        Capability('read_files', tuple(files.schemas()) if files and files.schemas() else (SEARCH_SCHEMA, READ_SCHEMA),
                   'available' if files and files.schemas() else 'unavailable',
                   'source_access_only' if files and files.schemas() else 'no_scoped_source',
                   files.reader_states() if files else {}),
        entry('read_chat_history', [HISTORY_SCHEMA], history is not None, reason='no_hidden_history'),
        Capability('github', tuple(GITHUB_SCHEMAS), github_state, github_reason),
        entry('web', [{'type': 'web_search'}], search_enabled,
              'disabled', 'user_disabled' if web_search == 'off' else 'side_call' if not tools_enabled else
              'partial_search_failure' if search_fallback else 'server_disabled'),
        entry('run_code', [CODE_SCHEMA], code_reason is None,
              'disabled' if code_reason == 'server_disabled' else 'unavailable', code_reason or ''),
    ]
    selected = []
    for item in items:
        reason = ('side_call' if not tools_enabled else 'finalizing' if finalizing else
                  'required_web_first' if required_search and item.name != 'web' else '')
        selected.append(Capability(item.name, item.schemas, 'disabled', reason, item.evidence)
                        if item.state == 'available' and reason else item)
    return ToolPlan(tuple(selected))
