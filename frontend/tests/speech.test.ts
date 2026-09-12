import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_VOICE, SpeechQueue, speakableText, splitSentences, type VoiceSettings } from '../src/speech';

class FakeUtterance {
  voice: unknown = null;
  lang = '';
  rate = 1;
  constructor(public text: string) {}
}

const spoken: string[] = [];
let cancels = 0;

beforeEach(() => {
  spoken.length = 0;
  cancels = 0;
  // jsdom không có Web Speech API, nên dựng một cái giả đủ dùng.
  Object.defineProperty(window, 'speechSynthesis', {
    configurable: true,
    value: {
      speak: (utterance: FakeUtterance) => { spoken.push(utterance.text); },
      cancel: () => { cancels += 1; },
      getVoices: () => [],
    },
  });
  (globalThis as { SpeechSynthesisUtterance?: unknown }).SpeechSynthesisUtterance = FakeUtterance;
});

afterEach(() => {
  delete (window as { speechSynthesis?: unknown }).speechSynthesis;
  delete (globalThis as { SpeechSynthesisUtterance?: unknown }).SpeechSynthesisUtterance;
});

const queueWith = (settings: VoiceSettings) => new SpeechQueue(() => settings);

describe('Chuẩn bị chữ để đọc', () => {
  it('bỏ khối mã, giữ lời văn quanh nó', () => {
    expect(speakableText('Đây nè:\n```python\nprint(1)\n```\nXong rồi.'))
      .toBe('Đây nè: (khối mã) Xong rồi.');
  });

  it('bỏ cả khối mã còn đang gõ dở', () => {
    expect(speakableText('Xem này:\n```python\nprint(')).toBe('Xem này: (khối mã)');
  });

  it('giữ chữ trong liên kết và bỏ dấu nhấn', () => {
    expect(speakableText('**Quan trọng**: xem [tài liệu](https://x.test) nhé'))
      .toBe('Quan trọng: xem tài liệu nhé');
  });

  it('bỏ hàng bảng và dấu đầu dòng', () => {
    expect(speakableText('| cột | giá |\n- một\n- hai')).toBe('một hai');
  });
});

describe('Cắt câu', () => {
  it('cắt khi sau dấu câu có khoảng trắng', () => {
    expect(splitSentences('Chào cậu. Hôm nay')).toEqual({ ready: ['Chào cậu.'], rest: ' Hôm nay' });
  });

  it('không xé số thập phân', () => {
    expect(splitSentences('Pi là 3.14 nhé')).toEqual({ ready: [], rest: 'Pi là 3.14 nhé' });
  });

  it('cắt ở chỗ xuống dòng', () => {
    expect(splitSentences('Một\nHai')).toEqual({ ready: ['Một'], rest: 'Hai' });
  });

  it('dấu câu ở ngay cuối đệm thì chờ thêm chữ', () => {
    expect(splitSentences('Xong.')).toEqual({ ready: [], rest: 'Xong.' });
  });
});

describe('Hàng đợi đọc', () => {
  it('đọc từng câu ngay khi chữ còn đang chảy về', () => {
    const queue = queueWith({ ...DEFAULT_VOICE, on: true });
    queue.push('Chào cậu.');
    expect(spoken).toEqual([]);
    queue.push(' Hôm nay thế nào?');
    expect(spoken).toEqual(['Chào cậu.']);
    queue.flush();
    expect(spoken).toEqual(['Chào cậu.', 'Hôm nay thế nào?']);
  });

  it('chưa đóng khối mã thì chưa đọc tới đó', () => {
    const queue = queueWith({ ...DEFAULT_VOICE, on: true });
    queue.push('Thử cái này nhé. ');
    queue.push('```python\nprint(');
    expect(spoken).toEqual(['Thử cái này nhé.']);
    queue.push('1)\n```\nXong. ');
    expect(spoken).toEqual(['Thử cái này nhé.', '(khối mã).', 'Xong.']);
  });

  it('đang tắt thì không đọc, và bật lên cũng không đọc dồn phần cũ', () => {
    const settings = { ...DEFAULT_VOICE, on: false };
    const queue = new SpeechQueue(() => settings);
    queue.push('Chữ cũ. ');
    queue.flush();
    expect(spoken).toEqual([]);

    settings.on = true;
    queue.push('Chữ mới. ');
    expect(spoken).toEqual(['Chữ mới.']);
  });

  it('dừng thì im ngay và quên phần chưa đọc', () => {
    const queue = queueWith({ ...DEFAULT_VOICE, on: true });
    queue.push('Một câu dài đang đọc dở. ');
    queue.cancel();
    queue.flush();
    expect(cancels).toBe(1);
    expect(spoken).toEqual(['Một câu dài đang đọc dở.']);
  });
});
