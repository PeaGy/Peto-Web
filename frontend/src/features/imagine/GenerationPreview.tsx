import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import type { ImagineImage } from '../../shared/api/api';
import './generationPreview.css';

/** Giữ cùng ô ảnh từ lúc chờ tới khi kết quả đã tải xong; không giả lập tiến độ AI. */
export default function GenerationPreview({ images, count, aspect, sourceUrl, pending, paused, status, elapsed, prompt, onOpen }: {
  images: ImagineImage[];
  count: number;
  aspect: string;
  sourceUrl?: string;
  pending: boolean;
  paused: boolean;
  status?: string;
  elapsed?: ReactNode;
  prompt: string;
  onOpen?: (index: number) => void;
}) {
  const [sourceRatio, setSourceRatio] = useState(1);
  const [hidden, setHidden] = useState(document.hidden);
  useEffect(() => {
    const change = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', change);
    return () => document.removeEventListener('visibilitychange', change);
  }, []);
  useEffect(() => {
    setSourceRatio(1);
  }, [sourceUrl, aspect]);
  const [width, height] = aspect.split(':').map(Number);
  // Tự động chưa có kích thước thật: dùng khung trung tính, không đoán độ phân giải đầu ra.
  const ratio = aspect !== 'auto' && width > 0 && height > 0 ? width / height : sourceRatio;
  const slots = pending ? Math.max(count, images.length) : images.length;
  const style = { '--generation-ratio': ratio, '--generation-columns': slots === 1 ? 1 : 2 } as CSSProperties;
  return <div className="generation-preview" data-pending={pending} data-paused={paused || hidden} style={style}>
    <div className="generation-grid imagine-thumbs">
      {Array.from({ length: slots }, (_, index) => <GenerationTile key={index} image={images[index]} sourceUrl={pending ? sourceUrl : undefined}
        prompt={prompt} index={index} onOpen={onOpen} onSourceSize={aspect === 'auto' && index === 0 ? setSourceRatio : undefined} />)}
    </div>
    {pending && <div className="generation-status"><span role="status" aria-live="polite">{status}</span>{elapsed}</div>}
  </div>;
}

function GenerationTile({ image, sourceUrl, prompt, index, onOpen, onSourceSize }: {
  image?: ImagineImage; sourceUrl?: string; prompt: string; index: number; onOpen?: (index: number) => void; onSourceSize?: (ratio: number) => void;
}) {
  const picture = useRef<HTMLImageElement>(null);
  const version = useRef(0);
  const [loaded, setLoaded] = useState('');
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const url = image?.url;
  useEffect(() => {
    const token = ++version.current;
    setFailed(false);
    const node = picture.current;
    if (!node || !url) return;
    const ready = async () => {
      try {
        if (node.decode) await node.decode();
        if (version.current === token && node.naturalWidth > 0) setLoaded(url);
      } catch { if (version.current === token) setFailed(true); }
    };
    const error = () => { if (version.current === token) setFailed(true); };
    node.addEventListener('load', ready);
    node.addEventListener('error', error);
    if (node.complete) { if (node.naturalWidth > 0) void ready(); else error(); }
    return () => { version.current++; node.removeEventListener('load', ready); node.removeEventListener('error', error); };
  }, [url, attempt]);
  const ready = !!url && loaded === url && !failed;
  return <div className="generation-tile" data-ready={ready} data-failed={failed}>
    <div className="generation-surface" aria-hidden="true">
      {sourceUrl && <img className="generation-source" src={sourceUrl} alt="" onLoad={event => {
        const { naturalWidth, naturalHeight } = event.currentTarget;
        // Đọc từ ảnh đã hiển thị, không tải trước mọi ảnh tham chiếu trong lịch sử.
        if (naturalWidth && naturalHeight) onSourceSize?.(Math.min(2.5, Math.max(.45, naturalWidth / naturalHeight)));
      }} />}
      <span className="generation-grain" />
      <span className="generation-drift"><span /><span /><span /></span>
    </div>
    <button type="button" className="imagine-thumb generation-result" disabled={!image}
      aria-label={image ? `Xem ảnh ${index + 1}: ${prompt}` : `Ảnh ${index + 1} đang tạo`}
      onClick={() => onOpen?.(index)}>
      {image && <img ref={picture} key={attempt} src={image.url} alt={prompt} loading="lazy" decoding="async" />}
      {image && <span className="image-open-hint">Xem ảnh ↗</span>}
    </button>
    {failed && <div className="generation-image-error"><span>Chưa tải được ảnh</span><button type="button" onClick={() => {
      setFailed(false); setLoaded(''); setAttempt(value => value + 1);
    }}>Tải lại ảnh</button></div>}
  </div>;
}
