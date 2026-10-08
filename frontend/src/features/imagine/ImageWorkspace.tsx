import { useEffect, useRef, useState, type PointerEvent } from 'react';
import type { ImagineImage, ImagineJob } from '../../shared/api/api';
import { imagineSources } from '../../shared/api/api';
import ImageComparison from './ImageComparison';
import StudioIcon from './studioIcons';
import { drawStrokes, extractPalette, renderEdit, FULL_CROP, type CropArea, type Stroke } from './imageTools';

type Tool = 'info' | 'palette' | 'crop' | 'brush';
const TOOL_LABELS: Record<Tool, string> = { info: 'Thông tin ảnh', palette: 'Bảng màu', crop: 'Cắt ảnh', brush: 'Bút vẽ' };
const PALETTES = [
  { name: 'Đất nung', colors: ['#a35132', '#d8b287', '#55624c', '#f2eee5'] },
  { name: 'Bắc Âu', colors: ['#e2f2ff', '#9acded', '#2999d7', '#1450a1'] },
  { name: 'Ngọc lục bảo', colors: ['#061713', '#205c4c', '#498e78', '#a7dfcb'] },
  { name: 'Hoàng hôn', colors: ['#ef4423', '#ff790a', '#ffba36', '#ffe5a0'] },
  { name: 'Phong lan', colors: ['#211332', '#7127d2', '#ae8af3', '#f0eaff'] },
  { name: 'Hoa anh đào', colors: ['#fbf1f2', '#f0b6c4', '#cd6a8a', '#77354e'] },
];
const COLORS = ['#ffffff', '#000000', '#f04444', '#fb8917', '#f7cf1b', '#21be65', '#397cf5'];
const RATIOS = ['auto', '1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '2:1', '1:2', '19.5:9', '9:19.5', '20:9', '9:20', '21:9', '5:2'];
const clamp = (n: number, min = 0, max = 1) => Math.max(min, Math.min(max, n));

export default function ImageWorkspace({ job, image, index, original, liked, disabled, canAdd, alreadyAdded, likeError, onClose, onNavigate, onLike, onUse, onAdd, onSubmit }: {
  job: ImagineJob; image: ImagineImage; index: number; original: boolean; liked: boolean; disabled: boolean; canAdd: boolean; alreadyAdded: boolean; likeError: string | null;
  onClose: () => void; onNavigate: (index: number) => void; onLike: () => void;
  onUse: (data?: string) => void; onAdd: (data?: string) => void;
  onSubmit: (prompt: string, aspect: string, data?: string) => Promise<void>;
}) {
  const [comparing, setComparing] = useState(false);
  const [tool, setTool] = useState<Tool>('info');
  const [panelOpen, setPanelOpen] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [space, setSpace] = useState({ width: 800, height: 600 });
  const [versions, setVersions] = useState([image.url]);
  const [version, setVersion] = useState(0);
  const [prompt, setPrompt] = useState('');
  const [aspect, setAspect] = useState('auto');
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [palette, setPalette] = useState<string[]>([]);
  const [color, setColor] = useState('#ffffff');
  const [brushSize, setBrushSize] = useState(12);
  const [erasing, setErasing] = useState(false);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [redoStrokes, setRedoStrokes] = useState<Stroke[]>([]);
  const [crop, setCrop] = useState<CropArea>({ x: .1, y: .1, width: .8, height: .8 });
  const [cropRatio, setCropRatio] = useState('free');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const cropImageRef = useRef<HTMLImageElement>(null);
  const strokeRef = useRef<Stroke | null>(null);
  const cropDrag = useRef<{ x: number; y: number; rect: CropArea; mode: string } | null>(null);
  const operationRef = useRef(false);
  const src = versions[version];
  const changed = src !== image.url || strokes.length > 0;
  const blocked = disabled || busy;
  const ready = dimensions.width > 0;
  const fit = ready ? Math.min((space.width - 48) / dimensions.width, (space.height - 36) / dimensions.height, 1) : 1;
  const displayWidth = ready ? dimensions.width * Math.max(.05, fit) * zoom : undefined;
  const displayHeight = ready ? dimensions.height * Math.max(.05, fit) * zoom : undefined;
  // Thanh trên và ô nhập bám vùng ảnh vừa khung, không kéo dài theo cả cửa sổ hay ảnh đang zoom.
  const controlWidth = Math.min(space.width, Math.max(360, (displayWidth ?? 640) / zoom + 80));

  useEffect(() => {
    const element = stageRef.current;
    if (!element) return;
    const measure = () => setSpace({ width: element.clientWidth || 800, height: element.clientHeight || 600 });
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure); observer.observe(element); return () => observer.disconnect();
  }, [panelOpen]);
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (canvas && context) drawStrokes(context, strokes, canvas.width, canvas.height);
  }, [strokes, dimensions, tool, src]);

  function appendPrompt(text: string) { setPrompt(current => current.trim() ? `${current.trimEnd()}\n${text}` : text); }
  function saveVersion(data: string) {
    const next = [versions[0], ...[...versions.slice(1, version + 1), data].slice(-5)];
    setVersions(next); setVersion(next.length - 1); setStrokes([]); setRedoStrokes([]); setPalette([]); setZoom(1); setNotice('Bản chỉnh sửa chưa lưu vào thư viện. Bạn tải xuống hoặc dùng làm tham chiếu trước khi đóng nhé. Ảnh gốc vẫn được giữ.');
  }
  async function execute(action: () => Promise<void>) {
    if (operationRef.current) return;
    operationRef.current = true; setBusy(true); setNotice(null);
    try { await action(); } catch (error) { setNotice(error instanceof Error ? error.message : 'Chưa hoàn tất thao tác. Bạn thử lại nhé.'); }
    finally { operationRef.current = false; setBusy(false); }
  }
  async function editData() { return strokes.length ? renderEdit(src, FULL_CROP, strokes) : src !== image.url ? src : undefined; }
  function point(event: PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
  }
  function beginStroke(event: PointerEvent<HTMLCanvasElement>) {
    if (blocked || event.button !== 0) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    const rect = event.currentTarget.getBoundingClientRect();
    const stroke = { points: [point(event)], color, size: brushSize / rect.width, erasing };
    strokeRef.current = stroke; setRedoStrokes([]); setStrokes(current => [...current, stroke]);
  }
  function moveStroke(event: PointerEvent<HTMLCanvasElement>) {
    if (!strokeRef.current || blocked) return;
    const next = { ...strokeRef.current, points: [...strokeRef.current.points, point(event)] };
    strokeRef.current = next; setStrokes(current => [...current.slice(0, -1), next]);
  }
  function setRatio(value: string) {
    setCropRatio(value);
    if (value === 'free') return;
    const [w, h] = value.split(':').map(Number);
    let width = .9, height = width * dimensions.width / dimensions.height / (w / h);
    if (height > .9) { height = .9; width = height * dimensions.height / dimensions.width * (w / h); }
    setCrop({ x: (1 - width) / 2, y: (1 - height) / 2, width, height });
  }
  function beginCrop(event: PointerEvent<HTMLElement>, mode: string) {
    if (blocked) return;
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    cropDrag.current = { x: event.clientX, y: event.clientY, rect: crop, mode };
  }
  function moveCrop(event: PointerEvent<HTMLElement>) {
    const drag = cropDrag.current, rect = cropImageRef.current?.getBoundingClientRect();
    if (!drag || !rect) return;
    const dx = (event.clientX - drag.x) / rect.width, dy = (event.clientY - drag.y) / rect.height;
    if (drag.mode === 'move') { setCrop({ ...drag.rect, x: clamp(drag.rect.x + dx, 0, 1 - drag.rect.width), y: clamp(drag.rect.y + dy, 0, 1 - drag.rect.height) }); return; }
    setCropRatio('free');
    const left = drag.mode.includes('w') ? clamp(drag.rect.x + dx, 0, drag.rect.x + drag.rect.width - .05) : drag.rect.x;
    const top = drag.mode.includes('n') ? clamp(drag.rect.y + dy, 0, drag.rect.y + drag.rect.height - .05) : drag.rect.y;
    const right = drag.mode.includes('e') ? clamp(drag.rect.x + drag.rect.width + dx, left + .05, 1) : drag.rect.x + drag.rect.width;
    const bottom = drag.mode.includes('s') ? clamp(drag.rect.y + drag.rect.height + dy, top + .05, 1) : drag.rect.y + drag.rect.height;
    setCrop({ x: left, y: top, width: right - left, height: bottom - top });
  }
  async function download() {
    const data = await editData();
    const link = document.createElement('a'); link.href = data ?? `${image.url}?download=1`; link.download = data ? 'peto-chinh-sua.png' : '';
    stageRef.current?.append(link); link.click(); link.remove();
  }
  async function share() {
    const data = await editData();
    const response = await fetch(data ?? image.url); if (!response.ok) throw new Error('Chưa tải được ảnh để chia sẻ.');
    const file = new File([await response.blob()], 'peto.png', { type: data ? 'image/png' : image.mime });
    if (navigator.canShare?.({ files: [file] }) && navigator.share) {
      try { await navigator.share({ files: [file] }); } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) throw error; }
    } else { await download(); setNotice('Trình duyệt chưa hỗ trợ chia sẻ tệp. Ảnh đã được tải xuống để bạn chia sẻ.'); }
  }

  return <div className={'image-workspace' + (!panelOpen ? ' panel-hidden' : '')} onKeyDown={event => { if (event.key === 'Escape' && tool === 'crop') { event.preventDefault(); event.stopPropagation(); if (!blocked) setTool('info'); } }}>
    <section className="workspace-main">
      <div className="workspace-tools" role="toolbar" aria-label="Công cụ ảnh">
        {(['info', 'palette', 'crop', 'brush'] as const).map(value => <button key={value} type="button" aria-label={TOOL_LABELS[value]} title={TOOL_LABELS[value]} aria-pressed={tool === value} disabled={blocked || !ready} onClick={() => { setComparing(false); if (strokes.length && value !== 'brush') { setNotice('Bạn áp dụng hoặc xóa nét vẽ trước khi đổi công cụ nhé.'); return; } setTool(value); setPanelOpen(true); setNotice(null); }}><StudioIcon name={value} /></button>)}
      </div>
      <div className="workspace-body">
      <div className="workspace-topbar" style={{ width: controlWidth }}>
        <button type="button" className="workspace-round" aria-label="Quay lại" onClick={onClose}><StudioIcon name="back" /></button>
        <div className="workspace-zoom"><button type="button" aria-label="Thu nhỏ ảnh" disabled={zoom <= .5} onClick={() => setZoom(value => Math.max(.5, value - .25))}><StudioIcon name="minus" /></button><button type="button" aria-label="Vừa khung" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button><button type="button" aria-label="Phóng to ảnh" disabled={zoom >= 3} onClick={() => setZoom(value => Math.min(3, value + .25))}><StudioIcon name="plus" /></button></div>
        <button type="button" className="workspace-round" aria-label={panelOpen ? 'Ẩn bảng công cụ' : 'Hiện bảng công cụ'} title={panelOpen ? 'Ẩn bảng công cụ' : 'Hiện bảng công cụ'} aria-controls="workspace-panel" aria-expanded={panelOpen} onClick={() => setPanelOpen(value => !value)}><StudioIcon name="panel" /></button>
      </div>
      <div ref={stageRef} className="workspace-canvas">
        <div className="workspace-canvas-inner">
          {comparing ? <ImageComparison sources={imagineSources(job)} image={{ ...image, url: src }} prompt={job.prompt} startComparing hideToggle /> : <div className="workspace-picture" style={{ width: displayWidth, height: displayHeight }}>
            <img src={src} alt={job.prompt} draggable={false} onLoad={event => setDimensions({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} onError={() => { setDimensions({ width: 0, height: 0 }); setNotice('Chưa tải được ảnh. Bạn đóng và mở lại ảnh nhé.'); }} />
            {tool === 'brush' && ready && <canvas ref={canvasRef} width={dimensions.width} height={dimensions.height} aria-label="Vẽ ghi chú lên ảnh" onPointerDown={beginStroke} onPointerMove={moveStroke} onPointerUp={() => { strokeRef.current = null; }} onPointerCancel={() => { strokeRef.current = null; }} />}
          </div>}
        </div>
      </div>
      <div className="workspace-edit-dock" style={{ width: controlWidth }}>
        <div className="workspace-source-chip"><span title={job.prompt}>{changed ? 'Bản chỉnh sửa · chưa lưu' : job.prompt}</span><button type="button" disabled={blocked} onClick={() => { if (!changed) onUse(); else void execute(async () => onUse(await editData())); }}>Sửa ảnh này</button></div>
        <form onSubmit={event => { event.preventDefault(); if (prompt.trim() && !blocked) void execute(async () => onSubmit(prompt.trim(), aspect, await editData())); }}>
          <textarea aria-label="Mô tả chỉnh sửa ảnh" placeholder="Mô tả chỉnh sửa bạn muốn thực hiện…" enterKeyHint="send" rows={1} value={prompt} disabled={blocked} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (prompt.trim() && !blocked) void execute(async () => onSubmit(prompt.trim(), aspect, await editData())); } }} />
          <button type="submit" disabled={!prompt.trim() || blocked} aria-label="Gửi chỉnh sửa ảnh"><StudioIcon name="arrowUp" /></button>
        </form>
      </div>
      </div>
    </section>
    <aside className="workspace-panel" id="workspace-panel">
      <h2 className="workspace-panel-title">{TOOL_LABELS[tool]}</h2>
      <div className="workspace-panel-body">
        {tool === 'info' && <>
          <p className="workspace-label">{original ? 'Ảnh tham chiếu' : 'Ảnh đã tạo'}</p><p className="workspace-prompt">{job.prompt}</p>
          {ready && !comparing && <p className="workspace-dimensions" aria-label="Kích thước ảnh thực tế">{dimensions.width} × {dimensions.height}</p>}
          <p className="workspace-label">{job.resolution.toUpperCase()} · {job.quality === 'low' ? 'Nhanh' : 'Chi tiết'}</p>
          {!original && job.images.length > 1 && <div className="workspace-navigation"><button type="button" disabled={index === 0 || blocked} onClick={() => onNavigate(index - 1)}>← Trước</button><span>{index + 1}/{job.images.length}</span><button type="button" disabled={index === job.images.length - 1 || blocked} onClick={() => onNavigate(index + 1)}>Sau →</button></div>}
          {!original && imagineSources(job).length > 0 && <button type="button" className="workspace-wide" aria-pressed={comparing} onClick={() => setComparing(value => !value)}>So sánh trước / sau</button>}
        </>}
        {tool === 'palette' && <>
          <p className="workspace-label">Bảng màu</p>
          {palette.length > 0 && <div className="palette-strip">{palette.map(hex => <button type="button" key={hex} style={{ background: hex }} title={hex} aria-label={`Màu ${hex}`} onClick={() => { setColor(hex); setTool('brush'); }} />)}</div>}
          <button type="button" className="workspace-wide" disabled={blocked} onClick={() => void execute(async () => { const colors = await extractPalette(src); setPalette(colors); })}>Lấy màu từ ảnh</button>
          <p className="workspace-label">Khám phá</p><div className="palette-presets">{PALETTES.map(item => <button type="button" key={item.name} disabled={blocked} onClick={() => { setPalette(item.colors); appendPrompt(`Áp dụng bảng màu ${item.name.toLowerCase()} (${item.colors.join(', ')}), giữ chủ thể và bố cục ảnh.`); }}><span className="palette-strip">{item.colors.map(hex => <i key={hex} style={{ background: hex }} />)}</span><span>{item.name}</span></button>)}</div>
          <p className="workspace-label">Chọn bảng màu để thêm vào mô tả, rồi gửi khi bạn sẵn sàng.</p>
        </>}
        {tool === 'brush' && <>
          <p className="workspace-label">Cỡ bút</p><input className="brush-size" type="range" aria-label="Cỡ bút" min="2" max="64" value={brushSize} onChange={event => setBrushSize(Number(event.target.value))} />
          <div className="seg"><button type="button" aria-pressed={!erasing} onClick={() => setErasing(false)}>Vẽ</button><button type="button" aria-pressed={erasing} onClick={() => setErasing(true)}>Tẩy nét vẽ</button></div>
          <p className="workspace-label">Màu</p><div className="brush-colors">{COLORS.map(hex => <button key={hex} type="button" style={{ background: hex }} aria-label={`Chọn màu ${hex}`} aria-pressed={color === hex} onClick={() => setColor(hex)} />)}<input type="color" aria-label="Màu tùy chọn" value={color} onChange={event => setColor(event.target.value)} /></div>
          <div className="brush-history"><button type="button" aria-label="Hoàn tác nét vẽ" disabled={!strokes.length || blocked} onClick={() => { setRedoStrokes(current => [...current, strokes[strokes.length - 1]]); setStrokes(current => current.slice(0, -1)); }}><StudioIcon name="undo" /></button><button type="button" aria-label="Làm lại nét vẽ" disabled={!redoStrokes.length || blocked} onClick={() => { setStrokes(current => [...current, redoStrokes[redoStrokes.length - 1]]); setRedoStrokes(current => current.slice(0, -1)); }}><StudioIcon name="redo" /></button><button type="button" aria-label="Xóa nét vẽ" disabled={!strokes.length || blocked} onClick={() => { setStrokes([]); setRedoStrokes([]); }}><StudioIcon name="trash" /></button></div>
          <button type="button" className="workspace-wide" disabled={!strokes.length || blocked} onClick={() => void execute(async () => saveVersion(await renderEdit(src, FULL_CROP, strokes)))}>Áp dụng nét vẽ</button><p className="workspace-label">Bút vẽ thêm nét trực tiếp lên ảnh; tẩy chỉ xóa nét đã vẽ.</p>
        </>}
      </div>
      <div className="workspace-panel-bottom">
        {(version > 0 || versions.length > 1) && <div className="brush-history"><button type="button" aria-label="Hoàn tác chỉnh sửa" disabled={version === 0 || blocked || strokes.length > 0} onClick={() => setVersion(value => value - 1)}><StudioIcon name="undo" /></button><button type="button" aria-label="Làm lại chỉnh sửa" disabled={version === versions.length - 1 || blocked || strokes.length > 0} onClick={() => setVersion(value => value + 1)}><StudioIcon name="redo" /></button></div>}
        <label className="workspace-aspect">Tỉ lệ ảnh <select aria-label="Tỉ lệ ảnh chỉnh sửa" value={aspect} disabled={blocked} onChange={event => setAspect(event.target.value)}>{RATIOS.map(ratio => <option key={ratio} value={ratio}>{ratio === 'auto' ? 'Theo ảnh nguồn' : ratio}</option>)}</select></label>
        <button type="button" className="workspace-wide" disabled={blocked || !canAdd || (alreadyAdded && !changed)} onClick={() => { if (!changed) onAdd(); else void execute(async () => onAdd(await editData())); }}><StudioIcon name="plus" />Thêm làm tham chiếu</button>
        <button type="button" className="workspace-share" disabled={blocked || !ready} onClick={() => void execute(share)}><StudioIcon name="share" />Chia sẻ</button>
        <div className="workspace-footer-actions">{!original && <button type="button" className={liked ? 'liked' : ''} aria-label="Thích" aria-pressed={liked} onClick={onLike}><StudioIcon name="heart" /></button>}<a href={src !== image.url ? src : `${image.url}?download=1`} download={src !== image.url ? 'peto-chinh-sua.png' : true} aria-label="Tải ảnh xuống" onClick={event => { if (strokes.length) { event.preventDefault(); void execute(download); } }}><StudioIcon name="download" /></a></div>
        {(notice || likeError) && <p className="workspace-notice" role="alert">{likeError ?? notice}</p>}
      </div>
    </aside>
    {tool === 'crop' && <div className="workspace-crop-overlay">
      <div className="crop-picture"><img ref={cropImageRef} src={src} alt="Ảnh để cắt" draggable={false} /><div className="crop-box" style={{ left: `${crop.x * 100}%`, top: `${crop.y * 100}%`, width: `${crop.width * 100}%`, height: `${crop.height * 100}%` }} tabIndex={0} role="group" aria-label="Vùng cắt, dùng phím mũi tên để di chuyển" onKeyDown={event => { const delta = event.shiftKey ? .05 : .01; const moves: Record<string, [number, number]> = { ArrowLeft: [-delta, 0], ArrowRight: [delta, 0], ArrowUp: [0, -delta], ArrowDown: [0, delta] }; const move = moves[event.key]; if (move && !blocked) { event.preventDefault(); setCrop(current => ({ ...current, x: clamp(current.x + move[0], 0, 1 - current.width), y: clamp(current.y + move[1], 0, 1 - current.height) })); } }} onPointerDown={event => beginCrop(event, 'move')} onPointerMove={moveCrop} onPointerUp={() => { cropDrag.current = null; }} onPointerCancel={() => { cropDrag.current = null; }}>
        {['nw', 'ne', 'sw', 'se'].map(handle => <button type="button" key={handle} className={`crop-handle ${handle}`} aria-label={`Góc cắt ${handle}`} onPointerDown={event => beginCrop(event, handle)} onPointerMove={moveCrop} onPointerUp={() => { cropDrag.current = null; }} onPointerCancel={() => { cropDrag.current = null; }} />)}
      </div></div>
      {notice && <p className="crop-notice" role="alert">{notice}</p>}
      <div className="crop-actions"><select aria-label="Tỉ lệ cắt" value={cropRatio} disabled={blocked} onChange={event => setRatio(event.target.value)}>{['free', '1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'].map(ratio => <option key={ratio} value={ratio}>{ratio === 'free' ? 'Tự do' : ratio}</option>)}</select><button type="button" disabled={blocked} onClick={() => setTool('info')}><StudioIcon name="close" />Hủy cắt</button><button type="button" className="crop-confirm" disabled={blocked} onClick={() => void execute(async () => { saveVersion(await renderEdit(src, crop)); setTool('info'); })}><StudioIcon name="check" />Cắt</button></div>
    </div>}
  </div>;
}
