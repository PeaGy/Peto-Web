import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  UnauthorizedError, createImagineJob, deleteImagineImage, deleteImagineJob, listImagineJobs, setImagineImageLiked,
  type ImagineImage, type ImagineJob, type ImagineQuality, type ImagineResolution,
  imagineSources, imaginePending, getImagineJob, checkImagineRequest, unconfirmedImagineRequest, ImagineRequestUncertainError,
} from "../../shared/api/api";
import ImagineLibrary, { HeartIcon } from "./ImagineLibrary";
import EditHistory from "./EditHistory";
import ImageComparison from "./ImageComparison";
import StudioMenu from "./StudioMenu";
import { LoadingIndicator } from '../../shared/ui/LoadingIndicator';
import { COMPACT_QUERY } from "../companion/characters/characterView";

const QUALITY_KEY = "peto-imagine-quality";
const RATIO_KEY = "peto-imagine-ratio";
const RES_KEY = "peto-imagine-res";
const COUNT_KEY = "peto-imagine-n";
const MAX_SOURCE_BYTES = 8 * 1024 * 1024;
type DraftSource = { name: string; preview: string; draftId?: string; size?: number; upload?: { data: string }; imageId?: string };
const RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "2:1", "1:2", "19.5:9", "9:19.5", "20:9", "9:20", "21:9", "5:2"];
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
      resolve({ name: file.name, preview, draftId: crypto.randomUUID(), size: file.size, upload: { data } });
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
  const [sources, setSources] = useState<DraftSource[]>([]);
  const source = sources[0] ?? null;
  const [uncertainRequest, setUncertainRequest] = useState(unconfirmedImagineRequest);
  const [checkingRequest, setCheckingRequest] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
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
  const [lightbox, setLightbox] = useState<{ job: ImagineJob; index: number; original?: boolean; sourceIndex?: number } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ImagineJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Chỉ có tác dụng trên điện thoại: thanh thu gọn mở ra khi đang nhập hoặc chỉnh tùy chọn.
  const [expanded, setExpanded] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [likeError, setLikeError] = useState<string | null>(null);
  const [previewLikes, setPreviewLikes] = useState<Record<string, boolean>>({});
  const compact = useCompact();
  const dockRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sourceStripRef = useRef<HTMLDivElement>(null);
  const sourceVersion = useRef(0);
  const readingRef = useRef(false);
  const moreRef = useRef(false);
  const [pollError, setPollError] = useState(false);
  const dragDepth = useRef(0);
  const galleryRef = useRef<HTMLDivElement>(null);
  const lightboxRef = useRef<HTMLDialogElement>(null);
  const deleteRef = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const deleteInFlight = useRef(false);
  const activeRef = useRef(active);
  const loadVersion = useRef(0);

  useLayoutEffect(() => {
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
  }, [active, loading]);

  const loadJobs = useCallback(async () => {
    const version = ++loadVersion.current;
    setLoading(true);
    setLoadFailed(false);
    try {
      const rows = await listImagineJobs();
      if (version === loadVersion.current) { setJobs(rows); setHasMore(rows.length === 40); }
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
  useLayoutEffect(() => { onJobsChange?.(jobs); }, [jobs, onJobsChange]);
  useEffect(() => {
    if (!active || loading || !focusJobId) return;
    galleryRef.current?.querySelector(`[data-job-id="${focusJobId}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    onFocusHandled?.();
  }, [active, loading, focusJobId, onFocusHandled]);
  useEffect(() => writeStored(QUALITY_KEY, quality), [quality]);
  useEffect(() => writeStored(RES_KEY, resolution), [resolution]);
  useEffect(() => writeStored(RATIO_KEY, aspect), [aspect]);
  useEffect(() => writeStored(COUNT_KEY, String(count)), [count]);
  useEffect(() => setLikeError(null), [lightbox]);

  async function chooseSource(files: FileList | File[]) {
    if (inFlight.current || pendingIds || uncertainRequest || readingRef.current || files.length === 0) return;
    if (sources.length + files.length > 5) { setError("Mỗi lượt sửa nhận tối đa 5 ảnh tham chiếu."); return; }
    const chosen = Array.from(files);
    if (chosen.some(file => !/^image\/(png|jpeg|webp)$/i.test(file.type) && !(file.type === "" && /\.(png|jpe?g|webp)$/i.test(file.name)))) {
      setError("Peto nhận ảnh PNG, JPEG hoặc WebP để chỉnh sửa."); return;
    }
    if (chosen.some(file => file.size === 0 || file.size > MAX_SOURCE_BYTES)) { setError("Ảnh gốc phải có nội dung và không vượt quá 8 MB."); return; }
    if (chosen.reduce((total, file) => total + file.size, 0) + sources.reduce((total, image) => total + (image.size ?? 0), 0) > 16 * 1024 * 1024) {
      setError("Tổng ảnh tham chiếu không được vượt quá 16 MB."); return;
    }
    const version = ++sourceVersion.current;
    readingRef.current = true;
    setReadingSource(true); setError(null);
    try {
      const images = await Promise.all(chosen.map(readSourceFile));
      if (version !== sourceVersion.current) return;
      setSources(prev => [...prev, ...images]);
      setExpanded(true);
      if (activeRef.current) textareaRef.current?.focus();
    } catch (err) {
      if (version === sourceVersion.current) setError(err instanceof Error ? err.message : "Không đọc được ảnh.");
    } finally {
      if (version === sourceVersion.current) { setReadingSource(false); readingRef.current = false; }
    }
  }
  function clearSource(index: number) {
    sourceVersion.current += 1;
    readingRef.current = false;
    setReadingSource(false);
    setSources(prev => prev.filter((_, i) => i !== index));
    if (fileRef.current) fileRef.current.value = "";
  }
  function moveSourceFirst(index: number) {
    flushSync(() => setSources(prev => [prev[index], ...prev.filter((_, i) => i !== index)]));
    sourceStripRef.current?.scrollTo({ left: 0 });
    sourceStripRef.current?.querySelector<HTMLElement>(".source-preview")?.focus({ preventScroll: true });
  }
  function addLibrarySources(images: ImagineImage[]) {
    if (inFlight.current || readingRef.current) return;
    const fresh = images.filter(image => !sources.some(source => source.imageId === image.id));
    if (sources.length + fresh.length > 5) { setError("Mỗi lượt sửa nhận tối đa 5 ảnh tham chiếu."); return; }
    setSources(prev => [...prev, ...fresh.map(image => ({ name: "Ảnh trong thư viện", preview: image.url, imageId: image.id }))]);
    setLibraryOpen(false); setExpanded(true); setError(null);
    textareaRef.current?.focus();
  }
  async function loadMore() {
    if (!hasMore || moreRef.current || !jobs.length) return;
    moreRef.current = true; setLoadingMore(true);
    try {
      const rows = await listImagineJobs(jobs[jobs.length - 1].id);
      setJobs(prev => [...prev, ...rows.filter(row => !prev.some(job => job.id === row.id))]);
      setHasMore(rows.length === 40);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError("Chưa tải được ảnh cũ hơn. Bạn thử lại nhé.");
    } finally { moreRef.current = false; setLoadingMore(false); }
  }
  async function checkUnconfirmed() {
    if (!uncertainRequest || checkingRequest) return;
    setCheckingRequest(true);
    try {
      const job = await checkImagineRequest(uncertainRequest);
      if (job) setJobs(prev => [job, ...prev.filter(row => row.id !== job.id)]);
      setUncertainRequest(null);
      setError(job ? null : "Máy chủ chưa có lượt vừa gửi, hoặc lượt đó đã bị xóa.");
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError("Chưa kiểm tra được lượt vừa gửi. Kiểm tra kết nối rồi thử lại nhé.");
    } finally { setCheckingRequest(false); }
  }
  const pendingIds = jobs.filter(imaginePending).map(job => job.id).join(",");
  useEffect(() => {
    if (!pendingIds) return;
    const controller = new AbortController();
    let timer: number;
    const poll = async () => {
      try {
        const rows = await Promise.all(pendingIds.split(",").map(id => getImagineJob(id, controller.signal)));
        if (controller.signal.aborted) return;
        setJobs(prev => prev.map(job => rows.find(row => row.id === job.id) ?? job));
        setPollError(false);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof UnauthorizedError) { onUnauthorized(); return; }
        setPollError(true);
      }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 2000);
    };
    timer = window.setTimeout(poll, 1000);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [pendingIds, onUnauthorized]);
  function editImage(job: ImagineJob, image: ImagineImage) {
    if (inFlight.current) return;
    sourceVersion.current += 1;
    setReadingSource(false);
    setSources([{ name: "Ảnh đã chọn", preview: image.url, imageId: image.id }]);
    setExpanded(true);
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
    const mark = (value: boolean) => {
      setPreviewLikes(prev => ({ ...prev, [imageId]: value }));
      setJobs((prev) => prev.map((job) => job.images.some((image) => image.id === imageId)
      ? { ...job, images: job.images.map((image) => image.id === imageId ? { ...image, liked: value } : image) }
      : job));
    };
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
    if (!text || inFlight.current || pendingIds || uncertainRequest || loading || loadFailed || readingSource) return;
    inFlight.current = true;
    setError(null);
    setGenerating(true);
    // Điện thoại: gửi rồi thì thu thanh lại và ẩn bàn phím để thấy ảnh đang tạo.
    const phone = isCompact();
    if (phone) { setExpanded(false); textareaRef.current?.blur(); }
    galleryRef.current?.scrollTo({ top: 0 });
    try {
      const job = await createImagineJob({ prompt: text, quality, resolution, aspect_ratio: aspect, n: count,
        ...(sources.length > 1 ? { source_images: sources.map(image => image.upload ?? { image_id: image.imageId! }) }
          : source?.upload ? { source_image: source.upload } : source?.imageId ? { source_image_id: source.imageId } : {}),
      });
      setJobs((prev) => [job, ...prev.filter(row => row.id !== job.id)]);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      if (err instanceof ImagineRequestUncertainError) setUncertainRequest(err.requestId);
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
    setSources(imagineSources(job).map(image => ({ name: "Ảnh gốc", preview: image.url, imageId: image.id })));
    setExpanded(true);
    setPrompt(job.prompt);
    setQuality(job.quality);
    setResolution(job.resolution);
    setAspect(job.aspect_ratio);
    textareaRef.current?.focus();
  }
  const lightboxImage = lightbox?.original ? imagineSources(lightbox.job)[lightbox.sourceIndex ?? 0] : lightbox?.job.images[lightbox.index];
  // lightbox giữ bản chụp của lượt lúc mở, nên trạng thái thích phải đọc từ danh sách hiện tại.
  const listedImage = lightboxImage && jobs.flatMap(job => job.images).find(image => image.id === lightboxImage.id);
  const lightboxLiked = !!lightboxImage && (previewLikes[lightboxImage.id] ?? listedImage?.liked ?? lightboxImage.liked ?? false);
  const latestImage = jobs.find((job) => job.images.length > 0)?.images[0];
  const controlsDisabled = generating || !!pendingIds || !!uncertainRequest || loading || loadFailed || readingSource;
  // Như Grok: thanh thu gọn mời gõ, còn khung đang mở thì nói rõ cần nhập gì.
  const showFull = expanded || !compact;
  const placeholder = source
    ? showFull ? "Nhập điều bạn muốn sửa trong ảnh" : "Gõ để sửa ảnh"
    : showFull ? "Nhập để tạo hình ảnh" : "Gõ để tưởng tượng";
  const sendLabel = generating ? source ? "Đang sửa…" : "Đang tạo…" : source ? "Sửa ảnh" : "Tạo ảnh";

  // Màn hình chờ chung kéo dài tới khi có thư viện; không hiện thêm một khung chờ bên trong studio.
  if (loading) return active ? <LoadingIndicator variant="screen" label="Loading" /> : null;

  return <main className="imagine" hidden={!active}>
      <button type="button" className="menu-btn studio-menu-btn" aria-label="Mở menu" onClick={onOpenSidebar}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
      </button>

    <div className="imagine-gallery" ref={galleryRef}>
      {pollError && <p className="error" role="status">Đang mất kết nối. Peto sẽ kiểm tra lại lượt ảnh khi có mạng.</p>}
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
      {jobs.length > 0 && <div className="studio-library-head"><h1>Ảnh của bạn</h1><span>{jobs.length} lượt đã tải</span><button type="button" className="studio-text-button" onClick={() => setLibraryOpen(true)}>Thư viện</button></div>}
      {jobs.map((job) => <section key={job.id} data-job-id={job.id} className="imagine-job">
        <div className="imagine-job-head">
          <div className="imagine-job-copy"><p className="imagine-prompt">{job.prompt}</p><div className="imagine-meta">
            <span>{qualityLabel(job.quality)}</span><span>{job.resolution.toUpperCase()}</span><span>{ratioLabel(job.aspect_ratio)}</span><span>{job.images.length} ảnh</span>
            {job.source_image && <span>Đã chỉnh sửa</span>}
            {job.created_at && <time dateTime={new Date(job.created_at * 1000).toISOString()}>{new Date(job.created_at * 1000).toLocaleDateString("vi-VN", { day: "numeric", month: "short" })}</time>}
          </div></div>
          <div className="imagine-job-actions">
            <button type="button" disabled={controlsDisabled} onClick={() => reuse(job)}>Dùng lại mô tả</button>
            <button type="button" className="imagine-delete" disabled={imaginePending(job)} aria-label={"Xóa lượt ảnh: " + job.prompt} onClick={() => { setDeleteError(null); setDeleteTarget(job); }}>Xóa</button>
          </div>
        </div>
        <div className="job-sources">{imagineSources(job).map((image, sourceIndex) => <button key={image.id} className="job-source" type="button" onClick={() => setLightbox({ job, index: 0, original: true, sourceIndex })}><img src={image.url} alt="" loading="lazy" /><span>{imagineSources(job).length === 1 ? "Xem ảnh gốc" : `Ảnh tham chiếu ${sourceIndex + 1}`}</span></button>)}</div>
        {imagineSources(job).some(image => image.parent_job_id) && <EditHistory job={job} jobs={jobs} onOpen={setLightbox} onUnauthorized={onUnauthorized} />}
        {imaginePending(job) && <div className="generation-pending" role="status"><strong>{job.status === "queued" ? "Đang chờ đến lượt…" : "Peto đang tạo ảnh…"}</strong><p>Bạn có thể chuyển tab hoặc tải lại trang; lượt này vẫn được theo dõi.</p><JobElapsed createdAt={job.created_at} /><div className="imagine-thumbs" aria-hidden="true">{Array.from({ length: job.n ?? 1 }, (_, index) => <div className="image-placeholder" key={index}><SparkleIcon /></div>)}</div></div>}
        {(job.status === "failed" || job.status === "unknown") && <p className="error">{job.error || "Chưa có kết quả cho lượt này."}{job.status === "unknown" && " Lượt này không được tự gửi lại."}</p>}
        <div className="imagine-thumbs">{job.images.map((image, index) => <button key={image.id} type="button" className="imagine-thumb" aria-label={"Xem ảnh " + (index + 1) + ": " + job.prompt} onClick={() => setLightbox({ job, index })}>
          <img src={image.url} alt={job.prompt} loading="lazy" decoding="async" /><span className="image-open-hint">Xem ảnh ↗</span>
        </button>)}</div>
      </section>)}
      {hasMore && <button type="button" className="load-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Đang tải…" : "Xem ảnh cũ hơn"}</button>}
    </div>

    <div ref={dockRef} className={"studio-dock" + (expanded ? " expanded" : "")}>
      {uncertainRequest && <div className="error" role="status">Chưa xác nhận được lượt vừa gửi. <button type="button" className="studio-text-button" disabled={checkingRequest} onClick={() => void checkUnconfirmed()}>{checkingRequest ? "Đang kiểm tra…" : "Kiểm tra lượt vừa gửi"}</button></div>}
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
          <input ref={fileRef} className="source-file-input" type="file" multiple accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" aria-label="Chọn ảnh để sửa" disabled={controlsDisabled} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void chooseSource(files); }} />
          {sources.length > 0 && <div className="source-collection"><div className="source-guidance">{sources.length}/5 ảnh · Bạn có thể viết “lấy nhân vật ở ảnh 1, nền ở ảnh 2”. Khi để Tự động, tỉ lệ theo ảnh đầu.</div><div className="source-strip" ref={sourceStripRef}>{sources.map((image, index) => <div className="source-preview" key={image.imageId ?? image.draftId} tabIndex={-1} role="group" aria-label={`Ảnh tham chiếu ${index + 1}`}>
            <img src={image.preview} alt={sources.length === 1 ? "Ảnh gốc để chỉnh sửa" : `Ảnh tham chiếu ${index + 1}`} /><div><strong>Ảnh {index + 1}</strong><span title={image.name}>{image.name}</span>{index > 0 && <button type="button" className="source-first" disabled={controlsDisabled} onClick={() => moveSourceFirst(index)}>Đặt làm ảnh đầu</button>}</div>
            <button type="button" disabled={generating || !!pendingIds} aria-label={sources.length === 1 ? "Gỡ ảnh gốc" : `Gỡ ảnh ${index + 1}`} onClick={() => clearSource(index)}>×</button>
          </div>)}</div></div>}
          <textarea id="image-prompt" ref={textareaRef} value={prompt} rows={2} aria-label={source ? "Bạn muốn sửa gì trong ảnh?" : "Bức ảnh bạn muốn tạo"} placeholder={placeholder}
            disabled={generating || !!pendingIds} onFocus={() => setExpanded(true)} onChange={(event) => setPrompt(event.target.value)}
            onPaste={(event) => { if (event.clipboardData.files.length) { event.preventDefault(); void chooseSource(event.clipboardData.files); } }} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void generate(); }
          }} />
          <div className="imagine-controls">
            <button className="add-source" type="button" disabled={controlsDisabled || sources.length >= 5}
              aria-label={readingSource ? "Đang đọc ảnh…" : source ? "Thêm ảnh tham chiếu" : "Thêm ảnh để chỉnh sửa"}
              title={readingSource ? "Đang đọc ảnh…" : (source ? "Thêm ảnh tham chiếu" : "Thêm ảnh để chỉnh sửa") + " · PNG, JPEG, WebP · tối đa 8 MB"}
              onClick={() => fileRef.current?.click()}><ImagePlusIcon />{source && <img className="add-source-thumb" src={source.preview} alt="" />}</button>
            <button type="button" className="studio-text-button reference-library" disabled={controlsDisabled || sources.length >= 5} onClick={() => setLibraryOpen(true)}>Từ thư viện</button>
            {/* Chỗ cặp nút Ảnh/Video của Grok. Peto chưa làm video nên dùng cho độ phân giải. */}
            <div className="seg" role="group" aria-label="Độ phân giải">
              {(["1k", "2k"] as const).map((value) => <button type="button" key={value} className={resolution === value ? "on" : ""} aria-pressed={resolution === value} disabled={controlsDisabled} onClick={() => setResolution(value)}>{value.toUpperCase()}</button>)}
            </div>
            <button type="submit" className="studio-send" aria-label={sendLabel} title={sendLabel} disabled={!prompt.trim() || controlsDisabled}>
              {generating ? <span aria-hidden="true"><LoadingIndicator variant="icon" label="Đang tạo ảnh" /></span> : <ArrowUpIcon />}
            </button>
          </div>
        </div>
        <button type="button" className="studio-options-toggle" aria-label="Mở tùy chọn tạo ảnh" onClick={openOptions}><SlidersIcon /></button>
      </form>
    </div>

    <ImagineLibrary open={active && libraryOpen} jobs={jobs} onClose={() => setLibraryOpen(false)}
      onOpenImage={(job, index) => setLightbox({ job, index })} onDeleteImages={removeImages}
      onUseSources={controlsDisabled ? undefined : addLibrarySources} sourceLimit={5 - sources.length}
      hasMore={hasMore} loadingMore={loadingMore} onLoadMore={() => void loadMore()} />
    <dialog ref={lightboxRef} className="imagine-lightbox" aria-label="Xem ảnh đã tạo" onCancel={() => setLightbox(null)} onClick={(event) => { if (event.target === event.currentTarget) setLightbox(null); }}>
      {lightbox && lightboxImage && <div className="imagine-lightbox-card">
        <div className="lightbox-head"><span>{lightbox.original ? "Ảnh gốc" : `Peto tạo ảnh · ${lightbox.index + 1} / ${lightbox.job.images.length}`}</span><button type="button" autoFocus className="dialog-close" aria-label="Đóng ảnh" onClick={() => setLightbox(null)}>×</button></div>
        {!lightbox.original && imagineSources(lightbox.job).length > 0
          ? <ImageComparison key={lightboxImage.id} sources={imagineSources(lightbox.job)} image={lightboxImage} prompt={lightbox.job.prompt} />
          : <img src={lightboxImage.url} alt={lightbox.job.prompt} />}
        <p>{lightbox.job.prompt}</p>
        {likeError && <p className="lightbox-error" role="alert">{likeError}</p>}
        <div className="imagine-lightbox-actions">
          {!lightbox.original && lightbox.job.images.length > 1 && <div className="lightbox-navigation"><button type="button" disabled={lightbox.index === 0} onClick={() => setLightbox({ ...lightbox, index: lightbox.index - 1 })}>← Trước</button><button type="button" disabled={lightbox.index === lightbox.job.images.length - 1} onClick={() => setLightbox({ ...lightbox, index: lightbox.index + 1 })}>Sau →</button></div>}
          {!lightbox.original && <button type="button" className={"lightbox-like" + (lightboxLiked ? " on" : "")} aria-pressed={lightboxLiked}
            onClick={() => void toggleLike(lightboxImage.id, !lightboxLiked)}><HeartIcon filled={lightboxLiked} />Thích</button>}
          <button type="button" disabled={controlsDisabled} onClick={() => editImage(lightbox.job, lightboxImage)}>Sửa ảnh này</button>
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


function JobElapsed({ createdAt }: { createdAt: number | null }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  if (!createdAt) return null;
  const elapsed = Math.max(0, Math.floor(now / 1000 - createdAt));
  return <span className="imagine-elapsed">Đã chờ {elapsed < 60 ? `${elapsed} giây` : `${Math.floor(elapsed / 60)} phút ${elapsed % 60} giây`}</span>;
}
