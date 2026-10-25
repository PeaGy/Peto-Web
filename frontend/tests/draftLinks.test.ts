import { describe, expect, it } from 'vitest';
import { describeLink, joinDraft, LINK_MARK, messageText, pastedLink, splitDraft } from '../src/features/chat/draftLinks';

const SONG = 'https://www.youtube.com/watch?v=sqK-jh4TDXo&list=RDsqK-jh4TDXo&start_radio=1';

describe('link trong bản nháp', () => {
  it('cất link sau dấu riêng, chữ gõ không mang được dấu đó vào', () => {
    const draft = joinDraft('Phân tích giúp tôi bài hát', [SONG]);
    expect(draft).toBe(`Phân tích giúp tôi bài hát${LINK_MARK}${SONG}`);
    expect(splitDraft(draft)).toEqual({ text: 'Phân tích giúp tôi bài hát', links: [SONG] });
    expect(splitDraft(joinDraft(`a${LINK_MARK}b`, []))).toEqual({ text: 'ab', links: [] });
    expect(joinDraft('chỉ chữ', [])).toBe('chỉ chữ');
  });

  it('tin gửi đi giữ link đầy đủ, mỗi link một dòng sau phần chữ', () => {
    expect(messageText(joinDraft('  Phân tích giúp tôi  ', [SONG, 'https://github.com/PeaGy/Peto-Web'])))
      .toBe(`Phân tích giúp tôi\n${SONG}\nhttps://github.com/PeaGy/Peto-Web`);
    expect(messageText(joinDraft('   ', [SONG]))).toBe(SONG);
    expect(messageText('  chỉ chữ  ')).toBe('chỉ chữ');
  });

  it('chỉ nhận đúng một link http(s) khi dán', () => {
    expect(pastedLink(`  ${SONG}\n`)).toBe(SONG);
    expect(pastedLink('xem https://github.com/PeaGy/Peto-Web')).toBeNull();
    expect(pastedLink('ftp://example.com/file')).toBeNull();
    expect(pastedLink('javascript:alert(1)')).toBeNull();
    expect(pastedLink('https://user:pass@example.com')).toBeNull();
    expect(pastedLink('không phải link')).toBeNull();
  });

  it('đặt nhãn ngắn theo hostname thật', () => {
    expect(describeLink(SONG)).toMatchObject({ kind: 'youtube', videoId: 'sqK-jh4TDXo', label: 'Video YouTube' });
    expect(describeLink('https://youtu.be/sqK-jh4TDXo')).toMatchObject({ kind: 'youtube', videoId: 'sqK-jh4TDXo' });
    expect(describeLink('https://github.com/PeaGy/Peto-Web')).toMatchObject({ kind: 'github', label: 'PeaGy/Peto-Web' });
    expect(describeLink('https://github.com/PeaGy/Peto-Web/pull/12')).toMatchObject({ label: 'PeaGy/Peto-Web#12', detail: 'Pull request' });
    expect(describeLink('https://github.com/PeaGy/Peto-Web/blob/main/backend/main.py').label).toBe('PeaGy/Peto-Web · main.py');
    expect(describeLink('https://www.docs.python.org/3/library/asyncio.html'))
      .toMatchObject({ kind: 'web', label: 'docs.python.org › asyncio.html' });
    // Tên miền giả có chữ github/youtube không được nhận là dịch vụ đó.
    expect(describeLink('https://github.com.evil.example/PeaGy/Peto-Web').kind).toBe('web');
    expect(describeLink('https://evil.example/youtube.com/watch?v=sqK-jh4TDXo').kind).toBe('web');
  });
});
