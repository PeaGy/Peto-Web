import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import {
  DISCORD_LOGIN_URL,
  UnauthorizedError,
  deleteConversation,
  getAuthState,
  getMessages,
  listConversations,
  logout,
  sendMessage,
  type AuthState,
  type ChatAttachment,
  type Conversation,
  type Effort,
  type Message,
  type OutgoingAttachment,
} from "./api";

const EFFORT_KEY = "peto-effort";
const MAX_FILES = 4;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,.txt,.md,.csv,.json,.pdf,.py,.js,.ts,.tsx,.css,.html";

const EFFORTS: { value: Effort; label: string; hint: string }[] = [
  { value: "auto", label: "Tự động", hint: "Peto tự chọn mức phù hợp" },
  { value: "low", label: "Thấp", hint: "Trả lời nhanh, chat thường" },
  { value: "medium", label: "Trung bình", hint: "Cân bằng tốc độ và độ sâu" },
  { value: "high", label: "Cao", hint: "Suy nghĩ kỹ cho bài khó" },
];

const THINKING: Record<string, string> = {
  low: "Đang trả lời…",
  medium: "Đang suy nghĩ…",
  high: "Đang suy nghĩ sâu…",
};

interface DraftFile {
  id: string;
  file: File;
  previewUrl: string | null;
}

function readStoredEffort(): Effort {
  try {
    const value = localStorage.getItem(EFFORT_KEY);
    return EFFORTS.some((item) => item.value === value) ? (value as Effort) : "auto";
  } catch {
    return "auto";
  }
}

function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|gif|webp)$/i.test(file.name);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("Không đọc được tệp"));
    reader.readAsDataURL(file);
  });
}

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21 12.5 12.12 21.38a5 5 0 0 1-7.07-7.07L14.5 4.86a3.5 3.5 0 0 1 4.95 4.95L10.12 19.14a2 2 0 0 1-2.83-2.83L16 7.6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

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

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function FileGlyph({ name, kind }: { name: string; kind: "image" | "file" }) {
  if (kind === "image") return null;
  const ext = name.split(".").pop()?.slice(0, 4).toUpperCase() || "FILE";
  return <span className="file-ext">{ext}</span>;
}

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [draftFiles, setDraftFiles] = useState<DraftFile[]>([]);
  const [effort, setEffort] = useState<Effort>(readStoredEffort);
  const [activeEffort, setActiveEffort] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const draftFilesRef = useRef<DraftFile[]>([]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const message = params.get("auth_error");
    if (message) {
      setAuthError(message);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  useEffect(() => {
    void getAuthState()
      .then(setAuth)
      .catch(() => setAuth({ authenticated: false, login_configured: false }));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(EFFORT_KEY, effort);
    } catch {}
  }, [effort]);

  useEffect(() => {
    draftFilesRef.current = draftFiles;
  }, [draftFiles]);

  useEffect(() => {
    return () => {
      for (const item of draftFilesRef.current) {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      }
    };
  }, []);

  /** Phiên hết hạn giữa chừng: quay về màn hình đăng nhập thay vì báo lỗi lạ. */
  const handleUnauthorized = useCallback(() => {
    setAuth({ authenticated: false, login_configured: true });
    setMessages([]);
    setConversations([]);
    setConversationId(null);
    setAuthError("Phiên đăng nhập đã hết hạn. Đăng nhập lại nhé.");
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch (err) {
      if (err instanceof UnauthorizedError) handleUnauthorized();
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    if (auth?.authenticated) void refreshConversations();
  }, [auth?.authenticated, refreshConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const addFiles = useCallback((list: FileList | File[]) => {
    const incoming = Array.from(list);
    setError(null);
    setDraftFiles((prev) => {
      const next = [...prev];
      for (const file of incoming) {
        if (next.length >= MAX_FILES) {
          setError(`Mỗi tin chỉ gửi tối đa ${MAX_FILES} tệp`);
          break;
        }
        if (file.size > MAX_FILE_BYTES) {
          setError(`«${file.name}» quá nặng (tối đa 8 MB)`);
          continue;
        }
        const duplicate = next.some(
          (item) => item.file.name === file.name && item.file.size === file.size,
        );
        if (duplicate) continue;
        next.push({
          id: crypto.randomUUID(),
          file,
          previewUrl: isImageFile(file) ? URL.createObjectURL(file) : null,
        });
      }
      return next;
    });
  }, []);

  function removeDraftFile(id: string) {
    setDraftFiles((prev) => {
      const target = prev.find((item) => item.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((item) => item.id !== id);
    });
  }

  if (auth === null) {
    return <div className="boot">Đang tải…</div>;
  }

  if (!auth.authenticated) {
    return (
      <div className="login">
        <div className="login-card">
          <span className="avatar big">P</span>
          <h1>Peto</h1>
          <p className="login-sub">
            Đăng nhập bằng Discord để Peto biết cậu là ai.
          </p>

          {authError && (
            <div className="error" role="alert">
              {authError}
            </div>
          )}

          {auth.login_configured ? (
            <a className="discord-button" href={DISCORD_LOGIN_URL}>
              Đăng nhập bằng Discord
            </a>
          ) : (
            <div className="error">
              Máy chủ chưa cấu hình <code>DISCORD_CLIENT_ID</code> và{" "}
              <code>DISCORD_CLIENT_SECRET</code>.
            </div>
          )}

          <p className="login-note">
            Chỉ những tài khoản đã được cho phép mới vào được. Peto chỉ đọc tên
            và ảnh đại diện của cậu.
          </p>
        </div>
      </div>
    );
  }

  async function openConversation(id: string) {
    if (streaming) return;
    setError(null);
    setConversationId(id);
    setSidebarOpen(false);
    try {
      setMessages(await getMessages(id));
    } catch (err) {
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setError(err instanceof Error ? err.message : "Không mở được hội thoại");
    }
  }

  function newConversation() {
    if (streaming) return;
    setConversationId(null);
    setMessages([]);
    setError(null);
    setSidebarOpen(false);
    textareaRef.current?.focus();
  }

  async function removeConversation(id: string) {
    if (streaming) return;
    try {
      await deleteConversation(id);
      if (id === conversationId) newConversation();
      await refreshConversations();
    } catch (err) {
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setError(err instanceof Error ? err.message : "Không xóa được");
    }
  }

  async function submit() {
    const text = draft.trim();
    if ((!text && draftFiles.length === 0) || streaming) return;

    const pending = draftFiles;
    setDraft("");
    setDraftFiles([]);
    setError(null);
    setStreaming(true);
    setActiveEffort(effort === "auto" ? null : effort);

    const optimistic: ChatAttachment[] = pending.map((item) => ({
      id: item.id,
      name: item.file.name,
      mime: item.file.type || "application/octet-stream",
      kind: isImageFile(item.file) ? "image" : "file",
      size: item.file.size,
      url: item.previewUrl || "",
    }));

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, attachments: optimistic },
      { role: "assistant", content: "" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    let activeId = conversationId;

    const appendToReply = (chunk: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + chunk };
        return next;
      });

    try {
      const attachments: OutgoingAttachment[] = await Promise.all(
        pending.map(async (item) => ({
          name: item.file.name,
          mime: item.file.type,
          data: await fileToBase64(item.file),
        })),
      );

      await sendMessage(
        {
          message: text,
          conversationId,
          effort,
          attachments,
        },
        {
          onMeta: (id, usedEffort) => {
            activeId = id;
            setConversationId(id);
            setActiveEffort(usedEffort);
          },
          onDelta: appendToReply,
          onError: (message) => {
            setError(message);
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              return last?.role === "assistant" && !last.content
                ? prev.slice(0, -1)
                : prev;
            });
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        handleUnauthorized();
      } else if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Mất kết nối tới máy chủ");
      }
    } finally {
      setStreaming(false);
      setActiveEffort(null);
      abortRef.current = null;
      if (activeId) void refreshConversations();
      textareaRef.current?.focus();
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
    setActiveEffort(null);
  }

  async function signOut() {
    await logout();
    setAuth({ authenticated: false, login_configured: true });
    setMessages([]);
    setConversations([]);
    setConversationId(null);
  }

  const canSend = (draft.trim().length > 0 || draftFiles.length > 0) && !streaming;
  const effortMeta = EFFORTS.find((item) => item.value === effort) ?? EFFORTS[0];

  return (
    <div className="app">
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="Đóng danh sách hội thoại"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={sidebarOpen ? "sidebar open" : "sidebar"}>
        <button className="new-chat" onClick={newConversation} disabled={streaming}>
          + Trò chuyện mới
        </button>
        <nav className="conversation-list">
          {conversations.length === 0 && (
            <p className="empty-hint">Chưa có cuộc trò chuyện nào.</p>
          )}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={
                conversation.id === conversationId ? "conv active" : "conv"
              }
            >
              <button
                className="conv-open"
                onClick={() => void openConversation(conversation.id)}
                disabled={streaming}
              >
                {conversation.title || "Chưa có tiêu đề"}
              </button>
              <button
                className="conv-delete"
                title="Xóa hội thoại"
                aria-label="Xóa hội thoại"
                onClick={() => void removeConversation(conversation.id)}
                disabled={streaming}
              >
                ×
              </button>
            </div>
          ))}
        </nav>

        <div className="account">
          <img
            className="account-avatar"
            src={auth.user?.avatar_url}
            alt=""
            width={32}
            height={32}
          />
          <div className="account-name">
            <strong>{auth.user?.display_name}</strong>
            <span>@{auth.user?.username}</span>
          </div>
          <button
            className="logout"
            onClick={() => void signOut()}
            disabled={streaming}
            title="Đăng xuất"
          >
            Thoát
          </button>
        </div>
      </aside>

      <main className="chat">
        <header className="chat-header">
          <button
            type="button"
            className="menu-btn"
            aria-label="Mở danh sách hội thoại"
            onClick={() => setSidebarOpen(true)}
          >
            <MenuIcon />
          </button>
          <span className="avatar">P</span>
          <div className="header-copy">
            <strong>Peto</strong>
            <span className="subtitle">
              {streaming
                ? THINKING[activeEffort ?? "low"]
                : `${effortMeta.label} · có thể gửi ảnh và tệp`}
            </span>
          </div>
        </header>

        <div className="messages">
          {messages.length === 0 && !streaming && (
            <div className="welcome">
              <span className="avatar big">P</span>
              <h1>Chào {auth.user?.display_name}</h1>
              <p>Nhắn gì đó, gửi ảnh, hoặc đính kèm tệp — Peto đang nghe đây.</p>
              <div className="welcome-hints">
                <span>Mức suy nghĩ: thấp / trung bình / cao</span>
                <span>Ảnh JPEG, PNG, WebP, GIF</span>
                <span>Tệp chữ và PDF</span>
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <article key={index} className={`bubble ${message.role}`}>
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
                      <a
                        key={file.id}
                        href={file.url || undefined}
                        className="file-chip"
                        download={file.name}
                      >
                        <FileGlyph name={file.name} kind="file" />
                        <span>
                          <strong>{file.name}</strong>
                          <em>{formatSize(file.size)}</em>
                        </span>
                      </a>
                    ),
                  )}
                </div>
              )}
              {message.content ? (
                <Markdown>{message.content}</Markdown>
              ) : message.role === "assistant" ? (
                <span className="typing" aria-label={THINKING[activeEffort ?? "low"]}>
                  <i />
                  <i />
                  <i />
                </span>
              ) : null}
            </article>
          ))}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <form
          className={dragging ? "composer-wrap dragging" : "composer-wrap"}
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
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
            if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
          }}
        >
          {dragging && <div className="drop-hint">Thả ảnh hoặc tệp vào đây</div>}

          <div className="composer">
            {draftFiles.length > 0 && (
              <ul className="attach-list">
                {draftFiles.map((item) => (
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
                      className="chip-remove"
                      aria-label={`Gỡ ${item.file.name}`}
                      onClick={() => removeDraftFile(item.id)}
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
              onChange={(event) => setDraft(event.target.value)}
              onPaste={(event) => {
                const files = Array.from(event.clipboardData.files);
                if (files.length) {
                  event.preventDefault();
                  addFiles(files);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
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
                    if (event.target.files) addFiles(event.target.files);
                    event.target.value = "";
                  }}
                />
                <button
                  type="button"
                  className="icon-btn"
                  title="Đính kèm ảnh hoặc tệp"
                  aria-label="Đính kèm ảnh hoặc tệp"
                  disabled={streaming}
                  onClick={() => fileRef.current?.click()}
                >
                  <PaperclipIcon />
                </button>

                <label className="effort-select">
                  <span className="effort-label">Suy nghĩ</span>
                  <select
                    value={effort}
                    disabled={streaming}
                    title={effortMeta.hint}
                    onChange={(event) => setEffort(event.target.value as Effort)}
                  >
                    {EFFORTS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {streaming ? (
                <button type="button" className="stop" onClick={stop}>
                  Dừng
                </button>
              ) : (
                <button type="submit" className="send" disabled={!canSend} aria-label="Gửi">
                  Gửi <SendIcon />
                </button>
              )}
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}
