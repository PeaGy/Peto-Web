import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  UnauthorizedError, createImagineJob, deleteImagineImage, deleteImagineJob, listImagineJobs, setImagineImageLiked,
  type ImagineImage, type ImagineJob, type ImagineQuality, type ImagineResolution,
} from "./api";
import ImagineLibrary, { HeartIcon } from "./ImagineLibrary";
import StudioMenu from "./StudioMenu";
import { COMPACT_QUERY } from "./characterView";

const QUALITY_KEY = "peto-imagine-quality";
const RATIO_KEY = "peto-imagine-ratio";
const RES_KEY = "peto-imagine-res";
const COUNT_KEY = "peto-imagine-n";
const MAX_SOURCE_BYTES = 8 * 1024 * 1024;
type DraftSource = { name: string; preview: string; upload?: { data: string }; imageId?: string };
const RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "2:1", "1:2"];
const COUNTS = [1, 2, 3, 4];
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
function ImagePlusIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M13 4H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    <path d="m4.5 17 4.2-4.2a1.5 1.5 0 0 1 2.1 0L16 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="9" cy="9" r="1.4" fill="currentColor" />
    <path d="M18 3v6M15 6h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>;
}
function SlidersIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M4 8h9M17 8h3M4 16h3M11 16h9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="15" cy="8" r="2" stroke="currentColor" strokeWidth="1.8" />
    <circle cx="9" cy="16" r="2" stroke="currentColor" strokeWidth="1.8" />
  </svg>;
}
function PhotoIcon() {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3.5" y="3.5" width="17" height="17" rx="4" stroke="currentColor" strokeWidth="1.8" />
    <circle cx="9" cy="9" r="1.5" fill="currentColor" />
    <path d="m4 17 5-5 4 4 2.5-2.5L20 18" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
  </svg>;
}
function ArrowUpIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 19V5M6 11l6-6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}
/** Khung vẽ đúng tỉ lệ đang chọn; "Tự động" là bốn góc khung ngắm. */
function RatioIcon({ value }: { value: string }) {
  if (value === "auto") return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M4 9V6a2 2 0 0 1 2-2h3M15 4h3a2 2 0 0 1 2 2v3M20 15v3a2 2 0 0 1-2 2h-3M9 20H6a2 2 0 0 1-2-2v-3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>;
  const [w, h] = value.split(":").map(Number);
  const width = 16 * w / Math.max(w, h);
  const height = 16 * h / Math.max(w, h);
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x={12 - width / 2} y={12 - height / 2} width={width} height={height} rx="2.5" stroke="currentColor" strokeWidth="1.8" />
  </svg>;
}
/** Cùng mốc 720px với CSS. Môi trường test và trình duyệt cũ có thể không có matchMedia. */
function isCompact() {
  return window.matchMedia?.(COMPACT_QUERY)?.matches === true;
}
function useCompact() {
  const [compact, setCompact] = useState(isCompact);
  useEffect(() => {
    const query = window.matchMedia?.(COMPACT_QUERY);
    if (!query) return;
    const update = () => setCompact(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return compact;
}
function readSourceFile(file: File): Promise<DraftSource> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const preview = String(reader.result ?? "");
      const data = preview.split(",")[1];
      if (!data) return reject(new Error("Không đọc được ảnh. Bạn thử chọn lại nhé."));
      resolve({ name: file.name, preview, upload: { data } });
    };
    reader.onerror = () => reject(new Error("Không đọc được ảnh. Bạn thử chọn lại nhé."));
    reader.readAsDataURL(file);
  });
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

export default function Imagine({ active, onUnauthorized, onOpenSidebar, onJobsChange, focusJobId, onFocusHandled }: {
  active: boolean;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
  onJobsChange?: (jobs: ImagineJob[]) => void;
  focusJobId?: string | null;
  onFocusHandled?: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [source, setSource] = useState<DraftSource | null>(null);
  const [readingSource, setReadingSource] = useState(false);
  const [draggingSource, setDraggingSource] = useState(false);
  const [quality, setQuality] = useState<ImagineQuality>(() => readStored(QUALITY_KEY, ["low", "medium"], "low"));
  const [resolution, setResolution] = useState<ImagineResolution>(() => readStored(RES_KEY, ["1k", "2k"], "1k"));
  const [aspect, setAspect] = useState(() => readStored(RATIO_KEY, RATIOS, "auto"));
  const [count, setCount] = useState(() => Number(readStored(COUNT_KEY, ["1", "2", "3", "4"], "1")));
  const [jobs, setJobs] = useState<ImagineJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ job: ImagineJob; index: number; original?: boolean } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ImagineJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Chỉ có tác dụng trên điện thoại: thanh thu gọn mở ra khi đang nhập hoặc chỉnh tùy chọn.
  const [expanded, setExpanded] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [likeError, setLikeError] = useState<string | null>(null);
  const compact = useCompact();
  const dockRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sourceVersion = useRef(0);
  const dragDepth = useRef(0);
  const galleryRef = useRef<HTMLDivElement>(null);
  const lightboxRef = useRef<HTMLDialogElement>(null);
  const deleteRef = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const deleteInFlight = useRef(false);
  const activeRef = useRef(active);
  const loadVersion = useRef(0);

  useEffect(() => {
    const dock = dockRef.current;
    const stage = dock?.parentElement;
    if (!dock || !stage || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      if (dock.offsetHeight) stage.style.setProperty("--studio-dock-height", `${dock.offsetHeight}px`);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(dock);
    return () => observer.disconnect();
  }, []);

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
    return () => { loadVersion.current += 1; sourceVersion.current += 1; };
  }, [loadJobs]);
  useEffect(() => {
    activeRef.current = active;
    if (!active) { setLightbox(null); setDeleteTarget(null); setDraggingSource(false); setExpanded(false); setLibraryOpen(false); dragDepth.current = 0; }
  }, [active]);
  useEffect(() => {
    if (active && lightbox) lightboxRef.current?.showModal();
    else lightboxRef.current?.close();
  }, [active, lightbox]);
  useEffect(() => {
    if (active && deleteTarget) deleteRef.current?.showModal();
    else deleteRef.current?.close();
  }, [active, deleteTarget]);
  useEffect(() => {
    if (!expanded) return;
    const outside = (event: PointerEvent) => {
      if (dockRef.current?.contains(event.target as Node)) return;
      setExpanded(false);
      // Điện thoại: bỏ focus để bàn phím ẩn cùng lúc thanh thu lại.
      if (isCompact() && document.activeElement === textareaRef.current) textareaRef.current?.blur();
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [expanded]);
  // Cột trái ở App.tsx liệt kê danh sách này, nhưng Imagine vẫn giữ trạng thái gốc
  // để lượt tạo ảnh đang chạy không mất khi người dùng sang tab trò chuyện.
  useEffect(() => { onJobsChange?.(jobs); }, [jobs, onJobsChange]);
  useEffect(() => {
    if (!active || !focusJobId) return;
    galleryRef.current?.querySelector(`[data-job-id="${focusJobId}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    onFocusHandled?.();
  }, [active, focusJobId, onFocusHandled]);
  useEffect(() => writeStored(QUALITY_KEY, quality), [quality]);
  useEffect(() => writeStored(RES_KEY, resolution), [resolution]);
  useEffect(() => writeStored(RATIO_KEY, aspect), [aspect]);
  useEffect(() => writeStored(COUNT_KEY, String(count)), [count]);
  useEffect(() => setLikeError(null), [lightbox]);

  async function chooseSource(files: FileList | File[]) {
    if (inFlight.current || files.length === 0) return;
    if (files.length > 1) { setError("Chọn một ảnh gốc cho mỗi lượt sửa nhé."); return; }
    const file = files[0];
    if (!/^image\/(png|jpeg|webp)$/i.test(file.type) && !(file.type === "" && /\.(png|jpe?g|webp)$/i.test(file.name))) {
      setError("Peto nhận ảnh PNG, JPEG hoặc WebP để chỉnh sửa."); return;
    }
    if (file.size === 0 || file.size > MAX_SOURCE_BYTES) { setError("Ảnh gốc phải có nội dung và không vượt quá 8 MB."); return; }
    const version = ++sourceVersion.current;
    setReadingSource(true);
    setError(null);
    try {
      const image = await readSourceFile(file);
      if (version !== sourceVersion.current) return;
      setSource(image);
      if (activeRef.current) textareaRef.current?.focus();
    } catch (err) {
      if (version === sourceVersion.current) setError(err instanceof Error ? err.message : "Không đọc được ảnh.");
    } finally {
      if (version === sourceVersion.current) setReadingSource(false);
    }
  }
  function clearSource() {
    sourceVersion.current += 1;
    setReadingSource(false);
    setSource(null);
    if (fileRef.current) fileRef.current.value = "";
  }
  function editImage(job: ImagineJob, image: ImagineImage) {
    if (inFlight.current) return;
    sourceVersion.current += 1;
    setReadingSource(false);
    setSource({ name: "Ảnh đã chọn", preview: image.url, imageId: image.id });
    setPrompt("");
    setQuality(job.quality);
    setResolution(job.resolution);
    setAspect("auto");
    setError(null);
    setLightbox(null);
    setLibraryOpen(false);
    lightboxRef.current?.close();
    textareaRef.current?.focus();
  }

  /** Xóa từng ảnh trong thư viện. Lượt hết ảnh biến khỏi bộ ảnh và cột trái; ảnh xóa lỗi thì ở lại. */
  async function removeImages(ids: string[]) {
    let failed = 0;
    let message = "";
    for (const id of ids) {
      try {
        const { job_deleted } = await deleteImagineImage(id);
        setJobs((prev) => prev.flatMap((job) => {
          if (!job.images.some((image) => image.id === id)) return [job];
          const images = job.images.filter((image) => image.id !== id);
          return job_deleted || images.length === 0 ? [] : [{ ...job, images }];
        }));
      } catch (err) {
        if (err instanceof UnauthorizedError) return onUnauthorized();
        failed += 1;
        message = err instanceof Error ? err.message : "";
      }
    }
    if (failed) throw new Error(message || `Chưa xóa được ${failed} ảnh. Thử lại nhé.`);
  }
  /** Đổi tim ngay khi bấm; máy chủ báo lỗi thì trả lại như cũ. */
  async function toggleLike(imageId: string, liked: boolean) {
    const mark = (value: boolean) => setJobs((prev) => prev.map((job) => job.images.some((image) => image.id === imageId)
      ? { ...job, images: job.images.map((image) => image.id === imageId ? { ...image, liked: value } : image) }
      : job));
    setLikeError(null);
    mark(liked);
    try {
      await setImagineImageLiked(imageId, liked);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      mark(!liked);
      setLikeError(err instanceof Error ? err.message : "Chưa lưu được lượt thích. Thử lại nhé.");
    }
  }
  function openOptions() {
    // Mở thanh ngay trong cú chạm rồi mới đặt focus, vì nút vừa bấm sẽ ẩn đi.
    flushSync(() => setExpanded(true));
    optionsRef.current?.querySelector<HTMLButtonElement>("button[aria-pressed='true']")?.focus();
  }
  async function generate() {
    const text = prompt.trim();
    if (!text || inFlight.current || loading || loadFailed || readingSource) return;
    inFlight.current = true;
    setError(null);
    setGenerating(true);
    // Điện thoại: gửi rồi thì thu thanh lại và ẩn bàn phím để thấy ảnh đang tạo.
    const phone = isCompact();
    if (phone) { setExpanded(false); textareaRef.current?.blur(); }
    galleryRef.current?.scrollTo({ top: 0 });
    try {
      const job = await createImagineJob({ prompt: text, quality, resolution, aspect_ratio: aspect, n: count,
        ...(source?.upload ? { source_image: source.upload } : {}),
        ...(source?.imageId ? { source_image_id: source.imageId } : {}),
      });
      setJobs((prev) => [job, ...prev]);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Peto chưa tạo được ảnh. Thử lại nhé.");
    } finally {
      inFlight.current = false;
      setGenerating(false);
      // Focus lại trên điện thoại sẽ bật bàn phím lên giữa lúc người dùng đang xem ảnh.
      if (activeRef.current && !phone) textareaRef.current?.focus();
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
    sourceVersion.current += 1;
    setReadingSource(false);
    setSource(job.source_image ? { name: "Ảnh gốc", preview: job.source_image.url, imageId: job.source_image.id } : null);
    setPrompt(job.prompt);
    setQuality(job.quality);
    setResolution(job.resolution);
    setAspect(job.aspect_ratio);
    textareaRef.current?.focus();
  }
  const lightboxImage = lightbox?.original ? lightbox.job.source_image : lightbox?.job.images[lightbox.index];
  // lightbox giữ bản chụp của lượt lúc mở, nên trạng thái thích phải đọc từ danh sách hiện tại.
  const lightboxLiked = !!lightboxImage && jobs.some((job) => job.images.some((image) => image.id === lightboxImage.id && image.liked));
  const latestImage = jobs.find((job) => job.images.length > 0)?.images[0];
  const controlsDisabled = generating || loading || loadFailed || readingSource;
  // Như Grok: thanh thu gọn mời gõ, còn khung đang mở thì nói rõ cần nhập gì.
  const showFull = expanded || !compact;
  const placeholder = source
    ? showFull ? "Nhập điều bạn muốn sửa trong ảnh" : "Gõ để sửa ảnh"
    : showFull ? "Nhập để tạo hình ảnh" : "Gõ để tưởng tượng";
  const sendLabel = generating ? source ? "Đang sửa…" : "Đang tạo…" : source ? "Sửa ảnh" : "Tạo ảnh";

  return <main className="imagine" hidden={!active}>
      <button type="button" className="menu-btn studio-menu-btn" aria-label="Mở menu" onClick={onOpenSidebar}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
      </button>

    <div className="imagine-gallery" ref={galleryRef}>
      {loading && <div className="loading-chat" role="status" aria-label="Đang mở bộ ảnh của bạn"><span className="loading-spinner" aria-hidden="true" /></div>}
      {loadFailed && <div className="studio-load-error" role="alert"><p>Chưa tải được ảnh đã tạo.</p><button type="button" onClick={() => void loadJobs()}>Thử tải lại</button></div>}
      {!loading && !loadFailed && jobs.length === 0 && !generating && <section className="studio-welcome">
        <span className="studio-eyebrow"><SparkleIcon /> Góc sáng tạo của bạn</span>
        <h1>{source ? "Giữ điều bạn thích." : "Bạn tưởng tượng."}<br /><span>{source ? "Sửa điều bạn muốn." : "Peto vẽ nên."}</span></h1>
        <p>{source ? "Ảnh gốc đã sẵn sàng. Kể Peto nghe bạn muốn thay đổi gì." : "Kể Peto nghe về bức ảnh trong đầu bạn, hoặc thêm ảnh để chỉnh sửa."}</p>
        {source ? <div className="edit-suggestions">{["Đổi nền thành khu vườn, giữ nguyên chủ thể.", "Chuyển thành tranh màu nước.", "Làm ánh sáng ấm hơn, giữ bố cục cũ."].map((text) => <button key={text} type="button" onClick={() => { setPrompt(text); textareaRef.current?.focus(); }}>{text}</button>)}</div> : <div className="studio-ideas">
          {IDEAS.map((idea) => <button type="button" className="studio-idea" key={idea.style} onClick={() => { setPrompt(idea.prompt); textareaRef.current?.focus(); }}>
            <IdeaArt style={idea.style} /><span><strong>{idea.label}</strong><span>{idea.prompt}</span></span>
          </button>)}
        </div>}
      </section>}
      {generating && <section className="generation-pending" role="status" aria-live="polite">
        <div className="generation-copy"><span className="imagine-mark"><SparkleIcon /></span><div><strong>{source ? `Peto đang sửa ảnh · ${count} kết quả…` : `Peto đang tạo ${count} ảnh…`}</strong><p>Bạn có thể sang trò chuyện trong lúc đợi.</p></div></div>
        <p className="pending-prompt">{prompt}</p>
        <div className="imagine-thumbs" aria-hidden="true">{Array.from({ length: count }, (_, index) => <div className="image-placeholder" key={index}><SparkleIcon /></div>)}</div>
      </section>}
      {jobs.length > 0 && <div className="studio-library-head"><h1>Ảnh của bạn</h1><span>{jobs.length} lượt gần đây</span></div>}
      {jobs.map((job) => <section key={job.id} data-job-id={job.id} className="imagine-job">
        <div className="imagine-job-head">
          <div className="imagine-job-copy"><p className="imagine-prompt">{job.prompt}</p><div className="imagine-meta">
            <span>{qualityLabel(job.quality)}</span><span>{job.resolution.toUpperCase()}</span><span>{ratioLabel(job.aspect_ratio)}</span><span>{job.images.length} ảnh</span>
            {job.source_image && <span>Đã chỉnh sửa</span>}
            {job.created_at && <time dateTime={new Date(job.created_at * 1000).toISOString()}>{new Date(job.created_at * 1000).toLocaleDateString("vi-VN", { day: "numeric", month: "short" })}</time>}
          </div></div>
          <div className="imagine-job-actions">
            <button type="button" disabled={generating} onClick={() => reuse(job)}>Dùng lại mô tả</button>
            <button type="button" className="imagine-delete" aria-label={"Xóa lượt ảnh: " + job.prompt} onClick={() => { setDeleteError(null); setDeleteTarget(job); }}>Xóa</button>
          </div>
        </div>
        {job.source_image && <button className="job-source" type="button" onClick={() => setLightbox({ job, index: 0, original: true })}><img src={job.source_image.url} alt="" loading="lazy" /><span>Xem ảnh gốc</span></button>}
        <div className="imagine-thumbs">{job.images.map((image, index) => <button key={image.id} type="button" className="imagine-thumb" aria-label={"Xem ảnh " + (index + 1) + ": " + job.prompt} onClick={() => setLightbox({ job, index })}>
          <img src={image.url} alt={job.prompt} loading="lazy" decoding="async" /><span className="image-open-hint">Xem ảnh ↗</span>
        </button>)}</div>
      </section>)}
    </div>

    <div ref={dockRef} className={"studio-dock" + (expanded ? " expanded" : "")}>
      {error && <div className="error" role="alert">{error}<button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button></div>}
      <form className={"composer-wrap studio-composer-wrap" + (draggingSource ? " dragging" : "")} onSubmit={(event) => { event.preventDefault(); void generate(); }}
        onDragEnter={(event) => { if (!event.dataTransfer.types.includes("Files") || generating) return; event.preventDefault(); dragDepth.current += 1; setDraggingSource(true); }}
        onDragOver={(event) => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); }}
        onDragLeave={(event) => { event.preventDefault(); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDraggingSource(false); }}
        onDrop={(event) => { event.preventDefault(); dragDepth.current = 0; setDraggingSource(false); void chooseSource(event.dataTransfer.files); }}>
        {draggingSource && <div className="drop-hint">Thả ảnh vào đây để Peto chỉnh sửa</div>}
        <div ref={optionsRef} className="studio-options" role="group" aria-label="Tùy chọn tạo ảnh">
          <div className="seg" role="group" aria-label="Mức chi tiết">
            {(["low", "medium"] as const).map((value) => <button type="button" key={value} className={quality === value ? "on" : ""} aria-pressed={quality === value} disabled={controlsDisabled} title={value === "low" ? "Tạo nhanh, phù hợp để thử ý tưởng" : "Dành thêm thời gian cho chi tiết"} onClick={() => setQuality(value)}>{qualityLabel(value)}</button>)}
          </div>
          <StudioMenu label="Số ảnh" value={count} icon={<PhotoIcon />} disabled={controlsDisabled} onChange={setCount}
            options={COUNTS.map((n) => ({ value: n, label: `${n} ảnh` }))} />
          <StudioMenu label="Tỉ lệ" value={aspect} icon={<RatioIcon value={aspect} />} disabled={controlsDisabled} onChange={setAspect}
            columns={2} align="end" options={RATIOS.map((ratio) => ({ value: ratio, label: ratioLabel(ratio), icon: <RatioIcon value={ratio} /> }))} />
        </div>
        {/* Nút thư viện (hiện ảnh mới nhất) và nút tùy chọn chỉ hiện ở thanh thu gọn trên điện thoại. */}
        <button type="button" className="studio-library" aria-label="Mở thư viện ảnh" onClick={() => setLibraryOpen(true)}>
          {latestImage ? <img src={latestImage.url} alt="" /> : <PhotoIcon />}
        </button>
        <div className="composer imagine-composer">
          <input ref={fileRef} className="source-file-input" type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" aria-label="Chọn ảnh để sửa" disabled={generating} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void chooseSource(files); }} />
          {source && <div className="source-preview"><img src={source.preview} alt="Ảnh gốc để chỉnh sửa" /><div><strong>{source.name}</strong><span>Ảnh gốc · kết quả được lưu riêng</span></div><button type="button" disabled={generating} aria-label="Gỡ ảnh gốc" onClick={clearSource}>×</button></div>}
          <textarea id="image-prompt" ref={textareaRef} value={prompt} rows={2} aria-label={source ? "Bạn muốn sửa gì trong ảnh?" : "Bức ảnh bạn muốn tạo"} placeholder={placeholder}
            disabled={generating} onFocus={() => setExpanded(true)} onChange={(event) => setPrompt(event.target.value)}
            onPaste={(event) => { if (event.clipboardData.files.length) { event.preventDefault(); void chooseSource(event.clipboardData.files); } }} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void generate(); }
          }} />
          <div className="imagine-controls">
            <button className="add-source" type="button" disabled={generating || readingSource}
              aria-label={readingSource ? "Đang đọc ảnh…" : source ? "Đổi ảnh gốc" : "Thêm ảnh để chỉnh sửa"}
              title={readingSource ? "Đang đọc ảnh…" : (source ? "Đổi ảnh gốc" : "Thêm ảnh để chỉnh sửa") + " · PNG, JPEG, WebP · tối đa 8 MB"}
              onClick={() => fileRef.current?.click()}><ImagePlusIcon />{source && <img className="add-source-thumb" src={source.preview} alt="" />}</button>
            {/* Chỗ cặp nút Ảnh/Video của Grok. Peto chưa làm video nên dùng cho độ phân giải. */}
            <div className="seg" role="group" aria-label="Độ phân giải">
              {(["1k", "2k"] as const).map((value) => <button type="button" key={value} className={resolution === value ? "on" : ""} aria-pressed={resolution === value} disabled={controlsDisabled} onClick={() => setResolution(value)}>{value.toUpperCase()}</button>)}
            </div>
            <button type="submit" className="studio-send" aria-label={sendLabel} title={sendLabel} disabled={!prompt.trim() || controlsDisabled}>
              {generating ? <span className="studio-spinner" aria-hidden="true" /> : <ArrowUpIcon />}
            </button>
          </div>
        </div>
        <button type="button" className="studio-options-toggle" aria-label="Mở tùy chọn tạo ảnh" onClick={openOptions}><SlidersIcon /></button>
      </form>
    </div>

    <ImagineLibrary open={active && libraryOpen} jobs={jobs} onClose={() => setLibraryOpen(false)}
      onOpenImage={(job, index) => setLightbox({ job, index })} onDeleteImages={removeImages} />
    <dialog ref={lightboxRef} className="imagine-lightbox" aria-label="Xem ảnh đã tạo" onCancel={() => setLightbox(null)} onClick={(event) => { if (event.target === event.currentTarget) setLightbox(null); }}>
      {lightbox && lightboxImage && <div className="imagine-lightbox-card">
        <div className="lightbox-head"><span>{lightbox.original ? "Ảnh gốc" : `Peto tạo ảnh · ${lightbox.index + 1} / ${lightbox.job.images.length}`}</span><button type="button" autoFocus className="dialog-close" aria-label="Đóng ảnh" onClick={() => setLightbox(null)}>×</button></div>
        <img src={lightboxImage.url} alt={lightbox.job.prompt} />
        <p>{lightbox.job.prompt}</p>
        {likeError && <p className="lightbox-error" role="alert">{likeError}</p>}
        <div className="imagine-lightbox-actions">
          {!lightbox.original && lightbox.job.images.length > 1 && <div className="lightbox-navigation"><button type="button" disabled={lightbox.index === 0} onClick={() => setLightbox({ ...lightbox, index: lightbox.index - 1 })}>← Trước</button><button type="button" disabled={lightbox.index === lightbox.job.images.length - 1} onClick={() => setLightbox({ ...lightbox, index: lightbox.index + 1 })}>Sau →</button></div>}
          {!lightbox.original && <button type="button" className={"lightbox-like" + (lightboxLiked ? " on" : "")} aria-pressed={lightboxLiked}
            onClick={() => void toggleLike(lightboxImage.id, !lightboxLiked)}><HeartIcon filled={lightboxLiked} />Thích</button>}
          <button type="button" disabled={generating} onClick={() => editImage(lightbox.job, lightboxImage)}>Sửa ảnh này</button>
          <a href={lightboxImage.url + "?download=1"} download>Tải ảnh xuống ↓</a>
        </div>
      </div>}
    </dialog>
    <dialog ref={deleteRef} className="confirm-dialog" aria-labelledby="delete-images-title" onCancel={(event) => { event.preventDefault(); if (!deleting) setDeleteTarget(null); }}>
      <h2 id="delete-images-title">Xóa lượt ảnh này?</h2>
      <p>{deleteTarget?.images.length} ảnh{deleteTarget?.source_image ? ", bản ảnh gốc đính kèm" : ""} và mô tả của lượt này sẽ bị xóa. Bạn không thể khôi phục sau khi xóa.</p>
      <p className="delete-prompt-preview">{deleteTarget?.prompt}</p>
      {deleteError && <p role="alert">{deleteError}</p>}
      <div className="dialog-actions"><button type="button" autoFocus disabled={deleting} onClick={() => setDeleteTarget(null)}>Giữ lại</button><button type="button" className="danger-button" disabled={deleting} onClick={() => void removeJob()}>{deleting ? "Đang xóa…" : "Xóa ảnh"}</button></div>
    </dialog>
  </main>;
}
