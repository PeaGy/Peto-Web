import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

/** Ảnh dọc đủ lớn để phát hiện lỗi kích thước; không dùng ảnh 1 px để đánh giá bố cục. */
async function setup(page: Page, prompt = 'Ngôi nhà giữa núi xanh', shape: 'portrait' | 'landscape' | 'square' = 'portrait') {
  await mockPeto(page);
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
  const job = { id: 'landscape', prompt, quality: 'medium', resolution: '2k', aspect_ratio: '2:3', created_at: 1, images: [image('portrait'), image('portrait-two')] };
  const posts: Record<string, unknown>[] = [];
  await page.route('**/api/imagine**', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.pathname.startsWith('/api/imagine/images/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') });
    if (request.method() === 'POST') {
      posts.push(request.postDataJSON());
      return route.fulfill({ status: 202, json: { job: { ...job, id: 'edited', prompt: posts.at(-1)?.prompt, status: 'running', images: [], n: 1 } } });
    }
    if (url.pathname === '/api/imagine') return route.fulfill({ json: { jobs: [job] } });
    return route.fulfill({ status: 404 });
  });
  return { posts };
}

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
    await expect(viewer.evaluate(element => element.matches(':modal'))).resolves.toBe(true);
  }
  await expect(viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' })).toBeDisabled();
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('workspace.png') });
  await viewer.getByRole('button', { name: 'Bảng màu', exact: true }).click();
  await viewer.getByRole('button', { name: 'Lấy màu từ ảnh' }).click();
  await expect(viewer.getByRole('button', { name: /^Màu #/ })).toHaveCount(4);
  await viewer.getByRole('button', { name: 'Bắc Âu', exact: true }).click();
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveValue(/Áp dụng bảng màu bắc âu/);
  expect(posts).toHaveLength(0);
  await page.screenshot({ path: testInfo.outputPath('palette.png') });
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(library).toBeVisible();
  await expect(tile.locator('img')).toHaveAttribute('src', '/api/imagine/images/portrait');
  await library.getByRole('button', { name: 'Quay lại Tạo ảnh' }).click();
  await expect(library).not.toBeVisible();
});

test('cắt/vẽ tạo nguồn PNG mới, hoàn tác giữ ảnh gốc, chỉ gửi khi bấm gửi', async ({ page }, testInfo) => {
  const { posts } = await setup(page);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await viewer.getByRole('button', { name: 'Cắt ảnh', exact: true }).click();
  await viewer.getByLabel('Tỉ lệ cắt').selectOption('1:1');
  await page.screenshot({ path: testInfo.outputPath('crop.png') });
  // Escape chỉ hủy vùng cắt; khung xem vẫn mở.
  await page.keyboard.press('Escape');
  await expect(viewer).toBeVisible();
  await expect(viewer.getByLabel('Tỉ lệ cắt')).toHaveCount(0);
  await viewer.getByRole('button', { name: 'Cắt ảnh', exact: true }).click();
  await viewer.getByRole('button', { name: 'Cắt', exact: true }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('864 × 864');
  await viewer.getByRole('button', { name: 'Hoàn tác chỉnh sửa' }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await viewer.getByRole('button', { name: 'Làm lại chỉnh sửa' }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('864 × 864');
  await viewer.getByRole('button', { name: 'Bút vẽ', exact: true }).click();
  const canvas = viewer.getByLabel('Vẽ ghi chú lên ảnh');
  const bounds = (await canvas.boundingBox())!;
  // Pointer dùng cùng đường xử lý cho chuột và cảm ứng.
  await canvas.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'mouse', button: 0, clientX: bounds.x + bounds.width / 2, clientY: bounds.y + bounds.height / 2 });
  await canvas.dispatchEvent('pointermove', { pointerId: 1, pointerType: 'mouse', clientX: bounds.x + bounds.width * .75, clientY: bounds.y + bounds.height / 2 });
  await canvas.dispatchEvent('pointerup', { pointerId: 1, pointerType: 'mouse' });
  await expect(viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' })).toBeEnabled();
  await viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' }).click();
  await expect(viewer.getByRole('button', { name: 'Áp dụng nét vẽ' })).toBeDisabled();
  await viewer.getByRole('button', { name: 'Làm lại nét vẽ' }).click();
  await viewer.getByRole('button', { name: 'Áp dụng nét vẽ' }).click();
  const data = await viewer.locator('.workspace-picture img').getAttribute('src');
  expect(data).toMatch(/^data:image\/png;base64,/);
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
  await expect(viewer).not.toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ n: 1, background: true, source_image: { data: data!.split(',')[1] }, prompt: 'Đổi thành tranh màu nước' });
  await expect(page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).locator('img')).toHaveAttribute('src', '/api/imagine/images/portrait');
});


test('bấm ảnh để xem, nhấn giữ để chọn và hủy chọn trả về xem ảnh', async ({ page }) => {
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
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText('1 đã chọn');
  await page.mouse.up();
  await expect(tile).toHaveAttribute('aria-pressed', 'true');
  await expect(viewer).not.toBeVisible();
  await expect(library.getByRole('menu')).toHaveCount(0);
  await expect(library.getByText(/Chọn theo thứ tự mong muốn/)).toHaveCount(0);
  await library.locator('[data-image-id="portrait-two"]').click();
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText('2 đã chọn');
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
  await library.getByRole('button', { name: 'Tìm trong thư viện' }).click();
  const search = library.getByRole('searchbox');
  if (testInfo.project.name === 'mobile') await expect(search).toHaveCSS('font-size', '16px');
  await search.fill('Kiến trúc Việt Nam');
  await library.locator('[data-image-id="portrait"]').click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.locator('.workspace-prompt')).toHaveText(prompt);
  await expect(viewer.locator('.workspace-source-chip span')).toHaveAttribute('title', prompt);
  const edit = viewer.getByRole('button', { name: 'Sửa ảnh này', exact: true });
  const bounds = (await edit.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(320);
  const input = viewer.getByLabel('Mô tả chỉnh sửa ảnh');
  await input.fill('Giữ tên bộ sưu tập và đổi sang phong cách màu nước');
  await expect(input).toHaveCSS('font-size', '16px');
  await expect(input).toHaveAttribute('enterkeyhint', 'send');
  expect(await input.evaluate(element => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
  await expect(viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' })).toBeEnabled();
  for (const name of ['Gửi chỉnh sửa ảnh', 'Ẩn bảng công cụ', 'Phóng to ảnh']) {
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
  await viewer.getByRole('button', { name: 'Phóng to ảnh' }).click();
  await expect(viewer.getByRole('button', { name: 'Vừa khung' })).toHaveText('125%');
  const zoomed = (await picture.boundingBox())!;
  const top = (await viewer.locator('.workspace-topbar').boundingBox())!;
  const dock = (await viewer.locator('.workspace-edit-dock').boundingBox())!;
  expect(top.y + top.height).toBeLessThanOrEqual(zoomed.y);
  expect(dock.y).toBeGreaterThanOrEqual(stage.y + stage.height);
  await viewer.getByRole('button', { name: 'Vừa khung' }).click();
  await viewer.getByRole('button', { name: 'Ẩn bảng công cụ' }).click();
  await expect(viewer.locator('.workspace-panel-body')).toBeHidden();
  if (testInfo.project.name === 'pc') {
    expect((await viewer.locator('.workspace-panel').boundingBox())!.width).toBe(60);
    await expect(viewer.getByRole('button', { name: 'Chia sẻ', exact: true })).toBeVisible();
    await viewer.getByRole('button', { name: 'Hiện bảng công cụ' }).click();
  } else {
    await expect(viewer.locator('.workspace-panel-bottom')).toBeHidden();
    await expect(viewer.getByRole('toolbar', { name: 'Công cụ ảnh' })).toBeVisible();
  }
  await viewer.getByRole('button', { name: 'Bảng màu', exact: true }).click();
  await expect(viewer.locator('.workspace-panel')).toBeVisible();
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
