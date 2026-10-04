import { useEffect, useRef, useState } from 'react';
import { UnauthorizedError } from '../../shared/api/api';
import { LoadingIndicator } from '../../shared/ui/LoadingIndicator';
import { GitHubIcon } from '../../shared/ui/GitHubIcon';
import { SettingsIcon } from '../settings/settingsUi';
import { checkGitHub, connectGitHub, disconnectGitHub, listConnectors, type Connector } from './connectorApi';
import './connectors.css';

const RESULTS: Record<string, string> = {
  connected: 'Đã kết nối GitHub. Bạn có thể nhờ Peto đọc repo và kiểm tra GitHub Actions trong chat.',
  cancelled: 'Bạn đã hủy cấp quyền GitHub. Kết nối trước đó, nếu có, vẫn được giữ.',
  invalid: 'Phiên cấp quyền không còn hợp lệ. Hãy bấm Kết nối để bắt đầu lại.',
  failed: 'Chưa kết nối được GitHub. Hãy thử lại.',
};

export default function ConnectorSettings({ open, result, onUnauthorized }: {
  open: boolean; result: string | null; onUnauthorized: () => void;
}) {
  const [items, setItems] = useState<Connector[]>([]);
  const [tab, setTab] = useState<'yours' | 'discover'>('yours');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(result ? RESULTS[result] : '');
  const [confirm, setConfirm] = useState(false);
  const [revision, setRevision] = useState(0);
  const alive = useRef(true);
  const operation = useRef<AbortController | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; operation.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    void listConnectors(controller.signal).then(data => {
      if (!controller.signal.aborted) setItems(data.connectors);
    }).catch(err => {
      if (controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError('Chưa tải được danh sách kết nối. Hãy thử lại.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, revision, onUnauthorized]);

  async function run(action: 'connect' | 'check' | 'disconnect') {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(action); setError(''); setNotice('');
    try {
      if (action === 'connect') {
        const { authorize_url } = await connectGitHub(controller.signal);
        if (alive.current && !controller.signal.aborted) window.location.assign(authorize_url);
      } else if (action === 'check') {
        const updated = await checkGitHub(controller.signal);
        if (alive.current && !controller.signal.aborted) {
          setItems([updated]); setNotice('Kết nối GitHub đang hoạt động.');
        }
      } else {
        await disconnectGitHub(controller.signal);
        if (alive.current && !controller.signal.aborted) {
          setConfirm(false); setSelected(false); setRevision(value => value + 1);
          setNotice('Đã ngắt kết nối khỏi Peto. Bạn có thể gỡ quyền của ứng dụng trong cài đặt GitHub.');
        }
      }
    } catch (err) {
      if (!alive.current || controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa xử lý được kết nối. Hãy thử lại.');
    } finally {
      operation.current = null;
      if (alive.current) setBusy('');
    }
  }

  const github = items.find(item => item.id === 'github');
  const visible = items.filter(item => (item.name + ' ' + (item.login ?? '')).toLowerCase().includes(query.toLowerCase().trim())
    && (tab === 'discover' || item.status !== 'not_connected')
    && (filter === 'all' || (filter === 'connected' ? item.status === 'connected' : item.status !== 'connected')));
  return <div className="connectors-settings">
    <p className="connectors-intro">Kết nối ứng dụng để Peto đọc dữ liệu và giúp bạn làm việc ngay trong chat.</p>
    <div className="connectors-toolbar">
      <div className="connectors-tabs" role="tablist" aria-label="Danh sách kết nối" onKeyDown={event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 'yours' : event.key === 'End' ? 'discover' : tab === 'yours' ? 'discover' : 'yours';
        setTab(next); setSelected(false);
        event.currentTarget.querySelector<HTMLButtonElement>(`#connectors-${next}`)?.focus();
      }}>
        <button type="button" role="tab" id="connectors-yours" tabIndex={tab === 'yours' ? 0 : -1} aria-selected={tab === 'yours'} aria-controls="connectors-list" onClick={() => { setTab('yours'); setSelected(false); }}>Đã kết nối</button>
        <button type="button" role="tab" id="connectors-discover" tabIndex={tab === 'discover' ? 0 : -1} aria-selected={tab === 'discover'} aria-controls="connectors-list" onClick={() => { setTab('discover'); setSelected(false); }}>Khám phá</button>
      </div>
      <input type="search" aria-label="Tìm kết nối" placeholder="Tìm kết nối" value={query} onChange={event => setQuery(event.target.value)} />
      <select aria-label="Lọc trạng thái kết nối" value={filter} onChange={event => setFilter(event.target.value)}>
        <option value="all">Tất cả trạng thái</option><option value="connected">Đang hoạt động</option><option value="disconnected">Chưa kết nối / cần kết nối lại</option>
      </select>
    </div>
    {notice && <p className="connectors-notice" role="status">{notice}</p>}
    {error && <div className="connectors-error" role="alert"><p>{error}</p>{!busy && <button type="button" className="settings-button" onClick={() => setRevision(value => value + 1)}>Tải lại danh sách</button>}</div>}
    <div id="connectors-list" role="tabpanel" aria-labelledby={tab === 'yours' ? 'connectors-yours' : 'connectors-discover'}>
      {loading ? <div className="settings-loading"><LoadingIndicator label="Đang tải kết nối" /></div> : <>
        {visible.map(item => <div className="connector-card" key={item.id}>
          <button type="button" className="connector-details-button" onClick={() => { setSelected(true); setConfirm(false); }} aria-label="Chi tiết kết nối GitHub">
            <span className="connector-logo"><GitHubIcon size={24} /></span>
            <span className="connector-description"><strong>GitHub</strong><span>Đọc repo, tệp và log GitHub Actions.</span>{item.login && <small>@{item.login}</small>}</span>
          </button>
          <span className={`connector-status ${item.status}`}>
            {item.status === 'connected' ? 'Đã kết nối' : item.status === 'reconnect' ? 'Cần kết nối lại' : 'Chưa kết nối'}
          </span>
          <button type="button" className="settings-button" disabled={!!busy || !item.configured} onClick={() => item.status === 'connected' ? setSelected(true) : void run('connect')}>
            {busy === 'connect' ? 'Đang kết nối…' : item.status === 'connected' ? 'Quản lý' : item.status === 'reconnect' ? 'Kết nối lại' : 'Kết nối'}
          </button>
        </div>)}
        {!visible.length && !error && <div className="connectors-empty"><SettingsIcon name="connectors" size={30} />
          <p>{query || filter !== 'all' ? 'Không có kết nối phù hợp.' : tab === 'yours' ? 'Bạn chưa kết nối ứng dụng nào.' : 'Chưa có ứng dụng để kết nối.'}</p>
          {tab === 'yours' && !query && filter === 'all' && <button type="button" className="settings-button" onClick={() => setTab('discover')}>Khám phá kết nối</button>}
        </div>}
        {github && !github.configured && <p className="connectors-note">Kết nối GitHub chưa được quản trị viên bật trên máy chủ.</p>}
      </>}
    </div>
    {selected && github && <div className="connector-detail" aria-label="Quản lý kết nối GitHub">
      <div className="connector-detail-head"><h3>GitHub</h3><button type="button" className="settings-button" onClick={() => { setSelected(false); setConfirm(false); }}>Đóng chi tiết</button></div>
      <p>Peto chỉ đọc dữ liệu. Kết nối này không sửa tệp, tạo bình luận hay chạy lại workflow.</p>
      <p>Chọn repo được phép truy cập trên GitHub. Nếu repo chưa xuất hiện, cấp quyền cho repo rồi thử lại trong chat.</p>
      <div className="connector-actions">
        {github.install_url && <a className="settings-button settings-link" href={github.install_url} target="_blank" rel="noopener noreferrer">Quản lý repo <SettingsIcon name="external" size={14} /></a>}
        {github.status !== 'not_connected' && <button type="button" className="settings-button" disabled={!!busy} onClick={() => void run('check')}>{busy === 'check' ? 'Đang kiểm tra…' : 'Kiểm tra kết nối'}</button>}
        <button type="button" className="settings-button" disabled={!!busy || !github.configured} onClick={() => void run('connect')}>{github.status === 'not_connected' ? 'Kết nối' : 'Kết nối lại'}</button>
        {github.status !== 'not_connected' && <button type="button" className="settings-button danger" disabled={!!busy} onClick={() => setConfirm(true)}>Ngắt kết nối</button>}
      </div>
      {confirm && <div className="connector-confirm"><p>Ngắt kết nối GitHub khỏi Peto? Nội dung đã có trong chat vẫn được giữ.</p><div className="connector-actions">
        <button type="button" className="settings-button" disabled={!!busy} onClick={() => setConfirm(false)}>Giữ kết nối</button>
        <button type="button" className="settings-button danger" disabled={!!busy} onClick={() => void run('disconnect')}>{busy === 'disconnect' ? 'Đang ngắt…' : 'Xác nhận ngắt kết nối'}</button>
      </div></div>}
      <p className="connectors-note">Sau khi kết nối, thử hỏi: “Kiểm tra lần chạy GitHub Actions mới nhất của owner/repo và giải thích lỗi.”</p>
    </div>}
  </div>;
}
