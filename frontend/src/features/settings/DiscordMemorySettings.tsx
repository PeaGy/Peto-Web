import { useEffect, useId, useRef, useState } from 'react';
import { getDiscordMemorySettings, setDiscordMemorySettings, UnauthorizedError, type DiscordMemorySettings as State } from '../../shared/api/api';
import { SettingsRow, SettingsSwitch } from './settingsUi';

/** Mounted only for a Discord account; the authenticated server decides whose preference is read/written. */
export default function DiscordMemorySettings({ open, onUnauthorized }: { open: boolean; onUnauthorized: () => void }) {
  const id = useId();
  const [state, setState] = useState<State | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const version = useRef(0);
  const mounted = useRef(true);
  const pending = useRef<Promise<State> | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const ticket = ++version.current;
    setLoading(true); setError('');
    void (async () => {
      try {
        // Reopening during a save must read the committed preference, not race that write.
        await pending.current?.catch(() => undefined);
        if (controller.signal.aborted) return;
        const result = await getDiscordMemorySettings(controller.signal);
        if (!controller.signal.aborted && ticket === version.current) setState(result);
      } catch (err) {
        if (controller.signal.aborted || ticket !== version.current) return;
        if (err instanceof UnauthorizedError) onUnauthorized();
        else { setState(null); setError('Chưa tải được lựa chọn.'); }
      } finally { if (!controller.signal.aborted && ticket === version.current) setLoading(false); }
    })();
    return () => { controller.abort(); version.current++; };
  }, [open, reload, onUnauthorized]);

  async function toggle(enabled: boolean) {
    if (!state || loading || pending.current) return;
    const previous = state, ticket = version.current;
    setState({ ...state, enabled }); setSaving(true); setError('');
    const request = setDiscordMemorySettings(enabled);
    pending.current = request;
    try {
      const result = await request;
      if (mounted.current && ticket === version.current) setState(result);
    } catch (err) {
      if (!mounted.current || ticket !== version.current) return;
      setState(previous);
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError('Chưa lưu được lựa chọn. Bạn thử lại nhé.');
    } finally {
      if (pending.current === request) pending.current = null;
      if (mounted.current) setSaving(false);
    }
  }

  return <>
    <SettingsRow label="Trí nhớ từ bot Discord" htmlFor={id}
      desc={loading ? 'Đang tải lựa chọn…' : state && !state.available
        ? 'Kết nối trí nhớ Discord chưa được cấu hình. Lựa chọn của bạn vẫn được lưu.'
        : 'Cho Peto đọc trí nhớ từ bot Discord ở lượt mới. Không xóa dữ liệu đã có.'}>
      <SettingsSwitch id={id} label="Trí nhớ từ bot Discord" checked={state?.enabled ?? false}
        disabled={loading || saving || !state} onChange={value => void toggle(value)} />
    </SettingsRow>
    {error && <div className="settings-error" role="alert">{error}{!state && <button type="button" className="settings-button" onClick={() => setReload(value => value + 1)}>Thử lại</button>}</div>}
  </>;
}
