import { useCallback, useEffect, useRef, useState, type DragEvent, type ReactNode } from 'react';
import './chatFileDrop.css';

interface Props {
  children: ReactNode;
  className: string;
  hidden: boolean;
  enabled: boolean;
  contextKey: string;
  onFiles: (files: FileList) => void;
}

// Khi kéo từ máy vào, trình duyệt giấu danh sách tệp tới lúc thả; kiểm tra loại dữ liệu trước.
function hasFiles(data: DataTransfer | null): boolean {
  return Boolean(data && Array.from(data.types).includes('Files'));
}

function DropArtwork() {
  return <svg className="chat-file-drop-art" width="112" height="92" viewBox="0 0 112 92" fill="none" aria-hidden="true">
    <g transform="rotate(-14 28 38)">
      <rect x="5" y="17" width="44" height="43" rx="12" fill="#B9BFFF" />
      <path d="m18 31 6 5-6 5m15 0h7" stroke="#17133D" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </g>
    <g transform="rotate(15 83 32)">
      <path d="M68 6h22l13 13v38a5 5 0 0 1-5 5H68a5 5 0 0 1-5-5V11a5 5 0 0 1 5-5Z" fill="#8585FF" />
      <path d="M90 6v13h13" fill="#161238" />
      <path d="M74 28h16M74 37h16M74 46h8" stroke="#17133D" strokeWidth="3.5" strokeLinecap="round" />
    </g>
    <rect x="37" y="46" width="47" height="44" rx="13" fill="#5752FF" />
    <circle cx="69" cy="59" r="4" fill="#17133D" />
    <path d="m47 78 10-13 9 11 5-6 6 8" stroke="#17133D" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

/** Vùng chat nhận tệp; sidebar là phần tử bên ngoài nên không thể thêm tệp qua đây. */
export default function ChatFileDropZone({ children, className, hidden, enabled, contextKey, onFiles }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const reset = useCallback(() => { depth.current = 0; setDragging(false); }, []);
  // Bảng tài liệu desktop dùng dialog không modal; vẫn cho thêm tệp khi nó mở cạnh chat.
  const canAccept = () => enabled && !hidden && !document.querySelector('dialog[open]:not([role="complementary"]), [aria-modal="true"]');

  useEffect(reset, [reset, enabled, hidden, contextKey]);

  useEffect(() => {
    if (hidden) return;
    // Thả nhầm ra sidebar không được khiến trình duyệt mở tệp và rời cuộc trò chuyện.
    // Không chặn kéo chữ/liên kết, và nhường các tab khác cho cơ chế kéo thả riêng của chúng.
    const guard = (event: globalThis.DragEvent) => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      if (event.type === 'drop') reset();
      else if (event.target instanceof Node && !root.current?.contains(event.target)) {
        if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
        reset();
      }
    };
    const cancel = (event: KeyboardEvent) => { if (event.key === 'Escape') reset(); };
    const visibility = () => { if (document.hidden) reset(); };
    window.addEventListener('dragover', guard);
    window.addEventListener('drop', guard);
    window.addEventListener('dragend', reset);
    window.addEventListener('blur', reset);
    window.addEventListener('keydown', cancel);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      window.removeEventListener('dragover', guard);
      window.removeEventListener('drop', guard);
      window.removeEventListener('dragend', reset);
      window.removeEventListener('blur', reset);
      window.removeEventListener('keydown', cancel);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [hidden, reset]);

  const over = (event: DragEvent<HTMLDivElement>) => {
    if (!hasFiles(event.dataTransfer)) return;
    event.preventDefault();
    const accepted = canAccept();
    event.dataTransfer.dropEffect = accepted ? 'copy' : 'none';
    if (accepted) setDragging(true);
    else reset();
  };

  return <div ref={root} className={className} hidden={hidden}
    onDragEnter={event => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      if (!canAccept()) return;
      depth.current += 1;
      setDragging(true);
    }}
    onDragOver={over}
    onDragLeave={event => {
      if (!hasFiles(event.dataTransfer)) return;
      const next = event.relatedTarget;
      if (next instanceof Node && !event.currentTarget.contains(next)) { reset(); return; }
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) reset();
    }}
    onDrop={event => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      reset();
      if (canAccept() && event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
    }}>
    {children}
    {dragging && enabled && !hidden && <div className="chat-file-drop-overlay" role="status">
      <div className="chat-file-drop-content">
        <DropArtwork />
        <strong>Thêm ảnh và tệp</strong>
        <span>Thả tệp vào đây để thêm vào cuộc trò chuyện</span>
      </div>
    </div>}
  </div>;
}
