// Kiểm chứng mạng thật theo yêu cầu chủ web. Backend/tài khoản giả, không gọi AI/TTS hoặc dùng profile cá nhân.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { parseArgs } from 'node:util';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { cpus, platform, release } from 'node:os';

const { values } = parseArgs({ options: {
  live: { type: 'boolean', default: false }, browser: { type: 'string', default: 'chrome' },
  headed: { type: 'boolean', default: false },
  'background-only': { type: 'boolean', default: false },
  base: { type: 'string', default: 'http://127.0.0.1:5188' },
  output: { type: 'string', default: '../.runtime/youtube-tv-stage4' },
  observe: { type: 'string', default: '15' }, sample: { type: 'string', default: '8' },
} });
if (!values.live) throw new Error('Chỉ chạy khi chủ web yêu cầu kiểm chứng mạng thật: thêm --live.');
const base = new URL(values.base);
assert(['127.0.0.1', 'localhost'].includes(base.hostname) && base.protocol === 'http:', 'Chỉ dùng bản build loopback.');
assert(['chrome', 'msedge'].includes(values.browser));
const seconds = Number(values.observe), sampleSeconds = Number(values.sample);
assert(seconds >= 5 && seconds <= 30 && sampleSeconds >= 5 && sampleSeconds <= 20);
const output = resolve(values.output); mkdirSync(output, { recursive: true });
const runFile = promisify(execFile);
const sleep = ms => new Promise(done => setTimeout(done, ms));
const videos = [
  { id: 'HDz9dSuAI4s', title: 'Miku concert' }, { id: 'e1xCOsgWG0M', title: 'DECO*27 — Vampire' },
  { id: 'Soy4jGPHr3g', title: 'Tetris' }, { id: 'dQw4w9WgXcQ', title: 'Rick Astley' },
  { id: 'JGwWNGJdvx8', title: 'Shape of You' }, { id: 'aircAruvnKk', title: '3Blue1Brown' },
];
const report = { date: new Date().toISOString(), browser: values.browser, headless: !values.headed,
  scope: values['background-only'] ? 'desktop background only' : 'six-video matrix and lifecycle',
  platform: `${platform()} ${release()}`, cpu: cpus()[0]?.model, logicalCpus: cpus().length,
  backend: 'fake', renderer: 'real Live2D', youtube: 'real iframe/API', observeSeconds: seconds,
  sampleSeconds, videos: [], resources: [], checks: [], javascriptErrors: [], limitations: [
    'Profile trình duyệt tạm, không đăng nhập YouTube; kết quả quảng cáo chỉ trong thời gian lấy mẫu.',
    'Mobile mô phỏng không thay cho nghiệm thu Android thật; chế độ không cửa sổ không luôn đổi document.hidden.',
    'CPU 100% = một lõi. RAM private là commit; tổng working set có thể tính trùng trang dùng chung, không gồm VRAM.',
  ] };
function save() { writeFileSync(resolve(output, `${values.browser}.json`), JSON.stringify(report, null, 2)); }
async function until(read, accept, timeout = 20000) {
  const end = performance.now() + timeout; let last;
  do { last = await read(); if (accept(last)) return last; await sleep(250); } while (performance.now() < end);
  throw new Error(`Hết thời gian đợi: ${JSON.stringify(last)}`);
}
async function check(name, action) {
  try { const details = await action(); report.checks.push({ name, passed: true, details }); }
  catch (error) { report.checks.push({ name, passed: error.name === 'NotExercised' ? null : false, error: String(error) }); }
  console.log(JSON.stringify(report.checks.at(-1))); save();
}
async function mockBackend(page) {
  const favorites = new Map();
  await page.addInitScript(() => {
    localStorage.setItem('peto-companion-muted', '1'); localStorage.setItem('peto-theme', 'dark');
    window.__playerCheckEvents = [];
    window.__playerCheckClicks = [];
    document.addEventListener('click', event => {
      if (event.target instanceof Element && event.target.closest('.yt-play-button')) {
        window.__playerCheckClicks.push(performance.now());
      }
    }, true);
    window.addEventListener('message', event => {
      if (event.origin !== 'https://www.youtube.com') return;
      try { const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (['onReady', 'onStateChange', 'onError', 'onAutoplayBlocked'].includes(data?.event)) {
          window.__playerCheckEvents.push({ time: performance.now(), event: data.event, info: data.info });
        }
      } catch { /* Không lưu message khác hay dữ liệu cá nhân. */ }
    });
  });
  page.on('pageerror', error => report.javascriptErrors.push(error.message));
  await page.route(url => url.origin === base.origin && url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith('/api/companion/player/')) {
      const id = path.split('/').at(-1), item = videos.find(video => video.id === id);
      const track = { video_id: id, title: item?.title ?? 'Video kiểm thử', artist: 'Metadata giả — YouTube phát thật' };
      if (path.includes('/videos/')) return route.fulfill({ json: track });
      if (path.includes('/favorites')) {
        if (route.request().method() === 'POST') favorites.set(id, track);
        if (route.request().method() === 'DELETE') favorites.delete(id);
        return route.fulfill({ json: { favorites: [...favorites.values()] } });
      }
    }
    const data = path === '/api/auth/me' ? { authenticated: true, login_configured: true,
      user: { id: 'youtube-stage4-test', provider: 'discord', username: 'kiem-thu', display_name: 'Kiểm thử Player', avatar_url: '' } }
      : path === '/api/app-info' ? { name: 'Peto', avatar_url: null }
      : path === '/api/projects' ? { projects: [] }
      : path === '/api/conversations' ? { conversations: [], has_more: false }
      : path === '/api/companion' ? { conversation_id: 'test', messages: [] }
      : path === '/api/companion/memory' ? { available: false, enabled: false, pending: false, limit: 50, memories: [] }
      : path === '/api/voice/health' ? { ok: false, voices: [], home: { online: false, voices: [] }, official: { allowed: false, voices: [], used: 0, limit: 0 } }
      : path === '/api/auth/logout' ? { ok: true } : null;
    return data ? route.fulfill({ json: data }) : route.fulfill({ status: 404, json: { detail: 'Không dùng trong kiểm chứng Player.' } });
  });
}
function requireVisibility(hidden) {
  if (hidden) return;
  const error = new Error(values['background-only'] ? 'Chưa quan sát được trang ẩn trong cửa sổ thật.'
    : 'Ma trận không kiểm chứng visibility; dùng --headed --background-only với context mặc định.');
  error.name = values['background-only'] ? 'Error' : 'NotExercised'; throw error;
}
let profile, browserProcess, browser;
if (values['background-only']) {
  assert(values.headed && platform() === 'win32', 'Ca nền tự nhiên cần --headed và Chrome/Edge Windows.');
  const executable = values.browser === 'chrome' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
    : 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
  profile = mkdtempSync(resolve(output, `${values.browser}-profile-`));
  browserProcess = spawn(executable, [`--user-data-dir=${profile}`, '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
    '--no-first-run', '--no-default-browser-check', '--lang=vi-VN', 'about:blank'], { windowsHide: false, stdio: 'ignore' });
  let launchError;
  browserProcess.on('error', error => { launchError = error; });
  const port = await until(() => {
    if (launchError) throw launchError;
    try { return Number(readFileSync(resolve(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]); } catch { return 0; }
  }, value => value > 0 && value < 65536);
  // noDefaults chỉ áp dụng cho context mặc định: không bật focus emulation hay cờ chống throttling.
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { noDefaults: true });
} else {
  browser = await chromium.launch({ channel: values.browser, headless: !values.headed,
    ignoreDefaultArgs: ['--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'] });
}
report.version = browser.version();
const system = await browser.newBrowserCDPSession();
const context = values['background-only'] ? browser.contexts()[0]
  : await browser.newContext({ locale: 'vi-VN', reducedMotion: 'no-preference' });
const page = context.pages()[0] ?? await context.newPage();
await page.setViewportSize({ width: 1440, height: 900 }); await mockBackend(page);
const clickOptions = values['background-only'] ? { force: true } : {};
const shell = page.locator('.yt-player');
const slider = shell.locator('input[aria-label="Vị trí phát"]');
const state = () => shell.getAttribute('data-status');
async function nativeSample(target = page, embedded = true) {
  try {
    const frame = embedded ? target.frames().find(frame => frame.url().startsWith('https://www.youtube.com/embed/')) : target.mainFrame();
    if (!frame) return null;
    return await frame.evaluate(() => {
      const player = document.querySelector('.html5-video-player'), video = document.querySelector('video');
      const link = document.querySelector('a[href*="/watch?v="]');
      return { adShowing: player ? player.classList.contains('ad-showing') : null,
        time: video?.currentTime ?? null, duration: Number.isFinite(video?.duration) ? video.duration : null,
        paused: video?.paused ?? null, muted: video?.muted ?? null, volume: video?.volume ?? null,
        width: video?.videoWidth ?? 0, height: video?.videoHeight ?? 0,
        title: document.title, pageUrl: location.href, href: link?.href ?? null,
        error: document.querySelector('.ytp-error-content-wrap')?.textContent?.slice(0, 240) ?? '' };
    });
  } catch { return null; }
}
async function observe(target, duration, embedded = true) {
  const samples = [], begin = performance.now();
  do { samples.push({ elapsedMs: Math.round(performance.now() - begin), ...await nativeSample(target, embedded) });
    await sleep(Math.min(1500, Math.max(0, duration * 1000 - (performance.now() - begin))));
  } while (performance.now() - begin < duration * 1000);
  return { actualSeconds: (performance.now() - begin) / 1000, samples,
    adsObserved: samples.filter(sample => sample.adShowing === true).length,
    adStateReadable: samples.some(sample => sample.adShowing !== null && sample.adShowing !== undefined) };
}
async function resource(label) {
  const start = (await system.send('SystemInfo.getProcessInfo')).processInfo;
  const begin = performance.now(); await sleep(sampleSeconds * 1000);
  const end = (await system.send('SystemInfo.getProcessInfo')).processInfo;
  const elapsed = (performance.now() - begin) / 1000;
  const old = new Map(start.map(process => [process.id, process.cpuTime]));
  const delta = end.reduce((total, process) => total + Math.max(0, process.cpuTime - (old.get(process.id) ?? 0)), 0);
  const ids = end.map(process => process.id).filter(id => Number.isSafeInteger(id) && id > 0);
  let memory = null;
  if (platform() === 'win32' && ids.length) {
    const command = `$playerProcesses=Get-Process -Id ${ids.join(',')} -ErrorAction SilentlyContinue; [pscustomobject]@{privateBytes=($playerProcesses | Measure-Object PrivateMemorySize64 -Sum).Sum; workingSetBytes=($playerProcesses | Measure-Object WorkingSet64 -Sum).Sum} | ConvertTo-Json -Compress`;
    const result = await runFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command], { windowsHide: true });
    memory = JSON.parse(result.stdout);
  }
  const result = { label, elapsedSeconds: elapsed, cpuPctOneCore: delta / elapsed * 100, processes: ids.length,
    exitedProcesses: start.filter(process => !ids.includes(process.id)).length,
    privateMiB: memory ? memory.privateBytes / 1048576 : null, workingSetMiB: memory ? memory.workingSetBytes / 1048576 : null,
    iframeCount: await shell.locator('iframe').count(), canvasCount: await page.locator('.character-canvas canvas').count() };
  report.resources.push(result); console.log(JSON.stringify(result)); save();
}
async function selectVideo(video, cold = false) {
  if (!await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).isVisible()) await shell.getByRole('button', { name: 'File', exact: true }).click(clickOptions);
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill(`https://www.youtube.com/watch?v=${video.id}`);
  const begin = performance.now();
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click(clickOptions);
  await sleep(150);
  await until(state, value => ['error', 'ready'].includes(value), 35000);
  const readyMs = performance.now() - begin;
  let nativeFallback = false, playWaitError = '', playBegin = null, clickActionMs = null;
  const clickIndex = await page.evaluate(() => window.__playerCheckClicks.length);
  if (await state() === 'ready') {
    playBegin = performance.now();
    await shell.getByRole('button', { name: 'Phát video', exact: true }).click(clickOptions);
    clickActionMs = performance.now() - playBegin;
    try { await until(state, value => ['playing', 'error', 'blocked'].includes(value), 20000); }
    catch (error) {
      playWaitError = String(error);
      await page.screenshot({ path: resolve(output, `${values.browser}-${video.id}-play-pending.png`) });
      const frame = page.frames().find(frame => frame.url().startsWith('https://www.youtube.com/embed/'));
      const play = frame?.getByRole('button', { name: /^(Phát video|Play video|Phát|Play)$/ }).first();
      if (play && await play.isVisible()) {
        nativeFallback = true; await play.click(clickOptions);
        await until(state, value => ['playing', 'error', 'blocked'].includes(value), 10000).catch(() => {});
      }
    }
  }
  const playState = await state(), playResponseMs = performance.now() - begin;
  const playLatencyMs = playBegin === null ? null : performance.now() - playBegin;
  const browserPlayLatencyMs = await page.evaluate(index => {
    const click = window.__playerCheckClicks[index];
    const playing = window.__playerCheckEvents.find(event => event.event === 'onStateChange' && event.info === 1 && event.time >= click);
    return playing ? playing.time - click : null;
  }, clickIndex);
  const observations = playState === 'playing' ? await observe(page, seconds) : null;
  const error = (await shell.locator('.yt-player-error').allTextContents()).join('\n');
  const samples = observations?.samples.filter(sample => sample.time !== null && sample.adShowing === false) ?? [];
  const progress = samples.length > 1 ? samples.at(-1).time - samples[0].time : null;
  const native = await nativeSample();
  const result = { ...video, cold, readyMs, playResponseMs, playLatencyMs, browserPlayLatencyMs, clickActionMs, playState, error, progressSeconds: progress, nativeFallback, playWaitError,
    events: await page.evaluate(() => window.__playerCheckEvents.slice(-12)),
    requestedVideoConfirmed: native?.href ? new URL(native.href).searchParams.get('v') === video.id : false,
    native, observations, iframeCount: await shell.locator('iframe').count() };
  report.videos.push(result); console.log(JSON.stringify({ video: video.title, state: playState, readyMs, progress, error, ads: observations?.adsObserved })); save();
  await page.screenshot({ path: resolve(output, `${values.browser}-${video.id}.png`) });
  return result;
}
try {
  await page.goto(`${base.origin}/companion`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion', exact: true }).waitFor({ timeout: 40000 });
  assert.equal(await page.locator('.character-canvas canvas').count(), 1);
  assert(!(await page.locator('.companion-title').textContent()).includes('Trả lời ngắn bằng tiếng Anh'));
  await sleep(3000); if (!values['background-only']) await resource('off_before_api');
  const openBegin = performance.now(); await page.getByRole('button', { name: 'Player', exact: true }).click(clickOptions);
  await shell.waitFor(); report.shellOpenMs = performance.now() - openBegin;
  const first = await selectVideo(videos[2], true);
  if (first.playState === 'playing') {
    if (!values['background-only']) await check('controls_pause_seek_volume_native_space', async () => {
      await shell.getByRole('button', { name: 'Tạm dừng video', exact: true }).click(clickOptions); await until(state, value => value === 'paused');
      const box = await slider.boundingBox(), duration = Number(await slider.getAttribute('max'));
      await page.mouse.click(box.x + box.width * (60 / duration), box.y + box.height / 2);
      await until(async () => Number(await slider.inputValue()), value => value > 50 && value < 70);
      await shell.getByRole('button', { name: 'Tắt tiếng', exact: true }).focus();
      const volume = shell.getByRole('slider', { name: 'Âm lượng Player', exact: true });
      await volume.press('End'); await until(() => volume.inputValue(), value => value === '100');
      await shell.getByRole('button', { name: 'Tắt tiếng', exact: true }).click(clickOptions); await until(() => volume.inputValue(), value => value === '0');
      await shell.getByRole('button', { name: 'Bật tiếng', exact: true }).click(clickOptions); await until(() => volume.inputValue(), value => value === '100');
      await shell.locator('iframe').focus(); await page.keyboard.press('Space'); await until(state, value => value === 'playing');
      await page.keyboard.press('Space'); await until(state, value => value === 'paused');
      await shell.getByRole('button', { name: 'Phát video', exact: true }).click(clickOptions); await until(state, value => value === 'playing');
      return { seekSeconds: Number(await slider.inputValue()), volume: 100 };
    });
    if (!values['background-only']) await resource('video_playing_visible');
    if (await state() !== 'playing') {
      await shell.getByRole('button', { name: 'Phát video', exact: true }).click(clickOptions); await until(state, value => value === 'playing');
    }
    await shell.getByRole('button', { name: 'Phát lại từ đầu', exact: true }).click(clickOptions);
    const iframe = await shell.locator('iframe').elementHandle();
    await check('desktop_minimize_player', async () => {
      const before = Number(await slider.inputValue()); await shell.getByRole('button', { name: 'Thu nhỏ Player', exact: true }).click(clickOptions);
      assert.equal(await shell.isVisible(), false); await sleep(6000);
      const after = Number(await slider.inputValue()); assert(after > before + 2); assert(await iframe.evaluate(node => node.isConnected));
      await page.getByRole('button', { name: 'Player', exact: true }).click(clickOptions); return { before, after };
    });
    if (!await shell.isVisible()) await page.getByRole('button', { name: 'Player', exact: true }).click(clickOptions);
    await check('desktop_browser_tab_background', async () => {
      if (!values.headed) requireVisibility(false);
      const before = Number(await slider.inputValue()), other = await context.newPage();
      try { await other.goto('about:blank'); await other.bringToFront(); await sleep(6000);
        const hidden = await page.evaluate(() => document.hidden), after = Number(await slider.inputValue());
        requireVisibility(hidden); assert(after > before + 2);
        return { hidden, before, after, sameIframe: await iframe.evaluate(node => node.isConnected) };
      } finally { await other.close(); await page.bringToFront(); }
    });
    await check('desktop_browser_window_minimized', async () => {
      if (!values.headed) requireVisibility(false);
      const session = await context.newCDPSession(page);
      const { windowId } = await session.send('Browser.getWindowForTarget');
      const before = Number(await slider.inputValue());
      try { await session.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'minimized' } }); await sleep(6000);
        const bounds = await session.send('Browser.getWindowBounds', { windowId });
        const hidden = await page.evaluate(() => document.hidden), after = Number(await slider.inputValue());
        assert.equal(bounds.bounds.windowState, 'minimized'); requireVisibility(hidden); assert(after > before + 2);
        return { hidden, before, after };
      } finally { await session.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal' } }); await session.detach(); await page.bringToFront(); }
    });
    await check('desktop_companion_to_chat', async () => {
      const before = Number(await slider.inputValue()); await page.getByRole('button', { name: 'Trò chuyện', exact: true }).click(clickOptions);
      assert.equal(await shell.isVisible(), false); await sleep(6000);
      const after = Number(await slider.inputValue()); assert(after > before + 2); assert(await iframe.evaluate(node => node.isConnected));
      return { before, after, canvasCount: await page.locator('.character-canvas canvas').count() };
    });
    if (!values['background-only']) await resource('video_background_in_chat');
    await page.getByRole('button', { name: 'Companion', exact: true }).click(clickOptions);
    if (!await shell.isVisible()) await page.getByRole('button', { name: 'Player', exact: true }).click(clickOptions);
    await shell.getByRole('button', { name: 'Tạm dừng video', exact: true }).click(clickOptions).catch(() => {});
  }
  for (const video of videos.filter(video => !values['background-only'] && video.id !== videos[2].id)) {
    try { await selectVideo(video); } catch (error) { report.videos.push({ ...video, failure: String(error) }); save(); }
  }
  await shell.getByRole('button', { name: 'Đóng Player', exact: true }).click(clickOptions);
  assert.equal(await page.locator('.yt-player iframe').count(), 0);
  if (!values['background-only']) { await sleep(2000); await resource('off_after_close'); }
  if (values.browser === 'chrome' && !values['background-only']) {
    const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: 'vi-VN' });
    const mobile = await mobileContext.newPage(); await mockBackend(mobile);
    await check('mobile_emulated_layout_hide_and_close', async () => {
      await mobile.goto(`${base.origin}/companion`, { waitUntil: 'domcontentloaded' });
      const chat = mobile.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion', exact: true }); await chat.waitFor({ timeout: 40000 });
      await mobile.getByRole('button', { name: 'Mở menu', exact: true }).click(clickOptions); await mobile.getByRole('button', { name: 'Player', exact: true }).click(clickOptions);
      await mobile.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('https://youtu.be/Soy4jGPHr3g');
      await mobile.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click(clickOptions);
      const root = mobile.locator('.yt-player'); await until(() => root.getAttribute('data-status'), value => value === 'ready', 35000);
      await root.getByRole('button', { name: 'Phát video', exact: true }).click(clickOptions);
      await until(() => root.getAttribute('data-status'), value => value === 'playing', 15000);
      await sleep(2000);
      const native = await root.locator('iframe').elementHandle(), sizes = [];
      for (const viewport of [{ width: 390, height: 844 }, { width: 320, height: 640 }, { width: 844, height: 390 }]) {
        await mobile.setViewportSize(viewport); await sleep(500);
        const box = await root.locator('iframe').boundingBox(); assert(box.width >= 200 && box.height >= 200); assert(await native.evaluate(node => node.isConnected));
        assert(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); sizes.push({ viewport, iframe: box });
      }
      await mobile.setViewportSize({ width: 390, height: 844 });
      await mobile.screenshot({ path: resolve(output, 'chrome-mobile-emulated.png') });
      const progress = root.locator('input[aria-label="Vị trí phát"]'), before = Number(await progress.inputValue());
      await root.getByRole('button', { name: 'Ẩn Player', exact: true }).click(clickOptions); await chat.fill('Kiểm tra mobile mô phỏng'); await sleep(4000);
      const after = Number(await progress.inputValue()); assert(after > before + 1);
      await mobile.getByRole('button', { name: 'Mở menu', exact: true }).click(clickOptions); await mobile.getByRole('button', { name: 'Player', exact: true }).click(clickOptions);
      assert(await native.evaluate(node => node.isConnected)); await root.getByRole('button', { name: 'Dừng và đóng Player', exact: true }).click(clickOptions);
      assert.equal(await mobile.locator('.yt-player iframe').count(), 0); return { sizes, before, after };
    });
    await mobileContext.close();
  }
  if (!values['background-only']) {
    const direct = await context.newPage();
    await check('direct_youtube_3blue1brown_ad_sample', async () => {
      await direct.goto('https://www.youtube.com/watch?v=aircAruvnKk', { waitUntil: 'domcontentloaded' });
      await sleep(3000);
      const play = direct.getByRole('button', { name: /^(Phát video|Play video|Phát|Play)$/ }).first();
      if (await play.isVisible()) await play.click(clickOptions);
      const observed = await observe(direct, seconds, false);
      assert(observed.samples.some(sample => sample.time > 0 && sample.paused === false), 'Trang YouTube chưa phát video/quảng cáo trong mẫu.');
      return observed;
    });
    await direct.close();
  }
  if (report.checks.some(check => check.passed === false) || report.videos.some(video => video.failure || video.playWaitError
    || (!['dQw4w9WgXcQ', 'JGwWNGJdvx8'].includes(video.id) && !(video.progressSeconds > 1)))) process.exitCode = 1;
} catch (error) { report.fatal = String(error); process.exitCode = 1; }
finally {
  save();
  if (browserProcess) {
    await system.send('Browser.close').catch(() => {}); await browser.close();
    await until(() => browserProcess.exitCode, value => value !== null, 15000).catch(() => {});
    // Chỉ xóa profile do lượt chạy này tạo, đã kiểm tra nằm trong thư mục output tuyệt đối.
    assert(resolve(profile).startsWith(output + sep) && profile !== output);
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 }); }
    catch (error) { report.cleanupError = String(error); save(); process.exitCode = 1; }
  } else await browser.close();
  console.log(JSON.stringify({ browser: values.browser, videos: report.videos.length, fatal: report.fatal ?? null, output }));
}
