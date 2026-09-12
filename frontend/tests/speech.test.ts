import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_VOICE, SpeechQueue, chunkLong, loadVoiceSettings, saveVoiceSettings,
  speakableText, splitSentences, type VoiceSettings } from '../src/speech';

class FakeUtterance {
  voice: unknown = null;
  lang = '';
  rate = 1;
  constructor(public text: string) {}
}

const spoken: string[] = [];
let cancels = 0;
let resumes = 0;

beforeEach(() => {
  spoken.length = 0;
  cancels = 0;
  resumes = 0;
  localStorage.clear();
  // jsdom không có Web Speech API, nên dựng một cái giả đủ dùng.
  Object.defineProperty(window, 'speechSynthesis', {
    configurable: true,
    value: {
      speak: (utterance: FakeUtterance) => { spoken.push(utterance.text); },
      cancel: () => { cancels += 1; },
      resume: () => { resumes += 1; },
      speaking: true,
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
    // Hai mẩu ngắn còn lại được gom, đọc nốt khi hết lượt.
    expect(spoken).toEqual(['Thử cái này nhé.']);
    queue.flush();
    expect(spoken).toEqual(['Thử cái này nhé.', '(khối mã). Xong.']);
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

  it('gom câu ngắn lại cho đỡ ngắt quãng, câu đầu vẫn đọc ngay', () => {
    const queue = queueWith({ ...DEFAULT_VOICE, on: true });
    queue.push('Một. ');
    expect(spoken).toEqual(['Một.']);
    queue.push('Hai. Ba. Bốn. ');
    expect(spoken).toEqual(['Một.']);
    queue.flush();
    expect(spoken).toEqual(['Một.', 'Hai. Ba. Bốn.']);
  });

  it('gom đủ dài thì đọc luôn, không đợi hết lượt', () => {
    const queue = queueWith({ ...DEFAULT_VOICE, on: true });
    const cau = 'Câu dài để thử ngưỡng gom mẩu cho đủ chữ. ';
    queue.push('Mở đầu. ');
    queue.push(cau.repeat(8));
    expect(spoken.length).toBe(2);
    expect(spoken[1].length).toBeGreaterThanOrEqual(240);
  });

  it('lượt trả lời sau lại được đọc ngay từ câu đầu', () => {
    const queue = queueWith({ ...DEFAULT_VOICE, on: true });
    queue.push('Lượt trước. ');
    queue.flush();
    spoken.length = 0;
    queue.push('Lượt sau. ');
    expect(spoken).toEqual(['Lượt sau.']);
  });

  it('gọi resume đều đặn để Chrome không cắt ngang lượt đọc dài', () => {
    vi.useFakeTimers();
    try {
      const queue = queueWith({ ...DEFAULT_VOICE, on: true });
      queue.push('Một câu đủ dài để bắt đầu đọc. ');
      expect(resumes).toBe(0);
      vi.advanceTimersByTime(11000);
      expect(resumes).toBeGreaterThan(0);

      queue.cancel();
      const after = resumes;
      vi.advanceTimersByTime(11000);
      expect(resumes).toBe(after);
    } finally {
      vi.useRealTimers();
    }
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

describe('Cắt mẩu dài và nhớ cài đặt', () => {
  it('không để mẩu nào dài quá mức, cắt ở khoảng trắng', () => {
    const pieces = chunkLong('từ '.repeat(200), 50);
    expect(pieces.every((piece) => piece.length <= 50)).toBe(true);
    expect(pieces.join(' ').split(' ').filter(Boolean).length).toBe(200);
  });

  it('bản lưu cũ đang ở mặc định cũ thì nâng lên mặc định mới', () => {
    localStorage.setItem('peto-voice', JSON.stringify({ on: true, voiceURI: '', rate: 1 }));
    expect(loadVoiceSettings().rate).toBe(DEFAULT_VOICE.rate);
  });

  it('tốc độ người dùng tự chỉnh thì giữ nguyên', () => {
    saveVoiceSettings({ ...DEFAULT_VOICE, rate: 1 });
    expect(loadVoiceSettings().rate).toBe(1);
  });
});

describe('Đọc bằng dịch vụ trả tiền', () => {
  const played: number[] = [];

  beforeEach(() => {
    played.length = 0;
    // jsdom không có Web Audio; giả đủ để biết mẩu nào được phát, theo thứ tự nào.
    class FakeContext {
      currentTime = 0;
      state = 'running';
      destination = {};
      createAnalyser() {
        return { fftSize: 0, frequencyBinCount: 8, connect() {}, getByteTimeDomainData() {} };
      }
      createBufferSource() {
        const node = {
          buffer: null as { id: number; duration: number } | null,
          connect() {},
          start() { played.push(node.buffer?.id ?? -1); },
          stop() {},
          onended: null,
        };
        return node;
      }
      async decodeAudioData(bytes: ArrayBuffer) {
        // Đánh dấu mẩu bằng chính độ dài, để biết thứ tự phát.
        return { id: bytes.byteLength, duration: 1 };
      }
      async resume() {}
    }
    vi.stubGlobal('AudioContext', FakeContext);
  });

  afterEach(() => { vi.unstubAllGlobals(); });

  const cloudSettings = (over: Partial<VoiceSettings> = {}): VoiceSettings => ({
    ...DEFAULT_VOICE,
    on: true,
    provider: 'elevenlabs',
    cloud: { elevenlabs: { key: 'k-1', voice: 'v-1', model: 'm-1' } },
    ...over,
  });

  it('phát đúng thứ tự dù mẩu sau tải xong trước', async () => {
    let count = 0;
    vi.stubGlobal('fetch', vi.fn(async () => {
      count += 1;
      const size = count;
      // Mẩu đầu về chậm hơn mẩu sau.
      await new Promise((resolve) => setTimeout(resolve, size === 1 ? 30 : 0));
      return new Response(new ArrayBuffer(size), { status: 200 });
    }));

    const queue = new SpeechQueue(() => cloudSettings());
    queue.push('Câu một. ');
    queue.push('Câu hai. ');
    queue.flush();

    await vi.waitFor(() => expect(played.length).toBe(2));
    expect(played).toEqual([1, 2]);
  });

  it('dịch vụ bị siết lượt gọi thì cả câu trả lời chỉ tốn một lượt', async () => {
    const fetchMock = vi.fn(async () => new Response(new ArrayBuffer(1), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const queue = new SpeechQueue(() => cloudSettings({
      provider: 'gemini',
      cloud: { gemini: { key: 'k', voice: 'Kore', model: 'm' } },
    }));

    queue.push('Câu một. ');
    queue.push('Câu hai. Câu ba. ');
    // Gemini miễn phí chỉ cho 3 lượt mỗi phút, nên chưa xong thì chưa được gọi.
    expect(fetchMock).not.toHaveBeenCalled();

    queue.flush();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('chưa điền khóa thì báo lỗi và không gọi mạng', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const errors: string[] = [];
    const queue = new SpeechQueue(
      () => cloudSettings({ cloud: { elevenlabs: { key: '', voice: 'v-1', model: 'm-1' } } }),
      { onError: (message) => errors.push(message) },
    );
    queue.push('Câu một. ');
    expect(fetchMock).not.toHaveBeenCalled();
    expect(errors[0]).toContain('Chưa điền khóa API');
  });

  it('đếm số ký tự đã gửi cho dịch vụ', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ArrayBuffer(1), { status: 200 })));
    const counts: number[] = [];
    const queue = new SpeechQueue(() => cloudSettings(), { onChars: (total) => counts.push(total) });
    queue.push('Câu một. ');
    expect(counts.at(-1)).toBe('Câu một.'.length);
  });

  it('dịch vụ hỏng thì báo một lần rồi thôi, không la làng từng mẩu', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 401 })));
    const errors: string[] = [];
    const queue = new SpeechQueue(() => cloudSettings(), { onError: (message) => errors.push(message) });
    queue.push('Câu một. ');
    await vi.waitFor(() => expect(errors.length).toBe(1));
    queue.push('Câu hai. ');
    queue.flush();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(errors.length).toBe(1);
    expect(errors[0]).toContain('không nhận khóa API');
  });
});
