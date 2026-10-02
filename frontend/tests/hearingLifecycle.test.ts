import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getHearingState, loadHearingSettings, setHearingPaused, setHearingSink, setHearingTestSink,
  startListening, stopListening } from '../src/features/companion/speech/hearingEngine';
import { openMicrophone } from '../src/features/companion/speech/hearingCapture';
import { transcribeWithKey } from '../src/features/companion/speech/hearingProviders';

vi.mock('../src/features/companion/speech/hearingCapture', () => ({
  captureSupported: () => true,
  openMicrophone: vi.fn(),
}));
vi.mock('../src/features/companion/speech/hearingProviders', async original => ({
  ...await original<typeof import('../src/features/companion/speech/hearingProviders')>(),
  transcribeWithKey: vi.fn(),
}));

class Recognition {
  static all: Recognition[] = [];
  onstart?: () => void;
  onresult?: (event: unknown) => void;
  abort = vi.fn();
  constructor() { Recognition.all.push(this); }
  start() { this.onstart?.(); }
  say(text: string, isFinal = true) { this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] }); }
}
const final = vi.fn(), stopped = vi.fn();
let chunk: (samples: Float32Array) => void;
let interrupted: ((error: Error) => void) | undefined;
const sentence = () => {
  for (let i = 0; i < 10; i++) chunk(new Float32Array(1024).fill(0.2));
  for (let i = 0; i < 20; i++) chunk(new Float32Array(1024));
};
beforeEach(() => {
  localStorage.clear();
  loadHearingSettings();
  Recognition.all = [];
  final.mockClear(); stopped.mockClear();
  vi.stubGlobal('SpeechRecognition', Recognition);
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
  vi.mocked(openMicrophone).mockImplementation(async (_device, callback, onInterrupted) => {
    chunk = callback; interrupted = onInterrupted;
    return { sampleRate: 16000, stop: stopped };
  });
  vi.mocked(transcribeWithKey).mockReset();
  setHearingSink({ onFinal: final });
});
afterEach(() => {
  stopListening(); setHearingPaused(false); setHearingSink(null); setHearingTestSink(null);
  vi.useRealTimers(); vi.unstubAllGlobals();
});

it.each(['hidden', 'offline', 'pagehide'])('dừng micro khi %s, giữ chữ dở và không tự mở hay nhận phiên cũ', async event => {
  await startListening();
  const first = Recognition.all[0];
  first.say('An unfinished sentence', false);
  if (event === 'hidden') {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
  } else window.dispatchEvent(new Event(event));
  expect(getHearingState()).toMatchObject({ listening: false, phase: 'off', interim: '' });
  expect(final).toHaveBeenCalledWith('An unfinished sentence', false, undefined);
  expect(first.abort).toHaveBeenCalledOnce(); expect(stopped).toHaveBeenCalledOnce();
  first.say('Late words');
  expect(final).toHaveBeenCalledOnce();
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('online'));
  expect(Recognition.all).toHaveLength(1);
  await startListening(); Recognition.all.at(-1)!.say('New words');
  expect(final.mock.calls.at(-1)?.[0]).toBe('New words');
});

it('nghe thử xuống nền giữ chữ riêng trong Cài đặt', async () => {
  const tested = vi.fn(); setHearingTestSink({ onFinal: tested });
  await startListening('test'); Recognition.all[0].say('Test only', false);
  window.dispatchEvent(new Event('pagehide'));
  expect(tested).toHaveBeenCalledWith('Test only', false, undefined);
  expect(final).not.toHaveBeenCalled();
});

it('xuống nền khi xin quyền micro chưa xong thì giải phóng capture đến muộn', async () => {
  let complete!: (value: Awaited<ReturnType<typeof openMicrophone>>) => void;
  vi.mocked(openMicrophone).mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  await startListening(); window.dispatchEvent(new Event('pagehide'));
  complete({ sampleRate: 16000, stop: stopped }); await Promise.resolve();
  expect(stopped).toHaveBeenCalledOnce(); expect(getHearingState().listening).toBe(false);
});

function keySource() {
  localStorage.setItem('peto-hearing-source', 'groq');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ groq: { key: 'test-key' } }));
  loadHearingSettings();
}
it('micro nguồn khóa bị ngắt không giữ trạng thái đang nghe', async () => {
  keySource(); await startListening(); interrupted!(new Error('Micro đã bị ngắt'));
  expect(getHearingState()).toMatchObject({ listening: false, phase: 'off', message: 'Micro đã bị ngắt' });
  expect(stopped).toHaveBeenCalledOnce();
});

it('dịch vụ treo không tích quá ba câu; hết thời gian vẫn chép được câu tiếp', async () => {
  vi.useFakeTimers(); keySource();
  let firstSignal!: AbortSignal;
  vi.mocked(transcribeWithKey).mockImplementationOnce(async (_provider, _config, _audio, _language, signal) => {
    firstSignal = signal; return new Promise(() => {});
  }).mockResolvedValue('Next sentence');
  await startListening();
  for (let i = 0; i < 10; i++) sentence();
  await vi.advanceTimersByTimeAsync(0);
  expect(transcribeWithKey).toHaveBeenCalledOnce();
  expect(getHearingState().message).toContain('chép chậm');
  await vi.advanceTimersByTimeAsync(30000);
  expect(firstSignal.aborted).toBe(true);
  expect(transcribeWithKey).toHaveBeenCalledTimes(3);
  expect(final).toHaveBeenCalledTimes(2);
  expect(getHearingState().phase).toBe('waiting');
  sentence(); await vi.advanceTimersByTimeAsync(0);
  expect(transcribeWithKey).toHaveBeenCalledTimes(4);
});

it('hủy phiên đang chép lời không để kết quả tới muộn vào bản nháp mới', async () => {
  keySource(); let resolve!: (text: string) => void;
  vi.mocked(transcribeWithKey).mockImplementationOnce(() => new Promise(done => { resolve = done; })).mockResolvedValue('New sentence');
  await startListening(); sentence();
  await vi.waitFor(() => expect(transcribeWithKey).toHaveBeenCalledOnce());
  window.dispatchEvent(new Event('offline'));
  await startListening(); sentence();
  await vi.waitFor(() => expect(final).toHaveBeenCalledOnce());
  resolve('Stale sentence'); await Promise.resolve();
  expect(final.mock.calls[0][0]).toBe('New sentence'); expect(final).toHaveBeenCalledOnce();
});
