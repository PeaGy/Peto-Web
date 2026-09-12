import { afterEach, describe, expect, it, vi } from 'vitest';
import { CLOUD_PROVIDERS, defaultConfig } from '../src/speechProviders';

const elevenlabs = CLOUD_PROVIDERS.elevenlabs;
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

  it('khóa sai thì báo bằng tiếng Việt chứ không ném mã lỗi trần', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 401 })));
    await expect(elevenlabs.synthesize('chào', defaultConfig(elevenlabs), signal()))
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
