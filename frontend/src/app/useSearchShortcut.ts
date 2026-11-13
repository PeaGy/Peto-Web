import { useEffect, type Dispatch, type SetStateAction } from 'react';

/** Tách khỏi App.tsx (G3.3, 13/11/2026). */
export function useSearchShortcut(streaming: boolean, setSearchOpen: Dispatch<SetStateAction<boolean>>) {
  // Ctrl+K (⌘K trên Mac) mở tìm hội thoại như Grok và ChatGPT, ở mọi tab; tooltip của nút tìm ghi phím này.
  // Không mở khi đang trả lời (nút tìm cũng tắt lúc đó) hay khi một hộp thoại modal khác đang mở.
  useEffect(() => {
    const openSearch = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.key.toLowerCase() !== 'k') return;
      let modal = false;
      try { modal = Boolean(document.querySelector('dialog:modal')); } catch { /* trình duyệt cũ không có :modal */ }
      if (streaming || modal) return;
      event.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener('keydown', openSearch);
    return () => window.removeEventListener('keydown', openSearch);
  }, [streaming]);
}
