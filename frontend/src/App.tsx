import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
// Nạp từng grammar một thay vì bộ `common` của lowlight: rehype-highlight chỉ
// đụng tới `common` khi không được truyền `languages`, nên cách này cho phép
// tree-shaking bỏ hơn ba trăm ngôn ngữ Peto gần như không bao giờ trả về. Thêm
// ngôn ngữ mới thì thêm cả nhãn vào CODE_LABELS, không thì đầu khối code hiện
// tên thô viết hoa như "CSHARP".
import bash from "highlight.js/lib/languages/bash";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";
import csharp from "highlight.js/lib/languages/csharp";
import css from "highlight.js/lib/languages/css";
import dart from "highlight.js/lib/languages/dart";
import diff from "highlight.js/lib/languages/diff";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import go from "highlight.js/lib/languages/go";
import ini from "highlight.js/lib/languages/ini";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import kotlin from "highlight.js/lib/languages/kotlin";
import lua from "highlight.js/lib/languages/lua";
import markdown from "highlight.js/lib/languages/markdown";
import php from "highlight.js/lib/languages/php";
import plaintext from "highlight.js/lib/languages/plaintext";
import powershell from "highlight.js/lib/languages/powershell";
import python from "highlight.js/lib/languages/python";
import ruby from "highlight.js/lib/languages/ruby";
import rust from "highlight.js/lib/languages/rust";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import Imagine from "./Imagine";
import ProfileSettings from "./ProfileSettings";
import Composer from "./Composer";
import { FileGlyph, formatSize, type DraftFile } from "./files";
import { fillName, greetingKey, pickGreeting } from "./timeGreeting";
import WebSources, { GlobeIcon, safeSources } from "./WebSources";
import {
  DISCORD_LOGIN_URL,
  GOOGLE_LOGIN_URL,
  UnauthorizedError,
  deleteConversation,
  getAppInfo,
  getAuthState,
  guestLogin,
  getMessages,
  listConversations,
  logout,
  sendMessage,
  type AppInfo,
  type AuthState,
  type ChatAttachment,
  type Conversation,
  type AccountUser,
  type Effort,
  type ImagineJob,
  type Message,
  type OutgoingAttachment,
  type WebSearchMode,
} from "./api";

const HIGHLIGHT_LANGUAGES = {
  bash, c, cpp, csharp, css, dart, diff, dockerfile, go, ini, java, javascript, json,
  kotlin, lua, markdown, php, plaintext, powershell, python, ruby, rust, sql, typescript,
  xml, yaml,
};

// Grammar tự khai báo alias riêng, nhưng khai thêm ở đây cho chắc: đây là những
// tên Peto hay viết sau dấu ``` nhất.
const HIGHLIGHT_ALIASES = {
  bash: ["sh", "shell", "console", "zsh"],
  cpp: ["c++", "cc"],
  csharp: ["cs", "c#"],
  dockerfile: ["docker"],
  go: ["golang"],
  ini: ["toml"],
  javascript: ["js", "jsx"],
  kotlin: ["kt"],
  markdown: ["md"],
  plaintext: ["text", "txt"],
  powershell: ["ps1", "pwsh"],
  ruby: ["rb"],
  rust: ["rs"],
  typescript: ["ts", "tsx"],
  xml: ["html"],
  yaml: ["yml"],
};

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

const EFFORT_KEY = "peto-effort";
const THEME_KEY = "peto-theme";
const SIDEBAR_KEY = "peto-sidebar-collapsed";
const MAX_FILES = 16;
const MAX_MEDIA_FILES = 4;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_TOTAL_BYTES = 16 * 1024 * 1024;
// Gợi ý ở màn hình trống, hiện ngay dưới ô nhắn.
const CHAT_HINTS = [
  "Hôm nay cậu thế nào?",
  "Giải thích giúp mình một bài khó",
  "Cùng lên kế hoạch cuối tuần nhé",
];

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

function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
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

function isMediaFile(file: File): boolean {
  return (
    isImageFile(file) ||
    file.type === "application/pdf" ||
    /\.pdf$/i.test(file.name) ||
    file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    /\.docx$/i.test(file.name)
  );
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


function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** Bút trên tờ giấy: như Grok, mục Trò chuyện cũng là nơi mở cuộc mới. */
function ComposeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="m17.5 3.5 3 3L12 15l-3.5.5.5-3.5 8.5-8.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="4" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="9" cy="9" r="1.6" fill="currentColor" />
      <path d="m4 17 4.5-4.5 3.5 3.5 3-3.5 5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SidebarIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M9.5 4.5v15" stroke="currentColor" strokeWidth="1.7" />
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

function CodeBlock({ language, children }: { language: string; children: ReactNode }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  const resetTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  async function copy() {
    // Lấy chữ từ DOM chứ không dựng lại từ cây hast: sau khi tô màu, code bị cắt
    // thành hàng chục thẻ con, còn textContent thì luôn đúng nguyên bản.
    const text = preRef.current?.textContent ?? "";
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

  const label = CODE_LABELS[language] ?? (language ? language.toUpperCase() : "Mã");
  const copyText = state === "done" ? "Đã chép" : state === "fail" ? "Chưa chép được" : "Sao chép";

  return (
    <div className="code-block">
      <div className="code-head">
        <span className="code-lang">{label}</span>
        <button type="button" className="code-copy" onClick={() => void copy()}>
          {state === "done" ? <CheckIcon /> : <CopyIcon />}
          {copyText}
        </button>
      </div>
      <pre ref={preRef}>{children}</pre>
    </div>
  );
}

function ThinkingPanel({
  live,
  text,
  label,
}: {
  live: boolean;
  text: string;
  label: string;
}) {
  // Tự mở lúc đang nghĩ, tự đóng khi câu trả lời tới — nhưng người dùng bấm thì
  // ý họ thắng. Suy ngay trong lúc render, không qua useEffect: effect chạy sau
  // khi commit nên panel loé mở đúng một khung hình lúc câu trả lời vừa hiện.
  const [choice, setChoice] = useState<boolean | null>(null);
  const open = choice ?? live;
  if (!live && !text) return null;
  return (
    <div className="thinking-panel">
      <button
        type="button"
        className="thinking-toggle"
        aria-expanded={open}
        onClick={() => setChoice(!open)}
      >
        <span className={open ? "thinking-chevron open" : "thinking-chevron"} aria-hidden="true">
          ▸
        </span>
        <span className={live ? "thinking-pulse" : undefined}>{live ? label : "Đã suy nghĩ"}</span>
      </button>
      {open && text ? <div className="thinking-body">{text}</div> : null}
    </div>
  );
}


/** Avatar của Peto: ảnh thật từ Discord application, chữ cái đầu nếu chưa có. */
function DiscordIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
  </svg>;
}

function GoogleIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M21.6 12.2c0-.7-.06-1.4-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.89-1.74 2.98-4.3 2.98-7.35Z" fill="#4285F4" />
    <path d="M12 22c2.7 0 4.965-.9 6.62-2.43l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.06v2.59A10 10 0 0 0 12 22Z" fill="#34A853" />
    <path d="M6.41 13.9a6 6 0 0 1 0-3.83V7.48H3.06a10 10 0 0 0 0 9.01l3.35-2.6Z" fill="#FBBC05" />
    <path d="M12 5.95c1.47 0 2.78.5 3.82 1.5l2.86-2.86C16.96 2.99 14.7 2 12 2a10 10 0 0 0-8.94 5.48l3.35 2.6C7.2 7.7 9.4 5.95 12 5.95Z" fill="#EA4335" />
  </svg>;
}

function GuestIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="8" r="3.6" stroke="currentColor" strokeWidth="1.7" />
    <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
  </svg>;
}

/** Avatar người dùng. Khách không có ảnh nên rơi về chữ cái đầu. */
function AccountAvatar({ user, size }: { user?: AccountUser; size: number }) {
  if (user?.avatar_url) {
    return <img className="account-avatar avatar-image" src={user.avatar_url}
      alt="" width={size} height={size} />;
  }
  return <span className="account-avatar account-initial" style={{ width: size, height: size }}>
    {(user?.display_name || "?").charAt(0).toUpperCase()}
  </span>;
}

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

/**
 * Lời chào đổi theo giờ trên máy, như Claude. Chọn một câu mỗi lần màn hình
 * trống hiện ra để chữ không nhảy trong lúc đang đọc. Quay lại tab khi đã sang
 * buổi khác hoặc ngày khác thì chọn lại, kẻo sáng ra vẫn còn "Khuya rồi".
 */
function Greeting({ name }: { name: string }) {
  const [greeting, setGreeting] = useState(() => {
    const now = new Date();
    return { key: greetingKey(now), text: pickGreeting(now) };
  });

  useEffect(() => {
    function refresh() {
      if (document.visibilityState !== "visible") return;
      const now = new Date();
      const key = greetingKey(now);
      setGreeting((prev) => (prev.key === key ? prev : { key, text: pickGreeting(now) }));
    }
    document.addEventListener("visibilitychange", refresh);
    return () => document.removeEventListener("visibilitychange", refresh);
  }, []);

  return <h1>{fillName(greeting.text, name)}</h1>;
}

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [guestBusy, setGuestBusy] = useState(false);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [draftFiles, setDraftFiles] = useState<DraftFile[]>([]);
  const [effort, setEffort] = useState<Effort>(readStoredEffort);
  const [webSearch, setWebSearch] = useState<WebSearchMode>("auto");
  const [activeEffort, setActiveEffort] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);
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
  // Bản sao chỉ để vẽ cột trái; Imagine.tsx mới là nơi tạo, xóa và giữ danh sách.
  const [imagineJobs, setImagineJobs] = useState<ImagineJob[]>([]);
  const [focusJobId, setFocusJobId] = useState<string | null>(null);
  const clearFocusJob = useCallback(() => setFocusJobId(null), []);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const draftFilesRef = useRef<DraftFile[]>([]);
  const loadRef = useRef<AbortController | null>(null);
  const loadVersion = useRef(0);
  const listVersion = useRef(0);
  const listCount = useRef(50);
  const nearBottom = useRef(true);
  const messagesRef = useRef<HTMLDivElement>(null);
  const deleteDialogRef = useRef<HTMLDialogElement>(null);
  const settingsDialogRef = useRef<HTMLDialogElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const composerBoxRef = useRef<HTMLDivElement>(null);
  // Chỗ ô nhắn đứng lúc còn ở giữa màn hình, đo ngay trước khi gửi tin đầu.
  const composerFrom = useRef<number | null>(null);
  const composerMove = useRef<Animation | null>(null);
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

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {}
  }, [collapsed]);

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
    // Giữ lại danh sách cách đăng nhập đã biết. Dựng state mới toanh ở đây làm
    // `providers` thành undefined, nên đăng xuất xong là nút Google biến mất
    // tới khi F5 gọi lại /api/auth/me. Đăng xuất không đổi gì ở phía máy chủ.
    setAuth((prev) => ({
      authenticated: false,
      login_configured: true,
      providers: prev?.providers,
    }));
    setMessages([]);
    setConversations([]);
    setConversationId(null);
    setDraft("");
    setNotice(null);
    setWebSearch("auto");
    for (const item of draftFilesRef.current) if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    setDraftFiles([]);
    setLoadingConversation(false);
    setLoadingList(false);
    // Rác của tài khoản trước. Máy chủ vẫn lọc theo owner nên không lộ nội dung
    // của ai, nhưng người kế tiếp không có lý do gì phải thấy danh sách ảnh cũ
    // nhấp nháy, hay ô soạn bị khóa vì một lần tải hỏng của người trước.
    setImagineJobs([]);
    setFocusJobId(null);
    setLoadFailed(false);
    setError(null);
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
        if (isMediaFile(file) && next.filter((item) => isMediaFile(item.file)).length >= MAX_MEDIA_FILES) {
          setError(`Mỗi tin chỉ gửi tối đa ${MAX_MEDIA_FILES} ảnh, PDF hoặc Word`);
          continue;
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

  async function enterAsGuest() {
    if (guestBusy) return;
    setGuestBusy(true);
    setAuthError(null);
    try {
      await guestLogin();
      setAuth(await getAuthState());
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Chưa vào được. Thử lại nhé.");
    } finally {
      // Phải dọn cả khi thành công. App không unmount lúc đăng nhập xong, nên
      // đăng xuất là thẻ này quay lại — bỏ sót ở đây thì nút kẹt "Đang vào…"
      // vĩnh viễn và không ai bấm được nữa.
      setGuestBusy(false);
    }
  }

  // Cuộc trò chuyện còn trống thì lời chào và ô nhắn đứng chung giữa màn hình như
  // Claude; có tin nhắn là ô nhắn về đáy (CSS .chat.empty-state).
  const emptyChat = messages.length === 0 && !streaming && !loadingConversation && !loadFailed;

  // Chỉ lần gửi tin đầu mới trượt ô nhắn xuống (FLIP): mắt người dùng đang ở đúng
  // ô đó, để nó nhảy cóc là mất dấu. Mở hội thoại hay tạo cuộc mới là điều hướng,
  // làm nhiều lần trong ngày, nên đổi ngay không hiệu ứng.
  useLayoutEffect(() => {
    const from = composerFrom.current;
    composerFrom.current = null;
    if (emptyChat) {
      composerMove.current?.cancel();
      return;
    }
    const form = composerRef.current;
    const box = composerBoxRef.current;
    if (from === null || !form || !box || typeof form.animate !== "function") return;
    const distance = from - box.getBoundingClientRect().top;
    // Điện thoại giữ ô nhắn ở đáy cả hai lúc, nên không có gì để trượt.
    if (Math.abs(distance) < 1) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) {
      // Giảm chuyển động: bỏ quãng trượt, chỉ để ô nhắn hiện dần ở chỗ mới.
      composerMove.current = form.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: "ease" });
      return;
    }
    const easing = getComputedStyle(document.documentElement).getPropertyValue("--ease-in-out").trim();
    composerMove.current = form.animate(
      [{ transform: `translateY(${distance}px)` }, { transform: "none" }],
      { duration: 300, easing: easing || "ease-in-out" },
    );
  }, [emptyChat]);

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
            Đăng nhập để Peto biết cậu là ai.
          </p>

          {authError && (
            <div className="error" role="alert">
              {authError}
            </div>
          )}

          {/* Gọi /api/auth/me hỏng thì login_configured là false. Không có
              cờ này thì màn hình bày ra nút bấm không ăn thua mà chẳng báo gì —
              đúng cái bẫy làm người ta tưởng nút Google bị thiếu. */}
          {auth.login_configured ? (
            <>
              {auth.providers?.discord !== false && (
                <a className="discord-button" href={DISCORD_LOGIN_URL}>
                  <DiscordIcon />
                  Đăng nhập bằng Discord
                </a>
              )}

              <div className="login-divider">
                <span>Đăng nhập bằng cách khác</span>
              </div>

              <div className="login-alts">
                {auth.providers?.google && (
                  <a className="alt-login" href={GOOGLE_LOGIN_URL}>
                    <GoogleIcon />
                    Google
                  </a>
                )}
                <button
                  type="button"
                  className="alt-login"
                  disabled={guestBusy}
                  onClick={() => void enterAsGuest()}
                >
                  <GuestIcon />
                  {guestBusy ? "Đang vào…" : "Khách"}
                </button>
              </div>
            </>
          ) : (
            <div className="error">
              Chưa kết nối được dịch vụ đăng nhập. Thử tải lại trang hoặc báo
              người quản trị nhé.
            </div>
          )}

          <p className="login-note">
            Peto chỉ đọc tên và ảnh đại diện của cậu. Vào với tư cách khách thì
            hội thoại gắn với trình duyệt này — xóa cookie là mất.
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
    // Tin đầu của cuộc mới: nhớ chỗ ô nhắn đang đứng để trượt nó xuống đáy.
    if (emptyChat) composerFrom.current = composerBoxRef.current?.getBoundingClientRect().top ?? null;
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

    const appendThinking = (chunk: string) => {
      if (session !== authVersion.current) return;
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role !== "assistant") return prev;
        next[next.length - 1] = { ...last, thinking: (last.thinking ?? "") + chunk };
        return next;
      });
    };

    const updateSearch = (update: Partial<Message>) => {
      if (session !== authVersion.current || controller.signal.aborted) return;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        return last?.role === "assistant" ? [...prev.slice(0, -1), { ...last, ...update }] : prev;
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
          webSearch,
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
            updateSearch({ reading: undefined });
            if (storedMessage) setMessages((prev) => [...prev.slice(0, -2), storedMessage, prev[prev.length - 1]]);
          },
          onDelta: appendToReply,
          onThinking: appendThinking,
          onReading: (text) => updateSearch({ reading: text || undefined }),
          onSearch: (status) => updateSearch({ search_status: status }),
          onSources: (sources) => updateSearch({ sources: safeSources(sources) }),
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

  // Như Grok: đang ở Trò chuyện mà bấm lại thì mở cuộc mới. Từ Tạo ảnh quay về
  // thì giữ nguyên cuộc đang dở, vì người ta hay qua lại giữa hai tab.
  function goChat() {
    if (view !== "chat") {
      go("chat");
    } else if (!deleting) {
      newConversation();
    }
  }

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

      <aside className={["sidebar", sidebarOpen && "open", collapsed && "collapsed"].filter(Boolean).join(" ")}>
        <div className="sidebar-head">
          <div className="sidebar-brand">
            <PetoAvatar info={appInfo} />
            <strong>{appInfo?.name ?? "Peto"}</strong>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            title={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            onClick={() => setCollapsed((value) => !value)}
          >
            <SidebarIcon />
          </button>
        </div>
        <nav className="app-nav" aria-label="Khu vực">
          <button
            type="button"
            className={view === "chat" ? "nav-item on" : "nav-item"}
            aria-current={view === "chat" ? "page" : undefined}
            title={view === "chat" ? "Trò chuyện mới" : collapsed ? "Trò chuyện" : undefined}
            onClick={goChat}
          >
            <ComposeIcon />
            <span className="nav-label">Trò chuyện</span>
          </button>
          <button
            type="button"
            className={view === "imagine" ? "nav-item on" : "nav-item"}
            aria-current={view === "imagine" ? "page" : undefined}
            title={collapsed ? "Tạo ảnh" : undefined}
            onClick={() => go("imagine")}
          >
            <ImageIcon />
            <span className="nav-label">Tạo ảnh</span>
          </button>
        </nav>
        {view === "imagine" && (
          <div className="sidebar-section">
            <div className="imagine-sidebar-note">
              <span className="studio-eyebrow">Peto tạo ảnh</span>
              <p>Một chút tưởng tượng,<br />một thế giới của riêng bạn.</p>
            </div>
            <div className="imagine-library">
              <h2 className="imagine-library-title">Thư viện</h2>
              <nav className="imagine-job-list" aria-label="Thư viện">
                {imagineJobs.length === 0 && (
                  <p className="empty-hint">Chưa có ảnh nào. Ảnh bạn tạo sẽ hiện ở đây.</p>
                )}
                {imagineJobs.map((job) => (
                  <button
                    key={job.id}
                    className="job-link"
                    title={job.prompt}
                    aria-label={job.prompt}
                    onClick={() => {
                      setFocusJobId(job.id);
                      setSidebarOpen(false);
                    }}
                  >
                    {job.images[0] ? (
                      <img src={job.images[0].url} alt="" loading="lazy" />
                    ) : (
                      <span className="job-link-blank" aria-hidden="true" />
                    )}
                  </button>
                ))}
              </nav>
            </div>
          </div>
        )}
        {view === "chat" && (
        <div className="sidebar-section">
        <h2 className="sidebar-label" id="sidebar-recent">Gần đây</h2>
        <nav className="conversation-list" aria-labelledby="sidebar-recent">
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
        </div>
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
            <AccountAvatar user={auth.user} size={32} />
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
          key={auth.user?.id}
          active={view === "imagine"}
          onUnauthorized={handleUnauthorized}
          onOpenSidebar={() => setSidebarOpen(true)}
          onJobsChange={setImagineJobs}
          focusJobId={focusJobId}
          onFocusHandled={clearFocusJob}
        />
      )}
      <main className={emptyChat ? "chat empty-state" : "chat"} hidden={view !== "chat"}>
        <button
          type="button"
          className="menu-btn chat-menu"
          aria-label="Mở danh sách hội thoại"
          onClick={() => setSidebarOpen(true)}
        >
          <MenuIcon />
        </button>

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
          {emptyChat && (
            <div className="welcome">
              <PetoAvatar info={appInfo} big />
              <Greeting name={auth.user?.nickname?.trim() || auth.user?.display_name || "cậu"} />
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
                              {file.document.status === "ready" ? "Đã đọc chữ" : file.document.status === "partial" ? "Đọc được một phần" : "Chưa đọc được"}
                              {file.document.pages != null && ` · ${file.document.pages} trang`}
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
                message.thinking ||
                (streaming && !stopping && index === messages.length - 1 && !message.search_status && !message.reading)
              ) ? (
                <ThinkingPanel
                  live={streaming && !stopping && index === messages.length - 1 && !message.content}
                  text={message.thinking ?? ""}
                  label={THINKING[activeEffort ?? "low"]}
                />
              ) : null}
              {message.role === "assistant" && message.reading && streaming && !stopping && index === messages.length - 1 && !message.content && <div className="document-reading" role="status"><span className="document-reading-dot" aria-hidden="true" />{message.reading}</div>}
              {message.role === "assistant" && message.search_status && streaming && !stopping && index === messages.length - 1 && !message.content && <div className="web-search-status" role="status"><GlobeIcon /><span>{message.search_status === "searching" ? "Peto đang tìm trên web…" : "Peto đang tổng hợp nguồn…"}</span></div>}
              {message.content ? (
                <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeHighlight, {
                  languages: HIGHLIGHT_LANGUAGES, aliases: HIGHLIGHT_ALIASES, ignoreMissing: true,
                }]]} components={{
                  table: ({children}) => <div className="table-scroll" tabIndex={0} role="region" aria-label="Bảng nội dung"><table>{children}</table></div>,
                  a: ({children, href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
                  pre: ({node, children}) => {
                    const code = node?.children?.[0];
                    const names = code?.type === "element" && Array.isArray(code.properties?.className)
                      ? code.properties.className.map(String) : [];
                    const tag = names.find((name) => name.startsWith("language-"));
                    return <CodeBlock language={tag ? tag.slice("language-".length) : ""}>{children}</CodeBlock>;
                  },
                }}>{message.content}</Markdown>
              ) : null}
              {message.role === "assistant" && <WebSources sources={message.sources} />}
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

        <Composer
          draft={draft}
          onDraftChange={setDraft}
          files={draftFiles}
          onAddFiles={addFiles}
          onRemoveFile={removeDraftFile}
          streaming={streaming}
          stopping={stopping}
          canSend={canSend}
          onSubmit={submit}
          onStop={stop}
          effort={effort}
          efforts={EFFORTS}
          onEffortChange={setEffort}
          webSearch={webSearch}
          onToggleWeb={() => setWebSearch((mode) => (mode === "off" ? "auto" : "off"))}
          menuDisabled={streaming || view !== "chat"}
          hints={emptyChat ? CHAT_HINTS : []}
          onPickHint={(hint) => { setDraft(hint); textareaRef.current?.focus(); }}
          formRef={composerRef}
          boxRef={composerBoxRef}
          textareaRef={textareaRef}
          fileRef={fileRef}
        />
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

        {/* Chỉ phần dưới đường ngăn được cuộn; tiêu đề "Cài đặt" đứng yên. */}
        <div className="settings-body">
          <ProfileSettings
            open={settingsOpen}
            avatar={<AccountAvatar user={auth.user} size={40} />}
            onUnauthorized={handleUnauthorized}
            onSaved={(profile) => setAuth((prev) => (prev?.user
              ? { ...prev, user: { ...prev.user, nickname: profile.nickname } }
              : prev))}
          />

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
              <AccountAvatar user={auth.user} size={38} />
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
        </div>
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
