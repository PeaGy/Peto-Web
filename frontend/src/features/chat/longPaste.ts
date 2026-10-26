/** Grok's observed default paste boundary; file bytes still use Peto's existing attachment limits. */
export const LONG_PASTE_CHARS = 50_000;
const pasted = new WeakSet<File>();

export function pastedTextFile(text: string, usedNames: string[]): File {
  const names = new Set(usedNames);
  let name = 'pasted-text.txt', index = 2;
  while (names.has(name)) name = `pasted-text-${index++}.txt`;
  const file = new File([text], name, { type: 'text/plain' });
  pasted.add(file);
  return file;
}

export function isPastedTextFile(file: File) { return pasted.has(file); }

export function pasteAtSelection(text: string, incoming: string, start: number, end: number) {
  const from = Math.max(0, Math.min(text.length, start));
  const to = Math.max(from, Math.min(text.length, end));
  return { remaining: text.slice(0, from) + text.slice(to),
    restored: text.slice(0, from) + incoming + text.slice(to), caret: from + incoming.length };
}
