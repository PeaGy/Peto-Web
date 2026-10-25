import { parseYouTubeUrl } from '../companion/ytplayer/youtubeUrl';

/**
 * Link dán vào ô nhắn hiện thành thẻ phía trên chữ, như Claude hiện "PeaGy/Peto-Web" thay cho cả đường dẫn
 * (chủ web chọn ngày 25/10/2026). Thẻ không làm đổi nội dung gửi đi: tin vẫn mang link đầy đủ.
 *
 * Link được cất ngay trong chuỗi nháp, sau một ký tự vùng riêng (LINK_MARK) mà bàn phím không gõ ra được. Nhờ vậy
 * kho nháp, sessionStorage, F5 và lúc máy chủ xác nhận tin vẫn chạy như cũ, không cần thêm trường mới.
 */
export const LINK_MARK = '';
export const MAX_DRAFT_LINKS = 8;
const MAX_URL = 2048;

export type DraftParts = { text: string; links: string[] };
export type LinkKind = 'youtube' | 'github' | 'web';
export type LinkDescription = { kind: LinkKind; label: string; detail: string; videoId?: string };

export function splitDraft(draft: string): DraftParts {
  const [text, ...links] = draft.split(LINK_MARK);
  return { text, links: links.filter(Boolean) };
}

export function joinDraft(text: string, links: string[]): string {
  const clean = text.split(LINK_MARK).join('');
  return links.length ? [clean, ...links].join(LINK_MARK) : clean;
}

/** Chữ gửi cho Peto: phần đã gõ rồi đến các link, mỗi link một dòng, nên model và bong bóng chat thấy link thật. */
export function messageText(draft: string): string {
  const { text, links } = splitDraft(draft);
  const typed = text.trim();
  if (!links.length) return typed;
  return typed ? `${typed}\n${links.join('\n')}` : links.join('\n');
}

/** Dán đúng một link http(s), không kèm chữ khác, thì trả về link đó; còn lại để ô nhắn dán chữ như thường. */
export function pastedLink(pasted: string): string | null {
  const value = pasted.trim();
  if (!value || value.length > MAX_URL || /\s/.test(value)) return null;
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
    return value;
  } catch {
    return null;
  }
}

function belongsTo(host: string, domain: string) {
  return host === domain || host.endsWith(`.${domain}`);
}

/** Nhãn ngắn của một link. Chỉ dựa vào hostname thật, không dựa vào chữ trong đường dẫn hay tên miền giả. */
export function describeLink(raw: string): LinkDescription {
  let url: URL;
  try { url = new URL(raw); } catch { return { kind: 'web', label: raw, detail: '' }; }
  const host = url.hostname.toLowerCase().replace(/^www\./, '');
  const youtube = parseYouTubeUrl(raw);
  if (youtube) return { kind: 'youtube', label: 'Video YouTube', detail: 'YouTube', videoId: youtube.videoId };
  if (belongsTo(host, 'youtube.com') || belongsTo(host, 'youtu.be')) return { kind: 'youtube', label: 'YouTube', detail: host };
  const path = url.pathname.split('/').filter(Boolean).map(part => { try { return decodeURIComponent(part); } catch { return part; } });
  if (host === 'github.com' && path.length) {
    const [owner, repo, section, number, ...rest] = path;
    if (!repo) return { kind: 'github', label: owner, detail: 'GitHub' };
    const name = `${owner}/${repo.replace(/\.git$/, '')}`;
    if ((section === 'issues' || section === 'pull') && /^\d+$/.test(number ?? ''))
      return { kind: 'github', label: `${name}#${number}`, detail: section === 'pull' ? 'Pull request' : 'Issue' };
    if ((section === 'blob' || section === 'tree') && rest.length)
      return { kind: 'github', label: `${name} · ${rest[rest.length - 1]}`, detail: 'GitHub' };
    return { kind: 'github', label: name, detail: 'GitHub' };
  }
  const tail = path.length ? ` › ${path[path.length - 1]}` : '';
  return { kind: 'web', label: host + tail, detail: host };
}
