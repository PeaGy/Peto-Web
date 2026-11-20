// @vitest-environment node
/**
 * Thang cỡ chữ (G4.3). Khung app (thanh bên, chat, ô nhắn, Cài đặt, dự án, kết nối, sơ đồ, khung tài liệu, phần dùng
 * chung) chỉ dùng cỡ có trong bảng ở DESIGN.md §3; nút và ô nhập không được rơi về chữ mặc định 13,33 px của trình
 * duyệt. Companion, Peto Media Player, Docs, Admin và Imagine có hệ thiết kế riêng nên không nằm trong phạm vi này.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src');
const SCALE = new Set([11, 12, 12.5, 13, 13.5, 14, 14.5, 15, 16, 19, 20, 22, 26, 28, 30, 34]);
const SHELL = ['app', 'shared', 'features/chat', 'features/settings', 'features/projects', 'features/connectors',
  'features/diagrams', 'features/documents/documentPanel.css'];
// Chữ là một phần của hình, không phải chữ để đọc (DESIGN.md §3, "Off the scale on purpose").
const GRAPHIC = new Set(['.file-ext', '.avatar.big', '.history-dialog-head button']);

function cssFiles(path: string): string[] {
  if (statSync(path).isFile()) return path.endsWith('.css') ? [path] : [];
  return readdirSync(path).flatMap((name) => cssFiles(join(path, name)));
}

function offScale(file: string): string[] {
  const css = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  const found: string[] = [];
  for (const rule of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = rule[1].trim().replace(/\s+/g, ' ');
    for (const size of rule[2].matchAll(/font-size:\s*([\d.]+)px/g)) {
      if (!SCALE.has(Number(size[1])) && !GRAPHIC.has(selector)) {
        found.push(`${relative(SRC, file)}: ${selector} ${size[1]}px`);
      }
    }
  }
  return found;
}

it('khung app chỉ dùng cỡ chữ trong thang của DESIGN.md', () => {
  const files = SHELL.flatMap((part) => cssFiles(join(SRC, part)));
  expect(files.length).toBeGreaterThan(20);
  expect(files.flatMap(offScale)).toEqual([]);
});

it('nút và ô nhập kế thừa phông và cỡ chữ thay vì Arial 13,33 px mặc định', () => {
  const base = readFileSync(join(SRC, 'shared', 'styles', 'base.css'), 'utf8');
  expect(base).toMatch(/:where\(button, input, select, textarea\) \{ font-family: inherit; font-size: inherit; \}/);
});
