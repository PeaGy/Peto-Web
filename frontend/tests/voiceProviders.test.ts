import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  defaultVoiceOf,
  keyProvider,
  keyReady,
  listKeyVoices,
  normalizeWav,
  pcmToWav,
  speakWithKey,
  suggestedVoices,
  voiceOf,
  type KeyConfig,
  type KeyProvider,
} from '../src/voiceProviders';

const fetchMock = vi.fn();
const provider = (id: string) => keyProvider(id) as KeyProvider;
const signal = () => new AbortController().signal;

/** Blob của jsdom không đọc được qua Response của Node; FileReader thì được. */
async function bytes(blob: Blob): Promise<Uint8Array<ArrayBuffer>> {
  if (typeof blob.arrayBuffer === 'function') return new Uint8Array(await blob.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

function text(data: Uint8Array, at: number, length = 4): string {
  return String.fromCharCode(...data.subarray(at, at + length));
}

function riff(): Uint8Array {
  return new Uint8Array([...'RIFF'].map((char) => char.charCodeAt(0)).concat([0, 0, 0, 0], [...'WAVE'].map((char) => char.charCodeAt(0))));
}

/** Gọi speakWithKey rồi trả yêu cầu mà trình duyệt đã gửi. */
async function sent(id: string, config: KeyConfig, response: Response, say = 'Hello') {
  fetchMock.mockResolvedValueOnce(response);
  const blob = await speakWithKey(provider(id), config, say, signal());
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { url, init, headers: init.headers as Record<string, string>, blob };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe('đủ thông tin để gọi', () => {
  it('cần khóa, riêng máy chủ tự dựng chỉ cần địa chỉ hợp lệ', () => {
    expect(keyReady(provider('openai'), undefined)).toBe(false);
    expect(keyReady(provider('openai'), { key: '  ' })).toBe(false);
    expect(keyReady(provider('openai'), { key: 'sk-1' })).toBe(true);
    expect(keyReady(provider('compat'), { baseUrl: 'http://127.0.0.1:8880/v1/' })).toBe(true);
    expect(keyReady(provider('compat'), { baseUrl: 'ftp://example.com' })).toBe(false);
  });

  it('Azure cần thêm vùng, chỉ chữ thường, số và gạch nối', () => {
    expect(keyReady(provider('azure'), { key: 'k' })).toBe(false);
    expect(keyReady(provider('azure'), { key: 'k', region: 'southeastasia' })).toBe(true);
    expect(keyReady(provider('azure'), { key: 'k', region: 'evil.com/x' })).toBe(false);
  });
});

describe('WAV', () => {
  it('bọc PCM16 thành WAV đúng header', async () => {
    const wav = await bytes(pcmToWav(new Uint8Array(480), 24000));
    const view = new DataView(wav.buffer);
    expect(text(wav, 0)).toBe('RIFF');
    expect(text(wav, 8)).toBe('WAVE');
    expect(view.getUint32(4, true)).toBe(36 + 480);
    expect(view.getUint32(24, true)).toBe(24000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(text(wav, 36)).toBe('data');
    expect(view.getUint32(40, true)).toBe(480);
  });

  it('sửa kích thước "không rõ" của WAV phát trực tuyến, để yên tệp không phải WAV', async () => {
    const streamed = await bytes(pcmToWav(new Uint8Array(100), 24000));
    const view = new DataView(streamed.buffer);
    view.setUint32(4, 0xffffffff, true);
    view.setUint32(40, 0xffffffff, true);
    const fixed = new DataView(normalizeWav(streamed.buffer as ArrayBuffer));
    expect(fixed.getUint32(4, true)).toBe(streamed.byteLength - 8);
    expect(fixed.getUint32(40, true)).toBe(100);
    const mp3 = new Uint8Array(64).fill(7).buffer;
    expect(normalizeWav(mp3)).toBe(mp3);
  });
});

describe('gọi thẳng nhà cung cấp bằng khóa của người dùng', () => {
  it('OpenAI: Bearer, model, giọng mặc định và WAV', async () => {
    const { url, init, headers, blob } = await sent('openai', { key: 'sk-user' }, new Response(riff()));
    expect(url).toBe('https://api.openai.com/v1/audio/speech');
    expect(headers.Authorization).toBe('Bearer sk-user');
    expect(JSON.parse(String(init.body))).toEqual({ model: 'tts-1', input: 'Hello', voice: 'nova', response_format: 'wav' });
    expect(text(await bytes(blob), 0)).toBe('RIFF');
  });

  it('máy chủ tương thích OpenAI: bỏ dấu / cuối địa chỉ, không có khóa thì không gửi Authorization', async () => {
    const { url, headers, init } = await sent('compat', { baseUrl: 'http://127.0.0.1:8880/v1/', voice: 'af_heart' }, new Response(riff()));
    expect(url).toBe('http://127.0.0.1:8880/v1/audio/speech');
    expect(headers.Authorization).toBeUndefined();
    expect(JSON.parse(String(init.body))).toMatchObject({ model: 'tts-1', voice: 'af_heart' });
  });

  it('ElevenLabs: xin WAV 24 kHz, mã giọng được mã hóa trong đường dẫn', async () => {
    const { url, headers, init } = await sent('elevenlabs', { key: 'el-key', voice: 'a b' }, new Response(riff()));
    expect(url).toBe('https://api.elevenlabs.io/v1/text-to-speech/a%20b?output_format=wav_24000');
    expect(headers['xi-api-key']).toBe('el-key');
    expect(JSON.parse(String(init.body))).toEqual({ text: 'Hello', model_id: 'eleven_multilingual_v2' });
  });

  it('ElevenLabs chưa chọn giọng thì báo, không gọi', async () => {
    await expect(speakWithKey(provider('elevenlabs'), { key: 'k' }, 'Hi', signal())).rejects.toThrow(/Chọn một giọng ElevenLabs/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('Azure: SSML thoát ký tự đặc biệt, gọi đúng vùng và xin PCM 24 kHz', async () => {
    const { url, headers, init } = await sent('azure', { key: 'az', region: 'SouthEastAsia' }, new Response(riff()), 'Tom & <Jerry>');
    expect(url).toBe('https://southeastasia.tts.speech.microsoft.com/cognitiveservices/v1');
    expect(headers['Ocp-Apim-Subscription-Key']).toBe('az');
    expect(headers['X-Microsoft-OutputFormat']).toBe('riff-24khz-16bit-mono-pcm');
    expect(String(init.body)).toContain('<voice name="en-US-AvaMultilingualNeural">Tom &amp; &lt;Jerry&gt;</voice>');
  });

  it('Gemini: gọi Interactions API, PCM trả về được bọc thành WAV', async () => {
    const pcm = btoa(String.fromCharCode(...new Uint8Array(48)));
    const response = new Response(JSON.stringify({ outputs: [{ type: 'audio', output_audio: { data: pcm, mime_type: 'audio/L16' } }] }));
    const { url, headers, init, blob } = await sent('gemini', { key: 'AIza-user', voice: 'Puck' }, response);
    expect(url).toBe('https://generativelanguage.googleapis.com/v1beta/interactions');
    expect(headers['x-goog-api-key']).toBe('AIza-user');
    expect(JSON.parse(String(init.body))).toMatchObject({
      model: 'gemini-3.8-flash-tts',
      input: [{ type: 'user_input', content: [{ type: 'text', text: 'Hello' }] }],
      generation_config: { speech_config: [{ voice: 'Puck' }] },
    });
    const wav = await bytes(blob);
    expect(text(wav, 0)).toBe('RIFF');
    expect(wav.byteLength).toBe(44 + 48);
  });

  it('Gemini không trả âm thanh thì báo rõ', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ outputs: [{ type: 'text', text: 'no' }] })));
    await expect(speakWithKey(provider('gemini'), { key: 'k' }, 'Hi', signal())).rejects.toThrow(/Gemini không trả về âm thanh/);
  });

  it('MiniMax: giải mã âm thanh dạng hex, mã lỗi khóa thành câu báo khóa sai', async () => {
    const hex = [...riff()].map((value) => value.toString(16).padStart(2, '0')).join('');
    const ok = await sent('minimax', { key: 'mm' }, new Response(JSON.stringify({ data: { audio: hex }, base_resp: { status_code: 0 } })));
    expect(ok.url).toBe('https://api.minimax.io/v1/t2a_v2');
    expect(ok.headers.Authorization).toBe('Bearer mm');
    expect(JSON.parse(String(ok.init.body))).toMatchObject({
      model: 'speech-2.8-turbo', output_format: 'hex', voice_setting: { voice_id: 'English_radiant_girl' },
    });
    expect(text(await bytes(ok.blob), 0)).toBe('RIFF');

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ base_resp: { status_code: 1004, status_msg: 'auth' } })));
    await expect(speakWithKey(provider('minimax'), { key: 'bad' }, 'Hi', signal())).rejects.toThrow(/Khóa MiniMax không đúng/);
  });

  it('Alibaba Cloud (Qwen) đi qua máy chủ Peto: khóa trong header, vùng Trung Quốc được giữ', async () => {
    const { url, headers, init } = await sent('qwen', { key: 'sk-qwen', region: 'cn' }, new Response(riff()));
    expect(url).toBe('/api/voice/relay');
    expect(headers['X-Voice-Key']).toBe('sk-qwen');
    expect(JSON.parse(String(init.body))).toEqual({
      provider: 'qwen', text: 'Hello', voice: 'Cherry', model: 'qwen3-tts-flash', region: 'cn',
    });
  });

  it('lỗi từ máy chủ chuyển tiếp được hiện nguyên câu tiếng Việt', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Khóa StepFun không đúng hoặc đã bị thu hồi.' }), { status: 400 }));
    await expect(speakWithKey(provider('stepfun'), { key: 'x' }, 'Hi', signal())).rejects.toThrow('Khóa StepFun không đúng hoặc đã bị thu hồi.');
  });

  it.each([
    [401, /Khóa OpenAI không đúng/],
    [402, /hết số dư/],
    [429, /giới hạn lượt gọi/],
    [404, /không nhận giọng hoặc model/],
    [500, /mã 500/],
  ])('mã %i thành câu báo tiếng Việt', async (status, message) => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status }));
    await expect(speakWithKey(provider('openai'), { key: 'k' }, 'Hi', signal())).rejects.toThrow(message);
  });

  it('không gọi được từ trình duyệt (mạng, CORS) thì nói rõ', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(speakWithKey(provider('openai'), { key: 'k' }, 'Hi', signal())).rejects.toThrow(/Không gọi được OpenAI từ trình duyệt/);
  });
});

describe('giọng gợi ý có sẵn', () => {
  const ids = (model: string) => suggestedVoices(provider('qwen'), model).map((voice) => voice.id);
  const AIRI = ['longwan', 'longcheng', 'longhua', 'longxiaochun', 'longxiaoxia', 'longxiaocheng', 'longxiaobai',
    'longlaotie', 'longshu', 'longshuo', 'longjing', 'longmiao', 'longyue', 'longyuan', 'longfei', 'longjielidou',
    'longtong', 'longxiang', 'loongstella', 'loongbella'];

  it('CosyVoice v2 giữ 18 trên 20 giọng AIRI (v1 ngừng ngày 10/10/2026), v3 Flash giữ 14', () => {
    expect(AIRI.filter((voice) => ids('cosyvoice-v2').includes(`${voice}_v2`))).toHaveLength(18);
    expect(AIRI.filter((voice) => ids('cosyvoice-v3-flash').includes(`${voice}_v3`))).toHaveLength(14);
  });

  it.each(['cosyvoice-v2', 'cosyvoice-v3-flash'])('%s: mã không trùng, có tên, mô tả, nhóm, qua được máy chủ chuyển tiếp', (model) => {
    const voices = suggestedVoices(provider('qwen'), model);
    expect(new Set(voices.map((voice) => voice.id)).size).toBe(voices.length);
    expect(voices.every((voice) => voice.label && voice.hint && voice.group)).toBe(true);
    expect(voices.every((voice) => /^[\w.\- ]{1,64}$/.test(voice.id))).toBe(true);
    expect(voices.map((voice) => voice.id)).toContain(defaultVoiceOf(provider('qwen'), model));
    // Companion trả lời bằng tiếng Anh: giọng chỉ nói tiếng Nhật, Hàn không có trong danh sách.
    expect(voices.some((voice) => /yuuna|tomoka|jihun|kyong/.test(voice.id))).toBe(false);
  });

  it('tên hiện của giọng CosyVoice: tên tiếng Trung kèm phiên âm, hay tên Latin', () => {
    const label = (id: string) => suggestedVoices(provider('qwen'), 'cosyvoice-v2').find((voice) => voice.id === id)?.label;
    expect(label('longwan_v2')).toBe('龙婉 · Long Wan');
    expect(label('loongstella_v2')).toBe('Stella');
    expect(label('libai_v2')).toBe('李白 · Li Bai');
    expect(voiceOf(provider('qwen'), { model: 'cosyvoice-v3-flash' })).toBe('longanhuan');
    expect(voiceOf(provider('qwen'), {})).toBe('Cherry');
  });

  it('Qwen: đủ 48 giọng của qwen3-tts-flash, có mô tả, 10 giọng phương ngữ, mã qua được máy chủ chuyển tiếp', () => {
    const voices = provider('qwen').voices ?? [];
    expect(voices).toHaveLength(48);
    expect(new Set(voices.map((voice) => voice.id)).size).toBe(48);
    expect(voices.every((voice) => voice.hint?.trim())).toBe(true);
    expect(voices.filter((voice) => voice.group === 'Phương ngữ Trung Quốc').map((voice) => voice.id)).toEqual(
      ['Jada', 'Dylan', 'Li', 'Marcus', 'Roy', 'Peter', 'Sunny', 'Eric', 'Rocky', 'Kiki'],
    );
    // Cùng luật với RELAY_TEXT trong backend/voice_api.py: mã có dấu cách như "Eldric Sage" vẫn phải qua được.
    expect(voices.every((voice) => /^[\w.\- ]{1,64}$/.test(voice.id))).toBe(true);
    expect(voices.map((voice) => voice.id)).toContain(provider('qwen').defaultVoice);
  });
});

describe('danh sách giọng tải bằng khóa', () => {
  it('ElevenLabs: lấy mã và tên giọng', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ voices: [{ voice_id: 'v1', name: 'Rachel' }, { name: 'thiếu mã' }] })));
    expect(await listKeyVoices(provider('elevenlabs'), { key: 'k' }, signal())).toEqual([{ id: 'v1', label: 'Rachel' }]);
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.elevenlabs.io/v2/voices?page_size=100');
  });

  it('Azure: chỉ giữ giọng tiếng Anh, Việt, Nhật', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([
      { ShortName: 'en-US-AvaMultilingualNeural', DisplayName: 'Ava', LocaleName: 'English (United States)', Locale: 'en-US' },
      { ShortName: 'vi-VN-HoaiMyNeural', DisplayName: 'HoaiMy', LocaleName: 'Vietnamese (Vietnam)', Locale: 'vi-VN' },
      { ShortName: 'de-DE-KatjaNeural', DisplayName: 'Katja', LocaleName: 'German (Germany)', Locale: 'de-DE' },
    ])));
    const voices = await listKeyVoices(provider('azure'), { key: 'k', region: 'eastus' }, signal());
    expect(voices?.map((voice) => voice.id)).toEqual(['en-US-AvaMultilingualNeural', 'vi-VN-HoaiMyNeural']);
    expect(fetchMock.mock.calls[0][0]).toBe('https://eastus.tts.speech.microsoft.com/cognitiveservices/voices/list');
  });

  it('nhà cung cấp có danh sách cố định thì không gọi gì', async () => {
    expect(await listKeyVoices(provider('openai'), { key: 'k' }, signal())).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
