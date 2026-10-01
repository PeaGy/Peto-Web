/**
 * Bảng sơ đồ bên phải (phần tải riêng): sơ đồ lớn kéo và phóng được, xem mã, tải PNG/SVG/PDF, mở bằng draw.io để sửa
 * tay. Mở và đóng như bảng tài liệu: màn rộng là bảng cạnh khung chat, dưới 1100px phủ kín màn hình.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DiagramIcon } from "./DiagramCard";
import { describe, kindNote, sized, svgSize, useDiagram, useDiagramTheme } from "./diagrams";
import { downloadPdf, downloadPng, downloadSvg, drawioUrl } from "./diagramExport";
import "./diagramPanel.css";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
  );
}
const CloseIcon = () => <Icon><path d="M6 6l12 12M18 6 6 18" /></Icon>;
const DownloadIcon = () => <Icon><path d="M12 4v11m0 0 4.5-4.5M12 15l-4.5-4.5M5 19.5h14" /></Icon>;
const ExternalIcon = () => <Icon><path d="M14 5h5v5M19 5l-8 8M17 13.5V18a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 5 18V8.5A1.5 1.5 0 0 1 6.5 7H11" /></Icon>;
const PlusIcon = () => <Icon><path d="M12 5v14M5 12h14" /></Icon>;
const MinusIcon = () => <Icon><path d="M5 12h14" /></Icon>;
const CopyIcon = () => <Icon><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h8" /></Icon>;
const CheckIcon = () => <Icon><path d="m5 12.5 4.5 4.5L19 7.5" /></Icon>;

interface View { scale: number; x: number; y: number }

/** Khung xem lớn: kéo để di chuyển, cuộn chuột hay chụm hai ngón để phóng, phím + − 0 và mũi tên. */
function PanZoom({ svg, label }: { svg: string; label: string }) {
  const frame = useRef<HTMLDivElement>(null);
  const natural = useMemo(() => svgSize(svg), [svg]);
  const html = useMemo(() => sized(svg, natural.width, natural.height), [svg, natural]);
  const [view, setView] = useState<View | null>(null);
  const [smooth, setSmooth] = useState(false);
  const pointers = useRef(new Map<number, { x: number; y: number }>());

  const fit = useCallback(() => {
    const element = frame.current;
    if (!element) return;
    const { width, height } = element.getBoundingClientRect();
    if (!width || !height) return;
    // Chừa 56px dưới cho cụm nút phóng, thu để nó không che phần cuối sơ đồ.
    const room = height - 56;
    const scale = Math.max(0.1, Math.min(1.5, (width - 48) / natural.width, (room - 40) / natural.height));
    setView({ scale, x: (width - natural.width * scale) / 2, y: Math.max(20, (room - natural.height * scale) / 2) });
  }, [natural]);

  useLayoutEffect(() => {
    fit();
    if (typeof ResizeObserver === "undefined" || !frame.current) return;
    const observer = new ResizeObserver(() => fit());
    observer.observe(frame.current);
    return () => observer.disconnect();
  }, [fit]);

  const zoomAt = useCallback((factor: number, x?: number, y?: number) => {
    setView((current) => {
      if (!current || !frame.current) return current;
      const rect = frame.current.getBoundingClientRect();
      const px = x ?? rect.width / 2;
      const py = y ?? rect.height / 2;
      const scale = Math.min(6, Math.max(0.1, current.scale * factor));
      const ratio = scale / current.scale;
      return { scale, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio };
    });
  }, []);

  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    // React gắn wheel dạng passive nên không chặn được cuộn trang; tự gắn để cuộn chuột là phóng.
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      setSmooth(false);
      const rect = element.getBoundingClientRect();
      zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX - rect.left, event.clientY - rect.top);
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [zoomAt]);

  function step(action: () => void) {
    setSmooth(true);
    action();
  }

  return (
    <div className="diagram-pz">
      <div ref={frame} className="diagram-pz-frame" tabIndex={0} role="img"
        aria-label={`${label}. Kéo để di chuyển, cuộn chuột hoặc chụm hai ngón để phóng to.`}
        onPointerDown={(event) => {
          frame.current?.setPointerCapture?.(event.pointerId);
          pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
          setSmooth(false);
        }}
        onPointerMove={(event) => {
          const map = pointers.current;
          const previous = map.get(event.pointerId);
          if (!previous) return;
          const next = { x: event.clientX, y: event.clientY };
          if (map.size === 1) {
            map.set(event.pointerId, next);
            setView((current) => current && { ...current, x: current.x + next.x - previous.x, y: current.y + next.y - previous.y });
            return;
          }
          const other = [...map.entries()].find(([id]) => id !== event.pointerId)?.[1];
          map.set(event.pointerId, next);
          if (!other || !frame.current) return;
          const before = Math.hypot(previous.x - other.x, previous.y - other.y);
          const after = Math.hypot(next.x - other.x, next.y - other.y);
          const rect = frame.current.getBoundingClientRect();
          if (before > 0) zoomAt(after / before, (next.x + other.x) / 2 - rect.left, (next.y + other.y) / 2 - rect.top);
        }}
        onPointerUp={(event) => pointers.current.delete(event.pointerId)}
        onPointerCancel={(event) => pointers.current.delete(event.pointerId)}
        onKeyDown={(event) => {
          const moves: Record<string, [number, number]> = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] };
          if (event.key === "+" || event.key === "=") step(() => zoomAt(1.25));
          else if (event.key === "-") step(() => zoomAt(0.8));
          else if (event.key === "0") step(fit);
          else if (moves[event.key]) {
            const [dx, dy] = moves[event.key];
            step(() => setView((current) => current && { ...current, x: current.x + dx, y: current.y + dy }));
          } else return;
          event.preventDefault();
        }}>
        {view && (
          <div className={smooth ? "diagram-pz-content smooth" : "diagram-pz-content"}
            style={{ width: natural.width, height: natural.height, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
            dangerouslySetInnerHTML={{ __html: html }} />
        )}
      </div>
      <div className="diagram-pz-controls">
        <button type="button" aria-label="Thu nhỏ" title="Thu nhỏ" onClick={() => step(() => zoomAt(0.8))}><MinusIcon /></button>
        <span className="diagram-pz-scale" aria-live="polite">{view ? Math.round(view.scale * 100) : 100}%</span>
        <button type="button" aria-label="Phóng to" title="Phóng to" onClick={() => step(() => zoomAt(1.25))}><PlusIcon /></button>
        <button type="button" className="diagram-pz-fit" onClick={() => step(fit)}>Vừa khung</button>
      </div>
    </div>
  );
}

/** Nút Tải: PNG (nền trắng, dán vào Word), SVG (phóng bao nhiêu cũng nét), PDF (khổ A4, in hay nộp). */
function DownloadMenu({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation(); // chỉ đóng menu, không đóng cả bảng
      setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", key, true);
    };
  }, [open]);
  const run = (action: (code: string) => Promise<void>) => {
    setOpen(false);
    setError("");
    action(code).catch(() => setError("Chưa tải được, thử lại nhé."));
  };
  return (
    <span className="diagram-download" ref={root}>
      <button type="button" className="diagram-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <DownloadIcon />Tải
      </button>
      {open && (
        <span className="diagram-menu" role="menu" aria-label="Tải sơ đồ">
          <button type="button" role="menuitem" onClick={() => run(downloadPng)}><strong>Ảnh PNG</strong><small>Nền trắng, dán vào Word hay slide</small></button>
          <button type="button" role="menuitem" onClick={() => run(downloadSvg)}><strong>Ảnh SVG</strong><small>Phóng to bao nhiêu cũng nét</small></button>
          <button type="button" role="menuitem" onClick={() => run(downloadPdf)}><strong>PDF</strong><small>Khổ A4, in hay nộp bài</small></button>
        </span>
      )}
      {error && <span className="diagram-download-error" role="alert">{error}</span>}
    </span>
  );
}

function CodeView({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <div className="code-block diagram-code">
      <div className="code-head">
        <span className="code-lang">Mermaid</span>
        <button type="button" className="code-copy" onClick={() => {
          navigator.clipboard?.writeText(code).then(() => {
            setCopied(true);
            window.clearTimeout(timer.current);
            timer.current = window.setTimeout(() => setCopied(false), 1800);
          }, () => undefined);
        }}>{copied ? <CheckIcon /> : <CopyIcon />}{copied ? "Đã chép" : "Sao chép"}</button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

export default function DiagramPanel({ codes, current, onPick, onClose }: {
  /** Các sơ đồ của hội thoại theo thứ tự, để chuyển qua lại. */
  codes: string[];
  current: string;
  onPick: (code: string) => void;
  onClose: () => void;
}) {
  const panel = useRef<HTMLDialogElement>(null);
  const [mobile, setMobile] = useState(() => window.matchMedia?.("(max-width: 1100px)")?.matches ?? false);
  const theme = useDiagramTheme();
  const { svg, error } = useDiagram(current, theme);
  const { kind, title } = useMemo(() => describe(current), [current]);
  const [tab, setTab] = useState<"diagram" | "code">("diagram");
  const [link, setLink] = useState("");
  const index = codes.indexOf(current);

  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 1100px)");
    if (!media) return;
    const update = () => setMobile(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    const element = panel.current;
    if (!element) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (mobile) element.showModal(); else element.show();
    return () => {
      element.close();
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [mobile]);
  useEffect(() => {
    let alive = true;
    setLink("");
    void drawioUrl(current).then((url) => { if (alive) setLink(url); });
    return () => { alive = false; };
  }, [current]);

  return (
    <dialog ref={panel} className="document-panel diagram-panel" aria-label="Sơ đồ trong hội thoại"
      aria-modal={mobile ? true : undefined}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onKeyDown={(event) => { if (!mobile && event.key === "Escape") { event.preventDefault(); onClose(); } }}>
      <header className="document-panel-head">
        <DiagramIcon size={18} /><h2>Sơ đồ</h2>
        <span className="document-panel-count">{index >= 0 ? `${index + 1} / ${codes.length}` : ""}</span>
        <button type="button" className="artifact-icon diagram-step" aria-label="Sơ đồ trước" title="Sơ đồ trước"
          disabled={index <= 0} onClick={() => onPick(codes[index - 1])}>‹</button>
        <button type="button" className="artifact-icon diagram-step" aria-label="Sơ đồ sau" title="Sơ đồ sau"
          disabled={index < 0 || index >= codes.length - 1} onClick={() => onPick(codes[index + 1])}>›</button>
        <button type="button" className="artifact-icon" aria-label="Đóng bảng sơ đồ" title="Đóng" onClick={onClose}><CloseIcon /></button>
      </header>
      <div className="document-panel-toolbar diagram-toolbar">
        <strong className="diagram-title" title={title}>{title}{kindNote(kind, title) && <small> · {kind}</small>}</strong>
        <span className="diagram-seg" role="tablist" aria-label="Cách xem sơ đồ">
          <button type="button" role="tab" aria-selected={tab === "diagram"} onClick={() => setTab("diagram")}>Sơ đồ</button>
          <button type="button" role="tab" aria-selected={tab === "code"} onClick={() => setTab("code")}>Mã</button>
        </span>
        <DownloadMenu code={current} />
        <a className="diagram-button" href={link || undefined} target="_blank" rel="noopener noreferrer" aria-disabled={!link}
          title="Mở bằng draw.io: sửa tay (thêm làn, kéo lại vị trí) rồi xuất PDF dạng nét vẽ">draw.io<ExternalIcon /></a>
      </div>
      <div className="diagram-panel-body">
        {error ? (
          <div className="diagram-panel-scroll">
            <p className="diagram-panel-error"><strong>Chưa vẽ được sơ đồ này.</strong> {error}</p>
            <CodeView code={current} />
          </div>
        ) : tab === "code" ? (
          <div className="diagram-panel-scroll"><CodeView code={current} /></div>
        ) : svg ? (
          <PanZoom key={`${current}-${theme}`} svg={svg} label={title} />
        ) : (
          <p className="diagram-panel-loading" role="status">Đang vẽ sơ đồ…</p>
        )}
      </div>
    </dialog>
  );
}
