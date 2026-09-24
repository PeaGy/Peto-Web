import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  HearingError,
  hearingKeyReady,
  hearingProvider,
  sttModelOf,
  transcribeWithKey,
  type HearingProvider,
} from '../src/hearingProviders';
import type { KeyConfig } from '../src/voiceProviders';

const fetchMock = vi.fn();
const provider = (id: string) => hearingProvider(id) as HearingProvider;
const signal = () => new AbortController().signal;
const audio = () => new Blob([new Uint8Array([82, 73, 70, 70, 0, 0, 0, 0, 87, 65, 86, 69])], { type: 'audio/wav' });

/** Chép một câu rồi trả yêu cầu trình duyệt đã gửi cùng chữ nhận được. */
async function sent(id: string, config: KeyConfig, response: Response, language: 'en' | 'vi' = 'en') {
  fetchMock.mockResolvedValueOnce(response);
  const text = await transcribeWithKey(provider(id), config, audio(), language, signal());
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { url, init, headers: (init.headers ?? {}) as Record<string, string>, text };
}

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe('đủ thông tin để chép lời', () => {
  it('cần khóa; Azure cần thêm vùng; máy chủ tự dựng chỉ cần địa chỉ', () => {
    expect(hearingKeyReady(provider('groq'), { key: '  ' })).toBe(false);
    expect(hearingKeyReady(provider('groq'), { key: 'gsk_1' })).toBe(true);
    expect(hearingKeyReady(provider('azure'), { key: 'az' })).toBe(false);
    expect(hearingKeyReady(provider('azure'), { key: 'az', region: 'eastus' })).toBe(true);
    expect(hearingKeyReady(provider('compat'), { baseUrl: 'http://127.0.0.1:8000/v1' })).toBe(true);
  });

  it('model chép lời để riêng với model của phần Peto nói', () => {
    expect(sttModelOf(provider('openai'), { model: 'tts-1' })).toBe('gpt-4o-mini-transcribe');
    expect(sttModelOf(provider('openai'), { sttModel: 'whisper-1' })).toBe('whisper-1');
    expect(sttModelOf(provider('gemini'), undefined)).toBe('gemini-3.8-flash');
    expect(sttModelOf(provider('compat'), undefined)).toBe('whisper-1');
  });
});

describe('gọi thẳng nhà cung cấp', () => {
  it('Groq: Whisper, gửi WAV kèm ngôn ngữ, khóa trong Bearer', async () => {
    const { url, init, headers, text } = await sent('groq', { key: 'gsk_user' }, json({ text: ' Hello Peto ' }));
    expect(url).toBe('https://api.groq.com/openai/v1/audio/transcriptions');
    expect(headers.Authorization).toBe('Bearer gsk_user');
    const form = init.body as FormData;
    expect(form.get('model')).toBe('whisper-large-v3-turbo');
    expect(form.get('language')).toBe('en');
    expect(form.get('response_format')).toBe('json');
    expect((form.get('file') as File).name).toBe('speech.wav');
    expect(text).toBe('Hello Peto');
  });

  it('OpenAI: model gpt tự nhận ngôn ngữ, chỉ whisper-1 mới gửi kèm ngôn ngữ', async () => {
    const first = await sent('openai', { key: 'sk-1' }, json({ text: 'Hi' }));
    expect(first.url).toBe('https://api.openai.com/v1/audio/transcriptions');
    expect((first.init.body as FormData).get('model')).toBe('gpt-4o-mini-transcribe');
    expect((first.init.body as FormData).has('language')).toBe(false);
    fetchMock.mockReset();
    const second = await sent('openai', { key: 'sk-1', sttModel: 'whisper-1' }, json({ text: 'Xin chào' }), 'vi');
    expect((second.init.body as FormData).get('language')).toBe('vi');
  });

  it('máy chủ tự dựng: bỏ dấu / cuối, không có khóa thì không gửi Authorization', async () => {
    const { url, headers } = await sent('compat', { baseUrl: 'http://127.0.0.1:8000/v1/' }, json({ text: 'ok' }));
    expect(url).toBe('http://127.0.0.1:8000/v1/audio/transcriptions');
    expect(headers.Authorization).toBeUndefined();
  });

  it('Azure: đúng vùng và ngôn ngữ, gửi WAV 16 kHz; không nghe ra chữ thì trả rỗng', async () => {
    const ok = await sent('azure', { key: 'az', region: 'EastUS' }, json({ RecognitionStatus: 'Success', DisplayText: 'Xin chào Peto.' }), 'vi');
    expect(ok.url).toBe('https://eastus.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=vi-VN&format=simple');
    expect(ok.headers['Ocp-Apim-Subscription-Key']).toBe('az');
    expect(ok.headers['Content-Type']).toBe('audio/wav; codecs=audio/pcm; samplerate=16000');
    expect(ok.text).toBe('Xin chào Peto.');

    fetchMock.mockResolvedValueOnce(json({ RecognitionStatus: 'NoMatch' }));
    expect(await transcribeWithKey(provider('azure'), { key: 'az', region: 'eastus' }, audio(), 'en', signal())).toBe('');

    fetchMock.mockResolvedValueOnce(json({ RecognitionStatus: 'Error' }));
    const error = await transcribeWithKey(provider('azure'), { key: 'az', region: 'eastus' }, audio(), 'en', signal()).catch((err) => err);
    expect(error).toBeInstanceOf(HearingError);
    expect((error as HearingError).fatal).toBe(false);
  });

  it('Deepgram: model và ngôn ngữ trên địa chỉ, khóa dạng Token, chữ ở kênh đầu', async () => {
    const response = json({ results: { channels: [{ alternatives: [{ transcript: 'Good morning' }] }] } });
    const { url, headers, text } = await sent('deepgram', { key: 'dg' }, response, 'vi');
    expect(url).toBe('https://api.deepgram.com/v1/listen?model=nova-3&language=vi&smart_format=true');
    expect(headers.Authorization).toBe('Token dg');
    expect(headers['Content-Type']).toBe('audio/wav');
    expect(text).toBe('Good morning');
  });

  it('ElevenLabs: Scribe, mã ngôn ngữ hai chữ', async () => {
    const { url, init, headers, text } = await sent('elevenlabs', { key: 'el' }, json({ text: 'Hey there' }));
    expect(url).toBe('https://api.elevenlabs.io/v1/speech-to-text');
    expect(headers['xi-api-key']).toBe('el');
    expect((init.body as FormData).get('model_id')).toBe('scribe_v2');
    expect((init.body as FormData).get('language_code')).toBe('en');
    expect(text).toBe('Hey there');
  });

  it('Gemini: Interactions API với âm thanh base64, lấy chữ ở bước model_output', async () => {
    const response = json({
      steps: [
        { type: 'user_input', content: [{ type: 'text', text: 'Transcribe this speech' }] },
        { type: 'model_output', content: [{ type: 'text', text: 'See you ' }, { type: 'text', text: 'tomorrow' }] },
      ],
    });
    const { url, init, headers, text } = await sent('gemini', { key: 'AIza' }, response);
    expect(url).toBe('https://generativelanguage.googleapis.com/v1beta/interactions');
    expect(headers['x-goog-api-key']).toBe('AIza');
    const body = JSON.parse(String(init.body));
    expect(body.model).toBe('gemini-3.8-flash');
    expect(body.input[0]).toMatchObject({ type: 'text' });
    expect(body.input[0].text).toContain('do not translate');
    expect(body.input[1]).toEqual({ type: 'audio', data: 'UklGRgAAAABXQVZF', mime_type: 'audio/wav' });
    expect(text).toBe('See you tomorrow');

    fetchMock.mockResolvedValueOnce(json({ output_text: 'Hello' }));
    expect(await transcribeWithKey(provider('gemini'), { key: 'AIza' }, audio(), 'en', signal())).toBe('Hello');
  });
});

describe('lỗi thành câu báo tiếng Việt', () => {
  it.each([
    [401, /Khóa Groq không đúng/, true],
    [402, /hết số dư/, true],
    [400, /không nhận model hay đoạn âm thanh/, true],
    [429, /giới hạn lượt gọi/, false],
    [503, /mã 503/, false],
  ])('mã %i', async (status, message, fatal) => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status }));
    const error = await transcribeWithKey(provider('groq'), { key: 'k' }, audio(), 'en', signal()).catch((err) => err);
    expect(error).toBeInstanceOf(HearingError);
    expect(error.message).toMatch(message);
    expect(error.fatal).toBe(fatal);
  });

  it('không gọi được từ trình duyệt thì báo rõ và vẫn nghe tiếp', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const error = await transcribeWithKey(provider('deepgram'), { key: 'k' }, audio(), 'en', signal()).catch((err) => err);
    expect(error.message).toMatch(/Không gọi được Deepgram từ trình duyệt/);
    expect(error.fatal).toBe(false);
  });
});
