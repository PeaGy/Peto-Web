import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

// Micro và dịch vụ chép lời giả; AudioWorklet, bộ nghe, ô nhắn và bố cục là mã sản phẩm thật.
test.use({ permissions: ['microphone'], launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] } });

test('Companion nhận chữ, giữ câu dở khi tắt, chặn phiên cũ và tiếp tục nghe', async ({ page }) => {
  const state = await mockPeto(page);
  await page.addInitScript(() => {
    type Result = { resultIndex: number; results: { isFinal: boolean; 0: { transcript: string } }[] };
    class Recognition {
      static instances: Recognition[] = [];
      lang = '';
      continuous = false;
      interimResults = false;
      onstart: (() => void) | null = null;
      onresult: ((event: Result) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      onspeechstart: (() => void) | null = null;
      onspeechend: (() => void) | null = null;
      constructor() { Recognition.instances.push(this); }
      start() { setTimeout(() => this.onstart?.(), 30); }
      stop() {}
      abort() {}
      say(text: string, isFinal: boolean) {
        this.onspeechstart?.();
        this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
      }
    }
    Object.assign(window, {
      SpeechRecognition: Recognition,
      testHearing: {
        say(text: string, final: boolean, index?: number) {
          const recognizer = index === undefined ? Recognition.instances.at(-1) : Recognition.instances[index];
          recognizer?.say(text, final);
        },
      },
    });
  });
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Companion', exact: true }).click();
  const composer = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await expect(composer).toBeVisible();
  await page.getByRole('button', { name: 'Bật nghe', exact: true }).click();
  await expect(page.locator('.hearing-mic')).toHaveClass(/waiting/);
  // Thanh đo thật nhận các khúc âm thanh từ AudioWorklet của Chromium.
  await expect.poll(() => page.locator('.hearing-mic').evaluate(el => Number((el as HTMLElement).style.getPropertyValue('--hearing-level')))).toBeGreaterThan(0.02);
  const say = (text: string, final: boolean, index?: number) => page.evaluate(({ text, final, index }) => {
    (window as unknown as { testHearing: { say(text: string, final: boolean, index?: number): void } }).testHearing.say(text, final, index);
  }, { text, final, index });
  await say('Can you hear', false);
  await expect(composer).toHaveValue('Can you hear');
  await expect(composer).toHaveJSProperty('readOnly', true);
  await page.locator('.hearing-mic').click();
  await expect(composer).toHaveValue('Can you hear');
  await expect(composer).toHaveJSProperty('readOnly', false);
  await say('Late final from the old session', true, 0);
  await expect(composer).toHaveValue('Can you hear');
  await composer.fill('');
  await page.getByRole('button', { name: 'Bật nghe', exact: true }).click();
  await expect(page.locator('.hearing-mic')).toHaveClass(/waiting/);
  await say('Hello Peto, can you hear me?', true);
  await expect(composer).toHaveValue('Hello Peto, can you hear me?');
  expect(state.posts).toBe(0);
  await page.locator('.hearing-mic').click();
  await noPageOverflow(page);
});
