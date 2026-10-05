import { useEffect, useState, type ReactNode } from 'react';
import { GitHubIcon } from '../../shared/ui/GitHubIcon';
import { GlobeIcon } from './WebSources';
import type { WorkLog, WorkStep } from '../../shared/api/api';

// Khối "Đang làm" kiểu Dòng thời gian (chủ dự án chọn ngày 5/10/2026 từ ba mẫu chạy được): đồng hồ chạy cạnh chữ, mỗi
// bước một dòng có thời gian riêng, tóm tắt suy nghĩ của Grok mở ra được, câu dẫn Peto nói giữa các bước nằm xen trong
// dòng thời gian. Tự thu lại khi bắt đầu có chữ trả lời; lượt hỏng mà chưa có chữ thì để mở cho thấy Peto đã thử gì.

/** "2:41": đồng hồ khi đang chạy. */
export const clock = (ms: number) => {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
};

/** "3 phút 18 giây": thời gian đã xong. */
export function duration(ms: number) {
  const whole = Math.max(1, Math.round(ms / 1000));
  const minutes = Math.floor(whole / 60), rest = whole % 60;
  return minutes ? (rest ? `${minutes} phút ${rest} giây` : `${minutes} phút`) : `${rest} giây`;
}

/** "Đang tìm trên web…" → "Đã tìm trên web", như máy chủ làm khi một bước xong. */
const doneLabel = (label: string) => label.replace(/…$/, '').replace(/^Đang /, 'Đã ');

/** Không nhận được bản chốt từ máy chủ (mất kết nối, bấm Dừng): tự đóng các bước còn dở theo đồng hồ trình duyệt. */
export function closeWork(work: WorkLog | undefined, complete: boolean, ms: number): WorkLog | undefined {
  if (!work) return work;
  const steps = work.steps.filter(step => step.kind !== 'wait').map(step => step.state !== 'live' ? step : complete
    ? { ...step, state: 'done' as const, end: Math.max(step.start, ms), label: doneLabel(step.label) }
    : { ...step, state: 'stopped' as const, end: Math.max(step.start, ms) });
  return { ms, steps, complete };
}

/** Mili giây từ lúc gửi, cập nhật mỗi giây khi lượt còn chạy. */
function useElapsed(live: boolean, startedAt?: number) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!live) return;
    setNow(performance.now());
    const timer = window.setInterval(() => setNow(performance.now()), 1000);
    return () => window.clearInterval(timer);
  }, [live]);
  return live && startedAt != null ? Math.max(0, now - startedAt) : 0;
}

const svg = (path: ReactNode) => <svg className="work-glyph" viewBox="0 0 24 24" width="14" height="14" fill="none"
  stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{path}</svg>;
const ICONS = {
  read: svg(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>),
  think: svg(<><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V16h5.2v-.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z" /></>),
  compose: svg(<><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m14 6 4 4" /></>),
  tool: svg(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M3 15h18M9 4v16" /></>),
  lookup: svg(<><circle cx="11" cy="11" r="6" /><path d="m20 20-4.5-4.5" /></>),
  done: svg(<path d="m5 12 4.5 4.5L19 7" />),
  failed: svg(<path d="M6 6l12 12M18 6 6 18" />),
  wait: svg(<><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 2" /></>),
};

function icon(step: WorkStep) {
  if (step.kind === 'github') return <GitHubIcon size={14} />;
  if (step.kind === 'search') return <GlobeIcon />;
  if (step.kind === 'tool' && (step.state === 'done' || step.state === 'failed')) return ICONS[step.state];
  return ICONS[step.kind as keyof typeof ICONS] ?? ICONS.wait;
}

/** Ý mới nhất trong tóm tắt của Grok: đề mục cuối ("**Checking codes**") nếu có, không thì đoạn cuối. Tóm tắt thật
 * (5/10/2026) là hàng chục đoạn tiếng Việt kiểu "Đang kiểm tra từng dòng nhân viên…", nên chỉ hiện một dòng này. */
export function latestThought(summary: string) {
  const headings = [...summary.matchAll(/\*\*([^*\n]+)\*\*/g)];
  const heading = headings[headings.length - 1]?.[1]?.trim();
  if (heading) return heading;
  const lines = summary.split('\n').map(line => line.replace(/\*\*/g, '').trim()).filter(Boolean);
  return lines[lines.length - 1] ?? '';
}

/** Đang chạy: ý mới nhất, một dòng, cắt bằng "…" nếu dài. Xong: "Đã suy nghĩ"; bấm mới mở cả tóm tắt. */
function thinkTitle(step: WorkStep) {
  if (step.state !== 'live') return step.label;
  return latestThought(step.summary ?? '') || 'Đang suy nghĩ…';
}

const stoppedLabel = (label: string) => `Đã dừng khi ${label.replace(/^Đang /, 'đang ').replace(/…$/, '')}`;

/** Tóm tắt suy nghĩ: từng đoạn, đề mục **…** đầu đoạn in đậm. Chữ của Grok, thường bằng tiếng Anh. */
function Thought({ text }: { text: string }) {
  const parts = text.split(/\n{2,}/).map(part => part.trim()).filter(Boolean);
  return <div className="work-thought">{parts.map((part, index) => {
    const heading = /^\*\*(.+?)\*\*\s*/.exec(part);
    return <p key={index}>{heading ? <><strong>{heading[1]}</strong>{part.slice(heading[0].length)}</> : part}</p>;
  })}</div>;
}

/** Bước suy nghĩ có tóm tắt: một dòng, bấm để mở cả tóm tắt (khung có thanh cuộn). Bước xong thì tự đóng lại. */
function ThinkStep({ step, head }: { step: WorkStep; head: ReactNode }) {
  const [open, setOpen] = useState(false);
  const live = step.state === 'live';
  useEffect(() => { if (!live) setOpen(false); }, [live]);
  // Tự bật/tắt bằng trạng thái thay vì để trình duyệt tự mở: đóng được khi bước xong, và chạy như nhau ở mọi nơi.
  return <li className={`work-item think ${step.state}`}>
    <details open={open}>
      <summary onClick={event => { event.preventDefault(); setOpen(value => !value); }}>{head}</summary>
      {open && <Thought text={step.summary ?? ''} />}
    </details>
  </li>;
}

function Step({ step, elapsed }: { step: WorkStep; elapsed: number }) {
  if (step.kind === 'note') return <li className="work-note">{step.label}</li>;
  const live = step.state === 'live';
  const ms = live ? elapsed - step.start : (step.end ?? step.start) - step.start;
  const time = live ? clock(ms) : ms >= 1000 ? duration(ms) : '';
  const label = step.state === 'stopped' ? stoppedLabel(step.label) : step.kind === 'think' ? thinkTitle(step) : step.label;
  const head = <>
    <span className="work-icon">{icon(step)}</span>
    <span className={live ? 'work-label work-shimmer' : 'work-label'}>{label}</span>
    {time && <span className="work-time">{time}</span>}
  </>;
  if (step.kind === 'think' && step.summary) return <ThinkStep step={step} head={head} />;
  return <li className={`work-item ${step.state}`}>
    <div className="work-row">{head}</div>
    {step.detail && <p className="work-sub">{step.detail}</p>}
    {step.problems?.length ? (step.kind === 'github'
      ? <details className="work-more"><summary>Xem mục chưa đọc được</summary><ul>{step.problems.map(item => <li key={item}>{item}</li>)}</ul></details>
      : <ul className="work-problems">{step.problems.map(item => <li key={item}>{item}</li>)}</ul>) : null}
  </li>;
}

function Chevron({ open }: { open: boolean }) {
  return <svg className={`work-chevron${open ? ' open' : ''}`} viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
    <path d="m9 6 6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function WorkTimeline({ work, live, startedAt, answering }: {
  work: WorkLog; live: boolean; startedAt?: number; answering: boolean;
}) {
  const elapsed = useElapsed(live, startedAt);
  const stopped = !live && work.complete === false;
  const [choice, setChoice] = useState<boolean | null>(null);
  // Xong lượt thì thu lại như mặc định, kể cả khi người dùng đã mở khối lúc đang chạy.
  useEffect(() => { if (!live) setChoice(null); }, [live]);
  const open = choice ?? (live ? !answering : stopped && !answering);
  const steps = work.steps;
  const title = live
    ? <><span className="work-shimmer">Đang làm</span><span className="work-clock" aria-hidden="true">{clock(elapsed)}</span></>
    : <span className={stopped ? 'work-stopped' : undefined}>{stopped ? `Đã dừng sau ${duration(work.ms)}` : `Đã làm trong ${duration(work.ms)}`}</span>;
  if (!steps.length) return <div className="work-log"><div className="work-head static">{title}</div></div>;
  return <div className="work-log">
    <button type="button" className="work-head" aria-expanded={open} onClick={() => setChoice(!open)}>
      <Chevron open={open} />{title}
    </button>
    {open && <ol className="work-timeline">{steps.map(step => <Step key={step.id} step={step} elapsed={elapsed} />)}</ol>}
  </div>;
}
