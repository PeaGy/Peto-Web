import { useCallback, useEffect, useRef, useState } from 'react';
import { getPlaylist, searchVideos } from './playerApi';
import type { MediaTrack } from './playerLibraryTypes';

const message = (reason: unknown) => reason instanceof TypeError ? 'Chưa kết nối được YouTube. Bạn thử lại nhé.'
  : reason instanceof Error ? reason.message : 'Chưa tải được danh sách YouTube.';

/** Chỉ gửi khi submit/tải thêm; yêu cầu mới hoặc hủy phiên vô hiệu hóa mọi phản hồi cũ. */
export function usePlayerDiscovery() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MediaTrack[]>([]);
  const [nextPageToken, setNextPageToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [kind, setKind] = useState<'search' | 'playlist' | null>(null);
  const [playlistNote, setPlaylistNote] = useState('');
  const pending = useRef<AbortController | null>(null);
  const queryRef = useRef('');
  const resultsRef = useRef<MediaTrack[]>([]);
  const tokenRef = useRef('');

  const cancel = useCallback(() => { pending.current?.abort(); pending.current = null; setBusy(false); }, []);
  useEffect(() => () => { pending.current?.abort(); pending.current = null; }, []);
  function begin(value: 'search' | 'playlist') {
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller;
    setKind(value); setBusy(true); setError(''); setPlaylistNote(''); return controller;
  }
  async function search(value: string, more = false) {
    if (more && (pending.current || !tokenRef.current || resultsRef.current.length >= 100)) return;
    const token = more ? tokenRef.current : '';
    const controller = begin('search');
    queryRef.current = value; setQuery(value);
    if (!more) { resultsRef.current = []; setResults([]); tokenRef.current = ''; setNextPageToken(''); }
    try {
      const data = await searchVideos(value, token, controller.signal);
      if (controller.signal.aborted) return;
      const merged = more ? [...resultsRef.current, ...data.tracks] : data.tracks;
      const unique = Array.from(new Map(merged.map(track => [track.videoId, track])).values()).slice(0, 100);
      resultsRef.current = unique; setResults(unique);
      tokenRef.current = unique.length < 100 && data.nextPageToken !== token ? data.nextPageToken : '';
      setNextPageToken(tokenRef.current);
    } catch (reason) { if (!controller.signal.aborted) setError(message(reason)); }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }
  async function playlist(id: string, limit: number) {
    const controller = begin('playlist');
    try {
      const data = await getPlaylist(id, limit, controller.signal);
      if (controller.signal.aborted) return null;
      if (!data.tracks.length) { setError('Playlist không có video có thể nhúng.'); return null; }
      return data;
    } catch (reason) { if (!controller.signal.aborted) setError(message(reason)); return null; }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }
  return { query, results, nextPageToken, busy, error, kind, playlistNote, setPlaylistNote, cancel, search, playlist,
    loadMore: () => void search(queryRef.current, true), retry: () => void search(queryRef.current, !!tokenRef.current) };
}
