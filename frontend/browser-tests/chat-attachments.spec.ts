import { test, expect, type Page } from '@playwright/test';
import { chatMessages, mockPeto, noPageOverflow, openChat } from './fixtures';

const imageNames = ['Biển buổi sáng.png', 'Núi xanh.png', 'Hoàng hôn.png', 'Bầu trời.png'];
const colors = ['#428a9e', '#659575', '#bf797b', '#7b84b7'];

async function mockImages(page: Page) {
  await page.route('**/api/attachments/scene-*', route => {
    const index = Number(new URL(route.request().url()).pathname.split('-').pop());
    // Ảnh giả có tỷ lệ khác nhau để kiểm tra thumbnail không làm nhảy bố cục.
    return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="${index % 2 ? 200 : 600}" height="400" viewBox="0 0 400 400"><rect width="400" height="400" fill="${colors[index % colors.length]}"/><circle cx="295" cy="100" r="42" fill="#f7ddad"/><path d="M-40 410 135 145 300 410M120 410 300 210 440 410" fill="#173b48" opacity=".6"/><path d="M0 330Q140 280 400 350V400H0" fill="#cee4dd" opacity=".35"/></svg>` });
  });
}

function historyAttachments() {
  return [
    ...imageNames.map((name, i) => ({ id: `scene-${i}`, name, mime: 'image/png', kind: 'image', size: 20480, url: `/api/attachments/scene-${i}` })),
    { id: 'readme', name: 'README.md', mime: 'text/markdown', kind: 'file', size: 2048, url: '/api/attachments/readme',
      document: { status: 'ready', notice: 'Đã đọc nội dung tài liệu.', characters: 500 } },
    { id: 'report', name: 'report.md', mime: 'text/markdown', kind: 'file', size: 4096, url: '/api/attachments/report' },
    { id: 'sheet', name: `${'Báo-cáo-phân-tích-dữ-liệu-'.repeat(8)}2026.xlsx`, mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', kind: 'file', size: 8192, url: '/api/attachments/sheet' },
  ];
}

test('ảnh và tệp đứng riêng phía trên lời nhắn, tự xuống hàng và hợp cả hai theme', async ({ page }, info) => {
  await mockPeto(page);
  await mockImages(page);
  await page.route('**/api/conversations/A/messages', route => route.fulfill({ json: {
    messages: chatMessages.map((message, index) => index ? message : {
      ...message, content: 'Bạn xem giúp những ảnh và tài liệu này nhé.', attachments: historyAttachments(),
    }),
  } }));
  await openChat(page);
  const user = page.locator('.chat-user-message');
  const images = user.locator('.message-image-link');
  const cards = user.locator('.message-file-card');
  await expect(images).toHaveCount(4);
  await expect(cards).toHaveCount(3);
  await expect(user.getByText('Đã đọc chữ', { exact: true })).toHaveCount(0);
  await expect.poll(() => images.locator('img').evaluateAll(nodes => nodes.every(node => (node as HTMLImageElement).complete && (node as HTMLImageElement).naturalWidth > 0))).toBe(true);
  const imageBoxes = await images.evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }));
  imageBoxes.forEach(box => {
    expect(box.width).toBe(info.project.name === 'mobile' ? 96 : 112);
    expect(box.height).toBe(box.width);
  });
  expect(imageBoxes[3].y > imageBoxes[0].y).toBe(info.project.name === 'mobile');
  const cardBoxes = await cards.evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, scrollWidth: node.scrollWidth }; }));
  for (let i = 1; i < cardBoxes.length; i++) {
    expect(cardBoxes[i].y).toBeGreaterThan(cardBoxes[i - 1].bottom);
    expect(cardBoxes[i].right).toBeCloseTo(cardBoxes[0].right, 0);
  }
  cardBoxes.forEach(box => expect(box.scrollWidth).toBeLessThanOrEqual(box.width + 1));
  const text = await user.locator('.user-message-text').boundingBox();
  expect(text!.y).toBeGreaterThan(cardBoxes[2].bottom);
  expect(text!.x + text!.width).toBeCloseTo(cardBoxes[0].right, 0);
  expect(await user.evaluate(node => getComputedStyle(node).backgroundColor)).toBe('rgba(0, 0, 0, 0)');
  await expect(cards.last()).toHaveAttribute('title', /Báo-cáo-phân-tích-dữ-liệu-.*2026.xlsx · Bảng tính · 8 KB/);
  await page.locator('.messages').evaluate(node => { node.scrollTop = 0; });
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('chat-attachments-dark.png') });
  // Dùng cơ chế theme thật của ứng dụng; không thay CSS để chụp ảnh.
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('chat-attachments-light.png') });
  await page.reload();
  await expect(images).toHaveCount(4);
  await expect(cards).toHaveCount(3);
});

test('vừa gửi và khi máy chủ xác nhận có cùng kích thước thumbnail, hỗ trợ sửa và tải tệp', async ({ page }) => {
  await mockPeto(page);
  await mockImages(page);
  let accept!: () => void;
  const receipt = new Promise<void>(resolve => { accept = resolve; });
  let payload: { message: string; attachments: { name: string; mime: string; data: string }[] } | undefined;
  await page.route('**/api/chat', async route => {
    payload = route.request().postDataJSON();
    await receipt;
    const attachments = payload!.attachments.map((file, i) => ({
      id: `stored-${i}`, name: file.name, mime: file.mime, kind: file.mime.startsWith('image/') ? 'image' : 'file',
      size: Buffer.from(file.data, 'base64').length, url: `/api/attachments/${file.mime.startsWith('image/') ? `scene-${i}` : `file-${i}`}`,
    }));
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low', message: { id: 101, role: 'user', content: payload!.message, attachments } })
      + event({ type: 'delta', text: 'Đã nhận ảnh và tài liệu.' }) + event({ type: 'done' }),
    });
  });
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aEAAAAABJRU5ErkJggg==', 'base64');
  await page.locator('.chat input[type=file]').setInputFiles([
    { name: imageNames[0], mimeType: 'image/png', buffer: png },
    { name: imageNames[1], mimeType: 'image/png', buffer: png },
    { name: 'README.md', mimeType: 'text/markdown', buffer: Buffer.from('Nội dung tài liệu giả.') },
    { name: 'report.md', mimeType: 'text/markdown', buffer: Buffer.from('Báo cáo giả.') },
  ]);
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Bạn xem giúp mình nhé.');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  const user = page.locator('.chat-user-message');
  const imageGrid = user.locator('.message-image-grid');
  await expect(user.getByRole('img')).toHaveCount(2);
  await expect.poll(() => Boolean(payload)).toBe(true);
  expect(payload!.attachments.map(file => file.name)).toEqual([imageNames[0], imageNames[1], 'README.md', 'report.md']);
  const before = await imageGrid.boundingBox();
  await user.locator('.message-image-link').first().click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đính kèm' });
  await expect(viewer.getByRole('combobox')).toBeEnabled();
  await viewer.getByRole('combobox').selectOption('2');
  accept();
  await expect(page.getByText('Đã nhận ảnh và tài liệu.', { exact: true })).toBeVisible();
  await expect(user.locator('.message-image-link').first()).toHaveAttribute('href', '/api/attachments/scene-0');
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole('img')).toHaveAttribute('src', '/api/attachments/scene-0');
  await expect(viewer.getByRole('combobox')).toHaveValue('2');
  await viewer.getByRole('button', { name: 'Đóng ảnh' }).click();
  const after = await imageGrid.boundingBox();
  expect(after!.width).toBe(before!.width);
  expect(after!.height).toBe(before!.height);
  await expect(user.getByRole('link', { name: /README.md/ })).toHaveAttribute('download', 'README.md');
  await user.hover();
  await user.getByRole('button', { name: 'Sửa tin nhắn', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Sửa tin nhắn', exact: true })).toHaveValue('Bạn xem giúp mình nhé.');
  await expect(user.getByRole('img')).toHaveCount(2);
  await noPageOverflow(page);
  await page.getByRole('button', { name: 'Hủy', exact: true }).click();
  await expect(user.locator('.user-message-text')).toHaveText('Bạn xem giúp mình nhé.');
});

test('mười sáu tệp vẫn đọc được tên, cuộn trong chat và không tràn trang', async ({ page }) => {
  await mockPeto(page);
  await page.route('**/api/conversations/A/messages', route => route.fulfill({ json: {
    messages: chatMessages.map((message, index) => index ? message : { ...message, content: '',
      attachments: Array.from({ length: 16 }, (_, i) => ({ id: `file-${i}`, name: `Tệp-${i}-${'tên-dài-'.repeat(40)}.txt`, mime: 'text/plain', kind: 'file', size: 1000, url: `/api/attachments/file-${i}` })),
    }),
  } }));
  await openChat(page);
  const user = page.locator('.chat-user-message');
  await expect(user.locator('.message-file-card')).toHaveCount(16);
  await expect(user.locator('.user-message-text')).toHaveCount(0);
  await user.locator('.message-file-card').last().scrollIntoViewIfNeeded();
  await expect(user.locator('.message-file-card').last()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeInViewport();
  expect(await page.locator('.messages').evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
  await noPageOverflow(page);
});
