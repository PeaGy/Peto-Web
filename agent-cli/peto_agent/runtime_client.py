"""Ghi từng physical request, kể cả nén/tên/agent con, trước khi gọi transport."""
from __future__ import annotations

import contextlib
from .client import ApiError


class RuntimeClient:
    def __init__(self, client, bind, publish, logical_step=lambda purpose: None):
        self.client, self.bind, self.publish = client, bind, publish
        self.logical_step = logical_step

    def __getattr__(self, name):
        return getattr(self.client, name)

    def stream(self, path, body, **options):
        journal = self.bind()
        # /btw giữ hợp đồng riêng tư: chỉ lưu vòng đời, không lưu câu hỏi/câu trả lời.
        purpose = body.get('context', {}).get('purpose') or 'work'
        private = purpose == 'btw'
        request_id = journal.request_started(body, private=private, logical_step=self.logical_step(purpose))
        def events():
            finished = False
            try:
                with contextlib.closing(self.client.stream(path, body, **options)) as source:
                    for event in source:
                        if not finished and event.get('type') == 'done':
                            if purpose == 'work' and isinstance(event.get('output'), list):
                                self.publish(journal, request_id, event)
                            else:
                                journal.request_finished(request_id, 'completed', {} if private else event)
                            finished = True
                        elif not finished and event.get('type') == 'error':
                            journal.request_finished(request_id, 'failed', {} if private else event)
                            finished = True
                        yield {**event, '_peto_request_id': request_id}
            except ApiError as error:
                if not finished:
                    status = 'failed' if 400 <= error.status < 500 and error.status != 408 else 'unknown'
                    journal.request_finished(request_id, status, {'http_status': error.status})
                    finished = True
                raise
            finally:
                if not finished:
                    journal.request_finished(request_id, 'unknown')
        return events()
