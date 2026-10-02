import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

const fakeAudioPath = decodeURIComponent(new URL('./fixtures/hearing.wav', import.meta.url).pathname).replace(/^\/([A-Za-z]:\/)/, '$1');
test.use({ permissions: ['microphone'], launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
  `--use-file-for-fake-audio-capture=${fakeAudioPath}`] } });

test('bật nói chen trong Cài đặt rồi ngắt SSE và tiếng; giữ micro, lời mới và bố cục PC/điện thoại', async ({ page }) => {
  await mockPeto(page);
  await page.addInitScript(() => {
    localStorage.setItem('peto-local-voice', '1'); localStorage.setItem('peto-companion-muted', '0');
    // SSE thật qua fetch, dịch vụ và thiết bị giả để chủ động tạo tình huống nói chen.
    const original = window.fetch;
    const turns: { emit(value: object): void; aborted: boolean }[] = [];
    window.fetch = async (input, init) => {
      if (String(input) !== '/api/chat') return original(input, init);
      let ended = false;
      const body = new ReadableStream<Uint8Array>({ start(controller) {
        const turn = { aborted: false, emit(value: object) {
          if (ended) return;
          controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(value)}\n\n`));
          if ((value as { type?: string }).type === 'done') { ended = true; controller.close(); }
        } };
        turns.push(turn);
        init?.signal?.addEventListener('abort', () => {
          turn.aborted = true;
          if (!ended) { ended = true; controller.error(new DOMException('Đã dừng', 'AbortError')); }
        }, { once: true });
      } });
      return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
    };
    class AudioStub {
      static instances: AudioStub[] = [];
      onplaying = null; onwaiting = null; onended = null; onerror = null; onpause = null;
      paused = false;
      constructor() { AudioStub.instances.push(this); }
      play() { return Promise.resolve(); }
      pause() { this.paused = true; }
      addEventListener() {} removeEventListener() {}
    }
    type Result = { resultIndex: number; results: { isFinal: boolean; 0: { transcript: string } }[] };
    class Recognition {
      static instances: Recognition[] = [];
      lang = ''; continuous = false; interimResults = false; aborted = false;
      onstart: (() => void) | null = null;
      onresult: ((event: Result) => void) | null = null;
      onerror = null; onend = null; onspeechend = null;
      onspeechstart: (() => void) | null = null;
      constructor() { Recognition.instances.push(this); }
      start() { setTimeout(() => this.onstart?.(), 30); }
      stop() { this.aborted = true; }
      abort() { this.aborted = true; }
      say(text: string, isFinal: boolean) {
        this.onspeechstart?.();
        this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
      }
    }
    Object.assign(window, { Audio: AudioStub, SpeechRecognition: Recognition, testBargeIn: {
      turns, audios: AudioStub.instances, recognitions: Recognition.instances,
      say(text: string, final: boolean) { Recognition.instances.at(-1)?.say(text, final); },
    } });
  });
  await page.route('**/api/voice/health', route => route.fulfill({ json: {
    ok: true, voices: ['stepfun:jilingshaonv'], home: { online: false, voices: [] },
    official: { allowed: true, voices: ['stepfun:jilingshaonv'], used: 0, limit: 5000 },
  } }));
  await page.route('**/api/voice/speak', route => route.fulfill({ contentType: 'audio/wav', body: 'RIFF' }));
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Companion', exact: true }).click();
  const composer = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  const panel = page.getByRole('region', { name: 'Trò chuyện trong Companion' });
  await expect(page.getByRole('button', { name: 'Tắt tiếng', exact: true })).toBeVisible();
  if (!await page.locator('.sidebar').isVisible()) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Tài khoản · Người kiểm thử' }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  await settings.getByRole('button', { name: 'Giọng nói', exact: true }).click();
  await settings.getByRole('tab', { name: 'Peto nghe' }).click();
  const barge = settings.getByRole('switch', { name: 'Cho phép nói chen' });
  await expect(barge).not.toBeChecked();
  await barge.check();
  await expect(settings.getByRole('switch', { name: 'Tạm không nghe khi Peto đang nói' })).toBeDisabled();
  await expect(settings.getByRole('switch', { name: 'Tự gửi khi nói xong' })).not.toBeChecked();
  await settings.getByRole('button', { name: 'Đóng cài đặt' }).click();
  if (page.viewportSize()!.width < 768 && await page.locator('.sidebar').isVisible()) {
    await page.getByRole('button', { name: 'Đóng danh sách hội thoại' }).click({ position: { x: page.viewportSize()!.width - 5, y: 300 } });
  }
  await page.getByRole('button', { name: 'Bật nghe', exact: true }).click();
  await expect(page.locator('.hearing-mic')).toHaveClass(/waiting/);
  type BargeState = {
    turns: { emit(value: object): void; aborted: boolean }[];
    audios: { paused: boolean }[]; recognitions: { aborted: boolean }[];
    say(text: string, final: boolean): void;
  };
  const state = () => page.evaluate(() => {
    const value = (window as unknown as { testBargeIn: BargeState }).testBargeIn;
    return { turns: value.turns.map(t => t.aborted), audios: value.audios.map(a => a.paused),
      recognitions: value.recognitions.map(r => r.aborted) };
  });
  const say = (text: string, final: boolean) => page.evaluate(({ text, final }) => {
    (window as unknown as { testBargeIn: BargeState }).testBargeIn.say(text, final);
  }, { text, final });
  const emit = (index: number, value: object) => page.evaluate(({ index, value }) => {
    (window as unknown as { testBargeIn: BargeState }).testBargeIn.turns[index].emit(value);
  }, { index, value });
  await say('Hello Peto', true);
  await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(async () => (await state()).turns.length).toBe(1);
  await emit(0, { type: 'meta', conversation_id: 'A', effort: 'low', voice_stream: true });
  await emit(0, { type: 'delta', text: 'Let me explain. ' });
  await expect(panel.getByText('Đang nói…', { exact: true })).toBeVisible();
  expect((await state()).recognitions).toEqual([false]);
  await composer.fill('Actually,');
  await say('wait please', false);
  await expect(composer).toHaveValue('Actually, wait please');
  await expect.poll(async () => (await state()).turns[0]).toBe(true);
  await expect.poll(async () => (await state()).audios[0]).toBe(true);
  await emit(0, { type: 'delta', text: 'Late old words. ' });
  await expect(panel.getByText(/Late old words/)).toHaveCount(0);
  await say('wait please, I meant something else', true);
  await expect(composer).toHaveValue('Actually, wait please, I meant something else');
  await expect(page.locator('.hearing-mic')).toHaveClass(/waiting/);
  expect((await state()).recognitions).toEqual([false]);
  await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(async () => (await state()).turns.length).toBe(2);
  await emit(1, { type: 'meta', conversation_id: 'A', effort: 'low', voice_stream: true });
  await emit(1, { type: 'delta', text: 'A fresh reply. ' });
  await emit(1, { type: 'done' });
  await expect(panel.getByText('Đang nói…', { exact: true })).toBeVisible();
  // Đã nhận hết chữ nhưng tiếng vẫn đang đọc cũng ngắt được, không tạo lại bộ nghe.
  await say('One more thing', true);
  await expect(composer).toHaveValue('One more thing');
  await expect.poll(async () => (await state()).audios.at(-1)).toBe(true);
  await expect(panel.getByText('Đang nói…', { exact: true })).toHaveCount(0);
  expect((await state()).recognitions).toEqual([false]);
  expect((await state()).turns).toHaveLength(2);
  await noPageOverflow(page);
});
