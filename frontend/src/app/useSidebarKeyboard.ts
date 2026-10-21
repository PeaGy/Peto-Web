import { useEffect, type RefObject } from 'react';

/** Sidebar là drawer khi layout nhỏ: giữ Tab bên trong, Escape đóng và trả focus về nút mở. */
export function useSidebarKeyboard(open: boolean, root: RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const media = matchMedia('(max-width: 720px)');
    const node = root.current;
    if (!node || !media.matches) return;
    const returnTo = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const controls = () => [...node.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),[tabindex]:not([tabindex="-1"])')]
      .filter(item => item.getClientRects().length > 0 && !item.closest('[hidden],[inert]'));
    (controls()[0] ?? node).focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (!media.matches || event.defaultPrevented) return;
      const active = document.activeElement;
      // Menu tài khoản/dialog có cơ chế focus riêng và có thể đặt ngoài aside.
      if (active instanceof Element && !node.contains(active) && active.closest('[role="menu"],[role="dialog"],dialog')) return;
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab') return;
      const list = controls(), first = list[0], last = list.at(-1);
      if (!first) { event.preventDefault(); node.focus(); }
      else if (!node.contains(active) || event.shiftKey && active === first) {
        event.preventDefault(); (event.shiftKey ? last : first)?.focus();
      } else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (returnTo?.isConnected && (node.contains(document.activeElement) || document.activeElement === document.body)) {
        returnTo.focus({ preventScroll: true });
      }
    };
  }, [open, root, close]);
}
