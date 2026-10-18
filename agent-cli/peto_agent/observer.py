"""Ranh giới Presenter: lỗi quan sát không làm mất kết quả; lỗi tương tác không cấp quyền."""
from __future__ import annotations

import logging

logger = logging.getLogger('peto_agent.presenter')
OBSERVATIONS = frozenset('tool_started tool_finished tool_progress explore_progress preview notice search request_finished '
                         'line step plan success failure item status clear_status bell title review_diff hand_over '
                         'set_session_title link_user_entry'.split())
INTERACTIONS = {'ask': 'n', 'wait_for_user': False, 'questions': None, 'choose': None, 'take_steers': []}


class Observer:
    def __init__(self, target):
        self.target = target
        self.failures = []
        self._failed_methods = set()

    def __setattr__(self, name, value):
        if name in {'target', 'failures', '_failed_methods'}:
            object.__setattr__(self, name, value)
        else:
            setattr(self.target, name, value)

    def failed(self, method, error):
        # Không ghi nội dung lỗi vì renderer có thể nhúng nội dung tệp/ảnh vào exception.
        self.failures.append({'method': method, 'error': type(error).__name__})
        self.failures[:] = self.failures[-20:]
        self._failed_methods.add(method)
        logger.warning('Lỗi hiển thị %s (%s); kết quả runtime được giữ riêng.', method, type(error).__name__)

    def __getattr__(self, name):
        value = getattr(self.target, name)
        if name == 'reply':
            def reply():
                try:
                    return Reply(self, value())
                except Exception as error:
                    self.failed(name, error)
                    return Reply(self, None)
            return reply
        if name not in OBSERVATIONS and name not in INTERACTIONS:
            return value
        def call(*args, **kwargs):
            if name in INTERACTIONS and self.failures:
                return INTERACTIONS[name]
            if name in OBSERVATIONS and name in self._failed_methods:
                return None
            try:
                return value(*args, **kwargs)
            except Exception as error:
                self.failed(name, error)
                return INTERACTIONS.get(name)
        return call


class Reply:
    def __init__(self, observer, target):
        self.observer, self.target, self.started = observer, target, False

    def _send(self, name, *args):
        if self.target is not None:
            try:
                getattr(self.target, name)(*args)
            except Exception as error:
                self.observer.failed('reply.' + name, error)
                self.target = None

    def feed(self, text):
        self.started = self.started or bool(text)
        self._send('feed', text)

    def think(self, text):
        self._send('think', text)

    def finish(self):
        self._send('finish')


def observe(ui):
    return ui if isinstance(ui, Observer) else Observer(ui)
