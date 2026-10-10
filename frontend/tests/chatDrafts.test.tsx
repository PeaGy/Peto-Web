import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { CHAT_DRAFT_PREFIX, ChatDraftStore, draftKey, newChatContext, type DraftScope } from '../src/features/chat/chatDrafts';
import { useChatDrafts } from '../src/features/chat/useChatDrafts';

const scope = (conversationId: string | null = 'A', projectId: string | null = null, ownerId = 'account'): DraftScope =>
  ({ ownerId, conversationId, projectId, persona: 'assistant' });
const key = (id: string | null = 'A') => draftKey(scope(id));
beforeEach(() => { sessionStorage.clear(); vi.useFakeTimers(); URL.revokeObjectURL = vi.fn(); });
afterEach(() => vi.useRealTimers());

it('tách tài khoản, hội thoại và chat mới theo dự án/chế độ; chuyển dự án không đổi khóa chat có ID', () => {
  expect(draftKey(scope('A', 'P'))).toBe(key());
  const scopes = [scope(), scope('B'), scope(null), scope(null, 'P'), scope(null, 'Q'),
    { ...scope(null), persona: 'roleplay' as const }, scope('A', null, 'other')];
  expect(new Set(scopes.map(draftKey)).size).toBe(scopes.length);
});

it('lưu chữ nguyên vẹn nhưng không lưu tệp hay URL xem trước; xóa chữ thì xóa bản lưu', () => {
  const store = new ChatDraftStore();
  const text = 'Tiếng Việt 👋\n'.repeat(1500);
  store.setText(key(), text);
  store.setFiles(key(), [{ id: 'file', file: new File(['bí mật'], 'note.txt'), previewUrl: 'blob:secret' }]);
  expect(sessionStorage.getItem(key())).toBeNull();
  vi.advanceTimersByTime(250);
  expect(JSON.parse(sessionStorage.getItem(key())!)).toEqual({ text });
  expect(new ChatDraftStore().get(key())).toMatchObject({ text, files: [] });
  store.setText(key(), ''); store.flush();
  expect(sessionStorage.getItem(key())).toBeNull();
});

it('xác nhận gửi xóa đúng nháp cũ, không xóa chat đang mở hoặc chữ/tệp thêm sau khi gửi', () => {
  const store = new ChatDraftStore();
  store.setText(key(), 'Đã gửi');
  store.setFiles(key(), [{ id: 'old', file: new File(['a'], 'a.txt'), previewUrl: 'blob:old' }]);
  const sent = store.snapshot(key());
  store.setText(key('B'), 'Nháp B');
  store.accept(sent);
  expect(store.get(key())).toMatchObject({ text: '', files: [] });
  expect(store.get(key('B')).text).toBe('Nháp B');
  expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  store.setText(key(), 'Lượt nữa');
  const next = store.snapshot(key());
  store.setText(key(), 'Chữ mới hơn');
  store.setFiles(key(), [{ id: 'new', file: new File(['b'], 'b.txt'), previewUrl: null }]);
  store.accept(next);
  expect(store.get(key())).toMatchObject({ text: 'Chữ mới hơn', files: [{ id: 'new' }] });
});

it('xóa hội thoại/dự án chỉ xóa phạm vi tương ứng, kể cả nháp chưa đọc vào bộ nhớ', () => {
  const store = new ChatDraftStore();
  for (const s of [scope(), scope('B'), scope(null, 'P'), scope('C', 'P'), scope(null)]) store.setText(draftKey(s), 'Nháp');
  store.flush();
  const fresh = new ChatDraftStore();
  fresh.removeConversation('A'); fresh.removeProject('P');
  expect(sessionStorage.getItem(key())).toBeNull();
  expect(sessionStorage.getItem(draftKey(scope(null, 'P')))).toBeNull();
  expect(fresh.get(key('B')).text).toBe('Nháp');
  expect(fresh.get(key('C')).text).toBe('Nháp');
  expect(fresh.get(key(null)).text).toBe('Nháp');
});

it('chat mới mang chữ gõ sau khi gửi theo ID vừa cấp, không để sót nháp ở trang chủ', () => {
  const store = new ChatDraftStore();
  store.setText(key(null), 'Tin đầu');
  const sent = store.snapshot(key(null));
  store.setText(key(null), 'Câu hỏi tiếp theo');
  store.accept(sent, 'C');
  expect(store.get(key('C')).text).toBe('Câu hỏi tiếp theo');
  expect(store.get(key(null)).text).toBe('');
  expect(sessionStorage.getItem(key(null))).toBeNull();
  expect(new ChatDraftStore().get(key('C')).text).toBe('Câu hỏi tiếp theo');
});

it('xác nhận chat mới không đè nháp đích hoặc hồi sinh nháp của tài khoản đã đóng', () => {
  const store = new ChatDraftStore();
  store.setText(key(null), 'Tin đầu');
  const sent = store.snapshot(key(null));
  store.setText(key(null), 'Nháp mới');
  store.setText(key('C'), 'Nháp đích');
  store.accept(sent, 'C');
  expect(store.get(key('C')).text).toBe('Nháp đích');
  expect(store.get(key(null)).text).toBe('Nháp mới');
  store.clear(); store.accept(sent, 'C');
  expect(sessionStorage.length).toBe(0);
});

it('đăng xuất hủy ghi đang chờ, thu hồi mọi URL và không xóa storage tính năng khác', () => {
  sessionStorage.setItem('other-feature', 'giữ');
  const store = new ChatDraftStore();
  for (const id of ['A', 'B']) {
    store.setText(key(id), id);
    store.setFiles(key(id), [{ id, file: new File(['a'], 'a.png'), previewUrl: `blob:${id}` }]);
  }
  const sent = store.snapshot(key());
  store.clear(); store.accept(sent); vi.runAllTimers();
  expect(sessionStorage.length).toBe(1);
  expect(sessionStorage.getItem('other-feature')).toBe('giữ');
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
});

it('storage bị chặn, đầy hoặc JSON hỏng vẫn cho gõ/chọn tệp và chuyển chat', () => {
  sessionStorage.setItem(key(), '{broken');
  expect(new ChatDraftStore().get(key()).text).toBe('');
  const blocked = new ChatDraftStore(() => { throw new DOMException('Bị chặn', 'SecurityError'); });
  blocked.setOwner('account'); blocked.setText(key(), 'Nháp trong RAM'); blocked.flush();
  expect(blocked.get(key()).text).toBe('Nháp trong RAM');
  blocked.clear();
  const full = new ChatDraftStore(() => ({ ...sessionStorage, getItem: () => null,
    setItem: () => { throw new DOMException('Hết dung lượng', 'QuotaExceededError'); } }) as Storage);
  full.setText(key(), 'Vẫn gõ được'); full.flush();
  expect(full.get(key()).text).toBe('Vẫn gõ được');
});

it('chưa xác minh đăng nhập không xóa nháp; xác minh tài khoản khác loại nháp cũ', () => {
  sessionStorage.setItem(key(), JSON.stringify({ text: 'Nháp cũ' }));
  const other = draftKey(scope('A', null, 'other'));
  sessionStorage.setItem(other, JSON.stringify({ text: 'Nháp mới' }));
  const { result, rerender } = renderHook(({ current, authenticated }) => useChatDrafts(current, authenticated),
    { initialProps: { current: null as DraftScope | null, authenticated: undefined as boolean | undefined } });
  expect(sessionStorage.getItem(key())).not.toBeNull();
  rerender({ current: scope(), authenticated: true });
  expect(result.current.draft).toBe('Nháp cũ');
  expect(sessionStorage.getItem(other)).toBeNull();
  act(() => result.current.setDraft('Chữ chưa flush'));
  sessionStorage.setItem(other, JSON.stringify({ text: 'Nháp đúng tài khoản mới' }));
  rerender({ current: scope('A', null, 'other'), authenticated: true });
  expect(result.current.draft).toBe('Nháp đúng tài khoản mới');
  vi.runAllTimers();
  expect(sessionStorage.getItem(key())).toBeNull();
  expect(JSON.parse(sessionStorage.getItem(other)!).text).toBe('Nháp đúng tài khoản mới');
});

it('pagehide ghi ký tự cuối trước debounce; remount phục hồi chữ, tệp chỉ theo chat trong RAM', () => {
  const { result, rerender, unmount } = renderHook(({ current }) => useChatDrafts(current, true), { initialProps: { current: scope() } });
  act(() => {
    result.current.setDraft('Ký tự cuối');
    result.current.setDraftFiles([{ id: 'file', file: new File(['a'], 'a.png'), previewUrl: 'blob:preview' }]);
    window.dispatchEvent(new Event('pagehide'));
  });
  expect(JSON.parse(sessionStorage.getItem(key())!).text).toBe('Ký tự cuối');
  rerender({ current: scope('B') });
  expect(result.current.draft).toBe(''); expect(result.current.draftFiles).toEqual([]);
  rerender({ current: scope() });
  expect(result.current.draftFiles).toHaveLength(1);
  unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview');
  const fresh = renderHook(() => useChatDrafts(scope(), true));
  expect(fresh.result.current.draft).toBe('Ký tự cuối');
  expect(fresh.result.current.draftFiles).toEqual([]);
});

it('StrictMode khôi phục nháp và không hồi sinh nháp khi phiên hết hạn', () => {
  sessionStorage.setItem(key(), JSON.stringify({ text: 'Khôi phục' }));
  const { result, rerender, unmount } = renderHook(({ loggedIn }) => useChatDrafts(loggedIn ? scope() : null, loggedIn),
    { initialProps: { loggedIn: true }, wrapper: StrictMode });
  expect(result.current.draft).toBe('Khôi phục');
  act(() => result.current.setDraft('Nháp cuối'));
  rerender({ loggedIn: false }); unmount(); vi.runAllTimers();
  expect(sessionStorage.getItem(key())).toBeNull();
});

it('ngữ cảnh history kiểm tra đúng tài khoản và quyền nhập vai, không chứa nội dung nháp', () => {
  const context = { ownerId: 'account', projectId: 'P', persona: 'roleplay' as const };
  expect(newChatContext({ chatDraftContext: context }, 'account', true)).toEqual(context);
  for (const state of [null, {}, { chatDraftContext: context }, { chatDraftContext: { ...context, projectId: 123 } }]) {
    expect(newChatContext(state, 'other', false)).toEqual({ ownerId: 'other', projectId: null, persona: 'assistant' });
  }
  expect(newChatContext({ chatDraftContext: context }, 'account', false).persona).toBe('assistant');
  expect(CHAT_DRAFT_PREFIX).toContain('v1');
});
