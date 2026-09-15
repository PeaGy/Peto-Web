import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import type { ImagineImage, ImagineJob } from "./api";

const COLUMNS_KEY = "peto-imagine-library-columns";
const LONG_PRESS_MS = 500;
const MENU_WIDTH = 200;
const MENU_HEIGHT = 140;

type Tile = { job: ImagineJob; image: ImagineImage; index: number };
type Menu = { tile: Tile; top: number; left: number };

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
export function HeartIcon({ filled }: { filled?: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} aria-hidden="true">
    <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
  </svg>;
}
const CheckIcon = () => <Icon size={16}><path d="m5 12.5 4.5 4.5L19 7" /></Icon>;
const ShareIcon = () => <Icon><circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4" /></Icon>;
const DownloadIcon = () => <Icon><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></Icon>;
const TrashIcon = () => <Icon><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></Icon>;

function readColumns(): 2 | 3 {
  try { return localStorage.getItem(COLUMNS_KEY) === "3" ? 3 : 2; } catch { return 2; }
}
/** Bỏ dấu để "meo" tìm ra "Mèo". Chữ đ không tách dấu được nên đổi riêng. */
function fold(text: string) {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/đ/g, "d");
}
/** Chia sẻ tệp ảnh cần Web Share có hỗ trợ tệp; Firefox trên máy tính chẳng hạn thì không. */
function canShareFiles() {
  try {
    return typeof navigator.share === "function" && typeof navigator.canShare === "function"
      && navigator.canShare({ files: [new File([""], "peto.png", { type: "image/png" })] });
  } catch { return false; }
}

/**
 * Thư viện ảnh kiểu Grok, mở từ nút bên trái thanh nhập trên điện thoại.
 *
 * Mỗi ô là một ảnh kết quả. Chạm để xem, "Chọn" để chọn nhiều, giữ lâu (hoặc chuột phải) để mở menu
 * của riêng ảnh đó. Việc gọi API xóa và cập nhật danh sách nằm ở Imagine, vì bộ ảnh và cột trái dùng chung.
 */
export default function ImagineLibrary({ open, jobs, onClose, onOpenImage, onDeleteImages }: {
  open: boolean;
  jobs: ImagineJob[];
  onClose: () => void;
  onOpenImage: (job: ImagineJob, index: number) => void;
  /** Xóa lần lượt từng ảnh; ném lỗi tiếng Việt nếu còn ảnh chưa xóa được. */
  onDeleteImages: (ids: string[]) => Promise<void>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLDialogElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const filterRef = useRef<HTMLDivElement>(null);
  const press = useRef<{ timer: number; x: number; y: number } | null>(null);
  const longPressed = useRef(false);
  const [query, setQuery] = useState("");
  const [columns, setColumns] = useState(readColumns);
  const [likedOnly, setLikedOnly] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [menu, setMenu] = useState<Menu | null>(null);
  const [confirmIds, setConfirmIds] = useState<string[] | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const shareable = useMemo(canShareFiles, []);

  const tiles = useMemo(() => jobs.flatMap((job) => job.images.map((image, index) => ({ job, image, index }))), [jobs]);
  const needle = fold(query.trim());
  const shown = tiles.filter((tile) => (!likedOnly || tile.image.liked) && (!needle || fold(tile.job.prompt).includes(needle)));
  const picked = tiles.filter((tile) => selected.has(tile.image.id));

  useEffect(() => {
    if (open) { dialogRef.current?.showModal(); return; }
    dialogRef.current?.close();
    cancelPress();
    setSelecting(false); setSelected(new Set()); setMenu(null); setFilterOpen(false);
    setConfirmIds(null); setNotice(null); setQuery(""); setLikedOnly(false);
  }, [open]);
  useEffect(() => {
    if (confirmIds) confirmRef.current?.showModal();
    else confirmRef.current?.close();
  }, [confirmIds]);
  useEffect(() => { try { localStorage.setItem(COLUMNS_KEY, String(columns)); } catch {} }, [columns]);
  useEffect(() => { if (menu) menuRef.current?.querySelector("button")?.focus(); }, [menu]);
  useEffect(() => {
    if (!menu && !filterOpen) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menu && !menuRef.current?.contains(target)) setMenu(null);
      if (filterOpen && !filterRef.current?.contains(target)) setFilterOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [menu, filterOpen]);
  useEffect(() => () => cancelPress(), []);

  function cancelPress() {
    if (press.current) window.clearTimeout(press.current.timer);
    press.current = null;
  }
  function exitSelecting() {
    setSelecting(false);
    setSelected(new Set());
    setMenu(null);
  }
  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }
  // Như Grok: giữ lâu thì ảnh được chọn luôn, menu hiện ngay dưới ảnh (hết chỗ thì lên trên).
  function openMenu(tile: Tile, element: HTMLElement) {
    const rect = element.getBoundingClientRect();
    const below = rect.bottom + 8 + MENU_HEIGHT <= window.innerHeight;
    setSelecting(true);
    setSelected((prev) => new Set(prev).add(tile.image.id));
    setMenu({
      tile,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - MENU_WIDTH - 8)),
      top: below ? rect.bottom + 8 : Math.max(8, rect.top - MENU_HEIGHT - 8),
    });
  }
  function onTilePointerDown(event: ReactPointerEvent<HTMLButtonElement>, tile: Tile) {
    if (event.button !== 0) return;
    cancelPress();
    longPressed.current = false;
    const element = event.currentTarget;
    const timer = window.setTimeout(() => {
      press.current = null;
      longPressed.current = true;
      openMenu(tile, element);
    }, LONG_PRESS_MS);
    press.current = { timer, x: event.clientX, y: event.clientY };
  }
  function onTilePointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    // Ngón tay trượt để cuộn thì không tính là giữ lâu.
    if (press.current && Math.hypot(event.clientX - press.current.x, event.clientY - press.current.y) > 10) cancelPress();
  }
  function onTileClick(tile: Tile) {
    if (longPressed.current) { longPressed.current = false; return; }
    if (selecting) toggle(tile.image.id);
    else onOpenImage(tile.job, tile.index);
  }

  function download(list: Tile[]) {
    setMenu(null);
    for (const { image } of list) {
      const link = document.createElement("a");
      link.href = image.url + "?download=1";
      link.download = "";
      link.hidden = true;
      dialogRef.current?.append(link);
      link.click();
      link.remove();
    }
  }
  async function share(list: Tile[]) {
    setMenu(null);
    setNotice(null);
    try {
      const files = await Promise.all(list.map(async ({ image }, index) => {
        const response = await fetch(image.url);
        if (!response.ok) throw new Error(String(response.status));
        const blob = await response.blob();
        const type = blob.type || image.mime;
        return new File([blob], `peto-${index + 1}.${type.split("/")[1] || "png"}`, { type });
      }));
      await navigator.share({ files });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setNotice("Chưa chia sẻ được ảnh. Bạn thử Tải xuống nhé.");
    }
  }
  async function confirmDelete() {
    if (!confirmIds || deleting) return;
    setDeleting(true);
    setNotice(null);
    try {
      await onDeleteImages(confirmIds);
      exitSelecting();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Chưa xóa được ảnh. Thử lại nhé.");
    } finally {
      setDeleting(false);
      setConfirmIds(null);
    }
  }

  return <dialog ref={dialogRef} className="imagine-library-view" aria-label="Thư viện ảnh" onCancel={(event) => {
    // Escape đóng từng lớp một: menu, bảng lọc, chế độ chọn, rồi mới tới thư viện.
    event.preventDefault();
    if (menu) setMenu(null);
    else if (filterOpen) setFilterOpen(false);
    else if (selecting) exitSelecting();
    else onClose();
  }}>
    {open && <>
      <div className="library-top">
        <button type="button" className="library-round" aria-label="Đóng thư viện" onClick={onClose}>
          <Icon><path d="M6 6l12 12M18 6 6 18" /></Icon>
        </button>
        <button type="button" className="library-pill" onClick={() => selecting ? exitSelecting() : setSelecting(true)}>{selecting ? "Hủy" : "Chọn"}</button>
      </div>
      <p className="sr-only" aria-live="polite">{selecting ? `Đã chọn ${picked.length} ảnh` : ""}</p>

      <div className="library-grid" style={{ "--library-columns": columns } as CSSProperties}>
        {tiles.length === 0 ? <p className="library-empty">Chưa có ảnh nào. Ảnh bạn tạo sẽ hiện ở đây.</p>
          : shown.length === 0 ? <p className="library-empty">Không có ảnh nào khớp</p>
          : shown.map((tile) => {
            const on = selected.has(tile.image.id);
            return <button key={tile.image.id} type="button" data-image-id={tile.image.id}
              className={"library-tile" + (on ? " selected" : "")}
              aria-label={(selecting ? "Chọn ảnh: " : "Xem ảnh: ") + tile.job.prompt} aria-pressed={selecting ? on : undefined}
              onPointerDown={(event) => onTilePointerDown(event, tile)} onPointerMove={onTilePointerMove}
              onPointerUp={cancelPress} onPointerCancel={cancelPress} onPointerLeave={cancelPress}
              onContextMenu={(event) => { event.preventDefault(); cancelPress(); openMenu(tile, event.currentTarget); }}
              onClick={() => onTileClick(tile)}>
              <img src={tile.image.url} alt="" loading="lazy" decoding="async" draggable={false} />
              {selecting && <span className="library-check" aria-hidden="true">{on && <CheckIcon />}</span>}
            </button>;
          })}
      </div>

      {notice && <div className="error library-notice" role="alert">{notice}<button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setNotice(null)}>×</button></div>}
      {selecting ? <div className="library-actions">
        {shareable && <button type="button" disabled={!picked.length} onClick={() => void share(picked)}><ShareIcon /><span>Chia sẻ</span></button>}
        <button type="button" disabled={!picked.length} onClick={() => download(picked)}><DownloadIcon /><span>Tải xuống</span></button>
        <button type="button" className="danger" disabled={!picked.length || deleting} onClick={() => setConfirmIds(picked.map((tile) => tile.image.id))}><TrashIcon /><span>Xóa</span></button>
      </div> : <div className="library-bottom">
        <div className="library-search">
          <Icon size={18}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></Icon>
          <input type="search" value={query} placeholder="Tìm kiếm" aria-label="Tìm ảnh theo mô tả" onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div ref={filterRef} className="library-filter">
          <button type="button" className="library-round" aria-label="Bố cục và bộ lọc" aria-expanded={filterOpen} onClick={() => setFilterOpen((value) => !value)}>
            <Icon><path d="M4 7h16M7 12h10M10 17h4" /></Icon>
          </button>
          {filterOpen && <div className="effort-options library-filter-panel" role="group" aria-label="Bố cục và bộ lọc">
            <p className="effort-heading">Bố cục</p>
            <div className="seg" role="group" aria-label="Số cột">
              {([2, 3] as const).map((value) => <button key={value} type="button" className={columns === value ? "on" : ""} aria-pressed={columns === value} onClick={() => setColumns(value)}>{value} cột</button>)}
            </div>
            <button type="button" className="effort-option" aria-pressed={likedOnly} onClick={() => setLikedOnly((value) => !value)}>
              <HeartIcon filled={likedOnly} /><span className="effort-option-label">Chỉ ảnh đã thích</span>{likedOnly && <span className="effort-check"><CheckIcon /></span>}
            </button>
          </div>}
        </div>
      </div>}

      {menu && <div ref={menuRef} className="effort-options library-menu" role="menu" aria-label="Thao tác với ảnh" style={{ top: menu.top, left: menu.left }}>
        <button type="button" role="menuitem" className="effort-option" onClick={() => download([menu.tile])}><DownloadIcon /><span className="effort-option-label">Tải xuống</span></button>
        {shareable && <button type="button" role="menuitem" className="effort-option" onClick={() => void share([menu.tile])}><ShareIcon /><span className="effort-option-label">Chia sẻ</span></button>}
        <button type="button" role="menuitem" className="effort-option danger" onClick={() => { setMenu(null); setConfirmIds([menu.tile.image.id]); }}><TrashIcon /><span className="effort-option-label">Xóa ảnh</span></button>
      </div>}

      <dialog ref={confirmRef} className="confirm-dialog" aria-labelledby="library-delete-title" onCancel={(event) => { event.preventDefault(); if (!deleting) setConfirmIds(null); }}>
        <h2 id="library-delete-title">{confirmIds && confirmIds.length > 1 ? `Xóa ${confirmIds.length} ảnh?` : "Xóa ảnh này?"}</h2>
        <p>Ảnh đã xóa không khôi phục được. Lượt nào không còn ảnh sẽ biến khỏi thư viện.</p>
        <div className="dialog-actions">
          <button type="button" autoFocus disabled={deleting} onClick={() => setConfirmIds(null)}>Giữ lại</button>
          <button type="button" className="danger-button" disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? "Đang xóa…" : "Xóa ảnh"}</button>
        </div>
      </dialog>
    </>}
  </dialog>;
}
