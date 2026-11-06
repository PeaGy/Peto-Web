import { useEffect, type RefObject } from 'react';

/**
 * Chuyển động khi cuộn của trang tải, theo số đo trên trang DeepSeek Harness (5/11/2026) mà chủ dự án chọn làm mẫu:
 * - khối có data-reveal hiện dần và trồi lên một lần khi vào khung nhìn (data-reveal là quãng trồi, px; data-blur thêm
 *   độ nhòe), các ô cùng hàng của một lưới lệch nhau 90 ms;
 * - khung ứng dụng data-tilt ngả ra sau tới 5° và thu còn 98,5% trong 900 px cuộn đầu, đi theo con lăn hơi trễ;
 * - vầng sáng data-glow lớn dần từ 85% khi khối của nó đi vào khung nhìn.
 * Tắt hiệu ứng động (enabled = false) thì mọi khối hiện sẵn và không có gì nghiêng: CSS chỉ ẩn khối dưới .docs-motion.
 */
export function useScrollMotion(root: RefObject<HTMLElement | null>, enabled: boolean) {
  useEffect(() => {
    const page = root.current;
    if (!page) return;
    const items = [...page.querySelectorAll<HTMLElement>('[data-reveal]')];
    const tilt = page.querySelector<HTMLElement>('[data-tilt]');
    const glow = page.querySelector<HTMLElement>('[data-glow]');
    const show = (item: HTMLElement) => { item.dataset.shown = ''; };
    if (!enabled || typeof IntersectionObserver === 'undefined') {
      items.forEach(show);
      return;
    }

    for (const item of items) {
      item.style.setProperty('--dl-rise', `${item.dataset.reveal || 24}px`);
      if (item.dataset.blur) item.style.setProperty('--dl-blur', `${item.dataset.blur}px`);
      const parent = item.parentElement;
      const style = parent ? getComputedStyle(parent) : null;
      const columns = style?.display === 'grid' ? style.gridTemplateColumns.split(' ').filter(Boolean).length : 1;
      const index = parent ? [...parent.children].indexOf(item) : 0;
      item.style.setProperty('--dl-delay', `${columns > 1 ? (index % columns) * 90 : Number(item.dataset.delay || 0)}ms`);
    }
    // Khối đã nằm phía trên khung nhìn (mở trang ở giữa, bật lại hiệu ứng) cũng hiện luôn, không chờ cuộn ngược lên.
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting || entry.boundingClientRect.bottom < 0) {
          show(entry.target as HTMLElement);
          observer.unobserve(entry.target);
        }
      }
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });
    items.filter(item => !('shown' in item.dataset)).forEach(item => observer.observe(item));

    let lean = 0;
    let frame = 0;
    const follow = () => {
      frame = 0;
      if (tilt) {
        const target = Math.min(1, Math.max(0, window.scrollY / 900));
        lean += (target - lean) * 0.16;
        if (Math.abs(target - lean) < 0.001) lean = target;
        tilt.style.transform = `perspective(1600px) rotateX(${(lean * 5).toFixed(3)}deg) scale(${(1 - lean * 0.015).toFixed(4)})`;
        if (lean !== target) frame = requestAnimationFrame(follow);
      }
      if (glow) {
        const box = glow.getBoundingClientRect();
        const seen = Math.min(1, Math.max(0, (window.innerHeight - box.top) / (window.innerHeight * 0.9)));
        glow.style.setProperty('--dl-glow', (0.85 + 0.15 * seen).toFixed(4));
        glow.style.setProperty('--dl-glow-y', `${((1 - seen) * 40).toFixed(1)}px`);
      }
    };
    const scroll = () => { if (!frame) frame = requestAnimationFrame(follow); };
    window.addEventListener('scroll', scroll, { passive: true });
    window.addEventListener('resize', scroll, { passive: true });
    follow();
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', scroll);
      window.removeEventListener('resize', scroll);
      cancelAnimationFrame(frame);
      if (tilt) tilt.style.transform = '';
      glow?.style.removeProperty('--dl-glow');
      glow?.style.removeProperty('--dl-glow-y');
    };
  }, [root, enabled]);
}
