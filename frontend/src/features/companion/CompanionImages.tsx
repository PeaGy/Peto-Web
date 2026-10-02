import type { ChatAttachment } from '../../shared/api/api';
import type { DraftFile } from '../chat/files';

export function CompanionImageIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.7" />
    <circle cx="9" cy="8" r="2" stroke="currentColor" strokeWidth="1.7" />
    <path d="m4 18 5-5 3 3 4-6 5 8" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
  </svg>;
}

/** Ảnh xem trước nằm ngay trong ô nhắn; trên điện thoại giữ kích thước nhỏ để nhường chỗ cho nhân vật. */
export function CompanionImageDrafts({ images, onRemove }: { images: DraftFile[]; onRemove(id: string): void }) {
  if (!images.length) return null;
  return <ul className="companion-image-drafts" aria-label="Ảnh chờ gửi">
    {images.map(image => <li key={image.id}>
      <img src={image.previewUrl ?? ''} alt={`Ảnh chờ gửi: ${image.file.name}`} />
      <button type="button" aria-label={`Gỡ ${image.file.name}`} title="Gỡ ảnh" onClick={() => onRemove(image.id)}>×</button>
    </li>)}
  </ul>;
}

export function CompanionMessageImages({ attachments }: { attachments?: ChatAttachment[] }) {
  const images = attachments?.filter(file => file.kind === 'image');
  if (!images?.length) return null;
  return <div className="companion-message-images">
    {images.map(image => <a key={image.id} href={image.url} target="_blank" rel="noopener noreferrer" aria-label={`Mở ảnh ${image.name}`}>
      <img src={image.url} alt={image.name} loading="lazy" />
    </a>)}
  </div>;
}
