import { useEffect, useState } from "react";
import { getImagineJob, imagineSources, UnauthorizedError, type ImagineImage, type ImagineJob } from "../../shared/api/api";

type HistoryImage = { job: ImagineJob; image: ImagineImage; index: number; original?: boolean; sourceIndex?: number };

/** Chỉ tải các lượt trước khi mở lịch sử; ảnh đã xóa vẫn còn bản tham chiếu của lượt sau. */
export default function EditHistory({ job, jobs, onOpen, onUnauthorized }: {
  job: ImagineJob; jobs: ImagineJob[];
  onOpen: (value: HistoryImage) => void;
  onUnauthorized: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [extra, setExtra] = useState<ImagineJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [incomplete, setIncomplete] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const load = async () => {
      setLoading(true); setIncomplete(false);
      const known = new Map(jobs.map(row => [row.id, row]));
      const queue = [job];
      const visited = new Set<string>();
      const fetched: ImagineJob[] = [];
      let missing = false;
      while (queue.length && visited.size < 100 && !controller.signal.aborted) {
        const current = queue.shift()!;
        if (visited.has(current.id)) continue;
        visited.add(current.id);
        for (const source of imagineSources(current)) {
          const id = source.parent_job_id;
          if (!id || visited.has(id)) continue;
          let parent = known.get(id);
          if (!parent) {
            try {
              parent = await getImagineJob(id, controller.signal);
              known.set(id, parent); fetched.push(parent);
            } catch (err) {
              if (controller.signal.aborted) return;
              if (err instanceof UnauthorizedError) { onUnauthorized(); return; }
              visited.add(id); missing = true;
            }
          }
          if (parent) queue.push(parent);
        }
      }
      if (!controller.signal.aborted) {
        setExtra(fetched); setIncomplete(missing || queue.length > 0); setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [open, job, jobs, onUnauthorized, attempt]);

  const known = new Map([...extra, ...jobs].map(row => [row.id, row]));
  const seen = new Set<string>();
  const nodes: HistoryImage[] = [];
  const visit = (current: ImagineJob, selectedImageId?: string) => {
    const key = `${current.id}:${selectedImageId ?? "all"}`;
    if (seen.has(key) || seen.size >= 100) return;
    seen.add(key);
    imagineSources(current).forEach((source, sourceIndex) => {
      const parent = source.parent_job_id ? known.get(source.parent_job_id) : undefined;
      if (parent?.images.some(image => image.id === source.parent_image_id)) visit(parent, source.parent_image_id!);
      else nodes.push({ job: current, image: source, index: 0, original: true, sourceIndex });
    });
    current.images.forEach((image, index) => {
      if (!selectedImageId || image.id === selectedImageId) nodes.push({ job: current, image, index });
    });
  };
  if (open) visit(job);
  const unique = nodes.filter((node, index) => nodes.findIndex(other => other.image.id === node.image.id) === index);
  return <details className="edit-history" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Lịch sử chỉnh sửa</summary>
    {loading && <p role="status">Đang mở các lượt sửa trước…</p>}
    {incomplete && <p>Một phần lịch sử chưa tải được hoặc đã bị xóa. Bản ảnh tham chiếu vẫn được giữ. <button type="button" className="studio-text-button" onClick={() => setAttempt(value => value + 1)}>Tải lại lịch sử</button></p>}
    <div className="edit-history-strip">{unique.map(node => <button type="button" key={node.image.id} onClick={() => onOpen(node)}><img src={node.image.url} alt="" loading="lazy" /><span>{node.original ? "Bản gốc đã lưu" : node.job.id === job.id ? "Lượt hiện tại" : node.job.prompt}</span></button>)}</div>
  </details>;
}
