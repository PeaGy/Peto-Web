import { beforeEach, expect, it } from 'vitest';
import { rememberChatLogin, takeChatLogin } from '../src/app/chatLoginReturn';

beforeEach(() => { sessionStorage.clear(); history.replaceState(null, '', '/'); });

it('chỉ lưu URL chat và chỉ dùng một lần sau đăng nhập', () => {
  history.replaceState(null, '', '/chat/A?source=bookmark');
  rememberChatLogin();
  history.replaceState(null, '', '/');
  expect(takeChatLogin()).toBe('/chat/A?source=bookmark');
  expect(takeChatLogin()).toBeNull();
  history.replaceState(null, '', '/imagine');
  rememberChatLogin();
  expect(takeChatLogin()).toBeNull();
});

it.each(['https://example.com/chat/A', '//example.com/chat/A', '/api/auth/me', '/chat/A/extra'])('không chuyển tới URL ngoài phạm vi: %s', path => {
  sessionStorage.setItem('peto-chat-login-return', path);
  expect(takeChatLogin()).toBeNull();
  expect(sessionStorage.getItem('peto-chat-login-return')).toBeNull();
});
