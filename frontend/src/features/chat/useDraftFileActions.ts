import { useCallback, type Dispatch, type RefObject, type SetStateAction } from 'react';
import { MAX_FILES, MAX_FILE_BYTES, MAX_MEDIA_FILES, MAX_TOTAL_BYTES, isImageFile, isMediaFile } from './attachments';
import type { useChatDrafts } from './useChatDrafts';

/** Thêm tệp vào bản nháp (kiểm số tệp, cỡ tệp, trùng tệp) và bỏ tệp ra. Tách khỏi App.tsx (G3.3, 13/11/2026). */
export function useDraftFileActions(setDraftFiles: ReturnType<typeof useChatDrafts>['setDraftFiles'],
  abortRef: RefObject<AbortController | null>, setError: Dispatch<SetStateAction<string | null>>) {
  const addFiles = useCallback((list: FileList | File[]) => {
    if (abortRef.current) return false;
    const incoming = Array.from(list);
    let accepted = false;
    setError(null);
    setDraftFiles((prev) => {
      const next = [...prev];
      for (const file of incoming) {
        if (next.length >= MAX_FILES) {
          setError(`Mỗi tin chỉ gửi tối đa ${MAX_FILES} tệp`);
          break;
        }
        if (isMediaFile(file) && next.filter((item) => isMediaFile(item.file)).length >= MAX_MEDIA_FILES) {
          setError(`Mỗi tin chỉ gửi tối đa ${MAX_MEDIA_FILES} ảnh, PDF, Word hoặc Excel`);
          continue;
        }
        if (file.size > MAX_FILE_BYTES) {
          setError(`«${file.name}» quá nặng (tối đa 8 MB)`);
          continue;
        }
        const duplicate = next.some(
          (item) => item.file.name === file.name && item.file.size === file.size,
        );
        if (duplicate) continue;
        if (next.reduce((total, item) => total + item.file.size, 0) + file.size > MAX_TOTAL_BYTES) {
          setError("Tổng tệp đính kèm tối đa 16 MB mỗi tin.");
          continue;
        }
        next.push({
          id: crypto.randomUUID(),
          file,
          previewUrl: isImageFile(file) ? URL.createObjectURL(file) : null,
        });
        accepted = true;
      }
      return next;
    });
    return accepted;
  }, [setDraftFiles]);

  function removeDraftFile(id: string) {
    setDraftFiles((prev) => {
      const target = prev.find((item) => item.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((item) => item.id !== id);
    });
  }
  return { addFiles, removeDraftFile };
}
