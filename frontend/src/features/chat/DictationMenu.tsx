import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { DICTATION_LANGUAGES, languageOf, matchesLanguage, resolveMic } from './dictationPrefs';
import type { ChatDictation } from './useChatDictation';

// Menu ở mũi tên cạnh nút micro, theo mẫu của Claude chủ web gửi ngày 20/11/2026: thanh âm lượng và danh sách micro,
// rồi "Ngôn ngữ ›" mở danh sách có ô tìm. Khác Claude: không có "Tự động" (Web Speech cần biết trước ngôn ngữ), và danh
// sách micro chỉ hiện ở trình duyệt nghe được từ micro đã chọn (dictationPrefs.deviceChoiceSupported).

const CHECK = <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
  <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
</svg>;

function Chevron({ back = false }: { back?: boolean }) {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d={back ? 'm15 6-6 6 6 6' : 'm9 6 6 6-6 6'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

interface Device { id: string; label: string }

/** Mở micro đang chọn để đo âm lượng và đọc tên các micro (trình duyệt chỉ cho đọc tên sau khi được phép dùng micro). */
function useMicrophones(active: boolean, mic: string, meter: RefObject<HTMLSpanElement | null>) {
  // `mic`: mã đã tìm lại được (resolveMic) hoặc rỗng; mã cũ không còn thì mở micro mặc định để vẫn đo được.
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    let frame = 0;
    setProblem('');
    navigator.mediaDevices.getUserMedia({ audio: mic ? { deviceId: { exact: mic } } : true })
      .then(async (opened) => {
        if (cancelled) { opened.getTracks().forEach((track) => track.stop()); return; }
        stream = opened;
        const listed = (await navigator.mediaDevices.enumerateDevices())
          .filter((item) => item.kind === 'audioinput')
          .map((item, index) => ({ id: item.deviceId, label: item.label || `Micro ${index + 1}` }));
        if (cancelled) return;
        setDevices(listed);
        try {
          context = new AudioContext();
          const analyser = context.createAnalyser();
          analyser.fftSize = 512;
          context.createMediaStreamSource(opened).connect(analyser);
          const samples = new Float32Array(analyser.fftSize);
          const draw = () => {
            analyser.getFloatTimeDomainData(samples);
            let sum = 0;
            for (const value of samples) sum += value * value;
            const level = Math.min(1, Math.sqrt(sum / samples.length) * 4);
            if (meter.current) meter.current.style.transform = `scaleX(${level.toFixed(3)})`;
            frame = requestAnimationFrame(draw);
          };
          draw();
        } catch { /* Không đo được âm lượng thì vẫn chọn được micro. */ }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const name = err instanceof DOMException ? err.name : '';
        setDevices([]);
        setProblem(name === 'NotAllowedError'
          ? 'Chưa được phép dùng micro. Bấm biểu tượng ổ khóa cạnh địa chỉ trang để cho phép.'
          : 'Không mở được micro. Kiểm tra micro đã cắm chưa.');
      });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
      void context?.close().catch(() => {});
    };
  }, [active, mic, meter]);
  return { devices, problem };
}

export default function DictationMenu({ dictation, disabled }: { dictation: ChatDictation; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<'main' | 'language'>('main');
  const [query, setQuery] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const meter = useRef<HTMLSpanElement>(null);
  const [current, setCurrent] = useState('');
  const { devices, problem } = useMicrophones(open && view === 'main' && dictation.canChooseMic, current, meter);
  const language = languageOf(dictation.language);
  const languages = DICTATION_LANGUAGES.filter((item) => matchesLanguage(item, query));
  const selectedMic = (devices && resolveMic(dictation.mic, devices.map((item) => ({ deviceId: item.id, label: item.label }))))
    || (devices?.some((item) => item.id === 'default') ? 'default' : devices?.[0]?.id);

  // Lần mở đầu đo micro mặc định (mới đọc được tên các micro); tìm ra micro đã chọn rồi thì đo đúng micro đó.
  useEffect(() => {
    if (selectedMic && selectedMic !== 'default' && selectedMic !== current) setCurrent(selectedMic);
  }, [selectedMic, current]);
  useEffect(() => { if (!open) setCurrent(''); }, [open]);
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    if (view === 'language') search.current?.focus();
    else menu.current?.querySelector<HTMLButtonElement>('[aria-checked="true"], [role="menuitem"]')?.focus();
  }, [open, view, devices]);

  function toggle() {
    setView('main');
    setQuery('');
    setOpen((value) => !value);
  }
  function close() { setOpen(false); trigger.current?.focus(); }
  function items() {
    return [...(menu.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not(:disabled)') ?? [])];
  }

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const list = items();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const move = (to: number) => { event.preventDefault(); list[(to + list.length) % list.length]?.focus(); };
    if (event.key === 'ArrowDown') move(at + 1);
    else if (event.key === 'ArrowUp') {
      if (at <= 0 && view === 'language') { event.preventDefault(); search.current?.focus(); } else move(at - 1);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      if (view === 'language') setView('main'); else close();
    } else if (event.key === 'Tab') setOpen(false);
  }

  return <div ref={root} className="dictation-menu" onBlur={(event) => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="dictation-more" disabled={disabled}
      aria-haspopup="menu" aria-expanded={open} aria-controls="dictation-options"
      aria-label="Cài đặt nhập giọng nói" data-tip="Micro và ngôn ngữ" onClick={toggle}>
      <svg className="effort-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
    {open && <div ref={menu} id="dictation-options" className="effort-options dictation-options" role="menu"
      aria-label={view === 'language' ? 'Ngôn ngữ nghe' : 'Nhập giọng nói'} onKeyDown={onMenuKey}>
      {view === 'main' ? <>
        {dictation.canChooseMic ? <>
          <div className="dictation-level" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
              strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
            <span className="dictation-level-track"><span ref={meter} className="dictation-level-fill" /></span>
          </div>
          {devices === null && <p className="dictation-menu-note">Đang mở micro…</p>}
          {problem && <p className="dictation-menu-note" role="alert">{problem}</p>}
          {devices?.map((item) => {
            const on = item.id === selectedMic;
            return <button key={item.id} type="button" role="menuitemradio" aria-checked={on}
              className={on ? 'effort-option dictation-device on' : 'effort-option dictation-device'}
              onClick={() => { dictation.setMic({ id: item.id, label: item.label }); setCurrent(item.id === 'default' ? '' : item.id); }}>
              <span className="effort-option-label">{item.label}</span>
              {on && CHECK}
            </button>;
          })}
        </> : <>
          <button type="button" role="menuitemradio" aria-checked="true" className="effort-option dictation-device on">
            <span className="effort-option-label">Micro mặc định của máy</span>{CHECK}
          </button>
          <p className="dictation-menu-note">Trình duyệt này chỉ nghe bằng micro mặc định. Chrome hoặc Edge trên máy tính chọn được micro.</p>
        </>}
        <div className="dictation-menu-separator" role="separator" />
        <p className="effort-heading" aria-hidden="true">Nhập giọng nói</p>
        <button type="button" role="menuitem" className="effort-option dictation-language" aria-haspopup="menu"
          onClick={() => setView('language')}>
          <span className="effort-option-label">Ngôn ngữ</span>
          <span className="dictation-value">{language.label}</span>
          <Chevron />
        </button>
        {dictation.phase !== 'off' && <p className="dictation-menu-note">Đổi micro hay ngôn ngữ có tác dụng từ lần nghe sau.</p>}
      </> : <>
        <button type="button" role="menuitem" className="effort-option dictation-back" onClick={() => { setView('main'); setQuery(''); }}>
          <Chevron back /><span className="effort-option-label">Ngôn ngữ</span>
        </button>
        <input ref={search} className="dictation-search" type="search" value={query} placeholder="Tìm ngôn ngữ"
          aria-label="Tìm ngôn ngữ" autoComplete="off" spellCheck={false}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown' || event.key === 'Enter') event.stopPropagation();
            if (event.key === 'ArrowDown') { event.preventDefault(); menu.current?.querySelector<HTMLElement>('.dictation-language-option')?.focus(); }
            if (event.key === 'Enter' && languages.length) { event.preventDefault(); dictation.setLanguage(languages[0].code); close(); }
          }} />
        <div className="dictation-language-list">
          {languages.map((item) => {
            const on = item.code === language.code;
            return <button key={item.code} type="button" role="menuitemradio" aria-checked={on}
              className={on ? 'effort-option dictation-language-option on' : 'effort-option dictation-language-option'}
              onClick={() => { dictation.setLanguage(item.code); close(); }}>
              <span className="effort-option-label">{item.label}</span>
              {on && CHECK}
            </button>;
          })}
          {!languages.length && <p className="dictation-menu-note">Không có ngôn ngữ nào khớp.</p>}
        </div>
      </>}
    </div>}
  </div>;
}
