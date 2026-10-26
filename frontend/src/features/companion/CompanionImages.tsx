import type { ChatAttachment } from '../../shared/api/api';
import type { DraftFile } from '../chat/files';

/** Ảnh xem trước nằm ngay trong ô nhắn; trên điện thoại giữ kích thước nhỏ để nhường chỗ cho nhân vật. */
export function CompanionImageDrafts({ images, onRemove }: { images: DraftFile[]; onRemove(id: string): void }) {
  if (!images.length) return null;
  return <ul className="companion-image-drafts" aria-label="Ảnh chờ gửi">
    {images.map(image => <li key={image.id}>
      <img src={image.previewUrl ?? ''} alt={`Ảnh chờ gửi: ${image.file.name}`} />
      <button type="button" aria-label={`Gỡ ${image.file.name}`} data-tip="Gỡ ảnh" onClick={() => onRemove(image.id)}>×</button>
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
