import { useEffect, useMemo, useState } from 'react';
import { GitHubIcon } from '../../shared/ui/GitHubIcon';
import { YouTubeIcon } from '../../shared/ui/YouTubeIcon';
import { describeLink, type LinkDescription, type LinkKind } from './draftLinks';
import { GlobeIcon } from './WebSources';

// Tiêu đề video lấy qua địa chỉ oEmbed sẵn có của Player (máy chủ chỉ gọi YouTube với mã video đã kiểm tra, có nhớ
// tạm). Mỗi mã chỉ hỏi một lần trong phiên; lỗi thì bỏ khỏi bộ nhớ để lần sau thử lại, thẻ vẫn hiện nhãn chung.
const titles = new Map<string, Promise<string>>();

function youtubeTitle(videoId: string): Promise<string> {
  let pending = titles.get(videoId);
  if (!pending) {
    pending = fetch(`/api/companion/player/videos/${encodeURIComponent(videoId)}`)
      .then(response => response.ok ? response.json() : null)
      .then((data: { title?: unknown } | null) => typeof data?.title === 'string' ? data.title.trim() : '')
      .catch(() => '')
      .then(title => { if (!title) titles.delete(videoId); return title; });
    titles.set(videoId, pending);
  }
  return pending;
}

export function useLinkDescription(url: string): LinkDescription {
  const base = useMemo(() => describeLink(url), [url]);
  const [title, setTitle] = useState<{ id: string; text: string } | null>(null);
  useEffect(() => {
    if (!base.videoId) return;
    let live = true;
    const id = base.videoId;
    void youtubeTitle(id).then(text => { if (live && text) setTitle({ id, text }); });
    return () => { live = false; };
  }, [base.videoId]);
  return title && title.id === base.videoId ? { ...base, label: title.text } : base;
}

function LinkIcon({ kind }: { kind: LinkKind }) {
  if (kind === 'youtube') return <YouTubeIcon size={16} />;
  if (kind === 'github') return <GitHubIcon size={16} />;
  return <GlobeIcon />;
}

/** Thẻ link phía trên ô nhắn, cạnh tệp đính kèm. */
export function ComposerLinkChip({ url, onRemove }: { url: string; onRemove: () => void }) {
  const link = useLinkDescription(url);
  return (
    <li className={`attach-chip link-chip ${link.kind}`} data-tip={url}>
      <span className="link-chip-icon"><LinkIcon kind={link.kind} /></span>
      <span>
        <strong>{link.label}</strong>
        <em>{link.detail}</em>
      </span>
      <button type="button" className="chip-remove" aria-label={`Gỡ link ${link.label}`} onClick={onRemove}>×</button>
    </li>
  );
}

/** Link trơn trong tin đã gửi hiện thành nhãn ngắn có biểu tượng; bấm vẫn mở đúng địa chỉ gốc. */
export function MessageLink({ href }: { href: string }) {
  const link = useLinkDescription(href);
  return (
    <a className={`message-link ${link.kind}`} href={href} target="_blank" rel="noopener noreferrer" title={href}>
      <LinkIcon kind={link.kind} /><span>{link.label}</span>
    </a>
  );
}
