export const MAX_SOURCE_IMAGE_BYTES = 20 * 1024 * 1024;
export const MAX_COMPANION_IMAGE_BYTES = 3 * 1024 * 1024;
export const MAX_IMAGE_EDGE = 1920;

/** Thu nhỏ như AIRI, giữ tỷ lệ và độ trong suốt; GIF giữ nguyên để không mất chuyển động. */
export async function prepareCompanionImage(file: File): Promise<File> {
  const extension = file.name.split('.').pop()?.toLowerCase();
  const mime = /^image\/(jpeg|png|webp|gif)$/i.test(file.type) ? file.type.toLowerCase()
    : ({ jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif' }[extension ?? ''] ?? '');
  if (mime === 'image/gif') return file;
  const source = URL.createObjectURL(file);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error(`Không đọc được ảnh «${file.name}». Hãy chọn lại ảnh khác nhé.`));
      image.src = source;
    });
    if (file.size <= MAX_COMPANION_IMAGE_BYTES && Math.max(image.naturalWidth, image.naturalHeight) <= MAX_IMAGE_EDGE) return file;
    const canvas = document.createElement('canvas');
    for (let edge = MAX_IMAGE_EDGE; edge >= 100; edge = Math.round(edge * 0.8)) {
      const scale = Math.min(1, edge / Math.max(image.naturalWidth, image.naturalHeight));
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Trình duyệt chưa xử lý được ảnh. Hãy thử lại nhé.');
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, mime, mime === 'image/jpeg' ? 0.85 : undefined));
      if (!blob) throw new Error(`Không thu nhỏ được ảnh «${file.name}». Hãy thử ảnh khác nhé.`);
      if (blob.size <= MAX_COMPANION_IMAGE_BYTES) {
        return new File([blob], file.name, { type: blob.type, lastModified: file.lastModified });
      }
    }
    throw new Error(`«${file.name}» vẫn quá nặng sau khi thu nhỏ (tối đa 3 MB).`);
  } finally {
    URL.revokeObjectURL(source);
  }
}
