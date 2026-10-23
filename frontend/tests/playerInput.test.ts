import { expect, it } from 'vitest';
import { parsePlayerInput } from '../src/features/companion/ytplayer/playerInput';
import { parseYouTubePlaylistUrl } from '../src/features/companion/ytplayer/youtubeUrl';

const list = 'PLabcdefghijk12345';
it.each(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'])('accepts shared playlist links on %s', host => {
  expect(parsePlayerInput(`https://${host}/playlist?list=${list}&si=share`)).toEqual({ kind: 'playlist', id: list });
});
it('keeps a video-with-playlist link as a video, with a separate playlist option', () => {
  const url = `https://youtu.be/Soy4jGPHr3g?list=${list}&t=12`;
  expect(parsePlayerInput(url).kind).toBe('video');
  expect(parseYouTubePlaylistUrl(url)).toBe(list);
});
it.each([`https://youtube.com.evil/playlist?list=${list}`, `https://user@youtube.com/playlist?list=${list}`,
  `https://youtube.com:444/playlist?list=${list}`, `https://youtube.com/playlist?list=${list}&list=${list}`,
  'https://youtube.com/playlist?list=WL', 'https://youtube.com/playlist?list=LL', 'javascript:alert(1)',
  `https://youtube.com/channel/test?list=${list}`, `https://youtube.com\\@evil/playlist?list=${list}`, 'www.youtube.com/playlist?list=abc'])('rejects malformed or fake URLs rather than searching them: %s', input => {
  expect(parsePlayerInput(input).kind).toBe('error');
  expect(parseYouTubePlaylistUrl(input)).toBeNull();
});
it.each(['Tetris', 'DECO*27   Vampire', '三原色 YOASOBI', 'AC/DC Thunderstruck', '🎵 Kasane Teto'])('searches by name: %s', query => {
  expect(parsePlayerInput(query)).toEqual({ kind: 'search', query: query.replace(/\s+/g, ' ') });
});
it('bounds query size and rejects control characters', () => {
  expect(parsePlayerInput('x'.repeat(201)).kind).toBe('error');
  expect(parsePlayerInput('Tetris\u0000')).toMatchObject({ kind: 'error' });
  expect(parsePlayerInput('   ').kind).toBe('error');
});
