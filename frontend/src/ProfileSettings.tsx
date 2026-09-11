import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react';
import { UnauthorizedError, getProfile, saveProfile, type Profile, type ProfileData } from './api';

const EMPTY: Profile = { full_name: '', nickname: '', occupation: '', instructions: '' };
const FIELDS = Object.keys(EMPTY) as (keyof Profile)[];

/**
 * Mục Hồ sơ trong Cài đặt: tên, cách Peto gọi, công việc và hướng dẫn riêng.
 * Máy chủ ghép hồ sơ vào prompt ở mỗi lượt chat, nên lưu xong là tin nhắn kế
 * tiếp đã theo.
 *
 * Nhãn gắn với ô nhập bằng htmlFor chứ không bọc ô nhập: mọi <label> trong app
 * đang user-select: none, và iOS Safari có lỗi khiến ô nhập nằm trong phần tử
 * như vậy không gõ hay bôi chọn được chữ.
 */
export default function ProfileSettings({ open, avatar, onUnauthorized, onSaved }: {
  open: boolean;
  avatar: ReactNode;
  onUnauthorized: () => void;
  /** Báo bản vừa lưu lên App, để lời chào ở màn hình trống đổi tên ngay. */
  onSaved?: (profile: Profile) => void;
}) {
  const [data, setData] = useState<ProfileData | null>(null);
  const [form, setForm] = useState<Profile>(EMPTY);
  const [saved, setSaved] = useState<Profile>(EMPTY);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const loadVersion = useRef(0);
  const savedTimer = useRef<number | undefined>(undefined);
  const dirty = FIELDS.some((field) => form[field] !== saved[field]);
  const dirtyRef = useRef(dirty);

  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  useEffect(() => () => window.clearTimeout(savedTimer.current), []);

  // Mở Cài đặt là tải lại, vì hồ sơ có thể vừa được sửa ở máy khác. Riêng khi
  // còn thay đổi chưa lưu thì giữ nguyên, để đóng rồi mở lại không mất chữ.
  useEffect(() => {
    if (!open || dirtyRef.current) return;
    const version = ++loadVersion.current;
    setLoadFailed(false);
    getProfile()
      .then((result) => {
        if (version !== loadVersion.current) return;
        setData(result);
        setForm(result.profile);
        setSaved(result.profile);
      })
      .catch((err: unknown) => {
        if (version !== loadVersion.current) return;
        if (err instanceof UnauthorizedError) { onUnauthorized(); return; }
        setLoadFailed(true);
      });
    return () => { loadVersion.current += 1; };
  }, [open, reloadKey, onUnauthorized]);

  function update(field: keyof Profile) {
    return (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const value = event.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
      setJustSaved(false);
      setError(null);
    };
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!dirty || saving) return;
    setSaving(true);
    setError(null);
    try {
      // Máy chủ trả về bản đã chuẩn hóa (gộp khoảng trắng, bỏ ký tự lạ); hiện
      // đúng bản đó để người dùng thấy chính xác thứ Peto sẽ đọc.
      const next = await saveProfile(form);
      setForm(next);
      setSaved(next);
      onSaved?.(next);
      setJustSaved(true);
      window.clearTimeout(savedTimer.current);
      savedTimer.current = window.setTimeout(() => setJustSaved(false), 2500);
    } catch (err) {
      if (err instanceof UnauthorizedError) { onUnauthorized(); return; }
      setError(err instanceof Error ? err.message : 'Chưa lưu được. Thử lại nhé.');
    } finally {
      setSaving(false);
    }
  }

  const limits = data?.limits ?? { full_name: 80, nickname: 40, instructions: 1500 };

  return <section className="settings-section profile-section" aria-labelledby="profile-title">
    <h3 id="profile-title">Hồ sơ</h3>
    <p className="settings-hint">
      Peto dựa vào đây để hiểu và xưng hô với bạn trong mọi cuộc trò chuyện. Chỉ dùng cho Peto trên web này.
    </p>
    {loadFailed ? (
      <div className="profile-load-error" role="alert">
        <span>Chưa tải được hồ sơ.</span>
        <button type="button" onClick={() => setReloadKey((key) => key + 1)}>Thử lại</button>
      </div>
    ) : !data ? (
      <p className="settings-hint" role="status">Đang tải hồ sơ…</p>
    ) : (
      <form className="profile-form" onSubmit={(event) => void save(event)}>
        <div className="profile-row">
          <span className="profile-label">Ảnh đại diện</span>
          {avatar}
        </div>
        <div className="profile-row">
          <label className="profile-label" htmlFor="profile-full-name">Họ và tên</label>
          <input id="profile-full-name" value={form.full_name} maxLength={limits.full_name}
            autoComplete="name" onChange={update('full_name')} />
        </div>
        <div className="profile-row">
          <label className="profile-label" htmlFor="profile-nickname">Peto nên gọi bạn là gì?</label>
          <input id="profile-nickname" value={form.nickname} maxLength={limits.nickname}
            autoComplete="nickname" onChange={update('nickname')} />
        </div>
        <div className="profile-row">
          <label className="profile-label" htmlFor="profile-occupation">Công việc của bạn</label>
          <select id="profile-occupation" value={form.occupation} onChange={update('occupation')}>
            <option value="">Chọn</option>
            {data.occupations.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </div>
        <div className="profile-notes">
          <label className="profile-label" htmlFor="profile-instructions">Hướng dẫn cho Peto</label>
          <p className="settings-hint" id="profile-instructions-hint">
            Peto sẽ nhớ những điều này trong mọi cuộc trò chuyện của bạn, nhưng không vì thế mà bỏ các quy tắc an toàn của mình.
          </p>
          <textarea id="profile-instructions" rows={4} value={form.instructions}
            maxLength={limits.instructions} aria-describedby="profile-instructions-hint"
            placeholder="Ví dụ: giải thích ngắn gọn, đi thẳng vào vấn đề" onChange={update('instructions')} />
          <span className="profile-count">{form.instructions.length}/{limits.instructions}</span>
        </div>
        <div className="profile-actions">
          <span className={error ? 'profile-status error' : 'profile-status'} role={error ? 'alert' : 'status'}>
            {error ?? (justSaved ? 'Đã lưu' : '')}
          </span>
          <button type="submit" className="profile-save" disabled={!dirty || saving}>
            {saving ? 'Đang lưu…' : 'Lưu thay đổi'}
          </button>
        </div>
      </form>
    )}
  </section>;
}
