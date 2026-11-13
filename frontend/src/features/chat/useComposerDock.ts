import { useEffect, useLayoutEffect, useRef } from 'react';
import { isReducedMotion } from '../../shared/motion';

/** Ô nhắn ở đáy tab Trò chuyện: đo chiều cao phần dưới cho CSS, và trượt ô nhắn từ giữa màn hình xuống khi gửi tin đầu.
 * Tách khỏi App.tsx (G3.3, 13/11/2026); thân các hiệu ứng giữ nguyên. */
export function useComposerDock(emptyChat: boolean, authenticated: boolean | undefined, view: string) {
  const composerRef = useRef<HTMLFormElement>(null);
  const chatDockRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const dock = chatDockRef.current;
    const chat = dock?.parentElement;
    if (!dock || !chat || typeof ResizeObserver === 'undefined') return;
    const measure = () => chat.style.setProperty('--chat-dock-height', `${dock.getBoundingClientRect().height}px`);
    const observer = new ResizeObserver(measure);
    observer.observe(dock);
    measure();
    return () => observer.disconnect();
  }, [authenticated, view]);
  const composerBoxRef = useRef<HTMLDivElement>(null);
  // Chỗ ô nhắn đứng lúc còn ở giữa màn hình, đo ngay trước khi gửi tin đầu.
  const composerFrom = useRef<number | null>(null);
  const composerMove = useRef<Animation | null>(null);
  // Chỉ lần gửi tin đầu mới trượt ô nhắn xuống (FLIP): mắt người dùng đang ở đúng
  // ô đó, để nó nhảy cóc là mất dấu. Mở hội thoại hay tạo cuộc mới là điều hướng,
  // làm nhiều lần trong ngày, nên đổi ngay không hiệu ứng.
  useLayoutEffect(() => {
    const from = composerFrom.current;
    composerFrom.current = null;
    if (emptyChat) {
      composerMove.current?.cancel();
      return;
    }
    const form = composerRef.current;
    const box = composerBoxRef.current;
    if (from === null || !form || !box || typeof form.animate !== "function") return;
    const distance = from - box.getBoundingClientRect().top;
    // Điện thoại giữ ô nhắn ở đáy cả hai lúc, nên không có gì để trượt.
    if (Math.abs(distance) < 1) return;
    if (isReducedMotion()) {
      // Giảm chuyển động: bỏ quãng trượt, chỉ để ô nhắn hiện dần ở chỗ mới.
      composerMove.current = form.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: "ease" });
      return;
    }
    const easing = getComputedStyle(document.documentElement).getPropertyValue("--ease-in-out").trim();
    composerMove.current = form.animate(
      [{ transform: `translateY(${distance}px)` }, { transform: "none" }],
      { duration: 300, easing: easing || "ease-in-out" },
    );
  }, [emptyChat]);
  return { composerRef, chatDockRef, composerBoxRef, composerFrom };
}
