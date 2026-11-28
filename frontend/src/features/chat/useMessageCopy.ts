import { useEffect, useRef, useState } from 'react';

/** Clipboard failures stay on the action itself, without changing the message. */
export function useMessageCopy() {
  const [state, setState] = useState<'idle' | 'done' | 'fail'>('idle');
  const timer = useRef<number | undefined>(undefined);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; window.clearTimeout(timer.current); };
  }, []);

  async function run(operation: () => Promise<void>) {
    let result: 'done' | 'fail' = 'done';
    try { await operation(); } catch { result = 'fail'; }
    if (!alive.current) return;
    setState(result);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState('idle'), 2200);
  }
  const label = state === 'done' ? 'Đã chép' : state === 'fail' ? 'Chưa chép được' : 'Sao chép';
  return {
    state, label, run,
    copy: (text: string) => run(() => navigator.clipboard.writeText(text)),
    /** Chép cả chữ thường (Markdown) lẫn HTML (dán vào Word, Docs, Gmail giữ định dạng); trình duyệt không hỗ trợ
     * ClipboardItem hay từ chối ghi HTML thì chép chữ thường như cũ. */
    copyRich: (text: string, html: () => string | null) => run(async () => {
      const rich = typeof ClipboardItem === 'undefined' || !navigator.clipboard.write ? null : html();
      if (rich) {
        try {
          await navigator.clipboard.write([new ClipboardItem({
            'text/plain': new Blob([text], { type: 'text/plain' }),
            'text/html': new Blob([rich], { type: 'text/html' }),
          })]);
          return;
        } catch { /* chép chữ thường bên dưới */ }
      }
      await navigator.clipboard.writeText(text);
    }),
  };
}
