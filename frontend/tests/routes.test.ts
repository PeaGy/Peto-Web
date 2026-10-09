import { expect, it } from 'vitest';
import { appPath, appView, chatId, chatRoute, imageMatch, imageRoute, legacyPath } from '../src/app/routes';

it.each([
  ['#companion', '/companion'], ['#imagine', '/imagine'],
  ['#imagine/root/version', '/imagine/root/version'],
])('nhận URL cũ %s và giữ đường dẫn phiên bản', (hash, expected) => {
  expect(legacyPath({ pathname: '/', hash })).toBe(expected);
  expect(appPath({ pathname: '/', hash })).toBe(expected);
});

it.each(['/docs', '/docs/giong-noi/', '/api/auth', '/khong-co'])('giữ anchor ngoài ứng dụng tại %s', pathname => {
  expect(legacyPath({ pathname, hash: '#companion' })).toBeNull();
});

it.each(['#khong-co', '#imagine/root', '#imagine/root/version/extra'])('không chuyển hash không hợp lệ %s', hash => {
  expect(legacyPath({ pathname: '/', hash })).toBeNull();
});

it('nhận đúng tab và encode từng ID, không biến ID thành đường dẫn', () => {
  expect(appView('/')).toBe('chat');
  expect(appView('/companion/')).toBe('companion');
  expect(appView('/imagine/root/version')).toBe('imagine');
  expect(appView('/imagines')).toBe('chat');
  expect(imageRoute('gốc/1', 'ảnh?2')).toBe('/imagine/g%E1%BB%91c%2F1/%E1%BA%A3nh%3F2');
  expect(imageMatch('/imagine/root/version')?.params).toEqual({ rootId: 'root', imageId: 'version' });
});

it('URL chat dùng ID riêng, giữ chat mới tại gốc và không đọc nhầm đường dẫn khác', () => {
  expect(chatRoute('hội thoại/1')).toBe('/chat/h%E1%BB%99i%20tho%E1%BA%A1i%2F1');
  expect(chatId('/chat/h%E1%BB%99i%20tho%E1%BA%A1i%2F1')).toBe('hội thoại/1');
  expect(chatId('/chat/A/')).toBe('A');
  expect(appView('/chat/A')).toBe('chat');
  for (const path of ['/', '/chat', '/chat/A/extra', '/companion']) expect(chatId(path)).toBeNull();
});
