import { useCallback, useEffect, useRef, useState } from 'react';
import { MAX_MEDIA_FILES } from '../chat/attachments';
import type { DraftFile } from '../chat/files';
import { prepareCompanionImage, MAX_SOURCE_IMAGE_BYTES, MAX_COMPANION_IMAGE_BYTES } from './prepareCompanionImage';

/** Ảnh chờ gửi chỉ sống trong tab; xóa đúng ảnh máy chủ đã nhận để giữ ảnh của lời nhắn tiếp theo. */
export function useCompanionImages(onError: (message: string | null) => void) {
  const [images, setImages] = useState<DraftFile[]>([]);
  const current = useRef(images);
  const [pending, setPending] = useState(0);
  const preparing = useRef(0);
  const reserved = useRef(0);
  const generation = useRef(0);
  const mounted = useRef(true);
  const update = useCallback((next: DraftFile[]) => { current.current = next; setImages(next); }, []);
  const remove = useCallback((ids: string[]) => {
    const removed = new Set(ids);
    for (const image of current.current) {
      if (removed.has(image.id) && image.previewUrl) URL.revokeObjectURL(image.previewUrl);
    }
    update(current.current.filter(image => !removed.has(image.id)));
  }, [update]);
  const add = useCallback(async (files: FileList | File[]) => {
    const batch = Array.from(files).filter(file => !current.current.some(image => image.file.name === file.name
      && image.file.size === file.size && image.file.lastModified === file.lastModified));
    if (!batch.length) return;
    onError(null);
    for (const file of batch) {
      if (!/^image\/(jpeg|png|webp|gif)$/i.test(file.type) && !/\.(jpe?g|png|webp|gif)$/i.test(file.name)) {
        onError(`«${file.name}» không phải ảnh được hỗ trợ. Chọn JPEG, PNG, WebP hoặc GIF nhé.`);
        return;
      }
      if (!file.size || file.size > MAX_SOURCE_IMAGE_BYTES) {
        onError(`«${file.name}» ${file.size ? 'quá nặng (ảnh gốc tối đa 20 MB)' : 'là ảnh trống'}.`);
        return;
      }
    }
    if (current.current.length + reserved.current + batch.length > MAX_MEDIA_FILES) {
      onError(`Mỗi tin chỉ gửi tối đa ${MAX_MEDIA_FILES} ảnh.`);
      return;
    }
    // Giữ chỗ trước khi giải mã để chọn/dán liên tiếp không vượt số ảnh cho phép.
    const revision = generation.current;
    reserved.current += batch.length;
    preparing.current++;
    setPending(preparing.current);
    try {
      const prepared: File[] = [];
      for (const file of batch) {
        if (!mounted.current || revision !== generation.current) return;
        prepared.push(await prepareCompanionImage(file));
      }
      if (!mounted.current || revision !== generation.current) return;
      const total = [...current.current.map(image => image.file), ...prepared].reduce((bytes, file) => bytes + file.size, 0);
      if (total > MAX_COMPANION_IMAGE_BYTES) {
        onError('Tổng ảnh sau khi thu nhỏ tối đa 3 MB mỗi tin. Hãy bớt ảnh hoặc chọn ảnh nhẹ hơn nhé.');
        return;
      }
      update([...current.current, ...prepared.map(file => ({ id: crypto.randomUUID(), file, previewUrl: URL.createObjectURL(file) }))]);
    } catch (error) {
      if (mounted.current && revision === generation.current) onError(error instanceof Error ? error.message : 'Không xử lý được ảnh. Hãy thử lại nhé.');
    } finally {
      if (mounted.current && revision === generation.current) {
        reserved.current -= batch.length;
        preparing.current--;
        setPending(preparing.current);
      }
    }
  }, [onError, update]);
  const clear = useCallback(() => {
    generation.current++;
    reserved.current = 0;
    preparing.current = 0;
    setPending(0);
    remove(current.current.map(image => image.id));
  }, [remove]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current++;
      for (const image of current.current) if (image.previewUrl) URL.revokeObjectURL(image.previewUrl);
    };
  }, []);
  return { images, add, remove, clear, pending, isPreparing: () => preparing.current > 0 };
}
