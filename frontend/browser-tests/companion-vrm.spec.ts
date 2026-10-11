import { expect, test, type Page } from '@playwright/test';
import { existsSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';
import type { VRM } from '@pixiv/three-vrm';
import { mockPeto } from './fixtures';

// Model có giấy phép riêng, chỉ nhập khi người chạy cung cấp tệp; không tải mạng hoặc đóng kèm bản phát hành.
const samplePath = process.env.PETO_VRM_SAMPLE_PATH;
type TestWindow = Window & {
  testVRM: VRM;
  stopTestVoice?: () => void;
};

test.use({ reducedMotion: 'no-preference', launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });
test.describe.configure({ timeout: 180000 });

async function faceValues(page: Page, name: string) {
  return page.evaluate(name => {
    const manager = (window as unknown as TestWindow).testVRM.expressionManager!;
    const expression = manager.getExpression(name)!;
    // Đọc cả morph trên mesh thật sau loaded.update(), kể cả override miệng/mắt trong metadata VRM.
    const morphs = expression.binds.flatMap(bind => {
      if (!('primitives' in bind) || !('index' in bind)) return [];
      const morph = bind as { primitives: { morphTargetInfluences?: number[] }[]; index: number };
      return morph.primitives.map(mesh => mesh.morphTargetInfluences?.[morph.index] ?? 0);
    });
    return { weight: manager.getValue(name) ?? 0, morph: Math.max(0, ...morphs) };
  }, name);
}

async function startVoice(page: Page) {
  await page.evaluate(async () => {
    const path = '/src/features/companion/speech/voiceActivity.ts';
    const { trackVoice } = await import(/* @vite-ignore */ path);
    // WAV PCM16 nhỏ và không phát ra loa: chạy đường nhép miệng thật, không gọi TTS hoặc AI.
    const rate = 16000, count = rate * 8;
    const bytes = new ArrayBuffer(44 + count * 2), view = new DataView(bytes);
    const text = (offset: number, value: string) => [...value].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
    text(0, 'RIFF'); view.setUint32(4, bytes.byteLength - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    text(36, 'data'); view.setUint32(40, count * 2, true);
    for (let i = 0; i < count; i++) view.setInt16(44 + i * 2, Math.sin(i * 2 * Math.PI * 440 / rate) * 15000, true);
    const blob = new Blob([bytes], { type: 'audio/wav' }), url = URL.createObjectURL(blob);
    const audio = new Audio(url); audio.muted = true; audio.loop = true;
    const stop = trackVoice(audio, blob, bytes);
    (window as unknown as TestWindow).stopTestVoice = () => { audio.pause(); stop(); URL.revokeObjectURL(url); };
    await audio.play();
  });
}

for (const baseline of [true, false]) {
  test(`VRM thật: ${baseline ? 'mức cũ' : 'mức nhẹ'} giữ chuyển mặt, chớp mắt và khẩu hình`, async ({ page }, info) => {
    test.skip(!samplePath || !existsSync(samplePath), 'Cần PETO_VRM_SAMPLE_PATH trỏ tới VRM1_Constraint_Twist_Sample.vrm.');
    await mockPeto(page);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    // Chỉ gắn điểm đọc model trong phản hồi module của bài kiểm tra; mã sản phẩm không có debug hook.
    await page.route('**/characters/VRMStage.tsx*', async route => {
      const source = await (await route.fetch()).text();
      const marker = 'const loaded = gltf.userData.vrm;';
      expect(source).toContain(marker);
      expect(source).toContain('new Blinker()');
      // Chọn khoảng chớp mắt ngắn nhất hợp lệ để kiểm tra không phụ thuộc ngẫu nhiên/tốc độ GPU.
      const body = source.replace(marker, `${marker} window.testVRM = loaded;`).replace('new Blinker()', 'new Blinker(() => 0)');
      await route.fulfill({ contentType: 'text/javascript', body });
    });
    if (baseline) await page.route('**/characters/builtinFaces.ts*', async route => {
      let source = await (await route.fetch()).text();
      // So sánh chỉ ba trọng số cũ; tốc độ, renderer và mọi đường xử lý còn lại dùng cùng mã thật.
      for (const [name, value] of [['happy', '0.7'], ['sad', '0.7'], ['surprised', '0.8']]) {
        const preset = new RegExp(`(expressions:\\s*\\[\\["${name}",\\s*)0?${value.slice(1).replace('.', '\\.')}([\\]\\]])`);
        expect(source).toMatch(preset);
        source = source.replace(preset, (_, start, end) => `${start}1${end}`);
      }
      await route.fulfill({ contentType: 'text/javascript', body: source });
    });
    await page.goto('/companion');
    // Giữ canvas nhỏ để renderer phần mềm không làm thời gian vẽ lấn hết sáu giây xem thử.
    // Viewport/dialog vẫn theo PC hoặc mobile; loader, mesh, FaceBlend và renderer dùng mã thật.
    await page.addStyleTag({ content: '.character-canvas { width: 360px !important; height: 480px !important; }' });
    await page.getByRole('button', { name: 'Đổi nhân vật Peto' }).click();
    await page.getByLabel('Nhập VRM', { exact: true }).setInputFiles(samplePath!);
    await expect(page.locator('.character-canvas canvas')).toBeVisible({ timeout: 30000 });
    await page.locator('summary').filter({ hasText: 'Cài đặt nhân vật' }).click();
    for (const [name, label, amount] of [['happy', 'Vui', 0.7], ['sad', 'Buồn', 0.7], ['surprised', 'Ngạc nhiên', 0.8]] as const) {
      await page.locator('.expression-cards').getByRole('button', { name: label, exact: true }).click();
      const expected = baseline ? 1 : amount;
      await expect.poll(async () => (await faceValues(page, name)).weight, { intervals: [50] }).toBeGreaterThan(expected - 0.01);
      const values = await faceValues(page, name);
      expect(values.weight).toBeLessThanOrEqual(expected);
      expect(values.morph).toBeGreaterThan(expected - 0.01);
      expect(values.morph).toBeLessThanOrEqual(expected);
      const shot = page.locator('.expression-snapshot img');
      await expect(shot).toBeVisible();
      const data = (await shot.getAttribute('src'))!.split(',')[1];
      const imagePath = info.outputPath(`${name}.png`);
      await writeFile(imagePath, Buffer.from(data, 'base64'));
      await info.attach(`${name}-${baseline ? 'before' : 'after'}`, { path: imagePath, contentType: 'image/png' });
    }
    await page.locator('.expression-cards').getByRole('button', { name: 'Bình thường', exact: true }).click();
    await expect.poll(async () => (await faceValues(page, 'surprised')).morph, { timeout: 15000 }).toBeLessThan(0.005);
    await expect.poll(async () => (await faceValues(page, 'blink')).morph, { timeout: 15000, intervals: [50] }).toBeGreaterThan(0.1);

    // Chờ tiếng thật chạy trước khi bấm xem mặt: khởi động media trên máy chậm không tiêu hết sáu giây xem thử.
    await startVoice(page);
    await expect.poll(async () => (await faceValues(page, 'aa')).weight).toBeGreaterThan(0.5);
    await page.locator('.expression-cards').getByRole('button', { name: 'Vui', exact: true }).click();
    await expect.poll(async () => (await faceValues(page, 'happy')).weight, { intervals: [50] }).toBeGreaterThan((baseline ? 1 : 0.7) - 0.001);
    if (baseline) expect((await faceValues(page, 'aa')).morph).toBeLessThan(0.01);
    else await expect.poll(async () => (await faceValues(page, 'aa')).morph).toBeGreaterThan(0.1);
    await page.evaluate(() => (window as unknown as TestWindow).stopTestVoice!());
    await expect.poll(async () => (await faceValues(page, 'aa')).weight).toBeLessThan(0.21);
    // Bấm xem thử tự hết hạn; cả mặt và miệng nền phải về bình thường, không kẹt biểu cảm.
    await expect.poll(async () => (await faceValues(page, 'happy')).morph, { timeout: 10000 }).toBeLessThan(0.005);
    await expect.poll(async () => (await faceValues(page, 'aa')).morph).toBeLessThan(0.005);
    await page.getByRole('button', { name: 'Đóng chọn nhân vật' }).click();
    await page.screenshot({ path: info.outputPath('stage.png') });
    if (!await page.locator('.sidebar').isVisible()) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
    await expect(page.locator('.sidebar')).toBeVisible();
    await page.getByRole('button', { name: 'Trò chuyện', exact: true }).click();
    await expect(page.locator('.character-canvas canvas')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
