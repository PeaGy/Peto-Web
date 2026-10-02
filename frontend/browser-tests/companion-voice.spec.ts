import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

test.use({ launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });

test('nhép miệng theo tiếng nén giải mã thật, im lặng/dừng thì đóng', async ({ page }) => {
  await mockPeto(page);
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const path = '/src/features/companion/speech/voiceActivity.ts';
    const { trackVoice, voiceMouth } = await import(/* @vite-ignore */ path);
    // Tạo tiếng nén bằng trình duyệt; không dùng micro, nhà cung cấp hay tệp bên ngoài.
    const context = new AudioContext();
    await context.resume();
    const destination = context.createMediaStreamDestination();
    const source = context.createBufferSource();
    const signal = context.createBuffer(1, context.sampleRate, context.sampleRate);
    const samples = signal.getChannelData(0);
    for (let i = Math.floor(context.sampleRate * 0.15); i < samples.length; i++) samples[i] = Math.sin(i * 2 * Math.PI * 440 / context.sampleRate) * 0.3;
    source.buffer = signal;
    source.connect(destination);
    const recorder = new MediaRecorder(destination.stream, { mimeType: 'audio/webm;codecs=opus' });
    const pieces: Blob[] = [];
    recorder.ondataavailable = event => pieces.push(event.data);
    const recorded = new Promise<void>(resolve => { recorder.onstop = () => resolve(); });
    recorder.start(); source.start();
    await new Promise(resolve => setTimeout(resolve, 1100));
    recorder.stop(); await recorded;
    destination.stream.getTracks().forEach(track => track.stop());
    await context.close();
    const blob = new Blob(pieces, { type: recorder.mimeType });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    const stop = trackVoice(audio, blob);
    await audio.play();
    let mouth = 0;
    const deadline = performance.now() + 3000;
    while (!audio.ended && performance.now() < deadline) {
      mouth = Math.max(mouth, voiceMouth());
      if (mouth > 0.5) break;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    const playingAt = audio.currentTime;
    audio.pause();
    const paused = voiceMouth();
    stop();
    const stopped = voiceMouth();
    URL.revokeObjectURL(url);
    return { mouth, paused, stopped, playingAt, bytes: blob.size, type: blob.type };
  });
  expect(result.type).toContain('opus');
  expect(result.bytes).toBeGreaterThan(100);
  expect(result.playingAt).toBeGreaterThan(0.1);
  expect(result.mouth).toBeGreaterThan(0.5);
  expect(result.paused).toBe(0);
  expect(result.stopped).toBe(0);
});

test('Companion gõ/nghĩ/nói/chờ/dừng và rời tab giữ giao diện gọn trên máy tính lẫn điện thoại', async ({ page }) => {
  await mockPeto(page);
  await page.addInitScript(() => {
    localStorage.setItem('peto-local-voice', '1');
    localStorage.setItem('peto-companion-muted', '0');
    class AudioStub {
      static current: AudioStub;
      onplaying: (() => void) | null = null;
      onwaiting: (() => void) | null = null;
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onpause: (() => void) | null = null;
      ready!: () => void;
      constructor() { AudioStub.current = this; }
      play() { return new Promise<void>(resolve => { this.ready = resolve; }); }
      pause() { this.onpause?.(); }
      addEventListener() {}
      removeEventListener() {}
    }
    Object.assign(window, { Audio: AudioStub, testVoice: {
      start() { AudioStub.current.onplaying?.(); AudioStub.current.ready(); },
      wait() { AudioStub.current.onwaiting?.(); },
      end() { AudioStub.current.onended?.(); },
    } });
  });
  // Chỉ thay lớp vẽ WebGL để đọc trạng thái; bộ chat, âm thanh và CSS dùng mã thật.
  await page.route('**/characters/Live2DStage.tsx*', async route => {
    const source = await (await route.fetch()).text();
    const reactUrl = source.match(/["'](\/node_modules\/\.vite\/deps\/react\.js[^"']*)["']/)?.[1];
    if (!reactUrl) throw new Error('Chưa tìm thấy module React dùng chung cho sân khấu giả.');
    await route.fulfill({ contentType: 'text/javascript', body:
      `import React from ${JSON.stringify(reactUrl)}; export default function Stage({activity, emotion, onStatusChange}) { React.useEffect(() => { onStatusChange?.('ready'); }, [onStatusChange]); return React.createElement('div', {'data-testid':'stage-state', 'data-activity':activity, 'data-emotion':emotion?.emotion ?? ''}); }` });
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
  const stage = page.getByTestId('stage-state');
  const composer = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await expect(composer).toBeVisible();
  await expect(page.getByRole('button', { name: 'Tắt tiếng', exact: true })).toBeVisible();
  await composer.fill('Hello Peto');
  await expect(stage).toHaveAttribute('data-activity', 'listening');
  await expect(stage).toHaveAttribute('data-activity', 'idle');
  await expect(composer).toHaveValue('Hello Peto');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Đang chuẩn bị giọng đọc, bấm để dừng' })).toBeVisible();
  await expect(stage).toHaveAttribute('data-activity', 'thinking');
  const signalVoice = (action: 'start' | 'wait' | 'end') => page.evaluate(action => {
    (window as unknown as { testVoice: Record<string, () => void> }).testVoice[action]();
  }, action);
  await signalVoice('start');
  await expect(stage).toHaveAttribute('data-activity', 'speaking');
  await signalVoice('wait');
  await expect(stage).toHaveAttribute('data-activity', 'thinking');
  await signalVoice('start');
  await expect(stage).toHaveAttribute('data-activity', 'speaking');
  await page.getByRole('button', { name: 'Dừng đọc', exact: true }).click();
  await expect(stage).toHaveAttribute('data-activity', 'idle');
  await noPageOverflow(page);
  await page.getByRole('button', { name: 'Nghe Peto đọc tin này' }).last().click();
  await signalVoice('start');
  await expect(stage).toHaveAttribute('data-activity', 'speaking');
  if (!await page.locator('.sidebar').isVisible()) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Trò chuyện', exact: true }).click();
  await expect(stage).toHaveCount(0);
});
