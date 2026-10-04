import { EditIcon } from '../../shared/ui/EditIcon';
import { GitHubIcon } from '../../shared/ui/GitHubIcon';
import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Markdown, { type Components } from 'react-markdown';
import { normalizeMath } from '../../shared/markdown/mathMarkdown';
import { useMarkdownPlugins } from '../../shared/markdown/markdownExtras';
import { DiagramCard } from '../diagrams/DiagramCard';
import { hastText } from '../diagrams/diagrams';
import { DocumentIcon } from '../documents/DocumentWorkspace';
import DocumentArtifactCard from '../documents/DocumentArtifactCard';
import { FileGlyph, formatSize } from './files';
import WebSources, { GlobeIcon } from './WebSources';
import type { Message, WorkStep } from '../../shared/api/api';

// Nhãn đầu khối code. Ngôn ngữ được tô màu nằm ở markdownCode.ts: thêm ngôn ngữ ở đó thì thêm nhãn ở đây.
const CODE_LABELS: Record<string, string> = {
  bash: "Bash", c: "C", "c#": "C#", "c++": "C++", cc: "C++", console: "Bash", cpp: "C++",
  cs: "C#", csharp: "C#", css: "CSS", dart: "Dart", diff: "Diff", docker: "Dockerfile",
  dockerfile: "Dockerfile", go: "Go", golang: "Go", h: "C", html: "HTML", ini: "INI",
  java: "Java", javascript: "JavaScript", js: "JavaScript", json: "JSON", jsx: "JSX",
  kotlin: "Kotlin", kt: "Kotlin", lua: "Lua", markdown: "Markdown", md: "Markdown",
  php: "PHP", plaintext: "Văn bản", powershell: "PowerShell", ps1: "PowerShell",
  pwsh: "PowerShell", python: "Python", rb: "Ruby", rs: "Rust", ruby: "Ruby",
  rust: "Rust", sh: "Bash", shell: "Bash", sql: "SQL", text: "Văn bản", toml: "TOML",
  ts: "TypeScript", tsx: "TSX", txt: "Văn bản", typescript: "TypeScript", xml: "HTML",
  yaml: "YAML", yml: "YAML", zsh: "Bash",
};

function CopyIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="9" y="9" width="11" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
    <path d="M15 5.5A2.5 2.5 0 0 0 12.5 3h-7A2.5 2.5 0 0 0 3 5.5v7A2.5 2.5 0 0 0 5.5 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
  </svg>;
}

function CheckIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

/** Chép chữ vào clipboard rồi giữ kết quả 2,2 giây, để nút đổi thành "Đã chép" hay "Chưa chép được". */
function useCopy() {
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  const resetTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  async function copy(text: string) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setState("done");
    } catch {
      setState("fail");
    }
    window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setState("idle"), 2200);
  }

  const label = state === "done" ? "Đã chép" : state === "fail" ? "Chưa chép được" : "Sao chép";
  return { state, label, copy };
}

function CodeBlock({ language, children }: { language: string; children: ReactNode }) {
  const preRef = useRef<HTMLPreElement>(null);
  const { state, label: copyText, copy } = useCopy();
  const label = CODE_LABELS[language] ?? (language ? language.toUpperCase() : "Mã");

  return (
    <div className="code-block">
      <div className="code-head">
        <span className="code-lang">{label}</span>
        {/* Lấy chữ từ DOM chứ không dựng lại từ cây hast: sau khi tô màu, code bị cắt thành hàng chục thẻ con,
            còn textContent thì luôn đúng nguyên bản. */}
        <button type="button" className="code-copy" onClick={() => void copy(preRef.current?.textContent ?? "")}>
          {state === "done" ? <CheckIcon /> : <CopyIcon />}
          {copyText}
        </button>
      </div>
      <pre ref={preRef}>{children}</pre>
    </div>
  );
}

/**
 * Nút chép cả câu trả lời. Chép chữ gốc Markdown chứ không phải chữ đã hiển thị, nên công thức LaTeX, bảng hay khối
 * code còn nguyên; đó cũng là cách xem model thật sự viết gì khi web hiển thị sai (như vụ dấu ~ bị KaTeX nuốt).
 */
function MessageCopy({ text }: { text: string }) {
  const { state, label, copy } = useCopy();
  return (
    <div className="message-actions">
      <button type="button" className={state === "done" ? "message-copy done" : "message-copy"}
        aria-label={`${label} câu trả lời`} onClick={() => void copy(text)}>
        {state === "done" ? <CheckIcon /> : <CopyIcon />}
        {label}
      </button>
    </div>
  );
}

function formatWorked(ms: number): string {
  const seconds = Math.max(1, Math.round(ms / 1000));
  return `Đã làm trong ${seconds} giây`;
}

function WorkLog({
  live,
  steps,
  ms,
}: {
  live: boolean;
  steps?: WorkStep[];
  ms?: number;
}) {
  const [choice, setChoice] = useState<boolean | null>(null);
  const open = choice ?? live;
  const list = steps ?? [];
  if (!live && list.length === 0 && ms == null) return null;
  const label = live ? "Đang làm…" : formatWorked(ms ?? 0);
  return (
    <div className="thinking-panel work-log">
      <button
        type="button"
        className="thinking-toggle"
        aria-expanded={open}
        onClick={() => setChoice(!open)}
      >
        <span className={open ? "thinking-chevron open" : "thinking-chevron"} aria-hidden="true">
          ▸
        </span>
        <span className={live ? "thinking-pulse" : undefined}>{label}</span>
      </button>
      {open && list.length > 0 ? (
        <ul className="work-steps" aria-live="polite">
          {list.map((step) => (
            <li key={step.id} className={step.live ? "live" : undefined}>
              {step.id === 'connector-github' ? (
                <GitHubIcon size={14} />
              ) : step.id === "search" || step.id.startsWith('connector-') ? (
                <GlobeIcon />
              ) : step.id === "document" || step.id.startsWith("file-") ? (
                <DocumentIcon />
              ) : (
                <span className="work-dot" aria-hidden="true" />
              )}
              <div className="work-step-content">
                <span>{step.label}</span>
                {step.details?.length ? <details className="work-step-details">
                  <summary>Xem mục chưa đọc được</summary>
                  <ul>{step.details.map(detail => <li key={detail}>{detail}</li>)}</ul>
                </details> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}


export const ChatMessage = memo(function ChatMessage({ message, live, writing, onPreview, onEdit, actionsDisabled, editor }: {
  message: Message; live: boolean; writing: boolean;
  actionsDisabled?: boolean; editor?: ReactNode;
  onPreview: (item: { id: string; version: number }) => void;
  onEdit: (item: { id: string; version: number }) => void;
}) {
  const text = message.content ? normalizeMath(message.content) : "";
  const { remarkPlugins, rehypePlugins } = useMarkdownPlugins(text);
  // Giữ nguyên các hàm dựng thẻ giữa các lần vẽ lại. Hàm mới mỗi lần thì React coi là loại thẻ mới, gỡ ra dựng lại cả khối:
  // thẻ sơ đồ phải vẽ lại từ đầu, nút Sao chép của khối code mất trạng thái.
  const components = useMemo<Components>(() => ({
    table: ({children}) => <div className="table-scroll" tabIndex={0} role="region" aria-label="Bảng nội dung"><table>{children}</table></div>,
    // Ô chữ dài (ghi chú, mô tả) rộng hơn hẳn các ô số, như bảng của Claude; không thì cột ghi chú hẹp làm hàng rất cao.
    td: ({node, children}) => <td className={hastText(node).length > 30 ? "wide" : undefined}>{children}</td>,
    a: ({children, href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    pre: ({node, children}) => {
      const code = node?.children?.[0];
      const names = code?.type === "element" && Array.isArray(code.properties?.className)
        ? code.properties.className.map(String) : [];
      const tag = names.find((name) => name.startsWith("language-"));
      // Khối ```mermaid thành thẻ sơ đồ; tin còn đang viết thì thẻ chỉ báo đang vẽ (mã có thể dở dang).
      if (tag === "language-mermaid") return <DiagramCard source={hastText(code)} pending={writing} />;
      return <CodeBlock language={tag ? tag.slice("language-".length) : ""}>{children}</CodeBlock>;
    },
  }), [writing]);
  return (<article className={`bubble ${message.role}${editor ? ' editing' : ''}`}>
              {message.attachments && message.attachments.length > 0 && (
                <div className="bubble-files">
                  {message.attachments.map((file) =>
                    file.kind === "image" && file.url ? (
                      <a
                        key={file.id}
                        href={file.url}
                        target="_blank"
                        rel="noreferrer"
                        className="bubble-image-link"
                      >
                        <img src={file.url} alt={file.name} className="bubble-image" />
                      </a>
                    ) : (
                      <div className="document-card" key={file.id}>
                        <a href={file.url || undefined} className="file-chip" download={file.name}>
                          <FileGlyph name={file.name} kind="file" />
                          <span>
                            <strong>{file.name}</strong>
                            <em>{formatSize(file.size)}</em>
                          </span>
                        </a>
                        {file.document && (
                          <details className={`document-details ${file.document.status === "ready" ? "ready" : "limited"}`}>
                            <summary>
                              {file.document.status === "ready" ? (file.document.ocr_pages ? "Đã đọc bằng OCR" : "Đã đọc chữ") : file.document.status === "partial" ? "Đọc được một phần" : "Chưa đọc được"}
                              {file.document.pages != null && ` · ${file.document.pages_read != null ? `${file.document.pages_read}/` : ""}${file.document.pages} trang`}
                              {file.document.sheets != null && ` · ${file.document.sheets_read != null && file.document.sheets_read !== file.document.sheets ? `${file.document.sheets_read}/` : ""}${file.document.sheets} trang tính`}
                              {file.document.status === "partial" && !!file.document.ocr_pages && " · có OCR"}
                            </summary>
                            <p>{file.document.notice}</p>
                          </details>
                        )}
                      </div>
                    ),
                  )}
                </div>
              )}
              {message.role === "assistant" && (
                (live) ||
                message.workSteps?.length ||
                message.workedMs != null
              ) ? (
                <WorkLog
                  live={live}
                  steps={message.workSteps}
                  ms={message.workedMs}
                />
              ) : null}
              {editor || (message.content ? (
                <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>{text}</Markdown>
              ) : null)}
              {message.role === "assistant" && <WebSources sources={message.sources} />}
              {message.artifacts?.map(artifact => <DocumentArtifactCard key={`${artifact.id}-${artifact.version}`} artifact={artifact} onOpen={onPreview} onEdit={onEdit} />)}
              {message.status === "incomplete" && <p className="message-status">Câu trả lời chưa hoàn tất</p>}
              {/* Tin đang được viết thì chưa có gì trọn vẹn để chép. */}
              {message.role === "assistant" && message.content && !(writing) && (
                <MessageCopy text={message.content} />
              )}
              {!writing && !editor && message.role === 'user' && <span className="user-message-actions">
                {message.id && <button type="button" aria-label="Sửa tin nhắn" title="Sửa tin nhắn" disabled={actionsDisabled} data-revise={message.id}><EditIcon /></button>}
              </span>}
            </article>);
});

