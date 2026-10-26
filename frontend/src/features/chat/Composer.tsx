import { useEffect, useState, type RefObject } from "react";
import ComposerMenu from "./ComposerMenu";
import EffortMenu from "./EffortMenu";
import { isSpreadsheetFile } from "./attachments";
import { FileGlyph, formatSize, type DraftFile } from "./files";
import ModelMenu from "./ModelMenu";
import { joinDraft, MAX_DRAFT_LINKS, pastedLink, splitDraft } from "./draftLinks";
import { ComposerLinkChip } from "./LinkChip";
import type { Effort, ModelOption, WebSearchMode, QuotedSource } from "../../shared/api/api";
import { QuoteExcerpt } from './QuotedFollowup';
import { isPastedTextFile, LONG_PASTE_CHARS, pasteAtSelection, pastedTextFile } from './longPaste';
import PastedTextPreview from './PastedTextPreview';

const ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,.txt,.md,.csv,.json,.pdf,.docx,.xlsx,.xlsm,.py,.js,.ts,.tsx,.jsx,.css,.html,.xml,.yml,.yaml,.rs,.go,.java,.c,.cpp,.h,.sql,.log";

export function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 12h14M13 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface ComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  files: DraftFile[];
  onAddFiles: (files: FileList | File[]) => boolean | void;
  onRemoveFile: (id: string) => void;
  streaming: boolean;
  stopping: boolean;
  canSend: boolean;
  onSubmit: () => void;
  onStop: () => void;
  effort: Effort;
  efforts: { value: Effort; label: string; hint: string }[];
  onEffortChange: (value: Effort) => void;
  webSearch: WebSearchMode;
  onToggleWeb: () => void;
  /** Menu dấu cộng tắt khi đang trả lời hoặc khi người dùng đang ở tab khác. */
  menuDisabled: boolean;
  /** Model cho tin sắp gửi, chọn ở nút bên trái nút Gửi. Dưới hai model thì không hiện nút. */
  model: string;
  models: ModelOption[];
  onModelChange: (value: string) => void;
  /** Gợi ý ở màn hình trống; mảng rỗng thì không hiện gì. */
  formRef: RefObject<HTMLFormElement | null>;
  boxRef: RefObject<HTMLDivElement | null>;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  fileRef: RefObject<HTMLInputElement | null>;
  contextKey?: string;
  quote?: QuotedSource;
  onRemoveQuote?: () => void;
  onJumpQuote?: (messageId: number) => void;
}

/**
 * Ô nhắn: chữ đang gõ, tệp đính kèm, nút gửi hoặc dừng, và các gợi ý.
 *
 * Chỉ lo phần hiển thị. Bản nháp, danh sách tệp và luồng gửi vẫn nằm ở App vì
 * chúng dính với quy ước giữ nháp tới khi máy chủ xác nhận. Kéo thả do vùng chat
 * nhận chung, còn chọn tệp và dán ảnh vẫn dùng cùng luồng thêm đính kèm.
 */
export default function Composer({
  draft, onDraftChange, files, onAddFiles, onRemoveFile,
  streaming, stopping, canSend, onSubmit, onStop,
  effort, efforts, onEffortChange, webSearch, onToggleWeb, menuDisabled,
  model, models, onModelChange, formRef, boxRef, textareaRef, fileRef, contextKey, quote, onRemoveQuote, onJumpQuote,
}: ComposerProps) {
  // Nháp gồm chữ đang gõ và các link đã dán (draftLinks.ts); ô chữ chỉ hiện phần chữ, link hiện thành thẻ.
  const { text, links } = splitDraft(draft);
  const [converted, setConverted] = useState<{ file: File; expected: string; restored: string; caret: number } | null>(null);
  const [preview, setPreview] = useState<File | null>(null);
  useEffect(() => { setConverted(null); setPreview(null); }, [contextKey]);
  useEffect(() => { if (converted && (streaming || !files.some(item => item.file === converted.file))) setConverted(null); }, [files, streaming, converted]);
  return (
    <form
      ref={formRef}
      className="composer-wrap"
      onSubmit={(event) => {
        event.preventDefault();
        if (!streaming && canSend) void onSubmit();
      }}
    >
      <div className="composer" ref={boxRef}>
        {quote && <QuoteExcerpt quote={quote} onJump={onJumpQuote} onRemove={onRemoveQuote} />}
        {(files.length > 0 || links.length > 0) && (
          <ul className="attach-list">
            {links.map((url) => (
              <ComposerLinkChip key={url} url={url}
                onRemove={() => onDraftChange(joinDraft(text, links.filter((item) => item !== url)))} />
            ))}
            {files.map((item) => (
              <li key={item.id} className="attach-chip">
                {isPastedTextFile(item.file) ? <button type="button" className="attach-pasted-preview" aria-label={`Xem ${item.file.name}`} onClick={() => setPreview(item.file)}>
                  <FileGlyph name={item.file.name} kind="file" /><span><strong>{item.file.name}</strong><em>{formatSize(item.file.size)}</em></span>
                </button> : <>{item.previewUrl ? (
                  <img src={item.previewUrl} alt="" />
                ) : (
                  <FileGlyph name={item.file.name} kind="file" />
                )}
                <span>
                  <strong>{item.file.name}</strong>
                  <em>{formatSize(item.file.size)}</em>
                </span></>}
                <button
                  type="button"
                  disabled={streaming}
                  className="chip-remove"
                  aria-label={`Gỡ ${item.file.name}`}
                  onClick={() => onRemoveFile(item.id)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        {converted && <p className="paste-conversion" role="status">Đã thêm nội dung dán thành tệp
          <button type="button" disabled={draft !== converted.expected || streaming} title={draft !== converted.expected ? 'Bản nháp đã được sửa; tệp vẫn giữ nội dung đã dán' : undefined} onClick={() => {
            if (draft !== converted.expected || streaming) return;
            const item = files.find(item => item.file === converted.file);
            if (item) onRemoveFile(item.id);
            onDraftChange(converted.restored);
            const caret = converted.caret;
            setConverted(null);
            requestAnimationFrame(() => { textareaRef.current?.focus(); textareaRef.current?.setSelectionRange(caret, caret); });
          }}>Hoàn tác</button>
        </p>}

        <textarea
          ref={textareaRef}
          value={text}
          rows={1}
          placeholder="Nhắn cho Peto…"
          aria-label="Nhắn cho Peto"
          enterKeyHint="send"
          onChange={(event) => onDraftChange(joinDraft(event.target.value, links))}
          onPaste={(event) => {
            const pasted = Array.from(event.clipboardData.files);
            if (pasted.length) {
              event.preventDefault();
              onAddFiles(pasted);
              return;
            }
            const incoming = event.clipboardData.getData('text/plain') || event.clipboardData.getData('text');
            if (!streaming && incoming.length > LONG_PASTE_CHARS) {
              const file = pastedTextFile(incoming, files.map(item => item.file.name));
              // Rejected attachments fall back to the browser's normal text paste; never drop the clipboard text.
              if (onAddFiles([file]) !== false) {
                event.preventDefault();
                const inserted = pasteAtSelection(text, incoming, event.currentTarget.selectionStart, event.currentTarget.selectionEnd);
                const expected = joinDraft(inserted.remaining, links);
                onDraftChange(expected);
                setConverted({ file, expected, restored: joinDraft(inserted.restored, links), caret: inserted.caret });
                const caret = Math.min(event.currentTarget.selectionStart, inserted.remaining.length);
                requestAnimationFrame(() => {
                  if (document.activeElement === textareaRef.current) textareaRef.current?.setSelectionRange(caret, caret);
                });
                return;
              }
            }
            // Dán đúng một link thì nó thành thẻ; dán link lẫn với chữ thì vẫn dán chữ như thường.
            const url = pastedLink(event.clipboardData.getData("text"));
            if (!url || links.length >= MAX_DRAFT_LINKS) return;
            event.preventDefault();
            if (!links.includes(url)) onDraftChange(joinDraft(text, [...links, url]));
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              if (!streaming && canSend) void onSubmit();
            }
          }}
        />

        <div className="composer-bar">
          <div className="composer-tools">
            <input
              ref={fileRef}
              type="file"
              hidden
              multiple
              accept={ACCEPT}
              onChange={(event) => {
                if (event.target.files) onAddFiles(event.target.files);
                event.target.value = "";
              }}
            />
            <ComposerMenu disabled={menuDisabled} webDisabled={webSearch === "off"}
              onAttach={() => fileRef.current?.click()} onToggleWeb={onToggleWeb} />

            <EffortMenu value={effort} options={efforts} disabled={streaming} onChange={onEffortChange} />
          </div>

          <div className="composer-send">
            {models.length > 1 && (
              <ModelMenu value={model} options={models} disabled={streaming} onChange={onModelChange} />
            )}
            {streaming ? (
              <button type="button" className="stop" disabled={stopping} onClick={onStop}>
                {stopping ? "Đang dừng…" : "Dừng"}
              </button>
            ) : (
              <button type="submit" className="send" disabled={!canSend} aria-label="Gửi">
                <span className="send-text">Gửi</span> <SendIcon />
              </button>
            )}
          </div>
        </div>
      </div>
      {files.some((item) => /\.pdf$/i.test(item.file.name) || item.file.type === "application/pdf") &&
        <p className="composer-note">Peto đọc chữ và dẫn số trang trong PDF, nhận dạng cả trang scan khi máy chủ có OCR. Chữ từ ảnh có thể nhận sai; kết quả đọc sẽ hiện dưới tệp.</p>}
      {files.some((item) => isSpreadsheetFile(item.file)) &&
        <p className="composer-note">Peto đọc dữ liệu, công thức, ghi chú, biểu đồ và bảng tổng hợp trong tệp Excel, và sửa thẳng được trên tệp mà giữ định dạng; chưa xem được hình ảnh và màu ô.</p>}
      {preview && <PastedTextPreview file={preview} onClose={() => setPreview(null)} />}
    </form>
  );
}
