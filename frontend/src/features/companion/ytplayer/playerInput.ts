import { parseYouTubePlaylistUrl, parseYouTubeUrl, type YouTubeSource } from './youtubeUrl';

export type PlayerInput = { kind: 'video'; source: YouTubeSource } | { kind: 'playlist'; id: string }
  | { kind: 'search'; query: string } | { kind: 'error'; message: string };

export function parsePlayerInput(input: string): PlayerInput {
  const value = input.trim();
  if (!value) return { kind: 'error', message: 'Nhập link hoặc tên video.' };
  const source = parseYouTubeUrl(value);
  // Link video có list vẫn mở riêng video; menu cung cấp thao tác nhập playlist rõ ràng.
  if (source) return { kind: 'video', source };
  const id = parseYouTubePlaylistUrl(value);
  if (id) return { kind: 'playlist', id };
  if (/^[a-z][a-z\d+.-]*:|^(?:\/\/|www\.|(?:m\.|music\.)?youtube\.com\b|youtu\.be\b)/i.test(value)
    || /[\u0000-\u001f\u007f\\]/.test(value)) return { kind: 'error', message: 'Link YouTube chưa hợp lệ. Hãy kiểm tra lại đường dẫn.' };
  if (value.length > 200) return { kind: 'error', message: 'Tên tìm kiếm tối đa 200 ký tự.' };
  return { kind: 'search', query: value.replace(/\s+/g, ' ') };
}
