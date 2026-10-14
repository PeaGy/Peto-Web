import { expect, test, type Page } from '@playwright/test';
import { existsSync } from 'node:fs';
import type { Cubism4InternalModel } from 'pixi-live2d-display/cubism4';
import { mockPeto, noPageOverflow } from './fixtures';

type ModelWindow = Window & { controlTestModel?: { internalModel: Cubism4InternalModel }; controlTestParameters?: Record<string, number> };
// Model của người dùng chỉ được đọc khi người chạy cung cấp đường dẫn, không đóng kèm hoặc tải từ mạng.
const samplePath = process.env.PETO_LIVE2D_SAMPLE_FOLDER;
test.use({ reducedMotion: 'no-preference' });
test.describe.configure({ timeout: 120000 });

async function openStage(page: Page) {
  await mockPeto(page, { preservePreferences: true });
  await page.addInitScript(() => localStorage.setItem('peto-character-motion', 'always'));
  await page.route('**/characters/Live2DStage.tsx*', async route => {
    const source = await (await route.fetch()).text();
    const marker = 'app.stage.addChild(current);';
    expect(source).toContain(marker);
    const capture = `window.controlTestModel = current;
      const parameterIds = new Set(current.internalModel.coreModel.getModel().parameters.ids);
      current.internalModel.on('beforeModelUpdate', () => {
        window.controlTestParameters = Object.fromEntries(['ParamAngleX', 'ParamAngleXIN'].filter(id => parameterIds.has(id))
          .map(id => [id, current.internalModel.coreModel.getParameterValueById(id)]));
      });`;
    await route.fulfill({ contentType: 'text/javascript', body: source.replace(marker, `${capture} ${marker}`) });
  });
  await page.goto('/#companion');
  await expect(page.locator('.character-canvas')).toBeVisible({ timeout: 45000 });
}

async function headInput(page: Page, id: string, x: number) {
  await page.mouse.move(x, 80);
  const assertion = expect.poll(() => page.evaluate(id => {
    // SDK trả lại nền motion sau khi vẽ; đọc giá trị tại lúc model chuẩn bị cập nhật hình học.
    return (window as unknown as ModelWindow).controlTestParameters?.[id];
  }, id), { timeout: 15000 });
  if (x < 720) await assertion.toBeLessThan(-5);
  else await assertion.toBeGreaterThan(5);
}

test('Hiyori giữ tham số chuẩn và vẫn nhìn theo chuột', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Nhìn theo chuột chỉ bật trên máy tính.');
  await openStage(page);
  const ids = await page.evaluate(() => {
    const model = (window as unknown as ModelWindow).controlTestModel!.internalModel;
    return [model.idParamAngleX, model.idParamAngleY, model.idParamAngleZ, model.idParamEyeBallX, model.idParamEyeBallY];
  });
  expect(ids).toEqual(['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamEyeBallX', 'ParamEyeBallY']);
  await headInput(page, 'ParamAngleX', 300);
  await headInput(page, 'ParamAngleX', 1400);
  await expect(page.locator('.character-fallback')).toHaveCount(0);
  await noPageOverflow(page);
});

for (const useControls of [true, false]) {
  test(`Teto gốc: ${useControls ? 'ánh xạ riêng được lưu và đầu nhìn theo chuột' : 'tắt ánh xạ thì dùng tham số mặc định'}`, async ({ page }, info) => {
    test.skip(!samplePath || !existsSync(samplePath), 'Cần PETO_LIVE2D_SAMPLE_FOLDER trỏ tới thư mục Teto gốc.');
    await openStage(page);
    await page.getByRole('button', { name: /^Đổi nhân vật / }).click();
    await page.getByRole('button', { name: 'Chọn nhân vật', exact: true }).click();
    await page.getByLabel('Nhập thư mục Live2D', { exact: true }).setInputFiles(samplePath!);
    await expect(page.getByRole('heading', { name: 'Trước khi nhập', exact: true })).toBeVisible({ timeout: 30000 });
    await page.getByText('Xem thông số điều khiển', { exact: true }).click();
    await expect(page.getByText('ParamAngleXIN', { exact: true })).toBeVisible();
    const toggle = page.getByRole('switch', { name: /Dùng cấu hình điều khiển của model/ });
    await expect(toggle).toBeChecked();
    await noPageOverflow(page);
    await page.screenshot({ path: info.outputPath('import-controls.png') });
    if (!useControls) await toggle.uncheck();
    await page.getByRole('button', { name: 'Vẫn nhập model', exact: true }).click();
    // Nhập xong hộp tự đóng; sân khấu của trang Nhân vật vẽ model mới. Về Companion để kiểm sân khấu thật.
    await expect(page.getByRole('dialog', { name: 'Chọn nhân vật' })).toBeHidden();
    await expect(page.locator('.character-canvas')).toBeVisible({ timeout: 45000 });
    await page.goto('/companion');
    await expect(page.locator('.character-canvas')).toBeVisible({ timeout: 45000 });
    const headId = await page.evaluate(() => (window as unknown as ModelWindow).controlTestModel!.internalModel.idParamAngleX);
    expect(headId).toBe(useControls ? 'ParamAngleXIN' : 'ParamAngleX');
    if (useControls && info.project.name === 'pc') {
      await headInput(page, 'ParamAngleXIN', 300);
      await headInput(page, 'ParamAngleXIN', 1400);
      await page.screenshot({ path: info.outputPath('teto-cursor.png') });
    }
    await expect(page.locator('.character-fallback')).toHaveCount(0);
  });
}
