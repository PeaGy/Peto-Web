import { UnauthorizedError } from '../../../shared/api/api';
import type { MediaTrack } from './playerLibraryTypes';

interface VideoInfo { video_id: string; title: string; artist: string }
const root = '/api/companion/player';
async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(root + path, init);
  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === 'string' ? error.detail : 'Chưa tải được thư viện Player. Bạn thử lại nhé.');
  }
  return response.json();
}
export function mediaFromId(videoId: string, title = '', artist = ''): MediaTrack {
  return { videoId, title, artist, url: `https://www.youtube.com/watch?v=${videoId}`, startSeconds: 0, duration: 0 };
}
const tracks = (data: { favorites: VideoInfo[] }) => data.favorites.map(item => mediaFromId(item.video_id, item.title, item.artist));
export const listFavorites = async (signal: AbortSignal) => tracks(await json<{ favorites: VideoInfo[] }>('/favorites', { signal }));
export const saveFavorite = async (videoId: string, save: boolean, signal: AbortSignal) => tracks(await json<{ favorites: VideoInfo[] }>(`/favorites/${encodeURIComponent(videoId)}`, { method: save ? 'POST' : 'DELETE', signal }));
export const getVideoInfo = (videoId: string, signal: AbortSignal) => json<VideoInfo>(`/videos/${encodeURIComponent(videoId)}`, { signal });
