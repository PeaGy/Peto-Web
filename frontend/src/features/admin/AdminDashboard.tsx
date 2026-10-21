import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { MenuIcon } from '../../app/navigationIcons';
import { UnauthorizedError } from '../../shared/api/api';
import { LoadingIndicator } from '../../shared/ui/LoadingIndicator';
import { Segmented } from '../settings/settingsUi';
import { AdminForbiddenError, getAdminOverview, type AdminModel, type AdminOverview, type AdminRange } from './adminApi';
import { CostColumns, LatencyRanges, OutcomeStrip, SERVICE_COLOR, SERVICES, ServiceLegend, Sparkline } from './AdminCharts';
import { NO_DATA, compact, day, num, pct, secs, surfaces, usd } from './format';
import './admin.css';
import { ChatMetrics } from './ChatMetrics';

const RANGE_KEY = 'peto-admin-range';
const RANGES: { value: AdminRange; label: string }[] = [
  { value: '24h', label: '24 giờ' }, { value: '7d', label: '7 ngày' }, { value: '30d', label: '30 ngày' }, { value: '90d', label: '90 ngày' },
];

function readRange(): AdminRange {
  try {
    const saved = localStorage.getItem(RANGE_KEY);
    return RANGES.some(item => item.value === saved) ? saved as AdminRange : '7d';
  } catch { return '7d'; }
}

function Card({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return <section className="adm-card"><header><h2>{title}</h2>{aside}</header>{children}</section>;
}

function Coverage({ data }: { data: AdminOverview }) {
  if (data.data_since === null) return <span className="adm-coverage">Chưa có dữ liệu. Số liệu bắt đầu ghi từ lần khởi động máy chủ có bản cập nhật này.</span>;
  const unit = data.bucket_unit === 'hour' ? 'giờ' : 'ngày';
  return <span className="adm-coverage">Có dữ liệu từ {day(data.data_since)}
    {data.covered_buckets < data.buckets.length && <> · <strong>mới có {data.covered_buckets}/{data.buckets.length} {unit}</strong></>}
  </span>;
}

function Delta({ now, before }: { now: number | null; before: number | null }) {
  if (now === null || before === null || before <= 0) return <small className="adm-delta none">Chưa đủ dữ liệu để so kỳ trước</small>;
  const change = (now - before) / before;
  // Chi phí tăng là chiều xấu: màu cảnh báo nhẹ, giảm là màu tốt, luôn kèm mũi tên chứ không chỉ màu.
  return <small className={change > 0 ? 'adm-delta up' : 'adm-delta down'}>{change > 0 ? '▲' : '▼'} {pct(Math.abs(change))} so với kỳ trước</small>;
}

function costLabel(data: AdminOverview) {
  if (data.cost.total_usd !== null) return usd(data.cost.total_usd);
  return data.cost.rates === 'invalid' ? 'Tệp giá lỗi' : 'Chưa có đơn giá';
}

function ModelTable({ models }: { models: AdminModel[] }) {
  if (!models.length) return <p className="adm-empty">Chưa có lượt gọi nào trong khoảng này.</p>;
  return <div className="adm-table-wrap"><table className="adm-table" aria-label="Số liệu theo model">
    <thead><tr>
      <th scope="col">Model</th><th scope="col">Lần gọi</th><th scope="col">Thành công</th><th scope="col">p50 · p95</th>
      <th scope="col">Token vào <small>(cache)</small></th><th scope="col">Token ra</th><th scope="col">Chi phí</th>
    </tr></thead>
    <tbody>{models.map(row => <tr key={row.key}>
      <th scope="row"><span className="adm-model">
        <i style={{ background: SERVICE_COLOR[row.service] ?? 'var(--muted)' }} aria-hidden="true" />{row.label}
        {row.surfaces.length > 0 && <small>{surfaces(row.surfaces)}</small>}
      </span></th>
      <td>{num(row.calls)}{row.side_calls > 0 && <small title="Lần gọi phụ: đặt tiêu đề, trí nhớ, tóm tắt"> ({num(row.side_calls)} phụ)</small>}</td>
      <td>{pct(row.success_rate)}</td>
      <td>{secs(row.p50_ms)} · {secs(row.p95_ms)}</td>
      <td className={row.input_tokens === null ? 'adm-missing' : ''}>{row.input_tokens === null ? NO_DATA : <>
        {compact(row.input_tokens)} <small>{row.cached_tokens === null ? '(chưa có dữ liệu)' : `(${compact(row.cached_tokens)})`}</small></>}</td>
      <td className={row.output_tokens === null ? 'adm-missing' : ''}>{row.output_tokens === null ? NO_DATA : compact(row.output_tokens)}</td>
      <td className={row.cost_usd === null ? 'adm-missing' : ''}>
        {row.cost_usd === null ? (row.unpriced_calls ? 'Chưa có đơn giá' : '—') : usd(row.cost_usd)}
        {row.cost_usd !== null && row.unpriced_calls > 0 && <small title="Một số lần gọi thiếu token hoặc đơn giá nên chưa cộng"> *</small>}
      </td>
    </tr>)}</tbody>
  </table></div>;
}

function Caveats({ data }: { data: AdminOverview }) {
  return <div className="adm-caveats">
    <p><strong>Ước tính, không phải hóa đơn.</strong> Tính từ token mỗi lần gọi và tệp giá bạn khai (PETO_COST_RATES_FILE). Đối chiếu với trang thanh toán của từng nhà cung cấp.</p>
    {data.cost.rates === 'missing' && <p>Chưa khai tệp giá nên chưa tính được chi phí. Xem hướng dẫn trong .env.example.</p>}
    {data.cost.rates === 'invalid' && <p>Tệp giá không đọc được hoặc sai định dạng; sửa xong trang tự đọc lại.</p>}
    <p>Chưa tính: {data.cost.not_counted.join(' · ')}. Lượt tra web trong kỳ: <b>{num(data.searches)}</b>.</p>
    {data.cost.rates === 'ok' && data.cost.unpriced_models.length > 0 && <p>Chưa có đơn giá hoặc thiếu token: {data.cost.unpriced_models.join(', ')} (không cộng vào tổng).</p>}
    {data.cost.cache_unknown_models.length > 0 && <p>Nhà cung cấp không báo token cache cho {data.cost.cache_unknown_models.join(', ')}, nên phần đó tính như không có cache (có thể cao hơn thực tế).</p>}
    {data.dropped_events > 0 && <p>Máy chủ đã bỏ {num(data.dropped_events)} sự kiện vì hàng đợi đầy từ lần khởi động gần nhất.</p>}
  </div>;
}

/** Trang /admin: chỉ chủ web. Số liệu không có nội dung chat hay danh tính người dùng. */
export default function AdminDashboard({ onUnauthorized, onForbidden, onOpenSidebar }: {
  onUnauthorized: () => void;
  onForbidden: () => void;
  onOpenSidebar: () => void;
}) {
  const [range, setRange] = useState<AdminRange>(readRange);
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [latency, setLatency] = useState<'total' | 'first'>('total');
  const [reload, setReload] = useState(0);
  const loadVersion = useRef(0);

  useEffect(() => {
    const version = ++loadVersion.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getAdminOverview(range, controller.signal).then(result => {
      if (version === loadVersion.current) setData(result);
    }).catch(err => {
      if (version !== loadVersion.current || controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else if (err instanceof AdminForbiddenError) onForbidden();
      else setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa tải được số liệu. Thử lại nhé.');
    }).finally(() => {
      if (version === loadVersion.current) setLoading(false);
    });
    return () => controller.abort();
  }, [range, reload, onUnauthorized, onForbidden]);

  const choose = useCallback((value: AdminRange) => {
    setRange(value);
    try { localStorage.setItem(RANGE_KEY, value); } catch { /* Không nhớ được khoảng thời gian thì thôi. */ }
  }, []);

  const head = <header className="adm-head">
    <button type="button" className="menu-btn" aria-label="Mở menu" onClick={onOpenSidebar}><MenuIcon /></button>
    <div className="adm-title"><h1>Tổng quan vận hành</h1>{data && <Coverage data={data} />}</div>
    <Segmented label="Khoảng thời gian" value={range} options={RANGES} onChange={choose} />
  </header>;

  if (!data) {
    return <main className="admin"><div className="adm">
      {head}
      {error ? <div className="adm-error" role="alert"><p>{error}</p>
        <button type="button" className="adm-retry" onClick={() => setReload(value => value + 1)}>Thử lại</button></div>
        : loading && <LoadingIndicator variant="panel" label="Đang tải số liệu" />}
    </div></main>;
  }

  const totals = data.buckets.map(bucket => SERVICES.reduce((sum, service) => sum + bucket.cost[service], 0));
  const complete = data.outcomes.find(item => item.key === 'complete')?.count ?? 0;
  return <main className="admin"><div className={loading ? 'adm refreshing' : 'adm'} aria-busy={loading}>
    {head}
    {error && <div className="adm-error inline" role="alert"><p>{error}</p>
      <button type="button" className="adm-retry" onClick={() => setReload(value => value + 1)}>Thử lại</button></div>}
    <div className="adm-tiles">
      <article className="adm-tile"><span>Chi phí ước tính</span>
        <div className="adm-tile-value"><strong className={data.cost.total_usd === null ? 'adm-missing-value' : ''}>{costLabel(data)}</strong>
          {data.cost.total_usd !== null && <Sparkline values={totals} />}</div>
        {data.cost.total_usd !== null && <Delta now={data.cost.total_usd} before={data.cost.previous_total_usd} />}
      </article>
      <article className="adm-tile"><span>Lần gọi AI</span>
        <div className="adm-tile-value"><strong>{num(data.calls)}</strong><Sparkline values={data.buckets.map(bucket => bucket.calls)} /></div>
        <small>{num(data.turns)} lượt chat và Agent{data.accounts !== null && <> · {num(data.accounts)} tài khoản</>}</small>
      </article>
      <article className="adm-tile"><span>Lượt thành công</span>
        <div className="adm-tile-value"><strong>{pct(data.success_rate)}</strong></div>
        <small>{data.turns ? `${num(data.turns - complete)} lượt không trọn vẹn` : 'Chưa có lượt nào'}</small>
      </article>
      <article className="adm-tile"><span>Thời gian trả lời p95</span>
        <div className="adm-tile-value"><strong>{secs(data.latency.p95_ms)}</strong></div>
        <small>p50 {secs(data.latency.p50_ms)} · chữ đầu p50 {secs(data.latency.first_p50_ms)}</small>
      </article>
    </div>
    <Card title="Chi phí ước tính" aside={<ServiceLegend values={data.cost.by_service} />}>
      {data.cost.total_usd === null
        ? <p className="adm-empty">{data.cost.rates === 'ok' ? 'Chưa có lần gọi nào có đủ token và đơn giá trong khoảng này.' : 'Chưa tính được chi phí vì chưa có tệp giá dùng được.'}</p>
        : <CostColumns buckets={data.buckets} unpriced={SERVICES.filter(service => data.cost.by_service?.[service] === null)} />}
    </Card>
    <div className="adm-split">
      <Card title="Kết quả các lượt">
        {data.turns ? <OutcomeStrip outcomes={data.outcomes} total={data.turns} /> : <p className="adm-empty">{NO_DATA}</p>}
      </Card>
      <Card title="Thời gian (p50 · p95)" aside={<Segmented label="Đo tới" value={latency}
        options={[{ value: 'total', label: 'Xong' }, { value: 'first', label: 'Chữ đầu' }]} onChange={setLatency} />}>
        <LatencyRanges models={data.models} field={latency} />
      </Card>
    </div>
    <Card title="Theo model"><ModelTable models={data.models} /></Card>
    <ChatMetrics data={data.chat} />
    <Caveats data={data} />
  </div></main>;
}
