import {useLayoutEffect, useRef, type ReactNode} from 'react';

export default function ConversationMenu({left, top, onClose, children, label='Tùy chọn hội thoại'}: {left:number; top:number; onClose:()=>void; children:ReactNode; label?:string}) {
  const ref = useRef<HTMLDialogElement>(null);
  // Chỗ mở do nơi gọi đoán theo chiều cao cũ của menu; từ khi có thêm Tải Markdown / In (28/11/2026), mở xong menu tự
  // đẩy lên cho trọn trong khung nhìn nếu hàng nằm sát đáy.
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu) return;
    menu.showModal();
    const box = menu.getBoundingClientRect();
    if (box.height && box.bottom > window.innerHeight - 8) menu.style.top = `${Math.max(8, window.innerHeight - box.height - 8)}px`;
  }, []);
  return <dialog ref={ref} className="conversation-menu-popup popup-menu" aria-label={label} style={{left,top}} onCancel={e => {e.preventDefault(); onClose();}} onClick={e => {if (e.target === ref.current) {const r=ref.current.getBoundingClientRect(); if(e.clientX<r.left || e.clientX>r.right || e.clientY<r.top || e.clientY>r.bottom) onClose();}}}>{children}</dialog>;
}
