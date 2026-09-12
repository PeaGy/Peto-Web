import { useRef, useState, type RefObject } from "react";
import ComposerMenu from "./ComposerMenu";
import EffortMenu from "./EffortMenu";
import { FileGlyph, formatSize, type DraftFile } from "./files";
import type { Effort, WebSearchMode } from "./api";

const ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,.txt,.md,.csv,.json,.pdf,.docx,.py,.js,.ts,.tsx,.jsx,.css,.html,.xml,.yml,.yaml,.rs,.go,.java,.c,.cpp,.h,.sql,.log";

function SendIcon() {
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

function SpeakerIcon({ on }: { on: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 9v6h4l5 4V5L8 9H4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      {on ? (
        <path d="M16.5 8.5a5 5 0 0 1 0 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      ) : (
        <path d="M17 9.5l4 5M21 9.5l-4 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      )}
    </svg>
  );
}

interface ComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  files: DraftFile[];
  onAddFiles: (files: FileList | File[]) => void;
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
  /** Gợi ý ở màn hình trống; mảng rỗng thì không hiện gì. */
  hints: string[];
  onPickHint: (hint: string) => void;
  voiceOn: boolean;
  /** Trình duyệt không đọc được thì giấu luôn nút loa cho đỡ rối. */
  voiceSupported: boolean;
  onToggleVoice: () => void;
  formRef: RefObject<HTMLFormElement | null>;
  boxRef: RefObject<HTMLDivElement | null>;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  fileRef: RefObject<HTMLInputElement | null>;
}

/**
 * Ô nhắn: chữ đang gõ, tệp đính kèm, nút gửi hoặc dừng, và các gợi ý.
 *
 * Chỉ lo phần hiển thị. Bản nháp, danh sách tệp và luồng gửi vẫn nằm ở App vì
 * chúng dính với quy ước giữ nháp tới khi máy chủ xác nhận. Riêng trạng thái kéo
 * thả thì ở đây: ngoài ô nhắn không ai cần biết.
 */
export default function Composer({
  draft, onDraftChange, files, onAddFiles, onRemoveFile,
  streaming, stopping, canSend, onSubmit, onStop,
  effort, efforts, onEffortChange, webSearch, onToggleWeb, menuDisabled,
  hints, onPickHint, voiceOn, voiceSupported, onToggleVoice,
  formRef, boxRef, textareaRef, fileRef,
}: ComposerProps) {
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);

  return (
    <form
      ref={formRef}
      className={dragging ? "composer-wrap dragging" : "composer-wrap"}
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit();
      }}
      onDragEnter={(event) => {
        event.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        event.preventDefault();
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        if (event.dataTransfer.files.length) onAddFiles(event.dataTransfer.files);
      }}
    >
      {dragging && <div className="drop-hint">Thả ảnh hoặc tệp vào đây</div>}

      <div className="composer" ref={boxRef}>
        {files.length > 0 && (
          <ul className="attach-list">
            {files.map((item) => (
              <li key={item.id} className="attach-chip">
                {item.previewUrl ? (
                  <img src={item.previewUrl} alt="" />
                ) : (
                  <FileGlyph name={item.file.name} kind="file" />
                )}
                <span>
                  <strong>{item.file.name}</strong>
                  <em>{formatSize(item.file.size)}</em>
                </span>
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

        <textarea
          ref={textareaRef}
          value={draft}
          rows={1}
          placeholder="Nhắn cho Peto…"
          aria-label="Nhắn cho Peto"
          disabled={streaming}
          onChange={(event) => onDraftChange(event.target.value)}
          onPaste={(event) => {
            const pasted = Array.from(event.clipboardData.files);
            if (pasted.length) {
              event.preventDefault();
              onAddFiles(pasted);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void onSubmit();
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

            {voiceSupported && (
              <button
                type="button"
                className={voiceOn ? "icon-btn voice-toggle on" : "icon-btn voice-toggle"}
                aria-pressed={voiceOn}
                aria-label={voiceOn ? "Tắt đọc thành tiếng" : "Đọc câu trả lời thành tiếng"}
                title={voiceOn ? "Tắt đọc thành tiếng" : "Đọc câu trả lời thành tiếng"}
                onClick={onToggleVoice}
              >
                <SpeakerIcon on={voiceOn} />
              </button>
            )}
          </div>

          {streaming ? (
            <button type="button" className="stop" disabled={stopping} onClick={onStop}>
              {stopping ? "Đang dừng…" : "Dừng"}
            </button>
          ) : (
            <button type="submit" className="send" disabled={!canSend} aria-label="Gửi">
              Gửi <SendIcon />
            </button>
          )}
        </div>
      </div>
      {hints.length > 0 && (
        <div className="welcome-hints">
          {hints.map((hint) => (
            <button key={hint} type="button" onClick={() => onPickHint(hint)}>{hint}</button>
          ))}
        </div>
      )}
      <p className="composer-note">
        {files.some((item) => /\.pdf$/i.test(item.file.name) || item.file.type === "application/pdf")
          ? "Peto đọc lớp chữ trong PDF và dẫn số trang. PDF ảnh scan chưa có chữ cần OCR trước nhé."
          : "Tệp chữ/code tối đa 16 · ảnh, PDF, Word tối đa 4 · 8 MB/tệp, tổng 16 MB."}
      </p>
    </form>
  );
}
