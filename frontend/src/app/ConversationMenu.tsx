import {useEffect, useRef, type ReactNode} from 'react';

export default function ConversationMenu({left, top, onClose, children}: {left:number; top:number; onClose:()=>void; children:ReactNode}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {ref.current?.showModal();}, []);
  return <dialog ref={ref} className="conversation-menu-popup" aria-label="Tùy chọn hội thoại" style={{left,top}} onCancel={e => {e.preventDefault(); onClose();}} onClick={e => {if (e.target === ref.current) {const r=ref.current.getBoundingClientRect(); if(e.clientX<r.left || e.clientX>r.right || e.clientY<r.top || e.clientY>r.bottom) onClose();}}}>{children}</dialog>;
}
