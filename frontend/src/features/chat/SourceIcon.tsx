import { useState } from 'react';
import { GitHubIcon } from '../../shared/ui/GitHubIcon';
import { YouTubeIcon } from '../../shared/ui/YouTubeIcon';
import { safeSourceUrl } from './sourceData';

export function GlobeIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z" stroke="currentColor" strokeWidth="1.6" /></svg>;
}

export function sourceHost(url: string) { return new URL(url).hostname.replace(/^www\./, ''); }

export function faviconUrl(url: string): string | undefined {
  if (!safeSourceUrl(url)) return;
  const host = sourceHost(url);
  // Icons receive only the public hostname; chat URLs, query strings and referrers stay private.
  if (!/^[a-z0-9.-]+\.[a-z]{2,63}$/i.test(host) || /\.(?:local|localhost|internal|lan|test|invalid)$/i.test(host)) return;
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`;
}

export function SourceIcon({ url }: { url: string }) {
  const host = sourceHost(url);
  const belongsTo = (domain: string) => host === domain || host.endsWith(`.${domain}`);
  const [failedHost, setFailedHost] = useState<string | null>(null);
  if (belongsTo('youtube.com') || belongsTo('youtu.be') || belongsTo('youtube-nocookie.com')) return <YouTubeIcon />;
  if (belongsTo('github.com')) return <GitHubIcon />;
  const src = faviconUrl(url);
  return src && failedHost !== host
    ? <img src={src} alt="" width="16" height="16" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailedHost(host)} />
    : <GlobeIcon />;
}
