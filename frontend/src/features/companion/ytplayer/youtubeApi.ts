export interface YouTubePlayer {
  cueVideoById(source: { videoId: string; startSeconds: number }): void;
  loadVideoById(source: { videoId: string; startSeconds: number }): void;
  getVideoUrl?(): string;
  playVideo(): void;
  pauseVideo(): void;
  stopVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  setVolume(volume: number): void;
  getVolume(): number;
  mute(): void;
  unMute(): void;
  isMuted(): boolean;
  getCurrentTime(): number;
  getDuration(): number;
  getIframe(): HTMLIFrameElement;
  destroy(): void;
}
export interface YouTubeEvent { target: YouTubePlayer; data: number }
export interface YouTubeOptions {
  videoId: string;
  width: string;
  height: string;
  playerVars: Record<string, string | number>;
  events: {
    onReady: (event: Pick<YouTubeEvent, 'target'>) => void;
    onStateChange: (event: YouTubeEvent) => void;
    onError: (event: YouTubeEvent) => void;
    onAutoplayBlocked: () => void;
  };
}
export interface YouTubeApi { Player: new (element: HTMLElement, options: YouTubeOptions) => YouTubePlayer }
declare global {
  interface Window { YT?: YouTubeApi; onYouTubeIframeAPIReady?: () => void }
}

const SCRIPT_ID = 'peto-youtube-iframe-api';
let pending: Promise<YouTubeApi> | null = null;

/** Dùng chung một lượt nạp, giữ callback có trước và cho thử lại khi tải thất bại. */
export function loadYouTubeApi(): Promise<YouTubeApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (pending) return pending;
  const promise = new Promise<YouTubeApi>((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    const script = existing ?? document.createElement('script');
    let settled = false;
    const cleanup = () => {
      window.clearTimeout(timer);
      script.removeEventListener('error', failed);
      script.removeEventListener('load', loaded);
      if (window.onYouTubeIframeAPIReady === ready) window.onYouTubeIframeAPIReady = previous;
    };
    const finish = () => {
      if (settled || !window.YT?.Player) return;
      settled = true;
      cleanup();
      resolve(window.YT);
    };
    const failed = () => {
      if (settled) return;
      settled = true;
      cleanup();
      if (!existing) script.remove();
      reject(new Error('Không tải được YouTube. Kiểm tra kết nối rồi thử lại.'));
    };
    const ready = () => { try { previous?.(); } finally { finish(); } };
    const loaded = () => finish();
    const timer = window.setTimeout(failed, 15000);
    window.onYouTubeIframeAPIReady = ready;
    script.addEventListener('error', failed);
    script.addEventListener('load', loaded);
    if (!existing) {
      script.id = SCRIPT_ID;
      script.src = 'https://www.youtube.com/iframe_api';
      script.async = true;
      script.referrerPolicy = 'strict-origin-when-cross-origin';
      document.head.append(script);
    }
  });
  pending = promise;
  void promise.catch(() => { if (pending === promise) pending = null; });
  return promise;
}
