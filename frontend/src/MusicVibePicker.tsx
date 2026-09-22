import { musicSupported, setMusicStrength, startMusicVibe, stopMusicVibe, useMusicVibe } from './musicVibe';

export default function MusicVibePicker() {
  const state = useMusicVibe();
  const supported = musicSupported();
  return <section className="music-vibe-picker" aria-label="Nhún theo nhạc">
    <h3>Nhún theo nhạc</h3>
    <p>Chọn tab đang phát nhạc và bật chia sẻ âm thanh trong cửa sổ trình duyệt.</p>
    <div className="music-vibe-actions">
      <button type="button" className="settings-button" disabled={!supported || state.status === 'starting'} onClick={() => void startMusicVibe()}>
        {state.status === 'active' ? 'Đổi nguồn âm thanh' : 'Chọn nguồn âm thanh'}
      </button>
      {state.status !== 'off' && <button type="button" className="settings-button" onClick={stopMusicVibe}>Tắt nhún theo nhạc</button>}
    </div>
    <label className="music-vibe-strength">Độ mạnh · {Math.round(state.strength * 100)}%
      <input aria-label="Độ mạnh nhún theo nhạc" type="range" min="0" max="100" step="5" value={state.strength * 100}
        onChange={event => setMusicStrength(Number(event.target.value) / 100)} />
    </label>
    <p role="status">{!supported ? 'Thiết bị hoặc trình duyệt này chưa hỗ trợ chia sẻ âm thanh.' : state.message || 'Đang tắt.'}</p>
    <p>Âm thanh được phân tích trên thiết bị, không gửi lên máy chủ. Peto không sử dụng hình ảnh từ nguồn chia sẻ. Rời Companion hoặc đổi model sẽ dừng chia sẻ.</p>
  </section>;
}
