import { useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import type { AdminBucket, AdminModel, AdminService, OutcomeKey } from './adminApi';
import { secs, usd } from './format';

export const SERVICES: AdminService[] = ['xai', 'openai', 'anthropic'];
// Màu theo nhà cung cấp, không theo thứ hạng: lọc bớt dữ liệu cũng không đổi màu của ai.
export const SERVICE_COLOR: Record<string, string> = { xai: 'var(--adm-s1)', openai: 'var(--adm-s2)', anthropic: 'var(--adm-s3)' };
export const SERVICE_NAME: Record<string, string> = { xai: 'xAI (Peto)', openai: 'OpenAI', anthropic: 'Anthropic' };

// Vẽ SVG theo đúng số pixel thật, không kéo giãn: chữ trên trục giữ nguyên cỡ ở mọi bề rộng.
function useWidth(box: RefObject<HTMLElement | null>, fallback: number) {
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    const update = () => {
      const next = Math.round(element.clientWidth);
      if (next > 0) setWidth(value => value === next ? value : next);
    };
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [box]);
  return width;
}

// Bước vạch tròn 1, 2, 5 × 10ⁿ: trục ra $0, $5, $10… chứ không $6,3.
function niceStep(value: number) {
  const base = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 5, 10].map(multiple => multiple * base).find(step => step >= value)!;
}

export function ServiceLegend({ values }: { values?: Record<AdminService, number | null> | null }) {
  return <ul className="adm-legend" aria-label="Chú thích màu">
    {SERVICES.map(service => <li key={service}><i style={{ background: SERVICE_COLOR[service] }} aria-hidden="true" />{SERVICE_NAME[service]}
      {values && (values[service] === null ? <em>chưa có giá</em> : <b>{usd(values[service])}</b>)}</li>)}
  </ul>;
}

/** Cột chồng chi phí theo nhà cung cấp; rê chuột hoặc dùng phím mũi tên để đọc từng cột. */
export function CostColumns({ buckets, unpriced = [], height = 200 }: { buckets: AdminBucket[]; unpriced?: AdminService[]; height?: number }) {
  const [active, setActive] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const width = useWidth(box, 720), left = 44, bottom = 22, top = 8;
  const totals = buckets.map(bucket => SERVICES.reduce((sum, service) => sum + bucket.cost[service], 0));
  const peak = Math.max(...totals, 0);
  const step = peak > 0 ? niceStep(peak / 4) : 1;
  const max = peak > 0 ? Math.ceil(peak / step) * step : 4;
  const plotH = height - bottom - top, plotW = Math.max(1, width - left - 4);
  const slot = plotW / Math.max(1, buckets.length), bar = Math.min(24, slot * .62);
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, index) => index * step);
  const every = Math.ceil(buckets.length / Math.max(3, Math.floor(plotW / 56)));
  const move = (event: KeyboardEvent) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    setActive(index => Math.max(0, Math.min(buckets.length - 1, (index ?? buckets.length) + (event.key === 'ArrowRight' ? 1 : -1))));
  };
  const shown = active === null ? null : buckets[active];
  const tip = (() => {
    if (active === null) return undefined;
    // Đặt cạnh cột đang xem (không che nó), lật sang trái khi gần mép phải.
    const center = left + (active + .5) * slot, gap = bar / 2 + 10;
    return center > width * .6 ? { left: center - gap, transform: 'translateX(-100%)' } : { left: center + gap };
  })();
  return <div className="adm-chart" ref={box} tabIndex={0} role="group" aria-labelledby={titleId} onKeyDown={move}
    onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}>
    <span id={titleId} className="adm-sr">Chi phí ước tính theo thời gian. Dùng phím mũi tên để đọc từng cột.</span>
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {ticks.map(tick => {
        const y = top + plotH - tick / max * plotH;
        return <g key={tick}>
          <line x1={left} x2={width} y1={y} y2={y} className="adm-grid" />
          <text x={left - 8} y={y + 4} className="adm-tick" textAnchor="end">{tick === 0 ? '0' : `$${tick.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}`}</text>
        </g>;
      })}
      {buckets.map((bucket, index) => {
        const x = left + index * slot + (slot - bar) / 2;
        const parts = SERVICES.filter(service => bucket.cost[service] > 0);
        let y = top + plotH;
        return <g key={bucket.start} className={active === index ? 'adm-col on' : active !== null ? 'adm-col dim' : 'adm-col'}>
          {bucket.empty && <rect x={x} y={top + plotH - 3} width={bar} height={3} rx={1.5} className="adm-empty-mark" />}
          {parts.map((service, part) => {
            const segment = Math.max(1, bucket.cost[service] / max * plotH - (part ? 2 : 0));
            y -= segment + (part ? 2 : 0);
            const isTop = part === parts.length - 1, radius = Math.min(4, segment, bar / 2);
            const path = isTop
              ? `M${x},${y + segment}V${y + radius}Q${x},${y} ${x + radius},${y}H${x + bar - radius}Q${x + bar},${y} ${x + bar},${y + radius}V${y + segment}Z`
              : `M${x},${y + segment}V${y}H${x + bar}V${y + segment}Z`;
            return <path key={service} d={path} fill={SERVICE_COLOR[service]} />;
          })}
          {index % every === 0 && <text x={x + bar / 2} y={height - 6} className="adm-tick" textAnchor="middle">{bucket.label}</text>}
          <rect x={left + index * slot} y={top} width={slot} height={plotH} fill="transparent" onPointerEnter={() => setActive(index)} />
        </g>;
      })}
      <line x1={left} x2={width} y1={top + plotH} y2={top + plotH} className="adm-axis" />
    </svg>
    {shown && active !== null && <div className="adm-tip" style={tip}>
      <span className="adm-tip-head">{shown.full}</span>
      {shown.empty ? <span className="adm-tip-row">Chưa có dữ liệu thời điểm này</span> : <>
        {SERVICES.map(service => <span key={service} className="adm-tip-row"><i style={{ background: SERVICE_COLOR[service] }} />
          {unpriced.includes(service) ? <em>chưa có giá</em> : <b>{usd(shown.cost[service])}</b>}{SERVICE_NAME[service]}</span>)}
        <span className="adm-tip-row total"><b>{usd(totals[active])}</b>{shown.calls.toLocaleString('vi-VN')} lần gọi</span>
      </>}
    </div>}
  </div>;
}

export function Sparkline({ values, width = 80, height = 28 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2 || values.every(value => value === 0)) return null;
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => `${(index / (values.length - 1)) * (width - 4) + 2},${height - 3 - (value / max) * (height - 6)}`);
  const [lastX, lastY] = points[points.length - 1].split(',');
  return <svg className="adm-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    <polyline points={points.join(' ')} fill="none" />
    <circle cx={lastX} cy={lastY} r={3} />
  </svg>;
}

type Tone = 'good' | 'neutral' | 'critical' | 'serious' | 'warning';
const OUTCOMES: Record<OutcomeKey, { label: string; tone: Tone; icon: string }> = {
  complete: { label: 'Thành công', tone: 'good', icon: '✓' },
  stopped: { label: 'Dừng hoặc ngắt kết nối', tone: 'neutral', icon: '■' },
  error: { label: 'Lỗi nhà cung cấp hoặc máy chủ', tone: 'critical', icon: '!' },
  timeout: { label: 'Hết thời gian', tone: 'serious', icon: '◷' },
  other: { label: 'Khác (hàng đợi, trả lời rỗng)', tone: 'warning', icon: '…' },
};

/** Dải 100% theo màu trạng thái, luôn kèm ký hiệu và chữ chứ không chỉ dựa vào màu. */
export function OutcomeStrip({ outcomes, total }: { outcomes: { key: OutcomeKey; count: number }[]; total: number }) {
  return <div className="adm-outcomes">
    <div className="adm-strip" aria-hidden="true">
      {outcomes.filter(item => item.count > 0).map(item => <span key={item.key} className={`tone-${OUTCOMES[item.key].tone}`} style={{ flexGrow: item.count }} />)}
    </div>
    <ul>
      {outcomes.map(item => <li key={item.key}>
        <span className={`adm-tone tone-${OUTCOMES[item.key].tone}`} aria-hidden="true">{OUTCOMES[item.key].icon}</span>
        <span>{OUTCOMES[item.key].label}</span>
        <b>{item.count.toLocaleString('vi-VN')}</b>
        <small>{total ? `${(item.count / total * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%` : '—'}</small>
      </li>)}
    </ul>
  </div>;
}

/** p50 → p95 của từng model trên cùng một trục giây. */
export function LatencyRanges({ models, field }: { models: AdminModel[]; field: 'total' | 'first' }) {
  const value = (row: AdminModel) => field === 'total' ? [row.p50_ms, row.p95_ms] : [row.first_p50_ms, row.first_p95_ms];
  const rows = models.filter(row => value(row)[0] !== null && value(row)[1] !== null);
  if (!rows.length) return <p className="adm-empty">Chưa có dữ liệu</p>;
  const peak = Math.max(...rows.map(row => value(row)[1]!)) / 1000;
  const max = niceStep(Math.max(peak, 1) / 2) * 2 * 1000;
  return <div className="adm-latency" role="table" aria-label={field === 'total' ? 'Thời gian trả lời xong' : 'Thời gian tới chữ đầu'}>
    {rows.map(row => {
      const [p50, p95] = value(row) as [number, number];
      return <div key={row.key} className="adm-latency-row" role="row">
        <span role="cell" className="adm-latency-name">{row.label}</span>
        <span role="cell" className="adm-latency-track" aria-label={`p50 ${secs(p50)}, p95 ${secs(p95)}`}>
          <i className="range" style={{ left: `${p50 / max * 100}%`, width: `${(p95 - p50) / max * 100}%`, background: SERVICE_COLOR[row.service] }} />
          <i className="dot p50" style={{ left: `${p50 / max * 100}%`, background: SERVICE_COLOR[row.service] }} />
          <i className="dot p95" style={{ left: `${p95 / max * 100}%`, borderColor: SERVICE_COLOR[row.service] }} />
        </span>
        <span role="cell" className="adm-latency-values"><b>{secs(p50)}</b> · {secs(p95)}</span>
      </div>;
    })}
    <div className="adm-latency-axis" aria-hidden="true"><span>0</span><span>{secs(max / 2)}</span><span>{secs(max)}</span></div>
  </div>;
}
