import { act, fireEvent, render, screen } from '@testing-library/react';
import { useRef, useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Composer from '../src/features/chat/Composer';
import { appendSpeech } from '../src/features/chat/useChatDictation';

// Nhập giọng nói ở ô nhắn Chat (G5): Web Speech của trình duyệt, chữ hiện dần, bấm Gửi khi đang nghe thì gửi cả phần
// đang nghe dở.

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
    act(() => this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] }));
  }
}

const sent: string[] = [];
function Harness({ initial = '', context = 'a' }: { initial?: string; context?: string }) {
  const [draft, setDraft] = useState(initial);
  return <Composer draft={draft} onDraftChange={setDraft} files={[]} onAddFiles={() => true} onRemoveFile={vi.fn()}
    streaming={false} stopping={false} canSend={Boolean(draft.trim())} onSubmit={() => { sent.push(draft); setDraft(''); }}
    onStop={vi.fn()} effort="low" efforts={[{ value: 'low', label: 'Thấp', hint: '' }]} onEffortChange={vi.fn()}
    webSearch="auto" onToggleWeb={vi.fn()} menuDisabled={false} model="peto" models={[]} onModelChange={vi.fn()}
    formRef={useRef(null)} boxRef={useRef(null)} textareaRef={useRef(null)} fileRef={useRef(null)} contextKey={context} />;
}
const box = () => screen.getByRole('textbox', { name: 'Nhắn cho Peto' }) as HTMLTextAreaElement;
function listen() {
  fireEvent.click(screen.getByRole('button', { name: 'Nói để nhập' }));
  const recognition = Recognition.instances.at(-1)!;
  act(() => recognition.onstart?.());
  return recognition;
}

beforeEach(() => {
  Recognition.instances = [];
  sent.length = 0;
  vi.stubGlobal('SpeechRecognition', Recognition);
});
afterEach(() => { vi.unstubAllGlobals(); });

it('joins heard words to what is already typed', () => {
  expect(appendSpeech('', 'xin chào')).toBe('xin chào');
  expect(appendSpeech('Peto ơi', 'tóm tắt giúp')).toBe('Peto ơi tóm tắt giúp');
  expect(appendSpeech('Dòng một\n', 'dòng hai')).toBe('Dòng một\ndòng hai');
});

it('shows live words while listening, keeps final ones in the draft and stops with ✓', () => {
  render(<Harness initial="Peto ơi" />);
  const recognition = listen();
  expect(recognition.lang).toBe('vi-VN');
  // Như Claude: lúc nghe chỉ còn sóng âm, ✕ và ✓; micro, mũi tên và Gửi ẩn đi.
  expect(screen.queryByRole('button', { name: 'Gửi' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Nói để nhập' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Hủy nhập giọng nói' })).toBeTruthy();
  recognition.say('tóm tắt giúp', false);
  expect(box().value).toBe('Peto ơi tóm tắt giúp');
  expect(box().readOnly).toBe(true);
  recognition.say('tóm tắt giúp mình');
  expect(box().value).toBe('Peto ơi tóm tắt giúp mình');
  expect(box().readOnly).toBe(false);
  recognition.say('bài này', false);
  fireEvent.click(screen.getByRole('button', { name: 'Xong nhập giọng nói' }));
  // Phần đang nghe dở vẫn vào nháp để sửa.
  expect(box().value).toBe('Peto ơi tóm tắt giúp mình bài này');
  expect(recognition.abort).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Nói để nhập' })).toBeTruthy();
});

it('shows "Đang nghe…" in the empty box while listening', () => {
  render(<Harness />);
  listen();
  expect(box().placeholder).toBe('Đang nghe…');
  expect(box().classList.contains('dictation-listening')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Xong nhập giọng nói' }));
  expect(box().placeholder).toBe('Nhắn cho Peto…');
});

it('✕ drops what was heard and puts the box back as it was', () => {
  render(<Harness initial="Peto ơi" />);
  const recognition = listen();
  recognition.say('câu này bỏ đi');
  recognition.say('và cả câu này', false);
  expect(box().value).toBe('Peto ơi câu này bỏ đi và cả câu này');
  fireEvent.click(screen.getByRole('button', { name: 'Hủy nhập giọng nói' }));
  expect(box().value).toBe('Peto ơi');
  expect(recognition.abort).toHaveBeenCalled();
  recognition.say('chữ đến muộn');
  expect(box().value).toBe('Peto ơi');
  expect(screen.getByRole('button', { name: 'Gửi' })).toBeTruthy();
});

it('Enter while listening sends everything, including the half-heard words; late results are ignored', () => {
  render(<Harness />);
  const recognition = listen();
  recognition.say('một câu hỏi');
  recognition.say('nữa', false);
  fireEvent.keyDown(box(), { key: 'Enter' });
  expect(sent).toEqual(['một câu hỏi nữa']);
  recognition.say('chữ đến muộn');
  expect(box().value).toBe('');
});

it('switching conversation stops listening and drops the half-heard words', () => {
  const { rerender } = render(<Harness context="a" />);
  const recognition = listen();
  recognition.say('dở dang', false);
  rerender(<Harness context="b" />);
  expect(box().value).toBe('');
  expect(recognition.abort).toHaveBeenCalled();
});

it('shows a Chat-worded error when the microphone is blocked, cleared by typing', () => {
  render(<Harness />);
  const recognition = listen();
  act(() => recognition.onerror?.({ error: 'not-allowed' }));
  const alert = screen.getByRole('alert');
  expect(alert.textContent).toContain('micro');
  expect(alert.textContent).not.toContain('Companion');
  fireEvent.change(box(), { target: { value: 'gõ tay' } });
  expect(screen.queryByRole('alert')).toBeNull();
});

it('hides the microphone where the browser cannot listen (Firefox)', () => {
  vi.unstubAllGlobals();
  vi.stubGlobal('SpeechRecognition', undefined);
  vi.stubGlobal('webkitSpeechRecognition', undefined);
  render(<Harness />);
  expect(screen.queryByRole('button', { name: 'Nói để nhập' })).toBeNull();
});
