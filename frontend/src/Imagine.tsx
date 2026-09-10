import { useCallback, useEffect, useRef, useState } from "react";
import {
  UnauthorizedError, createImagineJob, deleteImagineJob, listImagineJobs,
  type ImagineJob, type ImagineQuality, type ImagineResolution,
} from "./api";

const QUALITY_KEY = "peto-imagine-quality";
const RATIO_KEY = "peto-imagine-ratio";
const RES_KEY = "peto-imagine-res";
const COUNT_KEY = "peto-imagine-n";
const RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "2:1", "1:2"];
const IDEAS = [
  { label: "Một nhân vật", style: "character", prompt: "Mèo trắng đội mũ phù thủy màu tím, minh họa sách truyện, ánh sáng dịu và những ngôi sao nhỏ." },
  { label: "Một thế giới", style: "landscape", prompt: "Ngôi nhà nhỏ bên hồ trên một hành tinh xa, trời hoàng hôn màu hồng, phong cảnh điện ảnh yên bình." },
  { label: "Một ý tưởng", style: "poster", prompt: "Áp phích cho ban nhạc giả tưởng, phong cách synthwave, mặt trời và những đường nét hình học tím cam." },
];

function readStored<T extends string>(key: string, allowed: T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return allowed.includes(value as T) ? value as T : fallback;
  } catch { return fallback; }
}
function writeStored(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch {}
}
function SparkleIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m12 3 1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8L12 3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" fill="currentColor" />
  </svg>;
}
function IdeaArt({ style }: { style: string }) {
  return <span className={"idea-art " + style} aria-hidden="true">
    <svg viewBox="0 0 200 100" fill="none">
      {style === "character" ? <>
        <path d="M73 79V49l16 11h23l15-11v30c0 15-54 15-54 0Z" fill="#f2e5ff" />
        <path d="m74 55 32-47 17 47H74Z" fill="#9872d4" />
        <path d="M64 55h72" stroke="#c2a1f0" strokeWidth="6" strokeLinecap="round" />
        <path d="M88 75h1m21 0h1" stroke="#4c365f" strokeWidth="4" strokeLinecap="round" />
        <path d="m149 23 2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6Z" fill="#f6d398" />
      </> : style === "landscape" ? <>
        <circle cx="142" cy="32" r="18" fill="#f3b3a6" />
        <path d="m0 72 44-36 47 38 30-24 79 36v14H0Z" fill="#605b86" />
        <path d="m0 89 76-31 66 30 58-23v35H0Z" fill="#383c60" />
        <path d="M86 70h21v18H86Z" fill="#e5b692" /><path d="m81 71 16-14 15 14H81Z" fill="#242942" />
        <path d="M0 91h200" stroke="#b7a5d9" strokeWidth="2" />
      </> : <>
        <circle cx="100" cy="42" r="30" fill="#ecaf8d" />
        <path d="M67 41h66M66 48h68M68 55h64M71 62h58" stroke="#805887" strokeWidth="3" />
        <path d="m0 100 69-27h62l69 27M100 73v27M82 73l-32 27m68-27 32 27M29 89h142M48 81h104" stroke="#d4a1d7" strokeWidth="1.2" />
      </>}
    </svg>
  </span>;
}
const ratioLabel = (value: string) => value === "auto" ? "Tự động" : value;
const qualityLabel = (value: string) => value === "low" ? "Nhanh" : "Chi tiết";

export default function Imagine({ active, onUnauthorized, onOpenSidebar }: {
  active: boolean;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [quality, setQuality] = useState<ImagineQuality>(() => readStored(QUALITY_KEY, ["low", "medium"], "low"));
  const [resolution, setResolution] = useState<ImagineResolution>(() => readStored(RES_KEY, ["1k", "2k"], "1k"));
  const [aspect, setAspect] = useState(() => readStored(RATIO_KEY, RATIOS, "auto"));
  const [count, setCount] = useState(() => Number(readStored(COUNT_KEY, ["1", "2", "3", "4"], "1")));
  const [jobs, setJobs] = useState<ImagineJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ job: ImagineJob; index: number } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ImagineJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const galleryRef = useRef<HTMLDivElement>(null);
  const lightboxRef = useRef<HTMLDialogElement>(null);
  const deleteRef = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const deleteInFlight = useRef(false);
  const activeRef = useRef(active);
  const loadVersion = useRef(0);

  const loadJobs = useCallback(async () => {
    const version = ++loadVersion.current;
    setLoading(true);
    setLoadFailed(false);
    try {
      const rows = await listImagineJobs();
      if (version === loadVersion.current) setJobs(rows);
    } catch (err) {
      if (version !== loadVersion.current) return;
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setLoadFailed(true);
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }, [onUnauthorized]);
  useEffect(() => {
    void loadJobs();
    return () => { loadVersion.current += 1; };
  }, [loadJobs]);
  useEffect(() => {
    activeRef.current = active;
    if (!active) { setLightbox(null); setDeleteTarget(null); }
  }, [active]);
  useEffect(() => {
    if (active && lightbox) lightboxRef.current?.showModal();
    else lightboxRef.current?.close();
  }, [active, lightbox]);
  useEffect(() => {
    if (active && deleteTarget) deleteRef.current?.showModal();
    else deleteRef.current?.close();
  }, [active, deleteTarget]);
  useEffect(() => writeStored(QUALITY_KEY, quality), [quality]);
  useEffect(() => writeStored(RES_KEY, resolution), [resolution]);
  useEffect(() => writeStored(RATIO_KEY, aspect), [aspect]);
  useEffect(() => writeStored(COUNT_KEY, String(count)), [count]);

  async function generate() {
    const text = prompt.trim();
    if (!text || inFlight.current || loading || loadFailed) return;
    inFlight.current = true;
    setError(null);
    setGenerating(true);
    galleryRef.current?.scrollTo({ top: 0 });
    try {
      const job = await createImagineJob({ prompt: text, quality, resolution, aspect_ratio: aspect, n: count });
      setJobs((prev) => [job, ...prev]);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Peto chưa tạo được ảnh. Thử lại nhé.");
    } finally {
      inFlight.current = false;
      setGenerating(false);
      if (activeRef.current) textareaRef.current?.focus();
    }
  }
  async function removeJob() {
    if (!deleteTarget || deleteInFlight.current) return;
    const id = deleteTarget.id;
    deleteInFlight.current = true;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteImagineJob(id);
      setJobs((prev) => prev.filter((job) => job.id !== id));
      setLightbox((current) => current?.job.id === id ? null : current);
      setDeleteTarget(null);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setDeleteError(err instanceof Error ? err.message : "Chưa xóa được ảnh. Thử lại nhé.");
    } finally {
      deleteInFlight.current = false;
      setDeleting(false);
    }
  }
  function reuse(job: ImagineJob) {
    setPrompt(job.prompt);
    setQuality(job.quality);
    setResolution(job.resolution);
    setAspect(job.aspect_ratio);
    textareaRef.current?.focus();
  }
  const lightboxImage = lightbox?.job.images[lightbox.index];
  const controlsDisabled = generating || loading || loadFailed;

  return <main className="imagine" hidden={!active}>
    <header className="chat-header">
      <button type="button" className="menu-btn" aria-label="Mở menu" onClick={onOpenSidebar}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
      </button>
      <span className="imagine-mark"><SparkleIcon /></span>
      <div className="header-copy"><strong>Peto tạo ảnh</strong><span className="subtitle">Từ một ý tưởng đến hình ảnh của bạn</span></div>
    </header>

    <div className="imagine-gallery" ref={galleryRef}>
      {loading && <p className="loading-chat" role="status">Đang mở bộ ảnh của bạn…</p>}
      {loadFailed && <div className="studio-load-error" role="alert"><p>Chưa tải được ảnh đã tạo.</p><button type="button" onClick={() => void loadJobs()}>Thử tải lại</button></div>}
      {!loading && !loadFailed && jobs.length === 0 && !generating && <section className="studio-welcome">
        <span className="studio-eyebrow"><SparkleIcon /> Góc sáng tạo của bạn</span>
        <h1>Bạn tưởng tượng.<br /><span>Peto vẽ nên.</span></h1>
        <p>Kể Peto nghe về bức ảnh trong đầu bạn.<br />Thêm màu sắc, phong cách, một chút cảm hứng.</p>
        <div className="studio-ideas">
          {IDEAS.map((idea) => <button type="button" className="studio-idea" key={idea.style} onClick={() => { setPrompt(idea.prompt); textareaRef.current?.focus(); }}>
            <IdeaArt style={idea.style} /><span><strong>{idea.label}</strong><span>{idea.prompt}</span></span>
          </button>)}
        </div>
      </section>}
      {generating && <section className="generation-pending" role="status" aria-live="polite">
        <div className="generation-copy"><span className="imagine-mark"><SparkleIcon /></span><div><strong>Peto đang tạo {count} ảnh…</strong><p>Bạn có thể sang trò chuyện trong lúc đợi.</p></div></div>
        <p className="pending-prompt">{prompt}</p>
        <div className="imagine-thumbs" aria-hidden="true">{Array.from({ length: count }, (_, index) => <div className="image-placeholder" key={index}><SparkleIcon /></div>)}</div>
      </section>}
      {jobs.length > 0 && <div className="studio-library-head"><h1>Ảnh của bạn</h1><span>{jobs.length} lượt gần đây</span></div>}
      {jobs.map((job) => <section key={job.id} className="imagine-job">
        <div className="imagine-job-head">
          <div className="imagine-job-copy"><p className="imagine-prompt">{job.prompt}</p><div className="imagine-meta">
            <span>{qualityLabel(job.quality)}</span><span>{job.resolution.toUpperCase()}</span><span>{ratioLabel(job.aspect_ratio)}</span><span>{job.images.length} ảnh</span>
            {job.created_at && <time dateTime={new Date(job.created_at * 1000).toISOString()}>{new Date(job.created_at * 1000).toLocaleDateString("vi-VN", { day: "numeric", month: "short" })}</time>}
          </div></div>
          <div className="imagine-job-actions">
            <button type="button" disabled={generating} onClick={() => reuse(job)}>Dùng lại mô tả</button>
            <button type="button" className="imagine-delete" aria-label={"Xóa lượt ảnh: " + job.prompt} onClick={() => { setDeleteError(null); setDeleteTarget(job); }}>Xóa</button>
          </div>
        </div>
        <div className="imagine-thumbs">{job.images.map((image, index) => <button key={image.id} type="button" className="imagine-thumb" aria-label={"Xem ảnh " + (index + 1) + ": " + job.prompt} onClick={() => setLightbox({ job, index })}>
          <img src={image.url} alt={job.prompt} loading="lazy" decoding="async" /><span className="image-open-hint">Xem ảnh ↗</span>
        </button>)}</div>
      </section>)}
    </div>

    {error && <div className="error" role="alert">{error}<button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button></div>}
    <form className="composer-wrap studio-composer-wrap" onSubmit={(event) => { event.preventDefault(); void generate(); }}>
      <div className="composer imagine-composer">
        <label className="studio-prompt-label" htmlFor="image-prompt">Bức ảnh bạn muốn tạo</label>
        <textarea id="image-prompt" ref={textareaRef} value={prompt} rows={2} placeholder="Một chú mèo trên mặt trăng, màu nước, ánh sáng dịu…" disabled={generating} onChange={(event) => setPrompt(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void generate(); }
        }} />
        <div className="imagine-controls">
          <div className="seg" role="group" aria-label="Mức chi tiết">
            {(["low", "medium"] as const).map((value) => <button type="button" key={value} className={quality === value ? "on" : ""} aria-pressed={quality === value} disabled={controlsDisabled} title={value === "low" ? "Tạo nhanh, phù hợp để thử ý tưởng" : "Dành thêm thời gian cho chi tiết"} onClick={() => setQuality(value)}>{qualityLabel(value)}</button>)}
          </div>
          <div className="seg" role="group" aria-label="Độ phân giải">
            {(["1k", "2k"] as const).map((value) => <button type="button" key={value} className={resolution === value ? "on" : ""} aria-pressed={resolution === value} disabled={controlsDisabled} onClick={() => setResolution(value)}>{value.toUpperCase()}</button>)}
          </div>
          <label className="effort-select"><span className="effort-label">Tỉ lệ</span><select aria-label="Tỉ lệ" value={aspect} disabled={controlsDisabled} onChange={(event) => setAspect(event.target.value)}>{RATIOS.map((ratio) => <option key={ratio} value={ratio}>{ratioLabel(ratio)}</option>)}</select></label>
          <label className="effort-select"><span className="effort-label">Số ảnh</span><select aria-label="Số ảnh" value={count} disabled={controlsDisabled} onChange={(event) => setCount(Number(event.target.value))}>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n} ảnh</option>)}</select></label>
        </div>
        <div className="composer-bar"><p className="imagine-hint">{generating ? "Peto sẽ giữ ảnh ở đây khi hoàn tất." : "Enter để tạo · Shift + Enter để xuống dòng"}</p><button type="submit" className="send" disabled={!prompt.trim() || controlsDisabled}><SparkleIcon />{generating ? "Đang tạo…" : "Tạo ảnh"}</button></div>
      </div>
    </form>

    <dialog ref={lightboxRef} className="imagine-lightbox" aria-label="Xem ảnh đã tạo" onCancel={() => setLightbox(null)} onClick={(event) => { if (event.target === event.currentTarget) setLightbox(null); }}>
      {lightbox && lightboxImage && <div className="imagine-lightbox-card">
        <div className="lightbox-head"><span>Peto tạo ảnh · {lightbox.index + 1} / {lightbox.job.images.length}</span><button type="button" autoFocus className="dialog-close" aria-label="Đóng ảnh" onClick={() => setLightbox(null)}>×</button></div>
        <img src={lightboxImage.url} alt={lightbox.job.prompt} />
        <p>{lightbox.job.prompt}</p>
        <div className="imagine-lightbox-actions">
          {lightbox.job.images.length > 1 && <div className="lightbox-navigation"><button type="button" disabled={lightbox.index === 0} onClick={() => setLightbox({ ...lightbox, index: lightbox.index - 1 })}>← Trước</button><button type="button" disabled={lightbox.index === lightbox.job.images.length - 1} onClick={() => setLightbox({ ...lightbox, index: lightbox.index + 1 })}>Sau →</button></div>}
          <a href={lightboxImage.url + "?download=1"} download>Tải ảnh xuống ↓</a>
        </div>
      </div>}
    </dialog>
    <dialog ref={deleteRef} className="confirm-dialog" aria-labelledby="delete-images-title" onCancel={(event) => { event.preventDefault(); if (!deleting) setDeleteTarget(null); }}>
      <h2 id="delete-images-title">Xóa lượt ảnh này?</h2>
      <p>{deleteTarget?.images.length} ảnh và mô tả của lượt này sẽ bị xóa. Bạn không thể khôi phục sau khi xóa.</p>
      <p className="delete-prompt-preview">{deleteTarget?.prompt}</p>
      {deleteError && <p role="alert">{deleteError}</p>}
      <div className="dialog-actions"><button type="button" autoFocus disabled={deleting} onClick={() => setDeleteTarget(null)}>Giữ lại</button><button type="button" className="danger-button" disabled={deleting} onClick={() => void removeJob()}>{deleting ? "Đang xóa…" : "Xóa ảnh"}</button></div>
    </dialog>
  </main>;
}
