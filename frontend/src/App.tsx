import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Imagine from "./Imagine";
import {
  DISCORD_LOGIN_URL,
  UnauthorizedError,
  deleteConversation,
  getAppInfo,
  getAuthState,
  getMessages,
  listConversations,
  logout,
  sendMessage,
  type AppInfo,
  type AuthState,
  type ChatAttachment,
  type Conversation,
  type Effort,
  type Message,
  type OutgoingAttachment,
} from "./api";

const EFFORT_KEY = "peto-effort";
const THEME_KEY = "peto-theme";
const MAX_FILES = 4;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_TOTAL_BYTES = 16 * 1024 * 1024;
const ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,.txt,.md,.csv,.json,.pdf,.py,.js,.ts,.tsx,.css,.html";

const EFFORTS: { value: Effort; label: string; hint: string }[] = [
  { value: "auto", label: "Tự động", hint: "Peto tự chọn mức phù hợp" },
  { value: "low", label: "Thấp", hint: "Trả lời nhanh, chat thường" },
  { value: "medium", label: "Trung bình", hint: "Cân bằng tốc độ và độ sâu" },
  { value: "high", label: "Cao", hint: "Suy nghĩ kỹ cho bài khó" },
];

type ThemeChoice = "light" | "dark" | "system";
type AppView = "chat" | "imagine";

const THEMES: { value: ThemeChoice; label: string; hint: string }[] = [
  { value: "light", label: "Sáng", hint: "Nền trắng, hợp ban ngày" },
  { value: "dark", label: "Tối", hint: "Nền tối, dịu mắt buổi đêm" },
  { value: "system", label: "Theo máy", hint: "Đổi theo cài đặt của thiết bị" },
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

function readStoredTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return THEMES.some((item) => item.value === value) ? (value as ThemeChoice) : "system";
  } catch {
    return "system";
  }
}

/** Trình duyệt cũ hoặc môi trường test có thể không có matchMedia. */
function lightMediaQuery(): MediaQueryList | null {
  try {
    return typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: light)")
      : null;
  } catch {
    return null;
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

function GearIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.1" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M19.4 14.2a1.6 1.6 0 0 0 .32 1.77l.06.06a1.9 1.9 0 1 1-2.7 2.7l-.05-.06a1.6 1.6 0 0 0-1.78-.32 1.6 1.6 0 0 0-.96 1.46v.17a1.9 1.9 0 1 1-3.8 0v-.09a1.6 1.6 0 0 0-1.05-1.46 1.6 1.6 0 0 0-1.77.32l-.06.06a1.9 1.9 0 1 1-2.7-2.7l.06-.06a1.6 1.6 0 0 0 .32-1.77 1.6 1.6 0 0 0-1.46-.96h-.17a1.9 1.9 0 0 1 0-3.8h.09a1.6 1.6 0 0 0 1.46-1.05 1.6 1.6 0 0 0-.32-1.78l-.06-.05a1.9 1.9 0 1 1 2.7-2.7l.06.06a1.6 1.6 0 0 0 1.77.32h.08a1.6 1.6 0 0 0 .96-1.46v-.17a1.9 1.9 0 1 1 3.8 0v.09a1.6 1.6 0 0 0 .96 1.46 1.6 1.6 0 0 0 1.78-.32l.05-.06a1.9 1.9 0 1 1 2.7 2.7l-.06.06a1.6 1.6 0 0 0-.32 1.77v.08a1.6 1.6 0 0 0 1.46.96h.17a1.9 1.9 0 0 1 0 3.8h-.09a1.6 1.6 0 0 0-1.46.96Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FileGlyph({ name, kind }: { name: string; kind: "image" | "file" }) {
  if (kind === "image") return null;
  const ext = name.split(".").pop()?.slice(0, 4).toUpperCase() || "FILE";
  return <span className="file-ext">{ext}</span>;
}

/** Avatar của Peto: ảnh thật từ Discord application, chữ cái đầu nếu chưa có. */
function PetoAvatar({ info, big }: { info: AppInfo | null; big?: boolean }) {
  const className = big ? "avatar big" : "avatar";
  if (info?.avatar_url) {
    return (
      <img
        className={`${className} avatar-image`}
        src={info.avatar_url}
        alt={info.name}
        width={big ? 56 : 34}
        height={big ? 56 : 34}
      />
    );
  }
  return <span className={className}>{(info?.name ?? "Peto").charAt(0)}</span>;
}

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
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
  const [notice, setNotice] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>(readStoredTheme);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [view, setView] = useState<AppView>(() =>
    typeof window !== "undefined" && window.location.hash === "#imagine" ? "imagine" : "chat",
  );
  const [imageVisited, setImageVisited] = useState(view === "imagine");

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const draftFilesRef = useRef<DraftFile[]>([]);
  const loadRef = useRef<AbortController | null>(null);
  const loadVersion = useRef(0);
  const listVersion = useRef(0);
  const listCount = useRef(50);
  const nearBottom = useRef(true);
  const messagesRef = useRef<HTMLDivElement>(null);
  const deleteDialogRef = useRef<HTMLDialogElement>(null);
  const settingsDialogRef = useRef<HTMLDialogElement>(null);
  const authVersion = useRef(0);

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

  // Avatar và tên lấy từ Discord application. Hỏng thì giữ chữ cái đầu, không
  // để ảnh hưởng tới việc đăng nhập hay chat.
  useEffect(() => {
    void getAppInfo()
      .then(setAppInfo)
      .catch(() => setAppInfo(null));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(EFFORT_KEY, effort);
    } catch {}
  }, [effort]);

  // Giao diện sáng/tối: "Theo máy" bám theo cài đặt hệ thống và đổi ngay khi
  // hệ thống đổi, hai lựa chọn còn lại thì giữ nguyên.
  useEffect(() => {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {}
    const media = lightMediaQuery();
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media?.matches ? "light" : "dark") : theme;
    };
    apply();
    if (theme !== "system" || !media?.addEventListener) return;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    draftFilesRef.current = draftFiles;
  }, [draftFiles]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      loadRef.current?.abort();
      for (const item of draftFilesRef.current) {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      }
    };
  }, []);

  /** Phiên hết hạn giữa chừng: quay về màn hình đăng nhập thay vì báo lỗi lạ. */
  const handleUnauthorized = useCallback(() => {
    authVersion.current += 1;
    loadVersion.current += 1;
    listVersion.current += 1;
    loadRef.current?.abort();
    abortRef.current?.abort();
    setAuth({ authenticated: false, login_configured: true });
    setMessages([]);
    setConversations([]);
    setConversationId(null);
    setDraft("");
    setNotice(null);
    for (const item of draftFilesRef.current) if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    setDraftFiles([]);
    setLoadingConversation(false);
    setLoadingList(false);
    setDeleteTarget(null);
    setSettingsOpen(false);
    setHasMore(false);
    listCount.current = 50;
    setAuthError("Phiên đăng nhập đã hết hạn hoặc tài khoản không còn được cho phép.");
  }, []);

  const refreshConversations = useCallback(async () => {
    const version = ++listVersion.current;
    setLoadingList(true);
    try {
      const all: Conversation[] = [];
      let more = true;
      while (more && all.length < listCount.current) {
        const page = await listConversations(all.length);
        if (version !== listVersion.current) return;
        all.push(...page.conversations);
        more = page.has_more;
        if (!page.conversations.length) break;
      }
      setConversations(all);
      setHasMore(more);
    } catch (err) {
      if (version !== listVersion.current) return;
      if (err instanceof UnauthorizedError) handleUnauthorized();
      else setError("Không tải được danh sách hội thoại. Thử tải lại nhé.");
    } finally {
      if (version === listVersion.current) setLoadingList(false);
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    if (auth?.authenticated) void refreshConversations();
  }, [auth?.authenticated, refreshConversations]);

  useEffect(() => {
    if (nearBottom.current) bottomRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
    else setShowJump(true);
  }, [messages, streaming]);

  useEffect(() => {
    if (deleteTarget) deleteDialogRef.current?.showModal();
    else deleteDialogRef.current?.close();
  }, [deleteTarget]);

  useEffect(() => {
    if (settingsOpen) settingsDialogRef.current?.showModal();
    else settingsDialogRef.current?.close();
  }, [settingsOpen]);

  const addFiles = useCallback((list: FileList | File[]) => {
    if (abortRef.current) return;
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
        if (next.reduce((total, item) => total + item.file.size, 0) + file.size > MAX_TOTAL_BYTES) {
          setError("Tổng tệp đính kèm tối đa 16 MB mỗi tin.");
          continue;
        }
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
          <PetoAvatar info={appInfo} big />
          <h1>{appInfo?.name ?? "Peto"}</h1>
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
              Chưa kết nối được dịch vụ đăng nhập. Thử tải lại trang hoặc báo người quản trị nhé.
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
    if (abortRef.current || deleting) return;
    loadRef.current?.abort();
    const controller = new AbortController();
    loadRef.current = controller;
    const version = ++loadVersion.current;
    setError(null);
    setNotice(null);
    setConversationId(id);
    setMessages([]);
    setLoadingConversation(true);
    setLoadFailed(false);
    nearBottom.current = true;
    setShowJump(false);
    setSidebarOpen(false);
    try {
      const loaded = await getMessages(id, controller.signal);
      if (version !== loadVersion.current) return;
      setMessages(loaded);
    } catch (err) {
      if (version !== loadVersion.current || controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setLoadFailed(true);
      setError(err instanceof Error ? err.message : "Không mở được hội thoại");
    } finally {
      if (version === loadVersion.current) {
        setLoadingConversation(false);
        loadRef.current = null;
      }
    }
  }

  function newConversation() {
    if (abortRef.current) return;
    loadRef.current?.abort();
    loadVersion.current += 1;
    setLoadingConversation(false);
    setLoadFailed(false);
    nearBottom.current = true;
    setShowJump(false);
    setConversationId(null);
    setMessages([]);
    setError(null);
    setNotice(null);
    setSidebarOpen(false);
    textareaRef.current?.focus();
  }

  async function removeConversation(id: string) {
    if (abortRef.current || deleting) return;
    setDeleting(true);
    try {
      await deleteConversation(id);
      if (id === conversationId) newConversation();
      setDeleteTarget(null);
      await refreshConversations();
    } catch (err) {
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setError(err instanceof Error ? err.message : "Không xóa được");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  async function submit() {
    const text = draft.trim();
    if ((!text && draftFiles.length === 0) || abortRef.current || loadingConversation || loadFailed) return;

    const pending = draftFiles;
    const previousMessages = messages;
    setError(null);
    setNotice(null);
    setStreaming(true);
    setStopping(false);
    nearBottom.current = true;
    setShowJump(false);
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
    let accepted = false;
    let completed = false;
    const session = authVersion.current;

    const appendToReply = (chunk: string) => {
      if (session !== authVersion.current) return;
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role !== "assistant") return prev;
        next[next.length - 1] = { ...last, content: last.content + chunk };
        return next;
      });
    };

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
          onMeta: (id, usedEffort, storedMessage) => {
            if (session !== authVersion.current) return;
            accepted = true;
            activeId = id;
            setConversationId(id);
            setActiveEffort(usedEffort);
            setDraft("");
            setDraftFiles([]);
            if (storedMessage) setMessages((prev) => [...prev.slice(0, -2), storedMessage, prev[prev.length - 1]]);
          },
          onDelta: appendToReply,
          onError: (message) => {
            if (session !== authVersion.current) return;
            setError(message);
          },
          onDone: () => { completed = true; },
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        handleUnauthorized();
      } else if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : "Mất kết nối tới máy chủ";
        setError(accepted ? message : `${message} Bản nháp được giữ lại; kiểm tra lịch sử trước khi gửi lại nếu kết nối bị ngắt.`);
      }
    } finally {
      if (session === authVersion.current) {
        if (!accepted) setMessages(previousMessages);
        else {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role !== "assistant") return prev;
            return last.content
              ? [...prev.slice(0, -1), { ...last, status: completed ? "complete" : "incomplete" }]
              : prev.slice(0, -1);
          });
        }
        if (controller.signal.aborted) setNotice(accepted ? "Đã dừng. Phần đã trả lời được giữ lại." : "Đã dừng gửi. Bản nháp vẫn được giữ lại.");
        if (activeId || !accepted) void refreshConversations();
      }
      if (accepted) for (const item of pending) if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      setStreaming(false);
      setStopping(false);
      setActiveEffort(null);
      abortRef.current = null;
      textareaRef.current?.focus();
    }
  }

  function stop() {
    setStopping(true);
    abortRef.current?.abort();
  }

  async function signOut() {
    try {
      await logout();
      handleUnauthorized();
      setAuthError(null);
    } catch {
      setError("Chưa đăng xuất được. Thử lại nhé.");
    }
  }

  const canSend = (draft.trim().length > 0 || draftFiles.length > 0) && !streaming && !loadingConversation && !loadFailed;
  const effortMeta = EFFORTS.find((item) => item.value === effort) ?? EFFORTS[0];

  function go(next: AppView) {
    if (next === "imagine") setImageVisited(true);
    setView(next);
    setSidebarOpen(false);
    const url = next === "imagine" ? "#imagine" : `${window.location.pathname}${window.location.search}`;
    window.history.replaceState(null, "", url);
  }

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
        <nav className="app-tabs" aria-label="Khu vực">
          <button
            type="button"
            className={view === "chat" ? "on" : ""}
            aria-current={view === "chat" ? "page" : undefined}
            onClick={() => go("chat")}
          >
            Trò chuyện
          </button>
          <button
            type="button"
            className={view === "imagine" ? "on" : ""}
            aria-current={view === "imagine" ? "page" : undefined}
            onClick={() => go("imagine")}
          >
            Tạo ảnh
          </button>
        </nav>
        {view === "chat" && (
        <button className="new-chat" onClick={newConversation} disabled={streaming || deleting}>
          + Trò chuyện mới
        </button>
        )}
        {view === "imagine" && (
          <div className="imagine-sidebar-note">
            <span className="studio-eyebrow">Peto tạo ảnh</span>
            <p>Một chút tưởng tượng,<br />một thế giới của riêng bạn.</p>
            <span>Ảnh đã tạo được lưu tại đây để bạn xem và tải lại.</span>
          </div>
        )}
        {view === "chat" && (
        <nav className="conversation-list">
          {conversations.length === 0 && !loadingList && (
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
                aria-current={conversation.id === conversationId ? "page" : undefined}
                title={conversation.title}
                onClick={() => void openConversation(conversation.id)}
                disabled={streaming || deleting}
              >
                {conversation.title || "Chưa có tiêu đề"}
              </button>
              <button
                className="conv-delete"
                title="Xóa hội thoại"
                aria-label="Xóa hội thoại"
                onClick={() => setDeleteTarget(conversation)}
                disabled={streaming || deleting}
              >
                ×
              </button>
            </div>
          ))}
          {loadingList && <p className="empty-hint" role="status">Đang tải danh sách…</p>}
          {hasMore && <button className="load-more" disabled={loadingList || streaming} onClick={() => {
            listCount.current = conversations.length + 50;
            void refreshConversations();
          }}>Xem hội thoại cũ hơn</button>}
        </nav>
        )}

        <div className="sidebar-foot">
          <button
            type="button"
            className="account"
            aria-haspopup="dialog"
            aria-label={`Cài đặt · ${auth.user?.display_name}`}
            title="Mở cài đặt"
            onClick={() => setSettingsOpen(true)}
          >
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
            <span className="account-gear">
              <GearIcon />
            </span>
          </button>
        </div>
      </aside>

      {imageVisited && (
        <Imagine
          key={auth.user?.discord_id}
          active={view === "imagine"}
          onUnauthorized={handleUnauthorized}
          onOpenSidebar={() => setSidebarOpen(true)}
        />
      )}
      <main className="chat" hidden={view !== "chat"}>
        <header className="chat-header">
          <button
            type="button"
            className="menu-btn"
            aria-label="Mở danh sách hội thoại"
            onClick={() => setSidebarOpen(true)}
          >
            <MenuIcon />
          </button>
          <PetoAvatar info={appInfo} />
          <div className="header-copy">
            <strong>{appInfo?.name ?? "Peto"}</strong>
            <span className="subtitle">
              {streaming
                ? THINKING[activeEffort ?? "low"]
                : `${effortMeta.label} · có thể gửi ảnh và tệp`}
            </span>
          </div>
        </header>

        <div className="messages" ref={messagesRef} onScroll={() => {
          const element = messagesRef.current;
          if (!element) return;
          nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
          setShowJump(!nearBottom.current);
        }}>
          {loadingConversation && <p className="loading-chat" role="status">Đang mở hội thoại…</p>}
          {loadFailed && <div className="loading-chat">
            <p>Chưa tải được nội dung hội thoại.</p>
            <button className="load-more" onClick={() => conversationId && void openConversation(conversationId)}>Thử mở lại</button>
          </div>}
          {messages.length === 0 && !streaming && !loadingConversation && !loadFailed && (
            <div className="welcome">
              <PetoAvatar info={appInfo} big />
              <h1>Chào {auth.user?.display_name}</h1>
              <p>Nhắn gì đó, gửi ảnh, hoặc đính kèm tệp — Peto đang nghe đây.</p>
              <div className="welcome-hints">
                {["Hôm nay cậu thế nào?", "Giải thích giúp mình một bài khó", "Cùng lên kế hoạch cuối tuần nhé"].map((hint) => (
                  <button key={hint} type="button" onClick={() => { setDraft(hint); textareaRef.current?.focus(); }}>{hint}</button>
                ))}
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
                <Markdown remarkPlugins={[remarkGfm]} components={{
                  table: ({children}) => <div className="table-scroll" tabIndex={0} role="region" aria-label="Bảng nội dung"><table>{children}</table></div>,
                  a: ({children, href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
                }}>{message.content}</Markdown>
              ) : message.role === "assistant" && streaming && !stopping && index === messages.length - 1 ? (
                <span className="typing" aria-label={THINKING[activeEffort ?? "low"]}>
                  <i />
                  <i />
                  <i />
                </span>
              ) : null}
              {message.status === "incomplete" && <p className="message-status">Câu trả lời chưa hoàn tất</p>}
            </article>
          ))}
          <div ref={bottomRef} />
        </div>

        {showJump && <button className="jump-latest" onClick={() => {
          nearBottom.current = true;
          setShowJump(false);
          bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
        }}>↓ Tin mới nhất</button>}

        {error && (
          <div className="error" role="alert">
            {error}
            <button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button>
          </div>
        )}

        {notice && <div className="error notice" role="status">
          {notice}
          <button type="button" className="dismiss-error" aria-label="Đóng thông báo trạng thái" onClick={() => setNotice(null)}>×</button>
        </div>}

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
                      disabled={streaming}
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
              aria-label="Nhắn cho Peto"
              disabled={streaming}
              onChange={(event) => setDraft(event.target.value)}
              onPaste={(event) => {
                const files = Array.from(event.clipboardData.files);
                if (files.length) {
                  event.preventDefault();
                  addFiles(files);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
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
                <button type="button" className="stop" disabled={stopping} onClick={stop}>
                  {stopping ? "Đang dừng…" : "Dừng"}
                </button>
              ) : (
                <button type="submit" className="send" disabled={!canSend} aria-label="Gửi">
                  Gửi <SendIcon />
                </button>
              )}
            </div>
          </div>
          <p className="composer-note">
            {draftFiles.some((item) => /\.pdf$/i.test(item.file.name) || item.file.type === "application/pdf")
              ? "PDF được lưu để tải lại; Peto chưa đọc nội dung PDF. Dán phần chữ cần hỏi vào tin nhắn nhé."
              : "Gửi ảnh hoặc tệp chữ · tối đa 4 tệp, 8 MB/tệp, tổng 16 MB. PDF chỉ lưu để tải lại."}
          </p>
        </form>
      </main>
      <dialog
        ref={settingsDialogRef}
        className="settings-dialog"
        aria-labelledby="settings-title"
        onCancel={(event) => {
          event.preventDefault();
          setSettingsOpen(false);
        }}
      >
        <div className="settings-head">
          <h2 id="settings-title">Cài đặt</h2>
          <button
            type="button"
            className="dialog-close"
            aria-label="Đóng cài đặt"
            onClick={() => setSettingsOpen(false)}
          >
            ×
          </button>
        </div>

        <section className="settings-section">
          <h3>Giao diện</h3>
          <p className="settings-hint">Chọn nền sáng, nền tối, hoặc để Peto theo cài đặt của máy.</p>
          <div className="theme-options">
            {THEMES.map((item) => (
              <label
                key={item.value}
                className={theme === item.value ? "theme-option selected" : "theme-option"}
              >
                <input
                  type="radio"
                  name="theme"
                  value={item.value}
                  checked={theme === item.value}
                  onChange={() => setTheme(item.value)}
                />
                <span className={`theme-preview ${item.value}`} aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <strong>{item.label}</strong>
                <em>{item.hint}</em>
              </label>
            ))}
          </div>
        </section>

        <section className="settings-section">
          <h3>Tài khoản</h3>
          <div className="settings-account">
            <img
              className="account-avatar"
              src={auth.user?.avatar_url}
              alt=""
              width={38}
              height={38}
            />
            <div className="account-name">
              <strong>{auth.user?.display_name}</strong>
              <span>@{auth.user?.username}</span>
            </div>
          </div>
          <div className="settings-actions">
            <button
              type="button"
              className="logout"
              disabled={streaming}
              onClick={() => {
                setSettingsOpen(false);
                void signOut();
              }}
            >
              Đăng xuất
            </button>
          </div>
        </section>
      </dialog>
      <dialog ref={deleteDialogRef} className="confirm-dialog" aria-labelledby="delete-title" onCancel={(event) => {
        event.preventDefault();
        if (!deleting) setDeleteTarget(null);
      }}>
        <h2 id="delete-title">Xóa hội thoại này?</h2>
        <p>“{deleteTarget?.title || "Chưa có tiêu đề"}” và các tệp đính kèm sẽ bị xóa. Không thể hoàn tác.</p>
        <div className="dialog-actions">
          <button autoFocus disabled={deleting} onClick={() => setDeleteTarget(null)}>Giữ lại</button>
          <button className="danger-button" disabled={deleting} onClick={() => deleteTarget && void removeConversation(deleteTarget.id)}>{deleting ? "Đang xóa…" : "Xóa hội thoại"}</button>
        </div>
      </dialog>
    </div>
  );
}
