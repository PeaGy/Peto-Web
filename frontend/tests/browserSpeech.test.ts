import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { startBrowserSpeech } from '../src/features/companion/speech/browserSpeech';

class Recognition {
  static instances: Recognition[] = [];
  lang = '';
  continuous = false;
  interimResults = false;
  onstart: (() => void) | null = null;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onspeechstart: (() => void) | null = null;
  onspeechend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
  constructor() { Recognition.instances.push(this); }
  say(text: string, isFinal = true) {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
  }
}
const callbacks = () => ({
  onConnecting: vi.fn(), onReady: vi.fn(), onSpeechStart: vi.fn(), onSpeechEnd: vi.fn(), onInterim: vi.fn(),
  onFinal: vi.fn(), onDraft: vi.fn(), onNotice: vi.fn(), onError: vi.fn(),
});
let session: ReturnType<typeof startBrowserSpeech> | undefined;
beforeEach(() => {
  vi.useFakeTimers();
  Recognition.instances = [];
  vi.stubGlobal('SpeechRecognition', Recognition);
});
afterEach(() => { session?.stop(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it('kết quả và lỗi muộn sau khi tắt micro không chảy vào phiên nghe mới', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const old = Recognition.instances[0];
  session.stop();
  old.say('Late text');
  old.onerror?.({ error: 'network' });
  expect(handlers.onFinal).not.toHaveBeenCalled();
  expect(handlers.onError).not.toHaveBeenCalled();
});

it('dịch vụ không xác nhận khởi động thì báo lỗi thay vì nghe mãi', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  vi.advanceTimersByTime(10000);
  expect(handlers.onReady).not.toHaveBeenCalled();
  expect(handlers.onError).toHaveBeenCalledWith(expect.stringMatching(/chưa khởi động/));
  expect(Recognition.instances[0].abort).toHaveBeenCalled();
});

it('không nghe ra lời thì báo gợi ý, vẫn cho phiên sau nghe tiếp', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const first = Recognition.instances[0];
  first.onstart?.();
  first.onspeechstart?.();
  vi.advanceTimersByTime(1500);
  first.onerror?.({ error: 'no-speech' });
  expect(handlers.onNotice).toHaveBeenCalledWith(expect.stringMatching(/chưa nhận ra lời/));
  first.onend?.();
  vi.advanceTimersByTime(300);
  const next = Recognition.instances.at(-1)!;
  next.onstart?.();
  next.say('Hello Peto');
  expect(handlers.onFinal).toHaveBeenCalledWith('Hello Peto');
});

it('phiên hết giữa câu giữ chữ dở để sửa, kết quả cũ không bị thêm trùng', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const first = Recognition.instances[0];
  first.onstart?.();
  first.say('Can you hear', false);
  vi.advanceTimersByTime(1500);
  first.onend?.();
  expect(handlers.onDraft).toHaveBeenCalledWith('Can you hear');
  vi.advanceTimersByTime(300);
  first.say('Can you hear me?', true);
  expect(handlers.onFinal).not.toHaveBeenCalled();
});

it('im lặng không bị coi là dịch vụ hỏng; có âm thanh mà không ra chữ mới nhắc', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  Recognition.instances[0].onstart?.();
  vi.advanceTimersByTime(60000);
  expect(handlers.onNotice).not.toHaveBeenCalled();
  expect(handlers.onError).not.toHaveBeenCalled();
  session.noteSound();
  vi.advanceTimersByTime(8000);
  expect(handlers.onNotice).toHaveBeenCalledWith(expect.stringMatching(/có âm thanh.*chưa trả chữ/));
  Recognition.instances[0].say('Hello');
  expect(handlers.onNotice).toHaveBeenLastCalledWith('');
});

it('kết quả cuối không nhân đôi, chữ dở vẫn hiện khi resultIndex thay đổi', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const recognition = Recognition.instances[0];
  recognition.onstart?.();
  recognition.onresult?.({ resultIndex: 0, results: [
    { isFinal: true, 0: { transcript: 'First sentence.' } },
    { isFinal: false, 0: { transcript: 'Second' } },
  ] });
  recognition.onresult?.({ resultIndex: 1, results: [
    { isFinal: true, 0: { transcript: 'First sentence.' } },
    { isFinal: false, 0: { transcript: 'Second sentence' } },
  ] });
  expect(handlers.onFinal).toHaveBeenCalledExactlyOnceWith('First sentence.');
  expect(handlers.onInterim).toHaveBeenLastCalledWith('Second sentence');
});

it('lỗi mạng giữ phần chữ đã nghe, dọn mọi hẹn giờ và không tự khởi động lại', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const recognition = Recognition.instances[0];
  recognition.onstart?.();
  recognition.say('Partial sentence', false);
  recognition.onerror?.({ error: 'network' });
  recognition.onend?.();
  vi.advanceTimersByTime(60000);
  expect(handlers.onDraft).toHaveBeenCalledExactlyOnceWith('Partial sentence');
  expect(handlers.onError).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/không kết nối/));
  expect(Recognition.instances).toHaveLength(1);
  expect(vi.getTimerCount()).toBe(0);
});

it('kết thúc có chốt (Giữ để nói): gọi stop chứ không abort, chữ dở thành chữ chốt, không mở phiên mới', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const recognition = Recognition.instances[0];
  recognition.onstart?.();
  recognition.say('Hello Peto', true);
  recognition.say('how are', false);
  const done = vi.fn();
  session.finish(done);
  expect(recognition.stop).toHaveBeenCalledOnce();
  expect(recognition.abort).not.toHaveBeenCalled();
  // Trình duyệt trả nốt kết quả rồi mới kết thúc phiên.
  recognition.onresult?.({ resultIndex: 1, results: [{ isFinal: true, 0: { transcript: 'Hello Peto' } }, { isFinal: false, 0: { transcript: 'how are you' } }] });
  recognition.onend?.();
  expect(handlers.onFinal.mock.calls.map(call => call[0])).toEqual(['Hello Peto', 'how are you']);
  expect(handlers.onDraft).not.toHaveBeenCalled();
  expect(handlers.onNotice).not.toHaveBeenCalledWith(expect.stringMatching(/chưa được chốt/));
  expect(done).toHaveBeenCalledOnce();
  vi.advanceTimersByTime(1000);
  expect(Recognition.instances).toHaveLength(1);
});

it('kết thúc có chốt lúc trình duyệt báo lỗi hay đang nghỉ giữa hai phiên vẫn xong một lần', () => {
  const handlers = callbacks();
  session = startBrowserSpeech('en', handlers);
  const first = Recognition.instances[0];
  first.onstart?.();
  const done = vi.fn();
  session.finish(done);
  first.onerror?.({ error: 'no-speech' });
  first.onend?.();
  expect(done).toHaveBeenCalledOnce();
  expect(handlers.onError).not.toHaveBeenCalled();

  const later = startBrowserSpeech('en', callbacks());
  const second = Recognition.instances[1];
  second.onstart?.();
  second.onend?.();
  const after = vi.fn();
  later.finish(after);
  expect(after).toHaveBeenCalledOnce();
  vi.advanceTimersByTime(1000);
  expect(Recognition.instances).toHaveLength(2);
});
