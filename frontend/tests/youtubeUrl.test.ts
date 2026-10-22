import { expect, it } from 'vitest';
import { parseYouTubeUrl } from '../src/features/companion/ytplayer/youtubeUrl';

const id = 'Soy4jGPHr3g';
it.each([
  `https://www.youtube.com/watch?v=${id}&list=abc&si=track`, `https://youtube.com/watch?v=${id}`,
  `https://m.youtube.com/watch?v=${id}`, `https://music.youtube.com/watch?v=${id}`,
  `https://youtu.be/${id}?si=abc`, `https://www.youtu.be/${id}`, `https://www.youtube.com/shorts/${id}`,
  `https://www.youtube.com/live/${id}`, `https://www.youtube.com/v/${id}`, `https://youtube-nocookie.com/embed/${id}`,
  `https://www.youtube-nocookie.com/embed/${id}/`, ` HTTP://WWW.YOUTUBE.COM/watch?v=${id} `,
])('nhận link YouTube và chỉ giữ mã video: %s', url => {
  expect(parseYouTubeUrl(url)).toEqual({ videoId: id, startSeconds: 0, url: `https://www.youtube.com/watch?v=${id}` });
});
it.each([
  '', id, `youtube.com/watch?v=${id}`, `https://youtube.com.evil.example/watch?v=${id}`,
  `https://notyoutube.com/watch?v=${id}`, `https://youtu.be.evil/${id}`, `https://evil.example/?next=https://youtube.com/watch?v=${id}`,
  `javascript:alert('${id}')`, `ftp://youtu.be/${id}`, `https://youtube.com:444/watch?v=${id}`,
  `https://user:pass@youtube.com/watch?v=${id}`, `https://youtube.com@evil.example/watch?v=${id}`,
  `https://youtu.be/${id}/extra`, `https://youtube.com/embed/${id}/extra`, `https://youtube.com/channel/${id}`,
  'https://youtube.com/playlist?list=abc', 'https://youtube.com/watch?v=short', `https://youtube.com/watch?v=${id}!`,
  `https://youtube.com/watch?v=${id}&v=dQw4w9WgXcQ`, `https://youtube.com/watch?v=${id}\n&bad=true`,
  `https://youtube.com\\@evil.example/watch?v=${id}`, `xem https://youtu.be/${id}`, `https://youtu.be/${id}%20`,
])('từ chối đầu vào sai hoặc hostname giả: %s', url => { expect(parseYouTubeUrl(url)).toBeNull(); });
it.each([['?t=1h2m3s', 3723], ['?t=90', 90], ['?start=25', 25], ['#t=2m', 120], ['?t=-8', 0], ['?t=bad', 0],
  ['?t=99999999999999999999999', 0], ['?start=5&t=12', 5]])('đọc thời điểm bắt đầu %s', (suffix, value) => {
  expect(parseYouTubeUrl(`https://youtu.be/${id}${suffix}`)?.startSeconds).toBe(value);
});
