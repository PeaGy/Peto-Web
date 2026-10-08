import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  UnauthorizedError, createImagineJob, deleteImagineImage, deleteImagineJob, listImagineJobs, setImagineImageLiked,
  type ImagineImage, type ImagineJob, type ImagineQuality, type ImagineResolution,
  imagineSources, imaginePending, getImagineJob, checkImagineRequest, unconfirmedImagineRequest, ImagineRequestUncertainError,
  getImagineWorkspace, saveImagineRevision, type ImagineWorkspace,
} from "../../shared/api/api";
import ImagineLibrary from "./ImagineLibrary";
import EditHistory from "./EditHistory";
import ImageWorkspace from "./ImageWorkspace";
import type { ImageVersion } from "./ImageVersionRail";
import StudioMenu from "./StudioMenu";
import StudioIcon from "./studioIcons";
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
const RATIO_HINTS: Record<string, string> = {
  auto: "Theo ảnh đầu", "1:1": "Ảnh vuông", "16:9": "Ảnh bìa", "9:16": "Hình nền điện thoại",
  "4:3": "Ảnh ngang", "3:4": "Chân dung", "3:2": "Ảnh chụp ngang", "2:3": "Áp phích",
  "2:1": "Banner", "1:2": "Ảnh dọc dài", "19.5:9": "Màn hình rộng", "9:19.5": "Điện thoại dài",
  "20:9": "Màn hình rộng", "9:20": "Điện thoại dài", "21:9": "Siêu rộng", "5:2": "Banner rộng",
};
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
type ImageView = { job: ImagineJob; index: number; original?: boolean; sourceIndex?: number; using?: boolean };
function imageRoute(rootId: string, imageId: string) { return `#imagine/${encodeURIComponent(rootId)}/${encodeURIComponent(imageId)}`; }

export default function Imagine({ active, onUnauthorized, onOpenSidebar, onJobsChange, focusJobId, onFocusHandled, libraryRequest = 0 }: {
  active: boolean;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
  onJobsChange?: (jobs: ImagineJob[]) => void;
  focusJobId?: string | null;
  onFocusHandled?: () => void;
  libraryRequest?: number;
}) {
  const [prompt, setPrompt] = useState("");
  const [sources, setSources] = useState<DraftSource[]>([]);
  const [sourceOrderChanged, setSourceOrderChanged] = useState(false);
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
  const [submittingImageId, setSubmittingImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<ImageView | null>(null);
  const lightboxValue = useRef(lightbox); lightboxValue.current = lightbox;
  const [workspace, setWorkspace] = useState<ImagineWorkspace | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyReload, setHistoryReload] = useState(0);
  const routeVersion = useRef(0);
  const workspaceRootId = lightbox && !lightbox.original ? lightbox.job.root_image_id || lightbox.job.images[lightbox.index]?.id : null;
  const rootJobs = jobs.filter(job => !job.root_image_id);
  const viewerOpen = !!lightbox;
  const [deleteTarget, setDeleteTarget] = useState<ImagineJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Chỉ có tác dụng trên điện thoại: thanh thu gọn mở ra khi đang nhập hoặc chỉnh tùy chọn.
  const [expanded, setExpanded] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  useEffect(() => {
    if (libraryRequest > 0) { closeImage(); setLibraryOpen(true); }
  }, [libraryRequest]);
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

  function openImage(view: ImageView, push = true) {
    routeVersion.current += 1;
    setLightbox(view);
    if (!view.original) {
      const image = view.job.images[view.index];
      const hash = imageRoute(view.job.root_image_id || image.id, image.id);
      if (window.location.hash !== hash) window.history[push ? 'pushState' : 'replaceState'](null, '', hash);
    }
  }
  function closeImage() {
    routeVersion.current += 1; setLightbox(null);
    if (window.location.hash.startsWith('#imagine/')) window.history.pushState(null, '', '#imagine');
  }
  function selectVersion(entry: ImageVersion) { openImage({ job: entry.job, index: entry.job.images.findIndex(image => image.id === entry.image.id) }); }
  useEffect(() => {
    if (!active) return;
    const read = async () => {
      const match = /^#imagine\/([^/]+)\/([^/?]+)$/.exec(window.location.hash);
      const token = ++routeVersion.current;
      if (!match) { setLightbox(null); return; }
      try {
        const rootId = decodeURIComponent(match[1]), imageId = decodeURIComponent(match[2]);
        const loaded = await getImagineWorkspace(rootId);
        if (token !== routeVersion.current) return;
        const job = [loaded.root_job, ...loaded.jobs].find(job => (job.root_image_id === rootId || imageId === rootId) && job.images.some(image => image.id === imageId));
        if (loaded.root_image_id !== rootId || !job) throw new Error('Phiên bản này không còn tồn tại.');
        setWorkspace(loaded); setLightbox({ job, index: job.images.findIndex(image => image.id === imageId) });
        setJobs(previous => [...previous.filter(job => !loaded.jobs.some(child => child.id === job.id)), ...loaded.jobs]);
      } catch (err) {
        if (token !== routeVersion.current) return;
        if (err instanceof UnauthorizedError) return onUnauthorized();
        setLightbox(null); setError(err instanceof Error ? err.message : 'Chưa mở được phiên bản ảnh.');
      }
    };
    void read();
    window.addEventListener('popstate', read); window.addEventListener('hashchange', read);
    return () => { routeVersion.current += 1; window.removeEventListener('popstate', read); window.removeEventListener('hashchange', read); };
  }, [active, onUnauthorized]);
  useEffect(() => {
    if (!active || !workspaceRootId) { setWorkspace(null); setHistoryError(null); return; }
    const controller = new AbortController();
    setHistoryLoading(true); setHistoryError(null);
    void getImagineWorkspace(workspaceRootId, controller.signal).then(loaded => {
      if (controller.signal.aborted) return;
      setWorkspace(loaded);
      setJobs(previous => [...previous.filter(job => !loaded.jobs.some(child => child.id === job.id)), ...loaded.jobs]);
    }).catch(err => {
      if (controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setHistoryError('Chưa tải được lịch sử chỉnh sửa.');
    }).finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => controller.abort();
  }, [active, workspaceRootId, historyReload, onUnauthorized]);
  function acceptRevision(result: ImagineJob, select = true) {
    setJobs(previous => [result, ...previous.filter(job => job.id !== result.id)]);
    setWorkspace(previous => previous && result.root_image_id === previous.root_image_id
      ? { ...previous, jobs: [...previous.jobs.filter(job => job.id !== result.id), result] } : previous);
    const current = lightboxValue.current;
    const currentRoot = current && !current.original ? current.job.root_image_id || current.job.images[current.index].id : null;
    if (select && result.root_image_id === currentRoot && result.status === 'complete' && result.images.length && current) openImage({ job: result, index: 0 });
  }
  async function saveWorkspaceRevision(data: string, operation: 'crop' | 'brush', requestId: string) {
    const current = lightboxValue.current;
    if (!current || current.original) return;
    const result = await saveImagineRevision(current.job.images[current.index].id, data, operation, requestId);
    if (lightboxValue.current?.job.images[lightboxValue.current.index]?.id === current.job.images[current.index].id) acceptRevision(result);
  }

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
  }, [active, loading, libraryOpen]);

  const loadJobs = useCallback(async () => {
    const version = ++loadVersion.current;
    setLoading(true);
    setLoadFailed(false);
    try {
      const rows = await listImagineJobs();
      if (version === loadVersion.current) { setJobs(previous => [...rows, ...previous.filter(job => job.root_image_id && !rows.some(row => row.id === job.id))]); setHasMore(rows.filter(job => !job.root_image_id).length === 40); }
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
    const dialog = lightboxRef.current;
    if (!dialog) return;
    // Desktop dùng vùng nội dung hiện tại để thanh bên thật vẫn thao tác được.
    // Đóng trước khi đổi chế độ; trình duyệt không cho showModal trên dialog đã show.
    dialog.close();
    if (active && viewerOpen) { if (compact) dialog.showModal(); else dialog.show(); }
  }, [active, viewerOpen, compact, loading]);
  useEffect(() => {
    if (!active || !viewerOpen || !compact) return;
    const viewport = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
    if (!viewport || /viewport-fit\s*=/.test(viewport.content)) return;
    // Giữ viewport ổn định khi chọn phiên bản khác trong cùng khung xem.
    const previous = viewport.content; viewport.content = `${previous}, viewport-fit=cover`;
    return () => { viewport.content = previous; };
  }, [active, viewerOpen, compact]);
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
  useLayoutEffect(() => { onJobsChange?.(jobs.filter(job => !job.root_image_id)); }, [jobs, onJobsChange]);
  useEffect(() => {
    if (!active || loading || !focusJobId) return;
    if (lightbox || libraryOpen) { closeImage(); setLibraryOpen(false); return; }
    galleryRef.current?.querySelector(`[data-job-id="${focusJobId}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    onFocusHandled?.();
  }, [active, loading, focusJobId, onFocusHandled, lightbox, libraryOpen]);
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
    if (sources.length === 1) setSourceOrderChanged(false);
    else if (index < sources.length - 1) setSourceOrderChanged(true);
    if (fileRef.current) fileRef.current.value = "";
  }
  function moveSourceFirst(index: number) {
    flushSync(() => setSources(prev => [prev[index], ...prev.filter((_, i) => i !== index)]));
    setSourceOrderChanged(true);
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
      const rows = await listImagineJobs(rootJobs[rootJobs.length - 1].id);
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
      if (job) acceptRevision(job);
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
        const current = lightboxValue.current;
        const currentRoot = current && !current.original ? current.job.root_image_id || current.job.images[current.index].id : null;
        for (const row of rows) if (row.root_image_id === currentRoot) acceptRevision(row);
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
  function workspaceSource(image: ImagineImage, data?: string): DraftSource {
    if (!data) return { name: "Ảnh đã chọn", preview: image.url, imageId: image.id };
    const encoded = data.split(",")[1];
    const size = Math.floor((encoded?.length ?? 0) * 3 / 4);
    if (!data.startsWith("data:image/png;base64,") || !encoded || size > MAX_SOURCE_BYTES) throw new Error("Bản chỉnh sửa phải là ảnh PNG và không vượt quá 8 MB.");
    return { name: "Bản chỉnh sửa.png", preview: data, draftId: crypto.randomUUID(), size, upload: { data: encoded } };
  }
  function prepareWorkspaceSource(job: ImagineJob, image: ImagineImage, data: string | undefined, append: boolean) {
    if (controlsDisabled || inFlight.current) return;
    const draft = workspaceSource(image, data);
    if (append && sources.length >= 5) throw new Error("Mỗi lượt sửa nhận tối đa 5 ảnh tham chiếu.");
    if (append && (draft.size ?? 0) + sources.reduce((total, source) => total + (source.size ?? 0), 0) > 16 * 1024 * 1024) throw new Error("Tổng ảnh tham chiếu không được vượt quá 16 MB.");
    if (append && !data && sources.some(source => source.imageId === image.id)) return;
    sourceVersion.current += 1; readingRef.current = false;
    flushSync(() => {
      setReadingSource(false); setSources(append ? [...sources, draft] : [draft]);
      setSourceOrderChanged(append && sourceOrderChanged); setExpanded(true); setError(null);
      if (!append) {
        setPrompt(job.prompt); setQuality(job.quality); setResolution(job.resolution); setAspect("auto");
        // Dùng ảnh ngay trong khung xem, giữ canvas và thay ô sửa bằng bản nháp có ảnh đính kèm.
        setLightbox(current => current ? { ...current, using: true } : current);
      } else { closeImage(); setLibraryOpen(false); }
    });
    if (append) lightboxRef.current?.close();
    textareaRef.current?.focus();
  }
  async function submitWorkspaceEdit(job: ImagineJob, image: ImagineImage, text: string, ratio: string, data?: string) {
    if (controlsDisabled || inFlight.current) return;
    const draft = workspaceSource(image, data);
    inFlight.current = true; setGenerating(true); setSubmittingImageId(image.id); setError(null);
    try {
      const result = await createImagineJob({ prompt: text, quality: job.quality, resolution: job.resolution, aspect_ratio: ratio, n: 1,
        ...(draft.upload ? { source_image: draft.upload } : { source_image_id: image.id }),
        ...(!lightbox?.original ? { edit_parent_image_id: image.id } : {}) });
      acceptRevision(result); setPrompt(text); setSources([draft]); setSourceOrderChanged(false);
      if (!result.root_image_id) { closeImage(); setLibraryOpen(false); }
      setQuality(job.quality); setResolution(job.resolution); setAspect(ratio); setCount(1);
      if (isCompact()) setExpanded(false);
      galleryRef.current?.scrollTo({ top: 0 });
    } catch (error) {
      if (error instanceof UnauthorizedError) { onUnauthorized(); return; }
      if (error instanceof ImagineRequestUncertainError) {
        setUncertainRequest(error.requestId); setError(error.message);
      } else throw error;
    } finally { inFlight.current = false; setGenerating(false); setSubmittingImageId(null); }
  }

  /** Xóa từng ảnh trong thư viện. Lượt hết ảnh biến khỏi bộ ảnh và cột trái; ảnh xóa lỗi thì ở lại. */
  async function removeImages(ids: string[]) {
    let failed = 0;
    let message = "";
    for (const id of ids) {
      try {
        const { job_deleted } = await deleteImagineImage(id);
        setJobs((prev) => prev.flatMap((job) => {
          if (job.root_image_id === id) return [];
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
    const editing = lightbox && !lightbox.original && lightbox.using ? lightbox.job.images[lightbox.index] : null;
    if (editing) setSubmittingImageId(editing.id);
    if (!editing) closeImage();
    setLibraryOpen(false);
    const phone = isCompact();
    if (phone) { setExpanded(false); textareaRef.current?.blur(); }
    galleryRef.current?.scrollTo({ top: 0 });
    try {
      const job = await createImagineJob({ prompt: text, quality, resolution, aspect_ratio: aspect, n: count,
        ...(sources.length > 1 ? { source_images: sources.map(image => image.upload ?? { image_id: image.imageId! }) }
          : source?.upload ? { source_image: source.upload } : source?.imageId ? { source_image_id: source.imageId } : {}),
        ...(editing && sources.length && (source.upload || source.imageId === editing.id) ? { edit_parent_image_id: editing.id } : {}),
      });
      acceptRevision(job);
      if (editing && imaginePending(job)) setLightbox(current => current ? { ...current, using: false } : current);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      if (err instanceof ImagineRequestUncertainError) setUncertainRequest(err.requestId);
      setError(err instanceof Error ? err.message : "Peto chưa tạo được ảnh. Thử lại nhé.");
    } finally {
      inFlight.current = false;
      setGenerating(false);
      setSubmittingImageId(null);
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
      const imageIds = deleteTarget.images.map(image => image.id);
      setJobs((prev) => prev.filter((job) => job.id !== id && !imageIds.includes(job.root_image_id ?? '')));
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
    setSourceOrderChanged(false);
    setExpanded(true);
    setPrompt(job.prompt);
    setQuality(job.quality);
    setResolution(job.resolution);
    setAspect(job.aspect_ratio);
    textareaRef.current?.focus();
  }
  const lightboxImage = lightbox?.original ? imagineSources(lightbox.job)[lightbox.sourceIndex ?? 0] : lightbox?.job.images[lightbox.index];
  const imageVersions: ImageVersion[] = workspace && workspace.root_image_id === workspaceRootId ? [
    ...workspace.root_job.images.filter(image => image.id === workspace.root_image_id).map(image => ({ job: workspace.root_job, image })),
    ...workspace.jobs.slice().sort((a, b) => (a.created_at ?? 0) - (b.created_at ?? 0) || a.id.localeCompare(b.id))
      .flatMap(job => job.images.map(image => ({ job, image }))),
  ] : [];
  const workspaceJob = jobs.find(job => job.root_image_id === workspaceRootId && imaginePending(job));
  const latestEdit = workspace?.root_image_id === workspaceRootId ? workspace?.jobs.at(-1) : undefined;
  const failedEdit = latestEdit && (latestEdit.status === 'failed' || latestEdit.status === 'unknown') ? latestEdit : undefined;
  // lightbox giữ bản chụp của lượt lúc mở, nên trạng thái thích phải đọc từ danh sách hiện tại.
  const listedImage = lightboxImage && jobs.flatMap(job => job.images).find(image => image.id === lightboxImage.id);
  const lightboxLiked = !!lightboxImage && (previewLikes[lightboxImage.id] ?? listedImage?.liked ?? lightboxImage.liked ?? false);
  const latestImage = rootJobs.find((job) => job.images.length > 0)?.images[0];
  const controlsDisabled = generating || !!pendingIds || !!uncertainRequest || loading || loadFailed || readingSource;
  const usingImage = !!lightbox?.using;
  // Như Grok: thanh thu gọn mời gõ, còn khung đang mở thì nói rõ cần nhập gì.
  const showFull = expanded || !compact;
  const placeholder = source
    ? showFull ? "Nhập điều bạn muốn sửa trong ảnh" : "Gõ để sửa ảnh"
    : showFull ? "Nhập để tạo hình ảnh" : "Gõ để tưởng tượng";
  const sendLabel = generating ? source ? "Đang sửa…" : "Đang tạo…" : source ? "Sửa ảnh" : "Tạo ảnh";

  const studioOptions = <div ref={optionsRef} className="studio-options" role="group" aria-label="Tùy chọn tạo ảnh">
    <div className="seg" role="group" aria-label="Mức chi tiết">
      {(["low", "medium"] as const).map((value) => <button type="button" key={value} className={quality === value ? "on" : ""} aria-pressed={quality === value} disabled={controlsDisabled} title={value === "low" ? "Tạo nhanh, phù hợp để thử ý tưởng" : "Dành thêm thời gian cho chi tiết"} onClick={() => setQuality(value)}>{qualityLabel(value)}</button>)}
    </div>
    <StudioMenu label="Số ảnh" value={count} icon={<PhotoIcon />} disabled={controlsDisabled} onChange={setCount}
      options={COUNTS.map((n) => ({ value: n, label: `${n} ảnh` }))} />
    <StudioMenu label="Tỉ lệ" value={aspect} icon={<RatioIcon value={aspect} />} disabled={controlsDisabled} onChange={setAspect}
      columns={2} align="end" options={RATIOS.map((ratio) => ({ value: ratio, label: ratioLabel(ratio), description: ratio === "auto" && !source ? "Peto chọn khung hình" : RATIO_HINTS[ratio], icon: <RatioIcon value={ratio} /> }))} />
  </div>;

  const studioDock = <div ref={dockRef} className={"studio-dock" + (expanded ? " expanded" : "") + (usingImage ? " workspace-studio" : "")}>
      {uncertainRequest && <div className="error" role="status">Chưa xác nhận được lượt vừa gửi. <button type="button" className="studio-text-button" disabled={checkingRequest} onClick={() => void checkUnconfirmed()}>{checkingRequest ? "Đang kiểm tra…" : "Kiểm tra lượt vừa gửi"}</button></div>}
      {error && <div className="error" role="alert">{error}<button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button></div>}
      <form className={"composer-wrap studio-composer-wrap" + (draggingSource ? " dragging" : "")} onSubmit={(event) => { event.preventDefault(); void generate(); }}
        onDragEnter={(event) => { if (!event.dataTransfer.types.includes("Files") || generating) return; event.preventDefault(); dragDepth.current += 1; setDraggingSource(true); }}
        onDragOver={(event) => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); }}
        onDragLeave={(event) => { event.preventDefault(); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDraggingSource(false); }}
        onDrop={(event) => { event.preventDefault(); dragDepth.current = 0; setDraggingSource(false); void chooseSource(event.dataTransfer.files); }}>
        {draggingSource && <div className="drop-hint">Thả ảnh vào đây để Peto chỉnh sửa</div>}
        {!usingImage && studioOptions}
        {/* Nút thư viện (hiện ảnh mới nhất) và nút tùy chọn chỉ hiện ở thanh thu gọn trên điện thoại. */}
        <button type="button" className="studio-library" aria-label="Mở thư viện ảnh" onClick={() => setLibraryOpen(true)}>
          {latestImage ? <img src={latestImage.url} alt="" /> : <PhotoIcon />}
        </button>
        <div className="composer imagine-composer">
          <input ref={fileRef} className="source-file-input" type="file" multiple accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" aria-label="Chọn ảnh để sửa" disabled={controlsDisabled} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void chooseSource(files); }} />
          {sources.length > 0 && <div className="source-collection">
          {sourceOrderChanged && <div className="source-order-notice" role="status">Số thứ tự ảnh đã thay đổi. Bạn kiểm tra lại “ảnh 1”, “ảnh 2”… trong mô tả nhé.<button type="button" aria-label="Đóng nhắc thứ tự ảnh" onClick={() => setSourceOrderChanged(false)}>×</button></div>}
          <div className="source-strip" ref={sourceStripRef}>{sources.map((image, index) => <div className="source-preview" key={image.imageId ?? image.draftId} tabIndex={-1} role="group" aria-label={`Ảnh tham chiếu ${index + 1}`} title={image.name}>
            <img src={image.preview} alt={sources.length === 1 ? "Ảnh gốc để chỉnh sửa" : `Ảnh tham chiếu ${index + 1}`} />
            {sources.length > 1 && <span className="source-index" aria-hidden="true">{index + 1}</span>}
            {index > 0 && <button type="button" className="source-first" aria-label="Đặt làm ảnh đầu" title="Đặt làm ảnh đầu" disabled={controlsDisabled} onClick={() => moveSourceFirst(index)}><StudioIcon name="arrowUp" /></button>}
            <button type="button" className="source-remove" disabled={generating || !!pendingIds} aria-label={sources.length === 1 ? "Gỡ ảnh gốc" : `Gỡ ảnh ${index + 1}`} onClick={() => clearSource(index)}><StudioIcon name="close" /></button>
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
            {/* Chỗ cặp nút Ảnh/Video của Grok. Peto chưa làm video nên dùng cho độ phân giải. */}
            <div className="seg" role="group" aria-label="Độ phân giải">
              {(["1k", "2k"] as const).map((value) => <button type="button" key={value} className={resolution === value ? "on" : ""} aria-pressed={resolution === value} disabled={controlsDisabled} onClick={() => setResolution(value)}>{value.toUpperCase()}</button>)}
            </div>
            {usingImage && studioOptions}
            <button type="submit" className="studio-send" aria-label={sendLabel} title={sendLabel} disabled={!prompt.trim() || controlsDisabled}>
              {generating ? <span aria-hidden="true"><LoadingIndicator variant="icon" label="Đang tạo ảnh" /></span> : <ArrowUpIcon />}
            </button>
          </div>
        </div>
        <button type="button" className="studio-options-toggle" aria-label="Mở tùy chọn tạo ảnh" onClick={openOptions}><SlidersIcon /></button>
      </form>
    </div>;

  // Màn hình chờ chung kéo dài tới khi có thư viện; không hiện thêm một khung chờ bên trong studio.
  if (loading) return active ? <LoadingIndicator variant="screen" label="Loading" /> : null;

  return <main className={'imagine' + (lightbox ? ' viewer-open' : '')} hidden={!active}>
      <button type="button" hidden={!!lightbox || libraryOpen} className="menu-btn studio-menu-btn" aria-label="Mở menu" onClick={onOpenSidebar}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
      </button>

    <div className="imagine-gallery" ref={galleryRef} hidden={!!lightbox || libraryOpen}>
      {pollError && <p className="error" role="status">Đang mất kết nối. Peto sẽ kiểm tra lại lượt ảnh khi có mạng.</p>}
      {loadFailed && <div className="studio-load-error" role="alert"><p>Chưa tải được ảnh đã tạo.</p><button type="button" onClick={() => void loadJobs()}>Thử tải lại</button></div>}
      {!loading && !loadFailed && rootJobs.length === 0 && !generating && <section className="studio-welcome">
        <span className="studio-eyebrow"><SparkleIcon /> Góc sáng tạo của bạn</span>
        <h1>{source ? "Giữ điều bạn thích." : "Bạn tưởng tượng."}<br /><span>{source ? "Sửa điều bạn muốn." : "Peto vẽ nên."}</span></h1>
        <p>{source ? "Ảnh gốc đã sẵn sàng. Kể Peto nghe bạn muốn thay đổi gì." : "Kể Peto nghe về bức ảnh trong đầu bạn, hoặc thêm ảnh để chỉnh sửa."}</p>
        {!source && <div className="studio-ideas">
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
      {jobs.some(job => job.root_image_id && imaginePending(job)) && <p className="workspace-history-status" role="status">Peto đang chỉnh sửa ảnh. Mở ảnh chính để xem lịch sử và kết quả.</p>}
      {rootJobs.length > 0 && <div className="studio-library-head"><h1>Ảnh của bạn</h1><span>{rootJobs.length} lượt đã tải</span><button type="button" className="studio-text-button" onClick={() => setLibraryOpen(true)}>Thư viện</button></div>}
      {rootJobs.map((job) => <section key={job.id} data-job-id={job.id} className="imagine-job">
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
        {imagineSources(job).some(image => image.parent_job_id) && <EditHistory job={job} jobs={rootJobs} onOpen={openImage} onUnauthorized={onUnauthorized} />}
        {imaginePending(job) && <div className="generation-pending" role="status"><strong>{job.status === "queued" ? "Đang chờ đến lượt…" : "Peto đang tạo ảnh…"}</strong><p>Bạn có thể chuyển tab hoặc tải lại trang; lượt này vẫn được theo dõi.</p><JobElapsed createdAt={job.created_at} /><div className="imagine-thumbs" aria-hidden="true">{Array.from({ length: job.n ?? 1 }, (_, index) => <div className="image-placeholder" key={index}><SparkleIcon /></div>)}</div></div>}
        {(job.status === "failed" || job.status === "unknown") && <p className="error">{job.error || "Chưa có kết quả cho lượt này."}{job.status === "unknown" && " Lượt này không được tự gửi lại."}</p>}
        <div className="imagine-thumbs">{job.images.map((image, index) => <button key={image.id} type="button" className="imagine-thumb" aria-label={"Xem ảnh " + (index + 1) + ": " + job.prompt} onClick={() => openImage({ job, index })}>
          <img src={image.url} alt={job.prompt} loading="lazy" decoding="async" /><span className="image-open-hint">Xem ảnh ↗</span>
        </button>)}</div>
      </section>)}
      {hasMore && <button type="button" className="load-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Đang tải…" : "Xem ảnh cũ hơn"}</button>}
    </div>

    {!libraryOpen && !lightbox && studioDock}

    <ImagineLibrary composer={lightbox ? undefined : studioDock} open={active && libraryOpen} modal={compact} suspended={!!lightbox} jobs={rootJobs} onClose={() => setLibraryOpen(false)}
      onOpenImage={(job, index) => openImage({ job, index })} onDeleteImages={removeImages}
      onUseSources={controlsDisabled ? undefined : addLibrarySources} sourceLimit={5 - sources.length}
      hasMore={hasMore} loadingMore={loadingMore} onLoadMore={() => void loadMore()} />
    <dialog ref={lightboxRef} className="imagine-lightbox" aria-label="Xem ảnh đã tạo" aria-modal={compact} onCancel={() => closeImage()} onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); closeImage(); } }}>
      {lightbox && lightboxImage && <ImageWorkspace key={lightboxImage.id} job={lightbox.job} image={lightboxImage} index={lightbox.index}
        mobile={compact} pending={!!workspaceJob || submittingImageId === lightboxImage.id}
        original={!!lightbox.original} liked={lightboxLiked} disabled={controlsDisabled} likeError={likeError}
        canAdd={sources.length < 5} alreadyAdded={sources.some(source => source.imageId === lightboxImage.id)}
        history={imageVersions.length > 0 ? { versions: imageVersions, onSelect: selectVersion }
          : !compact && !lightbox.original && workspaceRootId === lightboxImage.id
            ? { versions: [{ job: lightbox.job, image: lightboxImage }], onSelect: selectVersion } : undefined}
        historyNotice={<>
          {historyLoading && <p className="workspace-history-status" role="status">Đang tải lịch sử…</p>}
          {historyError && <p className="workspace-history-status" role="alert">{historyError} <button type="button" onClick={() => setHistoryReload(value => value + 1)}>Thử lại</button></p>}
          {workspaceJob && (!compact || pollError) && <p className="workspace-history-status" role="status">{pollError ? 'Mất kết nối. Peto sẽ kiểm tra lại kết quả.' : 'Peto đang chỉnh sửa ảnh…'}</p>}
          {failedEdit && !workspaceJob && <p className="workspace-history-status" role="alert">{failedEdit.error || 'Lượt chỉnh sửa chưa có kết quả.'}</p>}
          {!usingImage && uncertainRequest && <p className="workspace-history-status" role="status">Chưa xác nhận lượt vừa gửi. <button type="button" disabled={checkingRequest} onClick={() => void checkUnconfirmed()}>Kiểm tra lượt vừa gửi</button></p>}
          {!usingImage && error && <p className="workspace-history-status" role="alert">{error}<button type="button" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button></p>}
        </>}
        onSave={saveWorkspaceRevision}
        draft={usingImage ? { composer: studioDock, aspect, onAspectChange: setAspect, onAppendPrompt: text => {
          setPrompt(current => current.trim() ? `${current.trimEnd()}\n${text}` : text);
          setExpanded(true); textareaRef.current?.focus();
        } } : undefined}
        onClose={closeImage} onNavigate={index => openImage({ ...lightbox, index, using: false })}
        onLike={() => void toggleLike(lightboxImage.id, !lightboxLiked)}
        onUse={data => prepareWorkspaceSource(lightbox.job, lightboxImage, data, false)}
        onAdd={data => prepareWorkspaceSource(lightbox.job, lightboxImage, data, true)}
        onSubmit={(text, ratio, data) => submitWorkspaceEdit(lightbox.job, lightboxImage, text, ratio, data)} />}

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
