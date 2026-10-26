/** Biểu tượng của khung chat Companion, vẽ lại theo dáng các biểu tượng AIRI dùng (không chép bộ Solar). */
import type { ReactNode } from 'react';

function Icon({ size = 18, children, fill = false }: { size?: number; children: ReactNode; fill?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={fill ? 'currentColor' : 'none'} stroke={fill ? 'none' : 'currentColor'}
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
  );
}

export const DotsIcon = () => <Icon size={16} fill><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></Icon>;
export const CheckIcon = () => <Icon size={16}><path d="m5 12.5 4.5 4.5L19 7.5" /></Icon>;
export const ReplyIcon = ({ size = 16 }: { size?: number }) => <Icon size={size}><path d="M9.5 6 4 11.5 9.5 17" /><path d="M4.5 11.5H14a6 6 0 0 1 6 6V19" /></Icon>;
export const CopyIcon = () => <Icon size={16}><rect x="8" y="8" width="12" height="12" rx="3" /><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8" /></Icon>;
export const TrashIcon = () => <Icon size={16}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></Icon>;
export const ListenIcon = () => <Icon size={16}><path d="M11 5 6.5 9H4v6h2.5L11 19z" /><path d="M15.5 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" /></Icon>;
export const StopSquareIcon = ({ size = 18 }: { size?: number }) => <Icon size={size}><rect x="6.5" y="6.5" width="11" height="11" rx="2.5" /></Icon>;
export const ArrowUpIcon = () => <Icon size={20}><path d="M12 19V5M6 11l6-6 6 6" /></Icon>;
export const GalleryIcon = () => <Icon size={20}><rect x="3.5" y="4.5" width="17" height="15" rx="4" /><circle cx="9" cy="10" r="1.6" /><path d="m4 17 4.5-4.5 3.5 3.5 3-3 5 4.5" /></Icon>;
export const PaperclipIcon = () => <Icon size={20}><path d="m20 11.5-7.8 7.8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.4 3.4 0 0 1 4.8 4.8l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8" /></Icon>;
export const SoundwaveIcon = ({ on = false }: { on?: boolean }) => (
  <Icon size={20}><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10.5v3" strokeWidth={on ? 2.4 : 1.8} /></Icon>
);
export const CloseCircleIcon = () => <Icon size={18}><circle cx="12" cy="12" r="9" /><path d="m9.5 9.5 5 5M14.5 9.5l-5 5" /></Icon>;
