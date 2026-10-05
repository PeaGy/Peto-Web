import { colorParts } from './workbookChanges';

/** Chữ của một dòng thay đổi trong tệp Excel Peto đã sửa; mã màu #RRGGBB hiện thành ô màu nhỏ. */
export default function ChangeText({ text }: { text: string }) {
  return <span>{colorParts(text).map((part, index) => part.color
    ? <i key={index} className="wb-swatch" style={{ background: part.color }} title={part.text} aria-label={`màu ${part.text}`} />
    : <span key={index}>{part.text}</span>)}</span>;
}
