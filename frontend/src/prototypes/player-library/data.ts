import type { PlayerTrack } from '../../features/companion/ytplayer/PlayerShell';

export interface DemoTrack extends PlayerTrack { id: string; cover: string; tone: 'rose' | 'teal' | 'sand' | 'ink' }
// Chỉ là catalogue của bản duyệt UI; không phải kết quả lấy từ YouTube.
export const TRACKS: DemoTrack[] = [
  { id: 'tetris', title: 'Tetris', artist: 'Kasane Teto SV', cover: 'TETRIS', tone: 'rose', duration: 143, url: 'https://www.youtube.com/watch?v=Soy4jGPHr3g' },
  { id: 'vampire', title: 'The Vampire', artist: 'DECO*27 · Hatsune Miku', cover: 'VAMPIRE', tone: 'ink', duration: 180, url: 'https://www.youtube.com/watch?v=e1xCOsgWG0M' },
  { id: 'mirai', title: 'Magical Mirai 2023', artist: 'Hatsune Miku', cover: 'MIKU LIVE', tone: 'teal', duration: 3457, url: 'https://www.youtube.com/watch?v=HDz9dSuAI4s' },
  { id: 'neural', title: 'But what is a neural network?', artist: '3Blue1Brown', cover: 'NEURAL', tone: 'sand', duration: 1120, url: 'https://www.youtube.com/watch?v=aircAruvnKk' },
];
export const SEARCH_TRACKS: DemoTrack[] = [
  TRACKS[0],
  { id: 'demo-miku-cover', title: 'Tetris — Miku cover', artist: 'Miku Studio', cover: 'MIKU', tone: 'teal', duration: 145, url: '' },
  { id: 'demo-live', title: 'Tetris — live session', artist: 'Vocaloid Stage', cover: 'LIVE', tone: 'ink', duration: 187, url: '' },
  { id: 'demo-piano', title: 'Tetris — piano arrange', artist: 'Piano Room', cover: 'PIANO', tone: 'sand', duration: 204, url: '' },
  { id: 'demo-instrumental', title: 'Tetris — instrumental', artist: 'Off Vocal', cover: 'OFF VOCAL', tone: 'rose', duration: 143, url: '' },
];
export const DEMO_PLAYLIST = 'https://www.youtube.com/playlist?list=PL_PETO_DEMO_VOCALOID';
