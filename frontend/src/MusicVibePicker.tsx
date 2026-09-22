import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { musicSupported, resetBeatParameters, setBeatParameters, setMusicStrength, startMusicVibe, stopMusicVibe, useMusicVibe } from './musicVibe';

export function BeatIndicator({ beats, lastBeat }: { beats: number; lastBeat: number }) {
  const [lit, setLit] = useState(false);
  useEffect(() => {
    const remaining = 160 - (performance.now() - lastBeat);
    setLit(beats > 0 && remaining > 0);
    if (remaining <= 0 || !beats) return;
    const timer = window.setTimeout(() => setLit(false), remaining);
    return () => window.clearTimeout(timer);
  }, [beats, lastBeat]);
  return <div className="beat-sync-pulse" aria-hidden="true"><span key={beats}
    data-lit={lit} className={beats ? 'beat-sync-ring' : ''} /></div>;
}

function BeatSyncPanel({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const state = useMusicVibe();
  const supported = musicSupported();
  const parameters = state.parameters;
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close(); }, []);
  return createPortal(<dialog ref={dialog} className="beat-sync-dialog" aria-labelledby="beat-sync-title"
    onCancel={event => { event.preventDefault(); event.stopPropagation(); onClose(); }}>
    <header className="character-picker-head"><div><h2 id="beat-sync-title">Beat Sync</h2><p>Cho nhân vật nhún theo nhạc</p></div>
      <button type="button" className="dialog-close" aria-label="Đóng Beat Sync" onClick={onClose}>×</button></header>
    <div className="beat-sync-layout">
      <div className="beat-sync-controls">
        <h3>Nguồn âm thanh</h3>
        <p>Chọn tab đang phát nhạc và bật “Chia sẻ âm thanh” trong cửa sổ trình duyệt.</p>
        <div className="music-vibe-actions">
          <button type="button" className="settings-button" disabled={!supported || state.status === 'starting'} onClick={() => void startMusicVibe()}>
            {state.status === 'active' ? 'Đổi nguồn âm thanh' : 'Chọn nguồn âm thanh'}</button>
          {state.status !== 'off' && <button type="button" className="settings-button" onClick={stopMusicVibe}>Dừng chia sẻ</button>}
        </div>
        <p role="status">{!supported ? 'Thiết bị hoặc trình duyệt này chưa hỗ trợ chia sẻ âm thanh và phân tích nhịp.' : state.message || 'Đang tắt.'}</p>
        <label className="music-vibe-strength">Độ nhạy bắt nhịp · {parameters.sensitivity.toFixed(2)}
          <input aria-label="Độ nhạy bắt nhịp" type="range" min="0" max="1" step="0.01" value={parameters.sensitivity}
            onChange={event => setBeatParameters({ sensitivity: Number(event.target.value) })} /></label>
        <label className="music-vibe-strength">Độ mạnh chuyển động · {Math.round(state.strength * 100)}%
          <input aria-label="Độ mạnh nhún theo nhạc" type="range" min="0" max="100" step="5" value={state.strength * 100}
            onChange={event => setMusicStrength(Number(event.target.value) / 100)} /></label>
        <details className="beat-sync-advanced"><summary>Điều chỉnh nâng cao</summary>
          {([
            ['minBeatInterval', 'Khoảng cách tối thiểu giữa nhịp', 0.1, 1, 0.05, 's'],
            ['lowpassFilterFrequency', 'Giảm âm cao trên', 50, 600, 10, 'Hz'],
            ['highpassFilterFrequency', 'Giảm âm trầm dưới', 10, 150, 5, 'Hz'],
            ['envelopeFilterFrequency', 'Độ mượt tín hiệu', 1, 40, 1, 'Hz'],
            ['bufferDuration', 'Thời gian phân tích', 2, 10, 0.5, 's'],
          ] as const).map(([key, title, min, max, step, unit]) => <label key={key} className="music-vibe-strength">{title} · {parameters[key]} {unit}
            <input type="range" aria-label={title} min={min} max={max} step={step} value={parameters[key]}
              onChange={event => setBeatParameters({ [key]: Number(event.target.value) })} /></label>)}
          {([
            ['warmup', 'Chờ đủ dữ liệu trước khi bắt nhịp'],
            ['adaptiveThreshold', 'Tự điều chỉnh ngưỡng theo âm thanh'],
            ['spectralFlux', 'Phát hiện thay đổi phổ âm thanh'],
          ] as const).map(([key, title]) => <label className="character-effect-option" key={key}><span>{title}</span>
            <input type="checkbox" checked={parameters[key]} onChange={event => setBeatParameters({ [key]: event.target.checked })} /></label>)}
        </details>
        <button type="button" className="settings-button" onClick={() => { resetBeatParameters(); setMusicStrength(0.5); }}>Khôi phục mặc định</button>
      </div>
      <section className="beat-sync-monitor" aria-label="Theo dõi tín hiệu">
        <h3>Âm thanh đầu vào</h3>
        <div className="beat-sync-spectrum" aria-label="Phổ âm thanh">
          {Array.from({ length: 40 }, (_, i) => <span key={i} style={{ height: `${Math.max(2, (state.spectrum[i] || 0) * 100)}%` }} />)}
        </div>
        <label>Mức âm thanh <meter aria-label="Mức âm thanh đầu vào" min="0" max="1" value={state.level} /></label>
        <BeatIndicator beats={state.beats} lastBeat={state.lastBeat} />
        <p className="beat-sync-count">Đã nhận <strong>{state.beats}</strong> nhịp</p>
        <p>Biểu đồ chuyển động: có âm thanh. Vòng tròn nháy: đã bắt nhịp. Nếu có nhịp nhưng nhân vật đứng yên, kiểm tra cài đặt giảm chuyển động và tham số góc đầu của model.</p>
      </section>
    </div>
    <footer className="beat-sync-footer">Âm thanh được phân tích trên thiết bị, không gửi lên máy chủ. Peto không dùng hình ảnh chia sẻ. Đóng bảng này vẫn tiếp tục nhún; rời Companion hoặc đổi model sẽ dừng chia sẻ.
      <a href="/vendor/beat-sync/NOTICE.txt" target="_blank" rel="noopener noreferrer">Nguồn và giấy phép</a></footer>
  </dialog>, document.body);
}

export default function MusicVibePicker() {
  const [open, setOpen] = useState(false);
  return <section className="music-vibe-picker" aria-label="Nhún theo nhạc">
    <h3>Nhún theo nhạc</h3><p>Chọn nguồn nhạc, xem tín hiệu và chỉnh độ nhạy trong Beat Sync.</p>
    <button type="button" className="settings-button" onClick={() => setOpen(true)}>Mở Beat Sync</button>
    {open && <BeatSyncPanel onClose={() => setOpen(false)} />}
  </section>;
}
