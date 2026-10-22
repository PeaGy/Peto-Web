export interface YouTubeSource { videoId: string; startSeconds: number; url: string }

// Cùng danh sách hostname và dạng đường dẫn với backend/shared/youtube.py.
const HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
  'youtu.be', 'www.youtu.be', 'youtube-nocookie.com', 'www.youtube-nocookie.com']);
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

function seconds(value: string | null): number {
  if (!value) return 0;
  if (/^\d+$/.test(value)) return Number.isSafeInteger(Number(value)) ? Number(value) : 0;
  const parts = /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/.exec(value);
  const result = parts ? Number(parts[1] || 0) * 3600 + Number(parts[2] || 0) * 60 + Number(parts[3] || 0) : 0;
  return Number.isSafeInteger(result) ? result : 0;
}

/** Chỉ nhận một URL; không dùng URL nhập vào làm địa chỉ iframe hoặc yêu cầu mạng. */
export function parseYouTubeUrl(input: string): YouTubeSource | null {
  const value = input.trim();
  if (!value || value.length > 4096 || /[\s\u0000-\u001f\u007f\\]/.test(value)) return null;
  let url: URL;
  try { url = new URL(value); } catch { return null; }
  if (!['https:', 'http:'].includes(url.protocol) || !HOSTS.has(url.hostname.toLowerCase()) || url.username || url.password || url.port) return null;
  const path = url.pathname.replace(/\/$/, '').split('/').slice(1);
  let videoId = '';
  if (url.hostname === 'youtu.be' || url.hostname === 'www.youtu.be') {
    if (path.length === 1) videoId = path[0];
  } else if (path.length === 1 && path[0] === 'watch' && url.searchParams.getAll('v').length === 1) {
    videoId = url.searchParams.get('v') || '';
  } else if (path.length === 2 && ['shorts', 'live', 'embed', 'v'].includes(path[0])) videoId = path[1];
  if (!VIDEO_ID.test(videoId)) return null;
  const fragment = new URLSearchParams(url.hash.slice(1));
  const startSeconds = seconds(url.searchParams.get('start') ?? url.searchParams.get('t') ?? fragment.get('t'));
  return { videoId, startSeconds, url: `https://www.youtube.com/watch?v=${videoId}${startSeconds ? `&t=${startSeconds}s` : ''}` };
}
