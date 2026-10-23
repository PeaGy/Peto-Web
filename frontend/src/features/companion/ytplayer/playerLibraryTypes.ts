import type { DragEvent, RefObject } from 'react';

export interface MediaTrack {
  videoId: string;
  title: string;
  artist: string;
  url: string;
  startSeconds: number;
  duration: number;
}
export interface QueueEntry { key: string; track: MediaTrack }
export type RepeatMode = 'off' | 'all' | 'one';
export type LibraryPanelKind = 'queue' | 'favorites' | 'search';
export const trackTitle = (track: MediaTrack) => track.title || 'Video YouTube';
export interface PlayerLibrary {
  track: MediaTrack | null;
  queue: QueueEntry[];
  favorites: MediaTrack[];
  favorite: boolean;
  repeat: RepeatMode;
  shuffle: boolean;
  panel: LibraryPanelKind | null;
  newItems: boolean;
  announcement: string;
  sourceRequest: number;
  queueButton: RefObject<HTMLButtonElement | null>;
  loadingFavorites: boolean;
  favoritesBusy: boolean;
  error: string;
  discovery: {
    query: string; results: MediaTrack[]; nextPageToken: string; busy: boolean; error: string;
    kind: 'search' | 'playlist' | null; playlistNote: string; loadMore: () => void; retry: () => void;
  };
  openInput: (value: string) => string | undefined;
  importPlaylist: (value: string) => string | undefined;
  cancelDiscovery: () => void;
  select: (track: MediaTrack) => void;
  next: () => void;
  append: (tracks: MediaTrack[]) => void;
  appendLink: (value: string) => string | undefined;
  toggleFavorite: (track?: MediaTrack) => void;
  openPanel: (panel: LibraryPanelKind) => void;
  closePanel: () => void;
  toggleQueue: () => void;
  toggleShuffle: () => void;
  cycleRepeat: () => void;
  move: (key: string, offset: number) => void;
  drop: (event: DragEvent, key: string) => void;
  remove: (key: string) => void;
  playEntry: (entry: QueueEntry) => void;
  requestSource: () => void;
  reloadFavorites: () => void;
}
