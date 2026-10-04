import type { ReactNode } from 'react';
import type { SheetChartData } from './documentApi';

// Cùng bảng màu với tệp Excel (backend sheets/view.py); chuỗi đầu tiên theo màu nhấn của giao diện.
const SERIES = ['var(--sheet-accent)', '#E09F3E', '#4F86C6', '#9A6FB0'];
const PIE: [string, string][] = [['#0F766E', '#fff'], ['#2A9D8F', '#fff'], ['#5FA8A0', '#fff'], ['#9CC9C2', '#1F2D33'], ['#C9D3DA', '#1F2D33'],
  ['#E09F3E', '#1F2D33'], ['#F2C14E', '#1F2D33'], ['#4F86C6', '#fff'], ['#9A6FB0', '#fff'], ['#D1495B', '#fff']];
const TEXT = 'var(--sheet-chart-text)';
const GRID = 'var(--sheet-chart-grid)';

/** Cắt nhãn cho vừa bề rộng (ước lượng 0,56 em mỗi ký tự). */
function fit(text: string, width: number, size = 12) {
  const room = Math.max(1, Math.floor(width / (size * 0.56)));
  return text.length > room ? text.slice(0, Math.max(1, room - 1)) + '…' : text;
}
const textWidth = (text: string, size = 12) => text.length * size * 0.56;

function Legend({ chart, y }: { chart: SheetChartData; y: number }) {
  const items = chart.series.map(series => ({ name: fit(series.name, 120), width: 16 + textWidth(fit(series.name, 120)) }));
  const total = items.reduce((sum, item) => sum + item.width, 0) + 16 * (items.length - 1);
  let x = (chart.width - total) / 2;
  return <g>{items.map((item, index) => {
    const at = x;
    x += item.width + 16;
    return <g key={index}><rect x={at} y={y - 9} width={10} height={10} rx={2} fill={SERIES[index % SERIES.length]} />
      <text x={at + 15} y={y} fontSize={12} fill={TEXT}>{item.name}</text></g>;
  })}</g>;
}

function AxisChart({ chart }: { chart: SheetChartData }) {
  const axis = chart.axis!;
  const { width: W, height: H } = chart;
  const legend = chart.series.length > 1;
  const span = axis.max - axis.min || 1;
  const ticks = axis.labels.map((label, index) => ({ label, value: axis.min + axis.step * index }));
  const count = Math.max(1, chart.categories.length);
  const single = chart.series.length === 1;
  const shapes: ReactNode[] = [];
  if (chart.type === 'bar') {
    const labelWidth = Math.min(W * 0.36, Math.max(...chart.categories.map(item => textWidth(item))) + 12);
    const left = 14 + labelWidth, right = W - (single ? 54 : 22), top = 46, bottom = H - (legend ? 44 : 22) - 18;
    const x = (value: number) => left + (value - axis.min) / span * (right - left);
    ticks.forEach((tick, index) => shapes.push(<g key={`t${index}`}><line x1={x(tick.value)} x2={x(tick.value)} y1={top} y2={bottom} stroke={GRID} />
      <text x={x(tick.value)} y={bottom + 15} fontSize={11.5} fill={TEXT} textAnchor="middle">{tick.label}</text></g>));
    const group = (bottom - top) / count;
    const bar = group * 0.62 / chart.series.length;
    const zero = x(Math.min(Math.max(0, axis.min), axis.max));
    chart.categories.forEach((category, index) => {
      // Excel xếp nhãn đầu tiên ở dưới cùng của biểu đồ thanh ngang.
      const base = bottom - group * (index + 1) + group * 0.19;
      shapes.push(<text key={`c${index}`} x={left - 8} y={bottom - group * (index + 0.5) + 4} fontSize={12} fill={TEXT} textAnchor="end">{fit(category, labelWidth - 8)}</text>);
      chart.series.forEach((series, number) => {
        const value = series.values[index];
        if (value == null) return;
        const y = base + bar * number;
        const end = x(value);
        shapes.push(<rect key={`b${index}-${number}`} x={Math.min(zero, end)} y={y} width={Math.abs(end - zero)} height={bar} fill={SERIES[number % SERIES.length]} />);
        if (single) shapes.push(<text key={`l${index}`} x={Math.max(zero, end) + 5} y={y + bar / 2 + 4} fontSize={11.5} fill={TEXT}>{series.labels[index]}</text>);
      });
    });
    shapes.push(<line key="axis" x1={zero} x2={zero} y1={top} y2={bottom} stroke={GRID} />);
  } else {
    const labelWidth = Math.max(...ticks.map(tick => textWidth(tick.label, 11.5))) + 12;
    const left = 10 + labelWidth, right = W - 16, top = 46, bottom = H - (legend ? 44 : 22) - 18;
    const y = (value: number) => bottom - (value - axis.min) / span * (bottom - top);
    ticks.forEach((tick, index) => shapes.push(<g key={`t${index}`}><line x1={left} x2={right} y1={y(tick.value)} y2={y(tick.value)} stroke={GRID} />
      <text x={left - 7} y={y(tick.value) + 4} fontSize={11.5} fill={TEXT} textAnchor="end">{tick.label}</text></g>));
    const group = (right - left) / count;
    chart.categories.forEach((category, index) => shapes.push(<text key={`c${index}`} x={left + group * (index + 0.5)} y={bottom + 16} fontSize={12} fill={TEXT} textAnchor="middle">{fit(category, group - 4)}</text>));
    if (chart.type === 'column') {
      const bar = group * 0.62 / chart.series.length;
      const zero = y(Math.min(Math.max(0, axis.min), axis.max));
      chart.series.forEach((series, number) => series.values.forEach((value, index) => {
        if (value == null) return;
        const x = left + group * index + group * 0.19 + bar * number;
        const top = y(value);
        shapes.push(<rect key={`b${index}-${number}`} x={x} y={Math.min(zero, top)} width={bar} height={Math.abs(zero - top)} fill={SERIES[number % SERIES.length]} />);
        if (single) shapes.push(<text key={`l${index}`} x={x + bar / 2} y={value >= 0 ? top - 6 : top + 14} fontSize={11.5} fill={TEXT} textAnchor="middle" fontWeight={600}>{series.labels[index]}</text>);
      }));
    } else {
      chart.series.forEach((series, number) => {
        const color = SERIES[number % SERIES.length];
        const points = series.values.map((value, index) => value == null ? null : [left + group * (index + 0.5), y(value)] as const);
        let path = '';
        points.forEach((point, index) => { if (point) path += `${index && points[index - 1] ? 'L' : 'M'}${point[0].toFixed(1)} ${point[1].toFixed(1)}`; });
        shapes.push(<path key={`p${number}`} d={path} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" />);
        points.forEach((point, index) => { if (point) shapes.push(<circle key={`d${number}-${index}`} cx={point[0]} cy={point[1]} r={3.5} fill={color} />); });
      });
    }
  }
  return <>{shapes}{legend && <Legend chart={chart} y={H - 14} />}</>;
}

function PieChart({ chart }: { chart: SheetChartData }) {
  const { width: W, height: H } = chart;
  const values = chart.series[0].values.map(value => Math.max(0, value ?? 0));
  const total = values.reduce((sum, value) => sum + value, 0) || 1;
  const legendWidth = Math.min(W * 0.4, Math.max(...chart.categories.map(item => textWidth(item))) + 26);
  const radius = Math.min((W - legendWidth - 40) / 2, (H - 60) / 2);
  const cx = (W - legendWidth) / 2 + 4, cy = 40 + (H - 40) / 2;
  let angle = -Math.PI / 2;
  const slices: ReactNode[] = [];
  values.forEach((value, index) => {
    const [fill, ink] = PIE[index % PIE.length];
    const sweep = value / total * Math.PI * 2;
    if (sweep <= 0) return;
    const end = angle + sweep;
    const point = (at: number) => `${(cx + radius * Math.cos(at)).toFixed(2)} ${(cy + radius * Math.sin(at)).toFixed(2)}`;
    slices.push(sweep >= Math.PI * 2 - 1e-9
      ? <circle key={index} cx={cx} cy={cy} r={radius} fill={fill} />
      : <path key={index} d={`M${cx} ${cy}L${point(angle)}A${radius} ${radius} 0 ${sweep > Math.PI ? 1 : 0} 1 ${point(end)}Z`} fill={fill} stroke="var(--sheet-bg)" strokeWidth={1.5} />);
    if (value / total >= 0.04) {
      const middle = angle + sweep / 2;
      slices.push(<text key={`l${index}`} x={cx + radius * 0.62 * Math.cos(middle)} y={cy + radius * 0.62 * Math.sin(middle) + 4.5} fontSize={12.5} fontWeight={700} fill={ink} textAnchor="middle">{Math.round(value / total * 100)}%</text>);
    }
    angle = end;
  });
  const rowHeight = Math.min(24, (H - 60) / Math.max(1, chart.categories.length));
  const startY = cy - rowHeight * chart.categories.length / 2;
  const legendX = W - legendWidth - 6;
  return <>{slices}{chart.categories.map((category, index) => <g key={`g${index}`}>
    <rect x={legendX} y={startY + rowHeight * index + rowHeight / 2 - 6} width={11} height={11} rx={2} fill={PIE[index % PIE.length][0]} />
    <text x={legendX + 17} y={startY + rowHeight * index + rowHeight / 2 + 4} fontSize={12} fill={TEXT}>{fit(category, legendWidth - 20)}</text></g>)}</>;
}

/** Biểu đồ của trang tính, vẽ lại từ cùng số liệu và cùng thang chia với biểu đồ Excel trong tệp. */
export default function SheetChart({ chart }: { chart: SheetChartData }) {
  return <svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={`Biểu đồ: ${chart.title}`}>
    <text x={chart.width / 2} y={27} fontSize={14.5} fontWeight={600} fill="var(--sheet-chart-title)" textAnchor="middle">{fit(chart.title, chart.width - 24, 14.5)}</text>
    {chart.type === 'pie' ? <PieChart chart={chart} /> : chart.axis ? <AxisChart chart={chart} /> : null}
  </svg>;
}
