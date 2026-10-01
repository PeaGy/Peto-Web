import { useEffect, useRef } from 'react';
import { DISCORD, GITHUB } from './docsShared';

type Layer = { current: HTMLElement | null };

/**
 * Nhân vật theo chuột như trang docs của AIRI (ParallaxCover.vue): chữ và nhân vật lùi ngược chiều chuột, hai lớp bóng
 * hồng và tím phía sau lệch theo hướng khác, mỗi lớp trôi tới chỗ mới trong 1,2 giây (chuyển động do CSS lo).
 * x, y là độ lệch của chuột so với giữa màn hình, theo tỉ lệ bề ngang và bề cao, trong khoảng -0,5..0,5.
 */
function offsets(x: number, y: number, width: number) {
  return [
    [-x * 0.03 * width, -y * 0.03 * width],
    [-x * 0.02 * width, -y * 0.02 * width],
    [0.01 * width - y * 0.015 * width, 0.02 * width + x * 0.015 * width],
    [0.01 * width + y * 0.01 * width, -0.01 * width - y * 0.01 * width],
  ];
}

function useParallax(motion: boolean, layers: Layer[]) {
  useEffect(() => {
    const place = (x: number, y: number) => {
      offsets(x, y, window.innerWidth).forEach(([left, top], index) => {
        const element = layers[index].current;
        if (element) element.style.transform = `translate3d(${left.toFixed(1)}px, ${top.toFixed(1)}px, 0)`;
      });
    };
    // Chỗ nghỉ đặt ngay, không trượt vào khi mở trang; chỉ những lần sau mới trôi (data-live bật transition trong CSS).
    place(0, 0);
    const live = requestAnimationFrame(() => layers.forEach(layer => layer.current?.setAttribute('data-live', '')));
    let frame = 0;
    let pointer: { x: number; y: number } | null = null;
    const move = (event: MouseEvent) => {
      pointer = { x: event.clientX, y: event.clientY };
      frame ||= requestAnimationFrame(() => {
        frame = 0;
        if (pointer) place((pointer.x - innerWidth / 2) / innerWidth, (pointer.y - innerHeight / 2) / innerHeight);
      });
    };
    const resize = () => place(0, 0);
    if (motion) window.addEventListener('mousemove', move, { passive: true });
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(live);
      cancelAnimationFrame(frame);
      window.removeEventListener('mousemove', move);
      window.removeEventListener('resize', resize);
    };
  }, [motion]); // eslint-disable-line react-hooks/exhaustive-deps
}

export default function DocsHome({ motion }: { motion: boolean }) {
  const copy = useRef<HTMLDivElement>(null);
  const art = useRef<HTMLImageElement>(null);
  const pink = useRef<HTMLDivElement>(null);
  const violet = useRef<HTMLDivElement>(null);
  useParallax(motion, [copy, art, pink, violet]);

  return <main id="docs-main" className="docs-home">
    <div className="docs-home-copy docs-parallax" ref={copy}>
      <p className="docs-chip">Hướng dẫn tiếng Việt</p>
      <h1>Peto</h1>
      <p className="docs-slogan">Trò chuyện, sáng tạo và làm việc cùng Peto: trên web, trong Companion và ngay trong thư mục dự án của bạn.</p>
      <div className="docs-home-actions">
        <a className="docs-glass docs-glass-primary" href="/">Mở Peto</a>
        <a className="docs-glass" href="/docs/cai-agent/">Cài Agent CLI</a>
        <a className="docs-glass" href="/docs/bat-dau/">Bắt đầu</a>
      </div>
    </div>
    {/* Nhân vật nằm ngay dưới hàng nút (tóc lùi ra sau nút như AIRI) và lớn theo chỗ trống còn lại, để mặt luôn trong màn hình. */}
    <div className="docs-stage" aria-hidden="true">
      <div className="docs-cover">
        <img ref={art} className="docs-parallax" src="/docs-assets/peto-hero.webp" alt="" width="1069" height="1472" draggable={false}
          fetchPriority="high" />
        <div ref={pink} className="docs-silhouette docs-silhouette-pink docs-parallax" />
        <div ref={violet} className="docs-silhouette docs-silhouette-violet docs-parallax" />
      </div>
    </div>
    <div className="docs-scene" aria-hidden="true">
      <div className="docs-pattern" />
      <div className="docs-fade" />
    </div>
    <footer className="docs-home-foot">
      Peto × PeaGy · <a href={DISCORD} target="_blank" rel="noreferrer">Discord</a> · <a href={GITHUB} target="_blank" rel="noreferrer">GitHub</a>
    </footer>
  </main>;
}
