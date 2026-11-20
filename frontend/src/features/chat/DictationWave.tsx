import { useEffect, useRef } from 'react';

// Sóng âm lúc đang nghe, như dải chấm của Claude: mỗi vạch là âm lượng một khoảnh khắc gần đây, vạch mới vào từ phải.
// Im lặng thì chỉ còn chấm. Cập nhật thẳng style của từng vạch, không render lại React mỗi khung hình.

const BARS = 18;
const STEP_MS = 70;

export default function DictationWave({ stream }: { stream: MediaStream | null }) {
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const bars = [...(root.current?.children ?? [])] as HTMLElement[];
    const levels = new Array<number>(BARS).fill(0);
    const paint = () => bars.forEach((bar, index) => {
      bar.style.transform = `scaleY(${Math.max(0.18, levels[index]).toFixed(3)})`;
    });
    paint();
    if (!stream) return;
    let context: AudioContext;
    try {
      context = new AudioContext();
    } catch {
      return;
    }
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      if (now - last >= STEP_MS) {
        last = now;
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const value of samples) sum += value * value;
        levels.shift();
        levels.push(Math.min(1, Math.sqrt(sum / samples.length) * 6));
        paint();
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      void context.close().catch(() => {});
    };
  }, [stream]);
  return (
    <span ref={root} className={stream ? 'dictation-wave' : 'dictation-wave idle'} aria-hidden="true">
      {Array.from({ length: BARS }, (_, index) => <span key={index} style={{ animationDelay: `${index * 60}ms` }} />)}
    </span>
  );
}
