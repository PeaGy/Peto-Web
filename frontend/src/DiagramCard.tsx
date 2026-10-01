/** Thẻ sơ đồ trong câu trả lời: ảnh thu nhỏ, tên và loại sơ đồ; bấm để mở lớn ở bảng bên phải (DiagramPanel). */
import { createContext, useContext, useMemo } from "react";
import { describe, kindNote, normalizeDiagram, sized, svgSize, useDiagram, useDiagramTheme } from "./diagrams";
import { diagramPanel } from "./diagramPanelLazy";

export interface DiagramPanelApi {
  /** Sơ đồ đang mở ở bảng bên phải (mã đã chuẩn hóa), hoặc null. */
  current: string | null;
  open: (code: string) => void;
}

export const DiagramContext = createContext<DiagramPanelApi>({ current: null, open: () => undefined });

export function DiagramIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="16" width="7" height="5" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" /><path d="M6.5 8v4.5a2 2 0 0 0 2 2H14M17.5 8v8" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9.5 6 6 6-6 6" /></svg>
  );
}

/** Ảnh thu nhỏ vừa ô 92 × 60 (ô thẻ trừ lề trong), không phóng to sơ đồ nhỏ. */
function thumbnail(svg: string): string {
  const { width, height } = svgSize(svg);
  const scale = Math.min(1, 92 / width, 60 / height);
  return sized(svg, Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale)));
}

/**
 * ``pending``: Peto còn đang viết tin này. Khi đó mã sơ đồ có thể dở dang, vẽ ra chỉ thấy lỗi cú pháp chớp lên, nên thẻ
 * chỉ báo đang vẽ; tin viết xong mới vẽ thật.
 */
export function DiagramCard({ source, pending }: { source: string; pending: boolean }) {
  const code = useMemo(() => normalizeDiagram(source), [source]);
  const theme = useDiagramTheme();
  const { svg, error, ready } = useDiagram(code, theme, !pending && code.length > 0);
  const { kind, title } = useMemo(() => describe(code), [code]);
  const panel = useContext(DiagramContext);
  const thumb = useMemo(() => (svg ? thumbnail(svg) : ""), [svg]);

  if (pending) {
    return (
      <div className="diagram-card pending" role="status">
        <span className="diagram-thumb" aria-hidden="true"><DiagramIcon size={20} /></span>
        <span className="diagram-card-text"><strong>Đang vẽ sơ đồ…</strong><small>Peto đang viết mã sơ đồ</small></span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="diagram-error" role="note">
        <p><strong>Chưa vẽ được sơ đồ này.</strong> {error} Mã gốc ở dưới; nhờ Peto sửa lại là được.</p>
        <div className="code-block">
          <div className="code-head"><span className="code-lang">Mermaid</span></div>
          <pre><code>{code}</code></pre>
        </div>
      </div>
    );
  }
  const active = panel.current === code;
  return (
    <button type="button" className={active ? "diagram-card active" : "diagram-card"} aria-pressed={active}
      onClick={() => panel.open(code)} onPointerEnter={() => void diagramPanel.preload().catch(() => undefined)}>
      <span className="diagram-thumb" aria-hidden="true">
        {thumb ? <span className="diagram-thumb-svg" dangerouslySetInnerHTML={{ __html: thumb }} /> : <DiagramIcon size={20} />}
      </span>
      <span className="diagram-card-text">
        <strong>{title}</strong>
        <small>{[kindNote(kind, title), active ? "Đang mở bên phải" : ready ? "Bấm để xem lớn" : "Đang vẽ…"].filter(Boolean).join(" · ")}</small>
      </span>
      <span className="diagram-card-go" aria-hidden="true"><ChevronIcon /></span>
    </button>
  );
}
