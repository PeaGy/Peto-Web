// Chỉ báo Tetris ở dòng "Đang làm" (27/11/2026): phỏng theo artifact "Peto – Thinking indicators" của chủ web, thu về
// lưới 6×6, nhiều màu (chủ web chọn từ ba mẫu: một màu, điểm màu, nhiều màu). Mỗi việc Peto đang làm một kiểu chơi.

const N = 6;
export type TetrisMode = 'autoplay' | 'rain' | 'next' | 'stack';
type Mode = TetrisMode;

type Cells = [number, number][];
// 7 khối Tetris: 1 I, 2 O, 3 T, 4 S, 5 Z, 6 J, 7 L.
const SHAPES: Cells[] = [[],
  [[0, 0], [1, 0], [2, 0], [3, 0]], [[0, 0], [1, 0], [0, 1], [1, 1]], [[1, 0], [0, 1], [1, 1], [2, 1]],
  [[1, 0], [2, 0], [0, 1], [1, 1]], [[0, 0], [1, 0], [1, 1], [2, 1]], [[0, 0], [0, 1], [1, 1], [2, 1]], [[2, 0], [0, 1], [1, 1], [2, 1]]];
// Màu Tetris quen thuộc; nền sáng dùng bản đậm hơn cho đủ tương phản trên nền trắng.
const DARK = [[0, 0, 0], [60, 210, 245], [245, 205, 50], [180, 95, 250], [80, 220, 110], [250, 75, 85], [85, 130, 255], [255, 150, 45]];
const LIGHT = [[0, 0, 0], [0, 150, 190], [200, 150, 0], [135, 55, 205], [30, 160, 65], [215, 45, 55], [45, 85, 215], [225, 115, 15]];

const rnd = (n: number) => Math.floor(Math.random() * n);
const at = (x: number, y: number) => y * N + x;

function rotate(cells: Cells, turns: number): Cells {
  let out = cells.map(([x, y]) => [x, y] as [number, number]);
  for (let i = 0; i < turns; i++) out = out.map(([x, y]) => [-y, x]);
  const minX = Math.min(...out.map(p => p[0])), minY = Math.min(...out.map(p => p[1]));
  return out.map(([x, y]) => [x - minX, y - minY]);
}
const width = (cells: Cells) => Math.max(...cells.map(p => p[0])) + 1;
const fits = (board: Uint8Array, cells: Cells, ox: number, oy: number) => cells.every(([x, y]) => {
  const X = x + ox, Y = y + oy;
  return X >= 0 && X < N && Y < N && (Y < 0 || !board[at(X, Y)]);
});
const fullRows = (board: Uint8Array) => [...Array(N).keys()].filter(y => [...Array(N).keys()].every(x => board[at(x, y)]));
function removeRows(board: Uint8Array, rows: number[]) {
  const keep: Uint8Array[] = [];
  for (let y = 0; y < N; y++) if (!rows.includes(y)) keep.push(board.slice(y * N, y * N + N));
  board.fill(0);
  keep.reverse().forEach((row, i) => board.set(row, (N - 1 - i) * N));
}

/** Một khung hình: màu từng ô (0 là trống), ô nào thuộc khối đang chuyển động, ô nào đang chớp (xóa hàng). */
type Frame = { cells: Uint8Array; active: Uint8Array; flash: Float32Array };
type Engine = { update(dt: number): void; render(frame: Frame): void };

function autoplay(): Engine {
  const board = new Uint8Array(N * N);
  let piece: { t: number; c: Cells; x: number; y: number } | null = null, wait = 0, clearing: { rows: number[]; t: number } | null = null, over = 0;
  function score(t: number, cells: Cells, x: number) {
    let y = -4;
    while (fits(board, cells, x, y + 1)) y++;
    if (cells.some(([, cy]) => cy + y < 0)) return null;
    const next = board.slice();
    cells.forEach(([cx, cy]) => { next[at(cx + x, cy + y)] = t; });
    let height = 0, holes = 0, bump = 0, prev = -1;
    for (let X = 0; X < N; X++) {
      let h = 0, seen = false;
      for (let Y = 0; Y < N; Y++) {
        if (next[at(X, Y)]) { if (!seen) h = N - Y; seen = true; } else if (seen) holes++;
      }
      height += h; if (prev >= 0) bump += Math.abs(h - prev); prev = h;
    }
    return fullRows(next).length * 3.4 - height * 0.5 - holes * 3.6 - bump * 0.2;
  }
  function spawn() {
    const t = 1 + rnd(7);
    let best: { s: number; c: Cells; x: number } | null = null;
    for (let r = 0; r < 4; r++) {
      const c = rotate(SHAPES[t], r);
      for (let x = 0; x <= N - width(c); x++) {
        const s = score(t, c, x);
        if (s !== null && (!best || s > best.s)) best = { s, c, x };
      }
    }
    if (!best) { over = 0.6; piece = null; return; }
    piece = { t, c: best.c, x: best.x, y: -Math.max(...best.c.map(p => p[1])) - 1 };
  }
  return {
    update(dt) {
      if (over > 0) { over -= dt; if (over <= 0) { board.fill(0); spawn(); } return; }
      if (clearing) { clearing.t -= dt; if (clearing.t <= 0) { removeRows(board, clearing.rows); clearing = null; spawn(); } return; }
      if (!piece) { spawn(); return; }
      wait += dt; if (wait < 0.11) return; wait = 0;
      if (fits(board, piece.c, piece.x, piece.y + 1)) { piece.y++; return; }
      const landed = piece;
      landed.c.forEach(([x, y]) => { if (y + landed.y >= 0) board[at(x + landed.x, y + landed.y)] = landed.t; });
      piece = null;
      const rows = fullRows(board);
      if (rows.length) clearing = { rows, t: 0.36 }; else spawn();
    },
    render({ cells, active, flash }) {
      cells.set(board);
      const live = piece;
      if (live) live.c.forEach(([x, y]) => {
        if (y + live.y >= 0) { cells[at(x + live.x, y + live.y)] = live.t; active[at(x + live.x, y + live.y)] = 1; }
      });
      if (clearing) {
        const on = Math.sin(clearing.t * 28) > 0;
        clearing.rows.forEach(y => { for (let x = 0; x < N; x++) flash[at(x, y)] = on ? 1 : 0.35; });
      }
      if (over > 0) flash.fill(0.4);
    },
  };
}

function rain(): Engine {
  let drops: { t: number; c: Cells; x: number; y: number; v: number }[] = [], wait = 0.3;
  return {
    update(dt) {
      wait += dt;
      if (wait > 0.42) {
        wait = 0;
        const t = 1 + rnd(7), c = rotate(SHAPES[t], rnd(4));
        drops.push({ t, c, x: rnd(N - width(c) + 1), y: -4, v: 5 + Math.random() * 3 });
      }
      drops.forEach(drop => { drop.y += drop.v * dt; });
      drops = drops.filter(drop => drop.y < N + 1);
    },
    render({ cells, active }) {
      // Khối nào cũng đang rơi nên đều là "khối đang chuyển động".
      drops.forEach(drop => drop.c.forEach(([x, y]) => {
        const Y = Math.floor(drop.y) + y;
        if (Y < 0 || Y >= N) return;
        cells[at(x + drop.x, Y)] = drop.t;
        active[at(x + drop.x, Y)] = 1;
      }));
    },
  };
}

function next(): Engine {
  let queue: { t: number; c: Cells; x: number; y: number }[] = [], wait = 0;
  const push = (y: number) => {
    const t = 1 + rnd(7), c = rotate(SHAPES[t], t === 1 ? 0 : rnd(4));
    queue.push({ t, c, x: Math.floor((N - width(c)) / 2), y });
  };
  for (let y = 1; y < N + 6; y += 4) push(y);
  return {
    update(dt) {
      wait += dt; if (wait < 0.14) return; wait = 0;
      queue.forEach(piece => { piece.y--; });
      queue = queue.filter(piece => piece.y > -3);
      while (queue[queue.length - 1].y < N + 2) push(queue[queue.length - 1].y + 4);
    },
    render({ cells, active }) {
      // Khối đang đi lên ở giữa lưới là khối "đang đọc".
      const reading = queue.find(piece => piece.y >= 1);
      queue.forEach(piece => piece.c.forEach(([x, y]) => {
        const Y = piece.y + y;
        if (Y < 0 || Y >= N) return;
        cells[at(x + piece.x, Y)] = piece.t;
        if (piece === reading) active[at(x + piece.x, Y)] = 1;
      }));
    },
  };
}

function stack(): Engine {
  const board = new Uint8Array(N * N), group = new Uint8Array(N * N);
  let count = 0, wait = 0, type = 1, clearing = 0;
  const cellAt = (k: number): [number, number] => {
    const y = N - 1 - Math.floor(k / N), r = k % N;
    return [y % 2 ? r : N - 1 - r, y];
  };
  return {
    update(dt) {
      if (clearing > 0) { clearing -= dt; if (clearing <= 0) { board.fill(0); group.fill(0); count = 0; } return; }
      wait += dt; if (wait < 0.07) return; wait = 0;
      if (count % 4 === 0) { type = 1 + rnd(7); group.fill(0); }
      const [x, y] = cellAt(count++);
      board[at(x, y)] = type; group[at(x, y)] = 1;
      if (count === N * 4) clearing = 0.42;
    },
    render({ cells, active, flash }) {
      cells.set(board);
      if (clearing > 0) {
        const on = Math.sin(clearing * 30) > 0;
        for (let y = N - 4; y < N; y++) for (let x = 0; x < N; x++) flash[at(x, y)] = on ? 1 : 0.3;
      } else active.set(group);
    },
  };
}

const ENGINES: Record<Mode, () => Engine> = { autoplay, rain, next, stack };

/** Màu chữ của giao diện (ô trống) và giao diện đang sáng hay tối. */
function tokens() {
  return {
    text: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#ececec',
    light: document.documentElement.dataset.theme === 'light',
  };
}

/**
 * Vẽ ô Tetris lên canvas vuông `size` px. `still` (giảm chuyển động) vẽ một khối T đứng yên trên một hàng gạch, không
 * chạy vòng lặp. Trả hàm dừng.
 */
export function mountTetris(canvas: HTMLCanvasElement, mode: Mode, size: number, still: boolean) {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.height = Math.round(size * dpr);
  const context = canvas.getContext('2d');
  if (!context) return () => {};
  const ctx = context;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const engine = ENGINES[mode]();
  const frame: Frame = { cells: new Uint8Array(N * N), active: new Uint8Array(N * N), flash: new Float32Array(N * N) };
  const cell = size / N, gap = Math.max(0.6, cell * 0.16), side = cell - gap, radius = Math.min(1.2, side * 0.25);

  function draw() {
    const theme = tokens(), colors = theme.light ? LIGHT : DARK;
    ctx.clearRect(0, 0, size, size);
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const k = at(x, y), X = x * cell + gap / 2, Y = y * cell + gap / 2;
      const type = frame.cells[k], flash = frame.flash[k];
      if (!type) {
        // Ô trống: một ô vuông rất mờ để thấy khung lưới.
        ctx.fillStyle = theme.text; ctx.globalAlpha = theme.light ? 0.06 : 0.055;
      } else if (flash > 0) {
        // Xóa hàng: chớp cầu vồng.
        const [r, g, b] = colors[1 + ((x + y + Math.floor(performance.now() / 70)) % 7)];
        ctx.fillStyle = `rgb(${r},${g},${b})`; ctx.globalAlpha = 0.45 + flash * 0.55;
      } else {
        // Khối đang chuyển động đậm hơn khối đã nằm yên một chút.
        const [r, g, b] = colors[type];
        ctx.fillStyle = `rgb(${r},${g},${b})`; ctx.globalAlpha = frame.active[k] ? 1 : 0.85;
      }
      ctx.beginPath(); ctx.roundRect(X, Y, side, side, radius); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  if (still) {
    rotate(SHAPES[3], 0).forEach(([x, y]) => { frame.cells[at(x + 1, y + 2)] = 3; frame.active[at(x + 1, y + 2)] = 1; });
    for (let x = 0; x < N; x++) if (x !== 2) frame.cells[at(x, N - 1)] = 2 + (x % 5);
    draw();
    const watch = new MutationObserver(draw);
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => watch.disconnect();
  }
  let last: number | null = null, handle = 0;
  const loop = (ms: number) => {
    const t = ms / 1000;
    const dt = last === null ? 0 : Math.min(0.1, t - last);
    last = t;
    engine.update(dt);
    frame.cells.fill(0); frame.active.fill(0); frame.flash.fill(0);
    engine.render(frame);
    draw();
    handle = requestAnimationFrame(loop);
  };
  handle = requestAnimationFrame(loop);
  return () => cancelAnimationFrame(handle);
}