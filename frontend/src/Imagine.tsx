import { useCallback, useEffect, useRef, useState } from "react";
import {
  UnauthorizedError,
  createImagineJob,
  deleteImagineJob,
  listImagineJobs,
  type AppInfo,
  type ImagineJob,
  type ImagineQuality,
  type ImagineResolution,
} from "./api";

const QUALITY_KEY = "peto-imagine-quality";
const RATIO_KEY = "peto-imagine-ratio";
const RES_KEY = "peto-imagine-res";
const COUNT_KEY = "peto-imagine-n";

const RATIOS: { value: string; label: string }[] = [
  { value: "auto", label: "Tự động" },
  { value: "1:1", label: "1:1" },
  { value: "16:9", label: "16:9" },
  { value: "9:16", label: "9:16" },
  { value: "4:3", label: "4:3" },
  { value: "3:4", label: "3:4" },
  { value: "3:2", label: "3:2" },
  { value: "2:3", label: "2:3" },
];

function readStored<T extends string>(key: string, allowed: T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return allowed.includes(value as T) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3.2 13.6 8.4 19 10l-5.4 1.6L12 16.8 10.4 11.6 5 10l5.4-1.6L12 3.2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M18.2 15.2 19 17.4 21.2 18.2 19 19l-.8 2.2L17.4 19 15.2 18.2 17.4 17.4 18.2 15.2Z" fill="currentColor" />
    </svg>
  );
}

export default function Imagine({
  appInfo,
  onUnauthorized,
  onOpenSidebar,
}: {
  appInfo: AppInfo | null;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [quality, setQuality] = useState<ImagineQuality>(() =>
    readStored(QUALITY_KEY, ["low", "medium"], "low"),
  );
  const [resolution, setResolution] = useState<ImagineResolution>(() =>
    readStored(RES_KEY, ["1k", "2k"], "1k"),
  );
  const [aspect, setAspect] = useState(() =>
    readStored(
      RATIO_KEY,
      RATIOS.map((item) => item.value),
      "auto",
    ),
  );
  const [count, setCount] = useState(() => {
    const raw = Number(readStored(COUNT_KEY, ["1", "2", "3", "4"], "1"));
    return Number.isFinite(raw) ? raw : 1;
  });
  const [jobs, setJobs] = useState<ImagineJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ job: ImagineJob; imageId: string } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await listImagineJobs());
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Không tải được ảnh đã tạo");
    } finally {
      setLoading(false);
    }
  }, [onUnauthorized]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => writeStored(QUALITY_KEY, quality), [quality]);
  useEffect(() => writeStored(RES_KEY, resolution), [resolution]);
  useEffect(() => writeStored(RATIO_KEY, aspect), [aspect]);
  useEffect(() => writeStored(COUNT_KEY, String(count)), [count]);

  async function generate() {
    const text = prompt.trim();
    if (!text || generating) return;
    setError(null);
    setGenerating(true);
    try {
      const job = await createImagineJob({
        prompt: text,
        quality,
        resolution,
        aspect_ratio: aspect,
        n: count,
      });
      setJobs((prev) => [job, ...prev]);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Không tạo được ảnh");
    } finally {
      setGenerating(false);
      textareaRef.current?.focus();
    }
  }

  async function removeJob(id: string) {
    try {
      await deleteImagineJob(id);
      setJobs((prev) => prev.filter((job) => job.id !== id));
      setLightbox((current) => (current?.job.id === id ? null : current));
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Không xóa được");
    }
  }

  const lightboxImage = lightbox?.job.images.find((image) => image.id === lightbox.imageId);

  return (
    <main className="imagine">
      <header className="chat-header">
        <button
          type="button"
          className="menu-btn"
          aria-label="Mở menu"
          onClick={onOpenSidebar}
        >
          <MenuIcon />
        </button>
        <span className="imagine-mark" aria-hidden="true">
          <SparkleIcon />
        </span>
        <div className="header-copy">
          <strong>Imagine</strong>
          <span className="subtitle">
            Grok Imagine · tạo ảnh tách khỏi chat của {appInfo?.name ?? "Peto"}
          </span>
        </div>
      </header>

      <div className="imagine-gallery">
        {loading && <p className="loading-chat" role="status">Đang tải ảnh đã tạo…</p>}
        {!loading && jobs.length === 0 && !generating && (
          <div className="welcome">
            <span className="imagine-hero" aria-hidden="true">
              <SparkleIcon />
            </span>
            <h1>Imagine</h1>
            <p>Viết prompt bên dưới. Chat thường sẽ không vẽ — chỉ tab này mới tạo ảnh.</p>
            <div className="welcome-hints">
              {[
                "mèo trắng đội mũ phù thủy, ánh đèn studio",
                "thành phố đêm mưa theo kiểu anime",
                "poster synthwave cho ban nhạc giả tưởng",
              ].map((hint) => (
                <button
                  key={hint}
                  type="button"
                  onClick={() => {
                    setPrompt(hint);
                    textareaRef.current?.focus();
                  }}
                >
                  {hint}
                </button>
              ))}
            </div>
          </div>
        )}

        {jobs.map((job) => (
          <section key={job.id} className="imagine-job">
            <div className="imagine-job-head">
              <p className="imagine-prompt">{job.prompt}</p>
              <div className="imagine-meta">
                <span>{job.quality === "low" ? "Nhanh" : "Chất lượng"}</span>
                <span>{job.resolution.toUpperCase()}</span>
                <span>{job.aspect_ratio}</span>
                <button type="button" className="imagine-delete" onClick={() => void removeJob(job.id)}>
                  Xóa
                </button>
              </div>
            </div>
            <div className="imagine-thumbs">
              {job.images.map((image) => (
                <button
                  key={image.id}
                  type="button"
                  className="imagine-thumb"
                  onClick={() => setLightbox({ job, imageId: image.id })}
                >
                  <img src={image.url} alt={job.prompt} />
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      {error && (
        <div className="error" role="alert">
          {error}
          <button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      <form
        className="composer-wrap"
        onSubmit={(event) => {
          event.preventDefault();
          void generate();
        }}
      >
        <div className="composer imagine-composer">
          <textarea
            ref={textareaRef}
            value={prompt}
            rows={2}
            placeholder="Mô tả ảnh muốn tạo…"
            aria-label="Prompt tạo ảnh"
            disabled={generating}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void generate();
              }
            }}
          />
          <div className="imagine-controls">
            <div className="seg" role="group" aria-label="Tốc độ hoặc chất lượng">
              <button
                type="button"
                className={quality === "low" ? "on" : ""}
                disabled={generating}
                title="Nhanh hơn, rẻ hơn — quality low"
                onClick={() => setQuality("low")}
              >
                Nhanh
              </button>
              <button
                type="button"
                className={quality === "medium" ? "on" : ""}
                disabled={generating}
                title="Nét hơn, chậm hơn — quality medium"
                onClick={() => setQuality("medium")}
              >
                Chất lượng
              </button>
            </div>
            <div className="seg" role="group" aria-label="Độ phân giải">
              <button
                type="button"
                className={resolution === "1k" ? "on" : ""}
                disabled={generating}
                onClick={() => setResolution("1k")}
              >
                1K
              </button>
              <button
                type="button"
                className={resolution === "2k" ? "on" : ""}
                disabled={generating}
                onClick={() => setResolution("2k")}
              >
                2K
              </button>
            </div>
            <label className="effort-select">
              <span className="effort-label">Tỉ lệ</span>
              <select
                value={aspect}
                disabled={generating}
                onChange={(event) => setAspect(event.target.value)}
              >
                {RATIOS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="effort-select">
              <span className="effort-label">Số ảnh</span>
              <select
                value={count}
                disabled={generating}
                onChange={(event) => setCount(Number(event.target.value))}
              >
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="composer-bar">
            <p className="imagine-hint">
              {quality === "low" ? "Speed · low" : "Quality · medium"} · {resolution.toUpperCase()} · {aspect}
            </p>
            <button type="submit" className="send" disabled={!prompt.trim() || generating}>
              {generating ? "Đang tạo…" : "Tạo ảnh"}
            </button>
          </div>
        </div>
      </form>

      {lightbox && lightboxImage && (
        <div
          className="imagine-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={lightbox.job.prompt}
          onClick={() => setLightbox(null)}
        >
          <div className="imagine-lightbox-card" onClick={(event) => event.stopPropagation()}>
            <img src={lightboxImage.url} alt={lightbox.job.prompt} />
            <p>{lightbox.job.prompt}</p>
            <div className="imagine-lightbox-actions">
              <a href={`${lightboxImage.url}?download=1`} download>
                Tải ảnh
              </a>
              <button type="button" onClick={() => setLightbox(null)}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
