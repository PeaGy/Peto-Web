import { afterEach, describe, expect, it, vi } from 'vitest';
import { CLOUD_PROVIDERS, defaultConfig } from '../src/speechProviders';

const elevenlabs = CLOUD_PROVIDERS.elevenlabs;
const gemini = CLOUD_PROVIDERS.gemini;
const openai = CLOUD_PROVIDERS.openai;
const signal = () => new AbortController().signal;

describe('Dịch vụ đọc thành tiếng', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('ElevenLabs nhận khóa qua header và mã giọng trên đường dẫn', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(new ArrayBuffer(8), { status: 200 });
    }));

    const bytes = await elevenlabs.synthesize('chào', { key: 'k-123', voice: 'giong-1', model: 'm-1' }, signal());
    expect(bytes.byteLength).toBe(8);
    expect(calls[0].url).toContain('/v1/text-to-speech/giong-1');
    expect((calls[0].init?.headers as Record<string, string>)['xi-api-key']).toBe('k-123');
    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ text: 'chào', model_id: 'm-1' });
  });

  it('OpenAI nhận khóa qua Authorization và xin về mp3', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(new ArrayBuffer(4), { status: 200 });
    }));

    await openai.synthesize('chào', { key: 'sk-abc', voice: 'alloy', model: 'gpt-4o-mini-tts' }, signal());
    expect(calls[0].url).toContain('/v1/audio/speech');
    expect((calls[0].init?.headers as Record<string, string>).Authorization).toBe('Bearer sk-abc');
    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({
      voice: 'alloy', input: 'chào', response_format: 'mp3',
    });
  });

  it('Gemini gửi khóa qua header và bọc PCM thành WAV', async () => {
    const pcm = new Uint8Array([1, 2, 3, 4]);
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(JSON.stringify({
        candidates: [{ content: { parts: [{
          inlineData: { mimeType: 'audio/L16;codec=pcm;rate=24000', data: btoa(String.fromCharCode(...pcm)) },
        }] } }],
      }), { status: 200 });
    }));

    const bytes = await gemini.synthesize('chào', { key: 'k-gemini', voice: 'Kore', model: 'm-tts' }, signal());
    // 44 byte tiêu đề WAV rồi mới tới dữ liệu; thiếu nó là trình duyệt không phát được.
    expect(new TextDecoder().decode(bytes.slice(0, 4))).toBe('RIFF');
    expect(bytes.byteLength).toBe(44 + pcm.length);
    expect(new DataView(bytes).getUint32(24, true)).toBe(24000);
    expect((calls[0].init?.headers as Record<string, string>)['x-goog-api-key']).toBe('k-gemini');
    // Khóa không được nằm trong đường dẫn, kẻo lọt vào log của mọi thứ trên đường đi.
    expect(calls[0].url).not.toContain('k-gemini');
  });

  it('Gemini không trả âm thanh thì nói rõ chứ không im lặng', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ candidates: [] }), { status: 200 })));
    await expect(gemini.synthesize('chào', defaultConfig(gemini), signal()))
      .rejects.toThrow(/không trả về âm thanh/);
  });

  it('khóa sai thì báo bằng tiếng Việt chứ không ném mã lỗi trần', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: { message: 'Invalid API key' } }), { status: 401 },
    )));
    // Kèm luôn câu của chính dịch vụ: người dùng cần biết vì sao, không chỉ là "sai".
    await expect(elevenlabs.synthesize('chào', defaultConfig(elevenlabs), signal()))
      .rejects.toThrow(/không nhận khóa API.*Invalid API key/s);
  });

  it('khóa sai mà dịch vụ trả 400 thì vẫn nói là lỗi khóa', async () => {
    // Google trả 400 cho khóa sai; nhìn mỗi mã số thì báo nhầm thành sai mã giọng.
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ error: { message: 'API key not valid. Please pass a valid API key.' } }),
      { status: 400 },
    )));
    await expect(gemini.synthesize('chào', defaultConfig(gemini), signal()))
      .rejects.toThrow(/không nhận khóa API/);
  });

  it('hết lượt thì nói rõ là hết lượt, không bắt người dùng tự đoán', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('slow down', { status: 429 })));
    await expect(openai.synthesize('chào', defaultConfig(openai), signal()))
      .rejects.toThrow(/hết lượt|quá nhanh/);
  });

  it('hỏng phía dịch vụ thì nói là lỗi của họ', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 503 })));
    await expect(openai.synthesize('chào', defaultConfig(openai), signal()))
      .rejects.toThrow(/trục trặc phía họ/);
  });

  it('lấy được danh sách giọng của tài khoản ElevenLabs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ voices: [{ voice_id: 'v1', name: 'Rachel' }] }), { status: 200 },
    )));
    expect(await elevenlabs.listVoices?.('k-123', signal())).toEqual([{ id: 'v1', name: 'Rachel' }]);
  });
});
