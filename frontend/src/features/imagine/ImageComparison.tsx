import { useState } from "react";
import type { ImagineImage } from "../../shared/api/api";
import MeasuredImage from "./MeasuredImage";

/** Hai khung giữ nguyên tỉ lệ riêng của mỗi ảnh, kể cả khi đã đổi khung hình. */
export default function ImageComparison({ sources, image, prompt }: {
  sources: ImagineImage[]; image: ImagineImage; prompt: string;
}) {
  const [comparing, setComparing] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);
  return <div className="image-comparison">
    <div className="comparison-tools">
      <button type="button" className="studio-text-button" aria-pressed={comparing} onClick={() => setComparing(value => !value)}>So sánh trước / sau</button>
      {comparing && sources.length > 1 && <label>Ảnh gốc <select aria-label="Chọn ảnh gốc để so sánh" value={sourceIndex} onChange={event => setSourceIndex(Number(event.target.value))}>
        {sources.map((source, index) => <option key={source.id} value={index}>Ảnh {index + 1}</option>)}
      </select></label>}
    </div>
    {comparing ? <div className="comparison-panes">
      <figure><figcaption>Trước · Ảnh {sourceIndex + 1}</figcaption><MeasuredImage src={sources[sourceIndex].url} alt={`Ảnh gốc ${sourceIndex + 1}`} /></figure>
      <figure><figcaption>Sau</figcaption><MeasuredImage src={image.url} alt={prompt} /></figure>
    </div> : <MeasuredImage src={image.url} alt={prompt} />}
  </div>;
}
