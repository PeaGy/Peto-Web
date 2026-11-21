import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

// Nhập giọng nói ở ô nhắn Chat (G5): micro giả của Chromium, nhận giọng giả ghi lại micro và ngôn ngữ được dùng. Menu
// cạnh micro, danh sách micro, ô tìm ngôn ngữ và ô nhắn là mã sản phẩm thật.
test.use({ permissions: ['microphone'], launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] } });

async function installRecognition(page: Page) {
  await page.addInitScript(() => {
    type Result = { resultIndex: number; results: { isFinal: boolean; 0: { transcript: string } }[] };
    const started: { lang: string; track: string | null }[] = [];
    class Recognition {
      static last: Recognition | null = null;
      lang = '';
      continuous = false;
      interimResults = false;
      onstart: (() => void) | null = null;
      onresult: ((event: Result) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      onspeechstart: (() => void) | null = null;
      onspeechend: (() => void) | null = null;
      constructor() { Recognition.last = this; }
      start(track?: MediaStreamTrack) {
        started.push({ lang: this.lang, track: track ? track.label : null });
        setTimeout(() => this.onstart?.(), 30);
      }
      stop() { setTimeout(() => this.onend?.(), 30); }
      abort() {}
    }
    Object.assign(window, {
      SpeechRecognition: Recognition,
      testDictation: {
        started,
        say(text: string, isFinal: boolean) {
          Recognition.last?.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
        },
      },
    });
  });
}

test('điện thoại giải thích khi micro bị chặn và giữ nguyên bản nháp', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile');
  await mockPeto(page);
  await page.addInitScript(() => {
    class BlockedRecognition {
      onerror?: (event: { error: string }) => void;
      start() { setTimeout(() => this.onerror?.({ error: 'not-allowed' }), 0); }
      stop() {}
      abort() {}
    }
    Object.assign(window, { SpeechRecognition: BlockedRecognition });
  });
  await page.goto('/');
  const draft = page.getByLabel('Nhắn cho Peto', { exact: true });
  await draft.fill('Nháp vẫn còn');
  await page.getByRole('button', { name: 'Nói để nhập' }).click();
  const sheet = page.getByRole('dialog', { name: 'Nhập giọng nói', exact: true });
  await expect(sheet.getByRole('alert')).toContainText('Chưa được phép');
  await sheet.getByRole('button', { name: 'Đã hiểu' }).click();
  await expect(sheet).toHaveCount(0);
  await expect(draft).toHaveValue('Nháp vẫn còn');
});

test('menu cạnh micro: chọn micro, tìm và đổi ngôn ngữ, nhớ qua F5, nghe đúng micro và ngôn ngữ đã chọn', async ({ page }) => {
  // Giữ lựa chọn trong localStorage qua F5 (mặc định fixture xóa chúng mỗi lần tải trang).
  await mockPeto(page, { preservePreferences: true });
  await installRecognition(page);
  await page.goto('/');
  const composer = page.getByLabel('Nhắn cho Peto', { exact: true });
  await expect(composer).toBeVisible();
  await page.getByRole('button', { name: 'Cài đặt nhập giọng nói' }).click();
  const menu = page.getByRole('menu', { name: 'Nhập giọng nói' });
  await expect(menu).toBeVisible();
  // Chọn micro theo nhãn trình duyệt (dictationPrefs.deviceChoiceSupported). Bản điện thoại giả lập của Playwright vẫn
  // là Chromium máy tính nên chọn được; điện thoại thật báo userAgentData.mobile và chỉ có micro mặc định.
  const mobile = await page.evaluate(() => Boolean((navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData?.mobile));
  const devices = menu.locator('.dictation-device');
  if (mobile) {
    await expect(devices).toHaveCount(1);
    await expect(devices).toHaveText(/Micro mặc định của máy/);
  } else {
    await expect.poll(() => devices.count()).toBeGreaterThan(1);
    await expect(menu.getByRole('menuitemradio', { checked: true })).toHaveCount(1);
  }
  await noPageOverflow(page);
  // Màn hình trống: ô nhắn ở giữa; menu phải nằm trọn trong màn hình (ngày 20/11 nó tràn lên, mất phần đầu).
  const box = (await menu.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
  await expect(menu).toHaveScreenshot('dictation-menu.png', { mask: [menu.locator('.dictation-level-fill')] });
  // Tên micro thật thường dài ("Default - Microphone (A303 Headset) (0b05:1c33)"): dòng phải cao lên, không đè dòng dưới.
  const rows = await devices.evaluateAll((items) => {
    const label = items[0].querySelector('.effort-option-label')!;
    const before = label.textContent;
    label.textContent = 'Default - Microphone (A303 Headset) (0b05:1c33) Communications';
    const boxes = items.map((item) => item.getBoundingClientRect()).map((box) => ({ top: box.top, bottom: box.bottom, height: box.height }));
    label.textContent = before;
    return boxes;
  });
  expect(rows[0].height).toBeGreaterThan(40);
  for (let index = 1; index < rows.length; index += 1) expect(rows[index].top).toBeGreaterThanOrEqual(rows[index - 1].bottom - 0.5);

  let chosen = '';
  if (!mobile) {
    const checked = await devices.evaluateAll((items) => items.findIndex((item) => item.getAttribute('aria-checked') === 'true'));
    const other = devices.nth(checked === 0 ? 1 : 0);
    // Mã thiết bị đổi sau F5 (Chromium của Playwright), nên so theo tên micro: app phải tìm lại đúng micro theo tên.
    chosen = (await other.textContent())?.trim() ?? '';
    await other.click();
    await expect(other).toHaveAttribute('aria-checked', 'true');
  }

  await menu.getByRole('menuitem', { name: /Ngôn ngữ/ }).click();
  const languages = page.getByRole('menu', { name: 'Ngôn ngữ nghe' });
  const search = languages.getByRole('searchbox', { name: 'Tìm ngôn ngữ' });
  await expect(search).toBeFocused();
  await search.fill('tieng anh');
  await expect(languages.getByRole('menuitemradio')).toHaveText(['Tiếng Anh (Mỹ)', 'Tiếng Anh (Anh)']);
  await search.fill('xyz');
  await expect(languages.getByText('Không có ngôn ngữ nào khớp.')).toBeVisible();
  await search.fill('nhat');
  await search.press('Enter');
  await expect(languages).toHaveCount(0);

  await page.reload();
  await expect(composer).toBeVisible();
  await page.getByRole('button', { name: 'Cài đặt nhập giọng nói' }).click();
  await expect(page.getByRole('menuitem', { name: /Ngôn ngữ/ })).toContainText('Tiếng Nhật');
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: 'Nói để nhập' }).click();
  await expect(page.getByRole('button', { name: 'Xong nhập giọng nói' })).toBeVisible();
  await expect(composer).toHaveAttribute('placeholder', /Đang (nghe|mở micro)…/);
  // Micro đã chọn được mở trước (getUserMedia) rồi mới bắt đầu nghe: chờ lần start thật.
  const startedList = () => page.evaluate(() => (window as unknown as { testDictation: { started: { lang: string; track: string | null }[] } }).testDictation.started);
  await expect.poll(async () => (await startedList()).length).toBeGreaterThan(0);
  const started = await startedList();
  expect(started.at(-1)?.lang).toBe('ja-JP');
  // Máy tính: nghe từ đúng micro đã chọn; điện thoại: micro mặc định, không truyền track.
  expect(started.at(-1)?.track).toBe(mobile ? null : chosen);
  await page.evaluate(() => (window as unknown as { testDictation: { say(text: string, final: boolean): void } }).testDictation.say('こんにちは', true));
  await expect(composer).toHaveValue('こんにちは');
  await noPageOverflow(page);
  await expect(page.locator('.composer-bar')).toHaveScreenshot('dictation-listening.png', { mask: [page.locator('.dictation-wave')] });
  await page.getByRole('button', { name: 'Xong nhập giọng nói' }).click();
  await expect(page.getByRole('button', { name: 'Nói để nhập' })).toBeVisible();
});
