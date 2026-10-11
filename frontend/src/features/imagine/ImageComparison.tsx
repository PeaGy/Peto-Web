import { useId, useState } from "react";
import { Dropdown } from "../../shared/ui/Dropdown";
import type { ImagineImage } from "../../shared/api/api";
import MeasuredImage from "./MeasuredImage";

/** Hai khung giữ nguyên tỉ lệ riêng của mỗi ảnh, kể cả khi đã đổi khung hình. */
export default function ImageComparison({ sources, image, prompt, startComparing = false, hideToggle = false }: {
  sources: ImagineImage[]; image: ImagineImage; prompt: string; startComparing?: boolean; hideToggle?: boolean;
}) {
  const [comparing, setComparing] = useState(startComparing);
  const [sourceIndex, setSourceIndex] = useState(0);
  const sourceId = useId();
  return <div className="image-comparison">
    <div className="comparison-tools">
      {!hideToggle && <button type="button" className="studio-text-button" aria-pressed={comparing} onClick={() => setComparing(value => !value)}>So sánh trước / sau</button>}
      {comparing && sources.length > 1 && <div className="comparison-source"><span aria-hidden="true">Ảnh gốc</span>
        <Dropdown id={sourceId} className="compact" ariaLabel="Chọn ảnh gốc để so sánh" value={String(sourceIndex)} onChange={next => setSourceIndex(Number(next))}
          options={sources.map((_, index) => ({ value: String(index), label: `Ảnh ${index + 1}` }))} />
      </div>}
    </div>
    {comparing ? <div className="comparison-panes">
      <figure><figcaption>Trước · Ảnh {sourceIndex + 1}</figcaption><MeasuredImage src={sources[sourceIndex].url} alt={`Ảnh gốc ${sourceIndex + 1}`} /></figure>
      <figure><figcaption>Sau</figcaption><MeasuredImage src={image.url} alt={prompt} /></figure>
    </div> : <MeasuredImage src={image.url} alt={prompt} />}
  </div>;
}
