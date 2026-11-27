import { useEffect, useRef } from 'react';
import { useReducedMotion } from '../../../shared/motion';
import { mountPeto } from './petoMark';
import { mountTetris, type TetrisMode } from './tetrisMark';
import { useIndicatorSettings, type IndicatorChoice, type IndicatorSize } from './indicatorSettings';

/**
 * Hình động nhỏ ở đầu dòng "Đang làm" (thay mũi tên khi lượt còn chạy). Theo Cài đặt → Giao diện; Tetris đổi kiểu theo
 * `mode` (việc Peto đang làm). Chuyển động Giảm thì đứng yên. `choice`/`size` để mục Cài đặt vẽ thử một lựa chọn.
 */
export default function WorkIndicator({ mode, choice, size: fixedSize }: {
  mode: TetrisMode; choice?: IndicatorChoice; size?: IndicatorSize;
}) {
  const settings = useIndicatorSettings();
  const indicator = choice ?? settings.indicator;
  const size = fixedSize ?? settings.size;
  const still = useReducedMotion();
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const node = canvas.current!;
    return indicator === 'tetris' ? mountTetris(node, mode, size, still)
      : mountPeto(node, indicator === 'machine-love-2', size, still);
  }, [indicator, mode, size, still]);
  return <canvas ref={canvas} className="work-indicator" data-indicator={indicator}
    data-mode={indicator === 'tetris' ? mode : undefined} style={{ width: size, height: size }} aria-hidden="true" />;
}

/** Việc của bước đang chạy → kiểu Tetris: nghĩ thì tự chơi, tìm web thì mưa khối, đọc thì khối trượt lên, viết thì xếp. */
export function tetrisMode(kind: string | undefined, answering: boolean): TetrisMode {
  if (answering) return 'stack';
  if (kind === 'search') return 'rain';
  if (kind === 'read' || kind === 'page' || kind === 'lookup' || kind === 'github' || kind === 'chats') return 'next';
  if (kind === 'compose' || kind === 'tool' || kind === 'code') return 'stack';
  return 'autoplay';
}
