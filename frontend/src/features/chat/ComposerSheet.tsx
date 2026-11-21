import { useLayoutEffect, useRef, type ReactNode } from 'react';

export function ComposerSheet({ label, onClose, children }: {
  label: string; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const dragStart = useRef<number | null>(null);
  useLayoutEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return <dialog ref={ref} className="composer-sheet" aria-label={label}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const box = event.currentTarget.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX >= box.right || event.clientY < box.top || event.clientY >= box.bottom) onClose();
    }}>
    <button type="button" className="sheet-handle" aria-label="Đóng bảng" onClick={onClose}
      onPointerDown={event => {
        dragStart.current = event.clientY;
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => {
        if (dragStart.current !== null && event.clientY - dragStart.current > 48) {
          dragStart.current = null;
          onClose();
        }
      }}
      onPointerCancel={() => { dragStart.current = null; }}
      onPointerUp={() => { dragStart.current = null; }} />
    <div className="sheet-body">{children}</div>
  </dialog>;
}
