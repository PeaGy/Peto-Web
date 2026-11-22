/**
 * Tin dài của người dùng được gập lại như Claude (22/11/2026, chủ web chọn sau khi xem claude.ai): cao quá
 * FOLD_LIMIT thì chỉ hiện FOLD_HEIGHT px, mờ dần ở đáy, kèm nút "Xem thêm" / "Thu gọn". Nhờ vậy câu hỏi dài vừa gửi
 * được ghim lên đỉnh (App: turnPin) mà đầu câu trả lời vẫn nằm ngay bên dưới, không bị đẩy khỏi màn hình.
 *
 * Trước khi đo, khung đã bị chặn ở FOLD_LIMIT (data-unmeasured, như Claude) để tin dài không cao vọt rồi co lại.
 */
import { useCallback, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';

export const FOLD_HEIGHT = 200;
// Chỉ gập khi phần bị ẩn đáng kể (hơn dải mờ 48 px); tin chỉ hơi cao hơn 200 px thì hiện hết.
export const FOLD_LIMIT = FOLD_HEIGHT + 48;

type FoldState = 'unmeasured' | 'short' | 'folded' | 'open';

export default function UserMessageFold({ text, children }: { text: string; children: ReactNode }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<FoldState>('unmeasured');
  const id = useId();

  const measure = useCallback(() => {
    const box = boxRef.current;
    if (!box) return;
    const long = box.scrollHeight > FOLD_LIMIT;
    setState(current => !long ? 'short' : current === 'open' ? 'open' : 'folded');
  }, []);

  useLayoutEffect(() => {
    measure();
  }, [text, measure]);

  useLayoutEffect(() => {
    // Đổi bề ngang (xoay điện thoại, kéo cửa sổ) làm chữ xuống dòng khác: đo lại.
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [measure]);

  function toggle() {
    const box = boxRef.current;
    if (state === 'open') {
      setState('folded');
      // Thu gọn khi đã kéo xuống giữa tin dài: đưa mép trên tin về trong tầm nhìn để không lạc chỗ.
      requestAnimationFrame(() => {
        const bubble = box?.closest('article');
        if (bubble && bubble.getBoundingClientRect().top < 0) bubble.scrollIntoView({ block: 'start', behavior: 'instant' });
      });
    } else setState('open');
  }

  return <>
    <div ref={boxRef} id={id} className={`user-fold${state === 'folded' ? ' folded' : ''}`}
      data-unmeasured={state === 'unmeasured' || undefined}>
      {children}
    </div>
    {(state === 'folded' || state === 'open') && (
      <button type="button" className="user-fold-toggle" aria-expanded={state === 'open'} aria-controls={id} onClick={toggle}>
        {state === 'open' ? 'Thu gọn' : 'Xem thêm'}
      </button>
    )}
  </>;
}
