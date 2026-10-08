import { expect, test, type Page, type Locator } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

async function clickTool(viewer: Locator, name: string) {
  if (!await viewer.getByRole('toolbar', { name: 'Công cụ ảnh' }).isVisible()) await viewer.getByRole('button', { name: 'Chỉnh sửa ảnh', exact: true }).click();
  await viewer.getByRole('button', { name, exact: true }).click();
}
async function clickWorkspaceAction(viewer: Locator, name: string) {
  const control = viewer.getByRole('button', { name, exact: true });
  if (!await control.isVisible()) await viewer.getByRole('button', { name: 'Tùy chọn ảnh', exact: true }).click();
  await control.click();
  const close = viewer.getByRole('button', { name: 'Đóng tùy chọn', exact: true });
  if (await close.isVisible()) await close.click();
}
async function swipeLeft(page: Page, list: Locator) {
  const touch = await page.context().newCDPSession(page), row = (await list.boundingBox())!;
  const point = { x: row.x + row.width - 30, y: row.y + row.height / 2 };
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point] });
  // Đi ngón tay trong 300ms; cử chỉ thô tức thì tạo fling rất nhanh và tap chỉ dừng fling.
  for (let step = 1; step <= 3; step++) {
    await page.waitForTimeout(100);
    await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ ...point, x: point.x - 60 * step }] });
  }
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(() => list.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  let last = -1, stable = 0;
  await expect.poll(async () => { const position = await list.evaluate(element => element.scrollLeft); stable = position === last ? stable + 1 : 0; last = position; return stable; }, { intervals: [100] }).toBeGreaterThan(2);
  await touch.detach();
}

/** Ảnh dọc đủ lớn để phát hiện lỗi kích thước; không dùng ảnh 1 px để đánh giá bố cục. */
async function setup(page: Page, prompt = 'Ngôi nhà giữa núi xanh', shape: 'portrait' | 'landscape' | 'square' = 'portrait', imageCount = 2) {
  await mockPeto(page, { preservePreferences: true });
  const png = await page.evaluate(shape => {
    const canvas = document.createElement('canvas'); canvas.width = shape === 'landscape' ? 1440 : 960; canvas.height = shape === 'portrait' ? 1440 : 960;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#74c8e9'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#ffe1a0'; ctx.beginPath(); ctx.arc(690, 320, 125, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#436b7c'; ctx.beginPath(); ctx.moveTo(0, 900); ctx.lineTo(400, 400); ctx.lineTo(960, 1100); ctx.lineTo(0, 1440); ctx.fill();
    ctx.fillStyle = '#245647'; ctx.beginPath(); ctx.moveTo(0, 1050); ctx.lineTo(750, 700); ctx.lineTo(960, 1050); ctx.lineTo(960, 1440); ctx.lineTo(0, 1440); ctx.fill();
    ctx.fillStyle = '#e5cfaf'; ctx.fillRect(350, 1000, 250, 240);
    ctx.fillStyle = '#8c4935'; ctx.beginPath(); ctx.moveTo(300, 1000); ctx.lineTo(475, 850); ctx.lineTo(650, 1000); ctx.fill();
    return canvas.toDataURL('image/png').split(',')[1];
  }, shape);
  const image = (id: string) => ({ id, mime: 'image/png', url: `/api/imagine/images/${id}` });
  const images: (ReturnType<typeof image> & { liked?: boolean })[] = Array.from({ length: imageCount }, (_, index) => ({ ...image(index === 0 ? 'portrait' : index === 1 ? 'portrait-two' : `photo-${index}`), liked: index === 0 }));
  const job = { id: 'landscape', prompt, quality: 'medium', resolution: '2k', aspect_ratio: '2:3', created_at: 1,
    images };
  const posts: Record<string, unknown>[] = [];
  const saves: Record<string, unknown>[] = [];
  const revisions: (typeof job & { root_image_id: string; edit_parent_image_id: string; status: string })[] = [];
  const files = new Map<string, string>();
  let finishEdits = true;
  await page.route('**/api/imagine**', async route => {
    const request = route.request(), url = new URL(request.url());
    const workspace = /^\/api\/imagine\/images\/([^/]+)\/workspace$/.exec(url.pathname);
    if (workspace) return route.fulfill({ json: { root_image_id: workspace[1], root_job: job, jobs: revisions.filter(child => child.root_image_id === workspace[1]) } });
    const save = /^\/api\/imagine\/images\/([^/]+)\/revisions$/.exec(url.pathname);
    if (save && request.method() === 'POST') {
      const body = request.postDataJSON(); saves.push(body);
      const parent = revisions.find(child => child.images.some(image => image.id === save[1]));
      const id = `saved-${saves.length}`;
      files.set(id, body.data);
      const child = { ...job, id, status: 'complete', images: [image(id)], created_at: revisions.length + 2,
        root_image_id: parent?.root_image_id ?? save[1], edit_parent_image_id: save[1] };
      revisions.push(child);
      return route.fulfill({ json: { job: child } });
    }
    if (url.pathname.startsWith('/api/imagine/images/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from(files.get(url.pathname.split('/').at(-1)!) ?? png, 'base64') });
    if (request.method() === 'POST') {
      posts.push(request.postDataJSON());
      const body = request.postDataJSON();
      const parent = revisions.find(child => child.images.some(image => image.id === body.edit_parent_image_id));
      const child = { ...job, id: `edited-${posts.length}`, prompt: body.prompt, status: 'running', images: [image(`result-${posts.length}`)],
        created_at: revisions.length + 2, root_image_id: parent?.root_image_id ?? body.edit_parent_image_id,
        edit_parent_image_id: body.edit_parent_image_id, n: body.n };
      if (body.edit_parent_image_id) revisions.push(child);
      return route.fulfill({ status: 202, json: { job: { ...child, images: [] } } });
    }
    if (url.pathname === '/api/imagine') return route.fulfill({ json: { jobs: [job] } });
    const child = revisions.find(child => url.pathname === `/api/imagine/${child.id}`);
    if (child) {
      if (!finishEdits) return route.fulfill({ json: { job: { ...child, images: [] } } });
      child.status = 'complete'; return route.fulfill({ json: { job: child } });
    }
    return route.fulfill({ status: 404 });
  });
  return { posts, saves, revisions, job, finish: (value: boolean) => { finishEdits = value; } };
}

test('mobile: menu trượt lên, kéo xuống đóng và bàn phím chuyển trạng thái ngay', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Khung xem dành cho điện thoại');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await setup(page, 'Ngôi nhà giữa núi xanh', 'square');
  await page.goto('/#imagine/portrait/portrait');
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo', exact: true });
  const rail = viewer.getByRole('navigation', { name: 'Lịch sử chỉnh sửa ảnh' });
  await expect(rail.getByRole('button', { name: 'Ảnh chính' })).toBeVisible();
  const thumb = (await rail.locator('.history-thumb').boundingBox())!;
  expect(thumb.width).toBe(44); expect(thumb.height).toBe(44);
  const picture = viewer.locator('.workspace-picture img');
  await expect(picture).toHaveJSProperty('naturalWidth', 960);
  const photo = (await picture.boundingBox())!;
  expect(photo.width).toBeGreaterThan(360);
  expect(thumb.y).toBeGreaterThan(photo.y + photo.height);
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer.png') });
  const more = viewer.getByRole('button', { name: 'Tùy chọn ảnh', exact: true });
  const frames = await more.evaluate(async element => {
    const sheet = document.querySelector<HTMLElement>('.mobile-image-sheet')!;
    // Đo khung chuyển động thực tế sau click, không chỉ kiểm tra giá trị CSS khai báo.
    getComputedStyle(sheet).transform; (element as HTMLButtonElement).click();
    const samples: number[] = [];
    for (let i = 0; i < 10; i++) {
      await new Promise(requestAnimationFrame);
      samples.push(new DOMMatrixReadOnly(getComputedStyle(sheet).transform).m42);
    }
    return samples;
  });
  expect(Math.max(...frames)).toBeGreaterThan(20);
  expect(frames.at(-1)!).toBeLessThan(frames[0]);
  const sheet = viewer.getByRole('dialog', { name: 'Tùy chọn ảnh', exact: true });
  const close = sheet.getByRole('button', { name: 'Đóng tùy chọn', exact: true });
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(sheet.getByRole('button', { name: 'Thêm làm tham chiếu' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(close).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer-sheet.png') });
  await page.keyboard.press('Escape');
  await expect(sheet).not.toBeVisible(); await expect(more).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(sheet).toBeVisible();
  await expect(sheet).toHaveCSS('transition-duration', '0s');
  await close.tap();
  await more.tap();
  await expect(sheet).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)');
  const handle = (await sheet.locator('.mobile-sheet-handle').boundingBox())!;
  const touch = await page.context().newCDPSession(page);
  const point = { x: handle.x + handle.width / 2, y: handle.y + handle.height / 2, id: 1 };
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ ...point, y: point.y + 100 }] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect(sheet).not.toBeVisible(); await expect(more).toBeFocused();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await more.tap(); await expect(sheet).toHaveCSS('transition-duration', '0s');
  await viewer.getByRole('button', { name: 'Đóng tùy chọn ảnh', exact: true }).tap({ position: { x: 20, y: 70 } });
  await expect(sheet).not.toBeVisible();
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const movement = await viewer.getByRole('button', { name: 'Chỉnh sửa ảnh', exact: true }).evaluate(async button => {
    const picture = document.querySelector<HTMLElement>('.workspace-picture')!;
    const before = picture.getBoundingClientRect(); (button as HTMLButtonElement).click();
    const frames: { top: number; animations: number }[] = [];
    for (let i = 0; i < 18; i++) {
      await new Promise(requestAnimationFrame);
      frames.push({ top: picture.getBoundingClientRect().top, animations: picture.getAnimations().length });
    }
    return { before: before.top, frames };
  });
  expect(movement.frames.some(frame => frame.animations > 0)).toBe(true);
  expect(Math.abs(movement.frames[0].top - movement.before)).toBeLessThan(8);
  expect(Math.abs(movement.frames.at(-1)!.top - movement.before)).toBeGreaterThan(20);
  await noPageOverflow(page); await touch.detach();
});

test('mobile: vẽ bằng cảm ứng, cỡ bút nổi và bảng màu cuộn ngang', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Công cụ cảm ứng dành cho điện thoại');
  const { saves, posts } = await setup(page);
  await page.goto('/#imagine/portrait/portrait');
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo', exact: true });
  await viewer.getByRole('button', { name: 'Chỉnh sửa ảnh', exact: true }).tap();
  const size = viewer.getByRole('slider', { name: 'Cỡ bút' });
  await expect(size).toBeInViewport();
  const slider = (await size.boundingBox())!;
  expect(slider.height).toBeGreaterThan(slider.width * 3);
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer-brush-size.png') });
  await viewer.getByRole('button', { name: 'Chọn màu bút' }).tap();
  await viewer.getByRole('button', { name: 'Chọn màu #f04444' }).tap();
  await expect(viewer.locator('.mobile-brush-colors')).toHaveCount(0);
  const canvas = viewer.getByLabel('Vẽ ghi chú lên ảnh');
  const bounds = (await canvas.boundingBox())!;
  const touch = await page.context().newCDPSession(page);
  const point = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2, id: 1 };
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ ...point, x: point.x + 40 }] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect(size).toHaveCount(0);
  await expect(viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer-brush.png') });
  await viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' }).tap();
  await viewer.getByRole('button', { name: 'Làm lại nét vẽ' }).tap();
  await viewer.getByRole('button', { name: 'Áp dụng nét vẽ' }).tap();
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/saved-1');
  expect(saves).toHaveLength(1); expect(posts).toHaveLength(0);
  const pixel = await viewer.locator('.workspace-picture img').evaluate(async element => {
    const img = element as HTMLImageElement; await img.decode();
    const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
    const ctx = c.getContext('2d')!; ctx.drawImage(img, 0, 0);
    return [...ctx.getImageData(c.width / 2, c.height / 2, 1, 1).data];
  });
  expect(pixel).toEqual([240, 68, 68, 255]);
  await page.setViewportSize({ width: 320, height: 844 });
  await clickTool(viewer, 'Bảng màu');
  const palettes = viewer.locator('.mobile-palette-list');
  await expect(palettes).toBeInViewport();
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).not.toBeVisible();
  await swipeLeft(page, palettes);
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer-palette.png') });
  await viewer.getByRole('button', { name: 'Đóng công cụ' }).tap();
  await clickTool(viewer, 'Cắt ảnh');
  const crop = viewer.getByRole('group', { name: 'Vùng cắt, dùng phím mũi tên để di chuyển' });
  await expect(crop).toBeFocused();
  const cropBox = (await crop.boundingBox())!, cropPoint = { x: cropBox.x + cropBox.width / 2, y: cropBox.y + cropBox.height / 2 };
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [cropPoint] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ ...cropPoint, x: cropPoint.x + 10 }] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await viewer.getByRole('button', { name: 'Cắt', exact: true }).tap();
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/saved-2');
  expect(saves).toHaveLength(2); expect(posts).toHaveLength(0);
  const input = viewer.getByLabel('Mô tả chỉnh sửa ảnh');
  await input.fill('Giữ ngôi nhà và đổi nền');
  // Bàn phím chỉ thu visualViewport, còn layout viewport vẫn cao 844px.
  await page.evaluate(() => { Object.defineProperty(window.visualViewport!, 'height', { value: 460, configurable: true }); window.visualViewport!.dispatchEvent(new Event('resize')); });
  await input.focus();
  await expect(input).toBeInViewport();
  await expect(viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' })).toBeInViewport();
  const inputBox = (await input.boundingBox())!;
  expect(inputBox.y + inputBox.height).toBeLessThanOrEqual(460);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer-small-keyboard.png') });
  await touch.detach();
});

test('mobile: chờ kết quả có hiệu ứng, chọn bản cũ tức thì và cuộn phiên bản riêng', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Trạng thái chỉnh sửa trên điện thoại');
  const { posts, revisions, job, finish } = await setup(page);
  for (let i = 1; i <= 12; i++) revisions.push({ ...job, id: `history-${i}`, created_at: i + 1, status: 'complete', root_image_id: 'portrait', edit_parent_image_id: 'portrait', images: [{ id: `history-image-${i}`, url: `/api/imagine/images/history-image-${i}`, mime: 'image/png' }] });
  finish(false);
  await page.goto('/#imagine/portrait/portrait');
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo', exact: true });
  const rail = viewer.getByRole('navigation', { name: 'Lịch sử chỉnh sửa ảnh' });
  const list = rail.locator('.history-list');
  await expect(rail.locator('.history-thumb')).toHaveCount(13);
  await swipeLeft(page, list);
  await rail.getByRole('button', { name: 'Phiên bản 2', exact: true }).tap();
  await expect(page).toHaveURL(/#imagine\/portrait\/history-image-2$/);
  await expect.poll(() => viewer.locator('.workspace-picture').evaluate(element => element.getAnimations().length)).toBe(0);
  await viewer.getByLabel('Mô tả chỉnh sửa ảnh').fill('Đổi thành tranh màu nước');
  await viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' }).tap();
  await expect(viewer.getByRole('status', { name: 'Phiên bản đang tạo' })).toBeInViewport();
  await expect(viewer.locator('.workspace-picture')).toHaveCSS('filter', 'blur(18px)');
  await expect(rail.locator('.history-thumb').first()).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath('mobile-viewer-pending.png') });
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ source_image_id: 'history-image-2', edit_parent_image_id: 'history-image-2' });
  finish(true);
  await expect(page).toHaveURL(/#imagine\/portrait\/result-1$/);
  await expect(rail.locator('.history-thumb')).toHaveCount(14);
  await expect(viewer.getByRole('status', { name: 'Phiên bản đang tạo' })).toHaveCount(0);
  await expect(viewer.locator('.workspace-picture')).toHaveCSS('filter', 'none');
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).tap();
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().tap();
  await expect(page.getByRole('dialog', { name: 'Thư viện ảnh' }).locator('.library-tile')).toHaveCount(2);
  await noPageOverflow(page);
});

test('thư viện mobile có tìm kiếm dưới đáy và hai bố cục như mẫu', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Bố cục dành cho điện thoại');
  await setup(page, 'Ngôi nhà giữa núi xanh', 'portrait', 3);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().tap();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const tile = library.locator('[data-image-id="portrait"]');
  await expect(tile.locator('img')).toHaveJSProperty('naturalWidth', 960);
  await expect(library.locator('.library-composer')).toHaveCount(0);
  const box = (await tile.boundingBox())!;
  expect(box.x).toBe(1);
  expect(box.width).toBeCloseTo(128, 0);
  expect(box.height).toBeCloseTo(box.width, 0);
  const bottom = library.locator('.library-mobile-bottom');
  const search = library.getByRole('searchbox');
  await expect(search).toHaveCSS('font-size', '16px');
  expect((await search.boundingBox())!.y).toBeGreaterThan(700);
  expect((await bottom.boundingBox())!.y + (await bottom.boundingBox())!.height).toBe(844);
  for (const button of await library.locator('.library-top button, .library-filter > button').all()) {
    const buttonBox = (await button.boundingBox())!;
    expect(buttonBox.width).toBeGreaterThanOrEqual(44); expect(buttonBox.height).toBeGreaterThanOrEqual(44);
  }
  await page.screenshot({ path: testInfo.outputPath('mobile-library-compact.png') });
  const filter = library.getByRole('button', { name: 'Bố cục và bộ lọc' });
  await filter.tap();
  await library.getByRole('button', { name: 'Rộng', exact: true }).tap();
  await expect(tile).toHaveCSS('aspect-ratio', '960 / 1440');
  const wide = (await tile.boundingBox())!;
  expect(wide.width).toBeCloseTo(193, 0); expect(wide.height / wide.width).toBeCloseTo(1.5, 2);
  await page.screenshot({ path: testInfo.outputPath('mobile-library-wide-filter.png') });
  await page.touchscreen.tap(190, 30);
  await expect(filter).toHaveAttribute('aria-expanded', 'false');
  await search.fill('khong co');
  await expect(library.getByText('Không có ảnh nào khớp')).toBeVisible();
  await search.fill('nui xanh');
  await expect(library.locator('.library-tile')).toHaveCount(3);
  await filter.tap();
  await library.getByRole('button', { name: 'Chỉ ảnh đã thích' }).tap();
  await expect(library.locator('.library-tile')).toHaveCount(1);
  await filter.tap();
  await library.getByRole('button', { name: 'Chỉ ảnh đã thích' }).tap();
  await expect(library.locator('.library-tile')).toHaveCount(3);
  await page.reload();
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().tap();
  await expect(library.locator('.library-wide')).toHaveCount(1);
  await expect(library.locator('.library-tile')).toHaveCount(3);
  // Ô tìm kiếm giữ trong viewport khi vùng hiển thị bị thu lại bởi bàn phím.
  await page.setViewportSize({ width: 320, height: 460 });
  await search.focus();
  await expect(bottom).toBeInViewport();
  await noPageOverflow(page);
  await filter.tap();
  await expect(library.getByRole('button', { name: 'Rộng', exact: true })).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('mobile-library-narrow.png') });
});

test('cảm ứng mobile: chạm xem, giữ chọn và vuốt cuộn không chọn nhầm', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Cử chỉ cảm ứng dành cho điện thoại');
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: () => true });
    Object.defineProperty(navigator, 'share', { configurable: true, value: async () => {} });
  });
  await setup(page, 'Ngôi nhà giữa núi xanh', 'portrait', 18);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().tap();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const tile = library.locator('[data-image-id="portrait"]');
  await tile.tap();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer).toBeVisible();
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).tap();
  const touch = await page.context().newCDPSession(page);
  const point = (await tile.boundingBox())!;
  const x = point.x + point.width / 2, y = point.y + point.height / 2;
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toBeVisible();
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect(tile).toHaveAttribute('aria-pressed', 'true');
  await expect(viewer).not.toBeVisible();
  await expect(library.getByRole('menu')).toHaveCount(0);
  const toolbar = library.getByRole('toolbar', { name: 'Thao tác với ảnh đã chọn' });
  await expect(toolbar).toBeInViewport();
  const selectedBox = (await tile.boundingBox())!;
  expect(selectedBox.height).toBeCloseTo(selectedBox.width, 0);
  await expect(toolbar.getByRole('button', { name: 'Chia sẻ' })).toBeVisible();
  const mark = (await tile.locator('.library-check').boundingBox())!;
  expect(mark.x).toBeGreaterThan(point.x + point.width / 2);
  await library.locator('[data-image-id="portrait-two"]').tap();
  await expect(library.locator('.sr-only')).toHaveText('Đã chọn 2 ảnh');
  await page.screenshot({ path: testInfo.outputPath('mobile-library-selected.png') });
  await library.getByRole('button', { name: 'Hủy', exact: true }).tap();
  await library.getByRole('button', { name: 'Chọn', exact: true }).tap();
  await expect(toolbar).toHaveCount(0);
  await expect(library.getByRole('searchbox')).toHaveCount(0);
  await library.getByRole('button', { name: 'Hủy', exact: true }).tap();
  // Cuộn thật bằng cảm ứng: trình duyệt phát pointercancel khi nhận thao tác pan.
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: 60, y: 520 }] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: 60, y: 460 }] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: 60, y: 380 }] });
  await expect.poll(() => library.locator('.library-grid').evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  // Chờ quá thời gian nhấn giữ để bắt lỗi tự bật chọn sau một cú vuốt.
  await page.waitForTimeout(600);
  await expect(library.getByRole('button', { name: 'Chọn', exact: true })).toBeVisible();
  await expect(library.locator('.library-tile[aria-pressed="true"]')).toHaveCount(0);
  await noPageOverflow(page);
  await touch.detach();
});

test('thư viện có ô ảnh nhỏ và khung xem vừa màn hình trên PC/mobile', async ({ page }, testInfo) => {
  const { posts } = await setup(page);
  if (testInfo.project.name === 'pc') await page.setViewportSize({ width: 1920, height: 960 });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const tile = library.getByRole('button', { name: 'Xem ảnh: Ngôi nhà giữa núi xanh', exact: true }).first();
  await expect(tile.locator('img')).toHaveJSProperty('naturalWidth', 960);
  await expect(page.locator('.image-nav-rail')).toHaveCount(0);
  await expect(library.getByText(/Chọn theo thứ tự mong muốn/)).toHaveCount(0);
  const bounds = (await tile.boundingBox())!;
  expect(bounds.width).toBeLessThanOrEqual(360);
  expect(Math.abs(bounds.width - bounds.height)).toBeLessThan(1);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('library.png') });
  await library.getByRole('button', { name: 'Chọn', exact: true }).click();
  await library.getByRole('button', { name: 'Chọn ảnh: Ngôi nhà giữa núi xanh', exact: true }).first().click();
  await expect(library.getByLabel('Bức ảnh bạn muốn tạo')).toHaveCount(0);
  await expect(library.getByRole('button', { name: 'Tải xuống', exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('library-selected.png') });
  await library.getByRole('button', { name: 'Hủy', exact: true }).click();
  await tile.click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await expect(viewer.locator('.image-nav-rail')).toHaveCount(0);
  const stage = (await viewer.locator('.workspace-canvas').boundingBox())!;
  const shown = (await viewer.locator('.workspace-picture img').boundingBox())!;
  expect(shown.width).toBeLessThanOrEqual(stage.width);
  expect(shown.height).toBeLessThanOrEqual(stage.height);
  const top = (await viewer.locator('.workspace-topbar').boundingBox())!;
  const dock = (await viewer.locator('.workspace-edit-dock').boundingBox())!;
  expect(dock.y).toBeGreaterThanOrEqual(shown.y + shown.height);
  expect(dock.width).toBeLessThanOrEqual(Math.min(stage.width, 800));
  await expect(viewer.getByRole('button', { name: 'Đóng khung xem' })).toHaveCount(0);
  if (testInfo.project.name === 'pc') {
    const tools = (await viewer.getByRole('toolbar', { name: 'Công cụ ảnh' }).boundingBox())!;
    const panel = (await viewer.locator('.workspace-panel').boundingBox())!;
    const sidebar = (await page.locator('.sidebar').boundingBox())!;
    await expect(viewer.evaluate(element => element.matches(':modal'))).resolves.toBe(false);
    expect((await viewer.boundingBox())!.x).toBe(sidebar.x + sidebar.width);
    expect(tools.x).toBeGreaterThanOrEqual(panel.x);
    expect(tools.y).toBeLessThan(16);
    expect(dock.width).toBe(800);
    const back = (await viewer.getByRole('button', { name: 'Quay lại', exact: true }).boundingBox())!;
    const zoom = (await viewer.locator('.workspace-zoom').boundingBox())!;
    expect(back.x + back.width).toBeLessThan(shown.x);
    expect(zoom.x).toBeGreaterThan(shown.x + shown.width);
  } else {
    expect(top.y + top.height).toBeLessThanOrEqual(shown.y);
    await expect(viewer).toHaveAttribute('aria-modal', 'true');
    expect(await viewer.evaluate(element => element.matches(':modal'))).toBe(true);
  }
  await expect(viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' })).toBeDisabled();
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('workspace.png') });
  await clickTool(viewer, 'Bảng màu');
  await viewer.getByRole('button', { name: 'Lấy màu từ ảnh' }).click();
  await expect(viewer.getByRole('button', { name: /^Màu #/ })).toHaveCount(4);
  await viewer.getByRole('button', { name: 'Bắc Âu', exact: true }).click();
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveValue(/Áp dụng bảng màu bắc âu/);
  expect(posts).toHaveLength(0);
  await page.screenshot({ path: testInfo.outputPath('palette.png') });
  if (testInfo.project.name === 'mobile') await viewer.getByRole('button', { name: 'Đóng công cụ', exact: true }).click();
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(library).toBeVisible();
  await expect(tile.locator('img')).toHaveAttribute('src', '/api/imagine/images/portrait');
  await library.getByRole('button', { name: 'Quay lại Tạo ảnh' }).click();
  await expect(library).not.toBeVisible();
});

test('cắt/vẽ tạo nguồn PNG mới, hoàn tác giữ ảnh gốc, chỉ gửi khi bấm gửi', async ({ page }, testInfo) => {
  const { posts, saves } = await setup(page);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await clickTool(viewer, 'Cắt ảnh');
  await viewer.getByLabel('Tỉ lệ cắt').selectOption('1:1');
  await page.screenshot({ path: testInfo.outputPath('crop.png') });
  // Escape chỉ hủy vùng cắt; khung xem vẫn mở.
  await page.keyboard.press('Escape');
  await expect(viewer).toBeVisible();
  await expect(viewer.getByLabel('Tỉ lệ cắt')).toHaveCount(0);
  await clickTool(viewer, 'Cắt ảnh');
  await viewer.getByRole('button', { name: 'Cắt', exact: true }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('864 × 864');
  await clickWorkspaceAction(viewer, 'Hoàn tác chỉnh sửa');
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await clickWorkspaceAction(viewer, 'Làm lại chỉnh sửa');
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('864 × 864');
  await clickTool(viewer, 'Bút vẽ');
  const canvas = viewer.getByLabel('Vẽ ghi chú lên ảnh');
  const bounds = (await canvas.boundingBox())!;
  // Pointer dùng cùng đường xử lý cho chuột và cảm ứng.
  await canvas.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, clientX: bounds.x + bounds.width / 2, clientY: bounds.y + bounds.height / 2 });
  await canvas.dispatchEvent('pointermove', { pointerId: 1, pointerType: 'mouse', clientX: bounds.x + bounds.width * .75, clientY: bounds.y + bounds.height / 2 });
  await canvas.dispatchEvent('pointerup', { pointerId: 1, pointerType: 'mouse' });
  await expect(viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' })).toBeEnabled();
  await viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' }).click();
  await expect(viewer.getByRole('button', { name: testInfo.project.name === 'mobile' ? 'Gửi chỉnh sửa ảnh' : 'Áp dụng nét vẽ' })).toBeDisabled();
  await viewer.getByRole('button', { name: 'Làm lại nét vẽ' }).click();
  await viewer.getByRole('button', { name: 'Áp dụng nét vẽ' }).click();
  const data = await viewer.locator('.workspace-picture img').getAttribute('src');
  expect(data).toBe('/api/imagine/images/saved-2');
  expect(saves).toHaveLength(2);
  const pixel = await viewer.locator('.workspace-picture img').evaluate(async img => {
    const image = img as HTMLImageElement; await image.decode();
    const c = document.createElement('canvas'); c.width = image.naturalWidth; c.height = image.naturalHeight;
    const ctx = c.getContext('2d')!; ctx.drawImage(image, 0, 0);
    return [...ctx.getImageData(c.width / 2, c.height / 2, 1, 1).data];
  });
  expect(pixel).toEqual([255, 255, 255, 255]);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('brush.png') });
  expect(posts).toHaveLength(0);
  await viewer.getByLabel('Mô tả chỉnh sửa ảnh').fill('Đổi thành tranh màu nước');
  await viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' }).click();
  await expect(viewer).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ n: 1, background: true, source_image_id: 'saved-2', edit_parent_image_id: 'saved-2', prompt: 'Đổi thành tranh màu nước' });
  await expect(viewer.getByRole('button', { name: 'Phiên bản 3', exact: true })).toBeVisible();
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).locator('img')).toHaveAttribute('src', '/api/imagine/images/portrait');
});


test('bấm ảnh để xem, nhấn giữ để chọn và hủy chọn trả về xem ảnh', async ({ page }, testInfo) => {
  await setup(page);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const tile = library.locator('[data-image-id="portrait"]');
  await tile.click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer).toBeVisible();
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(library.getByRole('button', { name: 'Chọn', exact: true })).toBeVisible();
  const box = (await tile.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  // Chờ trạng thái do cử chỉ giữ thực sự, không bấm nút Chọn để giả lập.
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText(testInfo.project.name === 'mobile' ? 'Hủy' : '1 đã chọn');
  await expect(library.locator('.sr-only')).toHaveText('Đã chọn 1 ảnh');
  await page.mouse.up();
  await expect(tile).toHaveAttribute('aria-pressed', 'true');
  await expect(viewer).not.toBeVisible();
  await expect(library.getByRole('menu')).toHaveCount(0);
  await expect(library.getByText(/Chọn theo thứ tự mong muốn/)).toHaveCount(0);
  await library.locator('[data-image-id="portrait-two"]').click();
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText(testInfo.project.name === 'mobile' ? 'Hủy' : '2 đã chọn');
  await expect(library.locator('.sr-only')).toHaveText('Đã chọn 2 ảnh');
  await library.getByRole('button', { name: 'Hủy', exact: true }).click();
  await tile.click();
  await expect(viewer).toBeVisible();
  await noPageOverflow(page);
});

test('mô tả dài và nút thao tác vẫn đọc/bấm được ở màn hình 320px', async ({ page }, testInfo) => {
  const prompt = 'Thiết kế bìa cho bộ sưu tập Kiến trúc Việt Nam — những ngôi nhà ven biển lúc bình minh 🌅, phối màu xanh ngọc và vàng nhạt. Tên tệp tham khảo: kien-truc-viet-nam-bo-suu-tap-nha-ven-bien-phien-ban-hoan-thien-2026.png';
  await setup(page, prompt);
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const search = library.getByRole('searchbox');
  if (testInfo.project.name === 'mobile') await expect(search).toHaveCSS('font-size', '16px');
  await search.fill('Kiến trúc Việt Nam');
  await library.locator('[data-image-id="portrait"]').click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.locator('.workspace-prompt')).toHaveText(prompt);
  await expect(viewer.locator('.workspace-source-chip span')).toHaveAttribute('title', prompt);
  const edit = viewer.getByRole('button', { name: 'Dùng ảnh này', exact: true });
  const bounds = (await edit.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(320);
  const input = viewer.getByLabel('Mô tả chỉnh sửa ảnh');
  await input.fill('Giữ tên bộ sưu tập và đổi sang phong cách màu nước');
  await expect(input).toHaveCSS('font-size', '16px');
  await expect(input).toHaveAttribute('enterkeyhint', 'send');
  expect(await input.evaluate(element => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
  await expect(viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' })).toBeEnabled();
  for (const name of ['Gửi chỉnh sửa ảnh', 'Chỉnh sửa ảnh', 'Tùy chọn ảnh']) {
    const control = (await viewer.getByRole('button', { name, exact: true }).boundingBox())!;
    expect(control.x + control.width).toBeLessThanOrEqual(320);
  }
  expect(await viewer.locator('.workspace-body').evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  expect(await viewer.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('narrow-long-prompt.png') });
});

test('ảnh ngang và zoom giữ nút cùng ô nhập ngoài vùng ảnh', async ({ page }, testInfo) => {
  await setup(page, 'Ngôi nhà giữa núi xanh', 'landscape');
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('1440 × 960');
  const picture = viewer.locator('.workspace-picture img');
  const shown = (await picture.boundingBox())!;
  expect(shown.width / shown.height).toBeCloseTo(1.5, 2);
  const stage = (await viewer.locator('.workspace-canvas').boundingBox())!;
  expect(shown.width).toBeLessThanOrEqual(stage.width);
  expect(shown.height).toBeLessThanOrEqual(stage.height);
  await clickWorkspaceAction(viewer, 'Phóng to ảnh');
  await expect(viewer.locator('.workspace-zoom button[aria-label="Vừa khung"]')).toHaveText('125%');
  const zoomed = (await picture.boundingBox())!;
  const top = (await viewer.locator('.workspace-topbar').boundingBox())!;
  const dock = (await viewer.locator('.workspace-edit-dock').boundingBox())!;
  expect(top.y + top.height).toBeLessThanOrEqual(zoomed.y);
  expect(dock.y).toBeGreaterThanOrEqual(stage.y + stage.height);
  await clickWorkspaceAction(viewer, 'Vừa khung');
  if (testInfo.project.name === 'pc') {
    await viewer.getByRole('button', { name: 'Ẩn bảng công cụ' }).click();
    await expect(viewer.locator('.workspace-panel-body')).toBeHidden();
    expect((await viewer.locator('.workspace-panel').boundingBox())!.width).toBe(60);
    await expect(viewer.getByRole('button', { name: 'Chia sẻ', exact: true })).toBeVisible();
    await viewer.getByRole('button', { name: 'Hiện bảng công cụ' }).click();
  } else {
    await viewer.getByRole('button', { name: 'Chỉnh sửa ảnh', exact: true }).click();
    await expect(viewer.locator('.workspace-panel')).toHaveCount(0);
    await expect(viewer.getByRole('toolbar', { name: 'Công cụ ảnh' })).toBeVisible();
  }
  await clickTool(viewer, 'Bảng màu');
  if (testInfo.project.name === 'pc') await expect(viewer.locator('.workspace-panel')).toBeVisible();
  else await expect(viewer.locator('.mobile-palette-list')).toBeVisible();
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('landscape-workspace.png') });
});

test('desktop giữ sidebar thật và bố cục Grok khi mở hoặc thu gọn các bảng', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'pc', 'Lượt này ưu tiên bố cục desktop.');
  const { posts } = await setup(page, 'Ngôi nhà giữa núi xanh', 'square');
  await page.setViewportSize({ width: 1910, height: 870 });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  const sidebar = page.locator('.sidebar');
  const picture = viewer.locator('.workspace-picture img');
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 960');
  async function checkLayout() {
    const nav = (await sidebar.boundingBox())!, view = (await viewer.boundingBox())!;
    const main = (await viewer.locator('.workspace-main').boundingBox())!;
    const image = (await picture.boundingBox())!;
    const form = (await viewer.locator('.workspace-edit-dock form').boundingBox())!;
    const back = (await viewer.getByRole('button', { name: 'Quay lại', exact: true }).boundingBox())!;
    expect(view.x).toBe(nav.x + nav.width);
    expect(view.x + view.width).toBe(1910);
    expect(image.width / image.height).toBeCloseTo(1, 2);
    expect(image.y).toBeCloseTo(40, 0);
    expect(image.height).toBeGreaterThan(640);
    expect(form.width).toBe(760);
    expect(form.x + form.width / 2).toBeCloseTo(main.x + main.width / 2, 0);
    expect(back.x).toBe(main.x + 12);
    expect(form.y).toBeGreaterThanOrEqual(image.y + image.height);
    await noPageOverflow(page);
  }
  await checkLayout();
  await page.screenshot({ path: testInfo.outputPath('desktop-sidebar-open.png') });
  // Nút thuộc sidebar thật phải bấm được khi khung xem đang mở.
  await sidebar.getByRole('button', { name: 'Thu gọn thanh bên', exact: true }).click();
  await expect(sidebar).toHaveClass(/collapsed/);
  await checkLayout();
  await page.screenshot({ path: testInfo.outputPath('desktop-sidebar-collapsed.png') });
  await viewer.getByRole('button', { name: 'Ẩn bảng công cụ' }).click();
  await expect(viewer.locator('.workspace-panel-body')).toBeHidden();
  expect((await viewer.locator('.workspace-panel').boundingBox())!.width).toBe(60);
  await checkLayout();
  await page.screenshot({ path: testInfo.outputPath('desktop-right-rail.png') });
  // Các thao tác đang có vẫn hiện ở dải phải, cùng nguồn tải ảnh ban đầu.
  await expect(viewer.getByRole('button', { name: 'Thích', exact: true })).toBeVisible();
  await expect(viewer.getByRole('link', { name: 'Tải ảnh xuống' })).toHaveAttribute('href', '/api/imagine/images/portrait?download=1');
  await viewer.getByRole('button', { name: 'Thiết lập tỉ lệ ảnh' }).click();
  await expect(viewer.getByLabel('Tỉ lệ ảnh chỉnh sửa')).toBeVisible();
  await sidebar.getByRole('button', { name: 'Mở rộng thanh bên', exact: true }).click();
  await sidebar.getByRole('button', { name: 'Thư viện', exact: true }).click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  await expect(library).toBeVisible();
  await expect(viewer).not.toBeVisible();
  await library.getByRole('button', { name: 'Tìm trong thư viện' }).click();
  await library.getByRole('searchbox').fill('núi xanh');
  await library.locator('[data-image-id="portrait"]').click();
  await expect(viewer).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(library).toBeVisible();
  await expect(library.getByRole('searchbox')).toHaveValue('núi xanh');
  expect(posts).toHaveLength(0);
});

test('desktop màn hình thấp và đổi kích thước giữ tỉ lệ ảnh cùng nội dung đang nhập', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'pc', 'Kiểm tra thay đổi vùng nội dung trên desktop.');
  await setup(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1366, height: 600 });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  const shown = (await viewer.locator('.workspace-picture img').boundingBox())!;
  const stage = (await viewer.locator('.workspace-canvas').boundingBox())!;
  const form = (await viewer.locator('.workspace-edit-dock form').boundingBox())!;
  expect(shown.width / shown.height).toBeCloseTo(2 / 3, 2);
  expect(shown.height).toBeLessThanOrEqual(stage.height);
  expect(shown.y).toBeGreaterThanOrEqual(76);
  expect(form.y).toBeGreaterThanOrEqual(shown.y + shown.height);
  expect(form.y + form.height).toBeLessThanOrEqual(600);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('desktop-short-portrait.png') });
  await viewer.getByLabel('Mô tả chỉnh sửa ảnh').fill('Giữ nguyên ngôi nhà và đổi màu trời');
  // Chuyển show/showModal không được gây InvalidStateError hoặc làm mất mô tả.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => viewer.evaluate(element => element.matches(':modal'))).toBe(true);
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveValue('Giữ nguyên ngôi nhà và đổi màu trời');
  await noPageOverflow(page);
  await page.setViewportSize({ width: 1366, height: 600 });
  await expect.poll(() => viewer.evaluate(element => element.matches(':modal'))).toBe(false);
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveValue('Giữ nguyên ngôi nhà và đổi màu trời');
  await expect(page.locator('.sidebar')).toBeVisible();
  await noPageOverflow(page);
  expect(errors).toEqual([]);
});

test('thư viện desktop giữ sidebar, font dự án và các lớp Escape sau khi thu gọn', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'pc', 'Thư viện desktop nằm cạnh sidebar thật.');
  await setup(page);
  await page.goto('/#imagine');
  const sidebar = page.locator('.sidebar');
  await sidebar.getByRole('button', { name: 'Thư viện', exact: true }).click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  await expect(library).toBeVisible();
  await expect(library.evaluate(element => element.matches(':modal'))).resolves.toBe(false);
  async function checkSidebar() {
    const nav = (await sidebar.boundingBox())!, lib = (await library.boundingBox())!;
    expect(lib.x).toBe(nav.x + nav.width);
    expect(lib.x + lib.width).toBe(1440);
    await expect(page.locator('.imagine-gallery')).toBeHidden();
    await noPageOverflow(page);
  }
  await checkSidebar();
  const projectFont = await page.locator('body').evaluate(element => getComputedStyle(element).fontFamily);
  await expect(library).toHaveCSS('font-family', projectFont);
  const choose = library.getByRole('button', { name: 'Chọn', exact: true });
  await expect(choose).toHaveCSS('font-size', '14px');
  expect((await choose.boundingBox())!.height).toBe(38);
  await page.screenshot({ path: testInfo.outputPath('desktop-library-sidebar.png') });
  await sidebar.getByRole('button', { name: 'Thu gọn thanh bên', exact: true }).click();
  await expect(sidebar).toHaveClass(/collapsed/);
  await checkSidebar();
  await library.getByRole('button', { name: 'Bố cục và bộ lọc' }).click();
  await expect(library.getByLabel('Lọc loại ảnh')).toHaveCSS('font-family', projectFont);
  await page.keyboard.press('Escape');
  await expect(library.getByLabel('Lọc loại ảnh')).toHaveCount(0);
  await expect(library).toBeVisible();
  const tile = library.locator('[data-image-id="portrait"]');
  await tile.click({ button: 'right' });
  await expect(library.getByRole('menu', { name: 'Thao tác với ảnh' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(library.getByRole('menu')).toHaveCount(0);
  await choose.click();
  await tile.click();
  await library.getByRole('button', { name: 'Xóa', exact: true }).click();
  const confirm = library.getByRole('dialog', { name: 'Xóa ảnh này?' });
  await expect(confirm).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(confirm).not.toBeVisible();
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText('1 đã chọn');
  await library.getByRole('button', { name: 'Hủy', exact: true }).focus();
  await page.keyboard.press('Escape');
  await expect(choose).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('desktop-library-collapsed.png') });
  await tile.click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  const panel = viewer.locator('.workspace-panel');
  await expect(viewer).toHaveCSS('font-family', projectFont);
  await expect(panel).toHaveCSS('font-size', '14px');
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveCSS('font-family', projectFont);
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveCSS('font-size', '16px');
  expect((await panel.boundingBox())!.width).toBeLessThanOrEqual(360);
  expect((await viewer.getByRole('button', { name: 'Quay lại', exact: true }).boundingBox())!.width).toBe(38);
  expect((await viewer.locator('.workspace-edit-dock form').boundingBox())!.height).toBe(60);
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await library.getByRole('button', { name: 'Quay lại Tạo ảnh' }).focus();
  await page.keyboard.press('Escape');
  await expect(library).not.toBeVisible();
  await expect(page.locator('.imagine-gallery')).toBeVisible();
});

test('Dùng ảnh này giữ canvas và mở ô nhập gọn với đúng ảnh đã chọn', async ({ page }, testInfo) => {
  const { posts } = await setup(page);
  if (testInfo.project.name === 'pc') await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  await library.locator('[data-image-id="portrait-two"]').click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await viewer.getByRole('button', { name: 'Dùng ảnh này', exact: true }).click();
  await expect(viewer).toBeVisible();
  await expect(library).not.toBeVisible();
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/portrait-two');
  const input = viewer.getByLabel('Bạn muốn sửa gì trong ảnh?');
  await expect(input).toBeFocused();
  await expect(input).toHaveValue('Ngôi nhà giữa núi xanh');
  await expect(viewer.getByRole('img', { name: 'Ảnh gốc để chỉnh sửa' })).toHaveAttribute('src', '/api/imagine/images/portrait-two');
  await expect(viewer.getByText('Gợi ý chỉnh sửa', { exact: true })).toHaveCount(0);
  await expect(viewer.getByText(/ảnh tham chiếu · Khi để Tự động/)).toHaveCount(0);
  await expect(viewer.getByText('Ảnh đã chọn', { exact: true })).toHaveCount(0);
  expect(posts).toHaveLength(0);
  const form = viewer.locator('.imagine-composer');
  if (testInfo.project.name === 'pc') {
    expect((await form.boundingBox())!.height).toBeLessThan(190);
    expect((await viewer.locator('.source-preview').boundingBox())!.width).toBe(56);
  }
  const picture = (await viewer.locator('.workspace-picture').boundingBox())!;
  expect((await form.boundingBox())!.y).toBeGreaterThanOrEqual(picture.y + picture.height);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('use-image-composer.png') });
  await input.fill('Giữ ngôi nhà, đổi sang cảnh hoàng hôn');
  const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  await viewer.getByLabel('Chọn ảnh để sửa').setInputFiles({ name: 'tham-khao.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await expect(viewer.getByRole('img', { name: 'Ảnh tham chiếu 2' })).toBeVisible();
  await viewer.getByRole('button', { name: 'Gỡ ảnh 2' }).click();
  await expect(input).toHaveValue('Giữ ngôi nhà, đổi sang cảnh hoàng hôn');
  if (testInfo.project.name === 'mobile') await viewer.getByRole('button', { name: 'Tùy chọn ảnh', exact: true }).click();
  await viewer.getByLabel('Tỉ lệ ảnh chỉnh sửa').selectOption('3:4');
  if (testInfo.project.name === 'mobile') await viewer.getByRole('button', { name: 'Đóng tùy chọn', exact: true }).click();
  await viewer.getByRole('button', { name: 'Tỉ lệ: 3:4' }).click();
  await viewer.getByRole('menuitemradio', { name: 'Tự động', exact: true }).click();
  await expect(viewer.getByLabel('Tỉ lệ ảnh chỉnh sửa')).toHaveValue('auto');
  await clickTool(viewer, 'Bảng màu');
  await viewer.getByRole('button', { name: 'Bắc Âu', exact: true }).click();
  await expect(input).toHaveValue(/Giữ ngôi nhà, đổi sang cảnh hoàng hôn\nÁp dụng bảng màu bắc âu/);
  await input.fill('Giữ ngôi nhà, đổi sang cảnh hoàng hôn');
  await viewer.getByRole('button', { name: 'Tỉ lệ: Tự động' }).click();
  await page.keyboard.press('Escape');
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole('menu', { name: 'Tỉ lệ' })).toHaveCount(0);
  await noPageOverflow(page);
  await viewer.getByRole('button', { name: 'Sửa ảnh', exact: true }).click();
  await expect(viewer).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ prompt: 'Giữ ngôi nhà, đổi sang cảnh hoàng hôn', source_image_id: 'portrait-two', aspect_ratio: 'auto' });
  expect(posts[0]).not.toHaveProperty('source_image');
});

for (const shape of ['portrait', 'landscape', 'square'] as const) {
  test(`bánh xe zoom ảnh ${shape}, giữ con trỏ và bấm phần trăm về 100%`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'pc', 'Bánh xe chuột dành cho desktop.');
    const { posts } = await setup(page, 'Ngôi nhà giữa núi xanh', shape);
    const errors: string[] = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto('/#imagine');
    await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
    const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
    const picture = viewer.locator('.workspace-picture img');
    const percent = viewer.getByRole('button', { name: 'Vừa khung', exact: true });
    const stage = viewer.locator('.workspace-canvas');
    await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toBeVisible();
    const initial = (await picture.boundingBox())!;
    const point = { x: initial.x + initial.width * .65, y: initial.y + initial.height * .65 };
    await page.mouse.move(point.x, point.y);
    await page.mouse.wheel(0, -120);
    await expect.poll(async () => (await picture.boundingBox())!.height).toBeGreaterThan(initial.height * 1.05);
    expect(Number((await percent.innerText()).replace('%', ''))).toBeGreaterThan(100);
    const enlarged = (await picture.boundingBox())!;
    // Điểm ảnh dưới chuột không nhảy sang chỗ khác khi ảnh đã cần cuộn.
    // Khi ảnh vẫn nhỏ hơn khung theo một chiều, chiều đó tiếp tục căn giữa.
    const overflow = await stage.evaluate(element => ({ x: element.scrollWidth > element.clientWidth, y: element.scrollHeight > element.clientHeight }));
    if (overflow.x) expect(Math.abs(enlarged.x + enlarged.width * .65 - point.x)).toBeLessThan(3);
    if (overflow.y) expect(Math.abs(enlarged.y + enlarged.height * .65 - point.y)).toBeLessThan(3);
    const pageScroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
    expect(pageScroll).toEqual({ x: 0, y: 0 });
    for (let i = 0; i < 8; i++) await page.mouse.wheel(0, -240);
    await expect(percent).toHaveText('800%');
    await expect(viewer.getByRole('button', { name: 'Phóng to ảnh' })).toBeDisabled();
    await viewer.getByRole('button', { name: 'Thu nhỏ ảnh' }).click();
    await expect(percent).toHaveText('775%');
    await clickWorkspaceAction(viewer, 'Phóng to ảnh');
    await expect(percent).toHaveText('800%');
    await expect(viewer.getByRole('button', { name: 'Phóng to ảnh' })).toBeDisabled();
    await page.mouse.move(point.x, point.y);
    for (let i = 0; i < 8; i++) await page.mouse.wheel(0, 240);
    await expect(percent).toHaveText('50%');
    await expect(viewer.getByRole('button', { name: 'Thu nhỏ ảnh' })).toBeDisabled();
    await percent.click();
    await expect(percent).toHaveText('100%');
    await expect.poll(async () => Math.abs((await picture.boundingBox())!.height - initial.height)).toBeLessThan(3);
    expect(await stage.evaluate(element => ({ left: element.scrollLeft, top: element.scrollTop }))).toEqual({ left: 0, top: 0 });
    const panel = (await viewer.locator('.workspace-panel-body').boundingBox())!;
    await page.mouse.move(panel.x + 20, panel.y + 20);
    await page.mouse.wheel(0, -120);
    await expect(percent).toHaveText('100%');
    // Các phím zoom trình duyệt và cuộn ngang không bị listener giữ lại.
    const untouched = await stage.evaluate(element => {
      const browserZoom = new WheelEvent('wheel', { deltaY: -120, ctrlKey: true, bubbles: true, cancelable: true });
      const horizontal = new WheelEvent('wheel', { deltaX: 120, bubbles: true, cancelable: true });
      element.dispatchEvent(browserZoom); element.dispatchEvent(horizontal);
      return !browserZoom.defaultPrevented && !horizontal.defaultPrevented;
    });
    expect(untouched).toBe(true);
    await expect(percent).toHaveText('100%');
    await noPageOverflow(page);
    expect(posts).toHaveLength(0);
    expect(errors).toEqual([]);
  });
}

test('lịch sử sát sidebar, cuộn riêng, mở lại URL và sửa tiếp từ bản cũ', async ({ page }, testInfo) => {
  const { posts, revisions, job } = await setup(page);
  for (let i = 1; i <= 16; i++) revisions.push({ ...job, id: `history-${i}`, created_at: i + 1, status: 'complete',
    root_image_id: 'portrait', edit_parent_image_id: i === 1 ? 'portrait' : `history-image-${i - 1}`,
    images: [{ id: `history-image-${i}`, url: `/api/imagine/images/history-image-${i}`, mime: 'image/png' }] });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  const rail = viewer.getByRole('navigation', { name: 'Lịch sử chỉnh sửa ảnh' });
  await expect(rail.getByRole('button', { name: 'Ảnh chính', exact: true })).toHaveAttribute('aria-current', 'true');
  await expect(rail.locator('.history-thumb')).toHaveCount(17);
  const list = rail.locator('.history-list');
  if (testInfo.project.name === 'pc') {
    const sidebar = (await page.locator('.sidebar').boundingBox())!;
    expect((await rail.boundingBox())!.x).toBe(sidebar.x + sidebar.width);
    expect((await rail.locator('.history-thumb').first().boundingBox())!.width).toBe(64);
    await rail.getByRole('button', { name: 'Cuộn lịch sử xuống' }).click();
    await expect.poll(() => list.evaluate(element => element.scrollTop)).toBeGreaterThan(20);
    await list.evaluate(element => { element.scrollTop = 0; });
    const bounds = (await list.boundingBox())!;
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.wheel(0, 480);
    await expect.poll(() => list.evaluate(element => element.scrollTop)).toBeGreaterThan(200);
    await expect(viewer.getByRole('button', { name: 'Vừa khung', exact: true })).toHaveText('100%');
  }
  await rail.getByRole('button', { name: 'Phiên bản 12', exact: true }).click();
  await expect(page).toHaveURL(/#imagine\/portrait\/history-image-12$/);
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/history-image-12');
  await page.reload();
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/history-image-12');
  await rail.getByRole('button', { name: 'Phiên bản 2', exact: true }).click();
  await page.goBack();
  await expect(page).toHaveURL(/#imagine\/portrait\/history-image-12$/);
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/history-image-12');
  await page.goForward();
  await expect(viewer.locator('.workspace-picture img')).toHaveAttribute('src', '/api/imagine/images/history-image-2');
  await viewer.getByLabel('Mô tả chỉnh sửa ảnh').fill('Đổi nền từ phiên bản cũ');
  await viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' }).click();
  expect(posts[0]).toMatchObject({ source_image_id: 'history-image-2', edit_parent_image_id: 'history-image-2' });
  await expect(rail.locator('.history-thumb')).toHaveCount(18);
  await expect(page).toHaveURL(/#imagine\/portrait\/result-1$/);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('version-history.png') });
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  await expect(library.locator('.library-tile')).toHaveCount(2);
});
