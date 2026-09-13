import { describe, expect, it } from 'vitest';
import { speakableText, speechChunks } from '../src/localSpeech';

describe('chữ để giọng nói đọc', () => {
  it('bỏ khối code, link và ký hiệu markdown, mỗi dòng thành một câu', () => {
    const text = speakableText([
      '## Quick plan',
      'Read **the docs** at [this page](https://example.com/docs) first',
      '```python',
      'print("không đọc")',
      '```',
      '- Use `git status`',
      '| Name | Age |',
      '|---|---|',
      '| Peto | 1 |',
    ].join('\n'));
    expect(text).toBe('Quick plan. Read the docs at this page first. Use git status. Name, Age. Peto, 1.');
  });

  it('gộp câu ngắn thành mẩu vừa, không cắt số thập phân và không làm mất chữ', () => {
    const input = ('Version 3.5 is out. ' + 'This sentence adds a little more length to the reply. '.repeat(12)).trim();
    const chunks = speechChunks(input);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks[0].startsWith('Version 3.5 is out. This sentence')).toBe(true);
    expect(chunks.every((chunk) => chunk.length <= 220)).toBe(true);
    expect(chunks.join(' ')).toBe(input);
  });

  it('chia câu dài quá giới hạn ở khoảng trắng', () => {
    const long = Array.from({ length: 80 }, (_, index) => `word${index}`).join(' ');
    const chunks = speechChunks(long);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every((chunk) => chunk.length <= 220)).toBe(true);
    expect(chunks.join(' ')).toBe(long);
  });
});
