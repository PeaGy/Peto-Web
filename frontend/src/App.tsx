import { memo, lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import './styles.css';
import { normalizeMath } from "./mathMarkdown";
import { useMarkdownPlugins } from "./markdownExtras";
import LazyBoundary from "./LazyBoundary";
import { preloadable } from "./preloadable";
import { useLocalVoice } from "./LocalVoice";
import type { VoiceTab } from "./VoiceSettings";
import AgentConnectDialog, { forgetAgentCode, takeAgentCode } from "./AgentConnectDialog";
import AccountMenu, { placeAccountMenu, type AccountMenuPlace } from "./AccountMenu";
import SettingsDialog, { CLOSED_SETTINGS, type SettingsSection, type SettingsView } from "./SettingsDialog";
import { Segmented, SettingsGroup, SettingsIcon, SettingsRow, type SegmentOption } from "./settingsUi";
import { useCharacters } from './useCharacters';
const CharacterPicker = lazy(() => import('./CharacterPicker'));
import { readCharacterMotion, writeCharacterMotion, type CharacterMotion } from "./characterView";
import Composer from "./Composer";
import TextEditDialog from './TextEditDialog';
import HistorySearch from './HistorySearch';
import ConversationMenu from './ConversationMenu';
import DocumentWorkspace, { DocumentIcon } from './DocumentWorkspace';
import DocumentArtifactCard from './DocumentArtifactCard';
import DocumentPanel, { RightPanelIcon, type DocumentPanelSelection } from './DocumentPanel';
import type { DocumentDraftRequest } from './documentApi';
import { FileGlyph, formatSize, type DraftFile } from "./files";
import { fillName, greetingKey, pickGreeting } from "./timeGreeting";
import WebSources, { GlobeIcon, safeSources } from "./WebSources";
import {
  DISCORD_LOGIN_URL,
  GOOGLE_LOGIN_URL,
  UnauthorizedError,
  confirmRoleplayAge,
  deleteConversation,
  getAppInfo,
  getAuthState,
  guestLogin,
  getMessages,
  listConversations,
  updateConversation,
  conversationVersions,
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
  type Persona,
  type WebSearchMode,
} from "./api";

// Tạo ảnh, Companion và nội dung Cài đặt tải riêng lúc mở lần đầu: phần lớn lượt vào chỉ để chat, và tệp JS chính càng
// nhỏ thì điện thoại càng sớm thấy ô chat (đo ngày 2026-09-27). preload* gọi lúc rê chuột hay chạm vào nút mở.
const imagine = preloadable(() => import("./Imagine"));
const companion = preloadable(() => import("./Companion"));
const profileSettings = preloadable(() => import("./ProfileSettings"));
const voiceSettings = preloadable(() => import("./VoiceSettings"));
const memorySettings = preloadable(() => import("./MemorySettings"));
const searchSettings = preloadable(() => import("./SearchSettings"));
const agentSettings = preloadable(() => import("./AgentSettings"));
const characterSettings = preloadable(() => import("./CharacterSettings"));
const loadImagine = imagine.preload;
const loadCompanion = companion.preload;
const loadSettings = () => Promise.all([
  profileSettings.preload(), voiceSettings.preload(), memorySettings.preload(), searchSettings.preload(),
  agentSettings.preload(), characterSettings.preload(),
]);
// Tải trước: lỗi ở đây bỏ qua, lần mở thật sẽ tải lại và LazyBoundary lo phần báo lỗi.
const preload = (load: () => Promise<unknown>) => () => void load().catch(() => {});
const Imagine = imagine.View;
const Companion = companion.View;
const ProfileSettings = profileSettings.View;
const VoiceSettings = voiceSettings.View;
const MemorySettings = memorySettings.View;
const SearchSettings = searchSettings.View;
const AgentSettings = agentSettings.View;
const CharacterSettings = characterSettings.View;

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

const EFFORT_KEY = "peto-effort";
const MODEL_KEY = "peto-model";
const THEME_KEY = "peto-theme";
const SIDEBAR_KEY = "peto-sidebar-collapsed";
const MAX_FILES = 16;
const MAX_MEDIA_FILES = 4;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_TOTAL_BYTES = 16 * 1024 * 1024;

const EFFORTS: { value: Effort; label: string; hint: string }[] = [
  { value: "auto", label: "Tự động", hint: "Peto tự chọn mức phù hợp" },
  { value: "none", label: "Không suy luận", hint: "Ưu tiên phản hồi nhanh" },
  { value: "low", label: "Thấp", hint: "Trả lời nhanh, chat thường" },
  { value: "medium", label: "Trung bình", hint: "Cân bằng tốc độ và độ sâu" },
  { value: "high", label: "Cao", hint: "Suy nghĩ kỹ cho bài khó" },
  { value: "xhigh", label: "Rất cao", hint: "Đào sâu hơn, có thể chờ lâu hơn" },
  { value: "max", label: "Tối đa", hint: "Mức suy luận cao nhất, dùng nhiều token hơn" },
];

type ThemeChoice = "light" | "dark" | "system";
type AppView = "chat" | "imagine" | "companion";

const THEMES: SegmentOption<ThemeChoice>[] = [
  { value: "system", label: "Theo máy", hint: "Theo máy: đổi theo cài đặt của thiết bị", icon: <SettingsIcon name="monitor" size={17} /> },
  { value: "light", label: "Sáng", hint: "Sáng: nền trắng, hợp ban ngày", icon: <SettingsIcon name="sun" size={17} /> },
  { value: "dark", label: "Tối", hint: "Tối: nền tối, dịu mắt buổi đêm", icon: <SettingsIcon name="moon" size={17} /> },
];

/** Model đã chọn lần trước; tài khoản không còn được dùng model đó thì lúc gửi tự về Peto. */
function readStoredModel(): string {
  try {
    return localStorage.getItem(MODEL_KEY) || "peto";
  } catch {
    return "peto";
  }
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

function CompanionIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z" stroke="currentColor" strokeWidth="2" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** Vòng chờ lúc tệp của Tạo ảnh hay Companion đang tải lần đầu. */
function ViewLoading({ label }: { label: string }) {
  return (
    <div className="view-loading" role="status" aria-label={label}>
      <span className="loading-spinner" aria-hidden="true" />
    </div>
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
  steps?: { id: string; label: string; live?: boolean }[];
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
              {step.id === "search" ? (
                <GlobeIcon />
              ) : step.id === "document" || step.id.startsWith("file-") ? (
                <DocumentIcon />
              ) : (
                <span className="work-dot" aria-hidden="true" />
              )}
              {step.label}
            </li>
          ))}
        </ul>
      ) : null}
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
  return <span className="account-avatar account-initial" style={{ width: size, height: size }} aria-hidden="true">
    {(user?.display_name || "?").charAt(0).toUpperCase()}
  </span>;
}

/**
 * Dòng phụ dưới tên ở ô tài khoản, như chữ "Plus" của ChatGPT. Tài khoản Google có tên người dùng trùng tên hiển thị,
 * nên ghi nơi đăng nhập thay vào.
 */
function accountSubtitle(user?: AccountUser): string {
  if (user?.provider === "guest") return "Tài khoản khách";
  if (user?.provider === "google") return "Google";
  return user?.username ? `@${user.username}` : "Discord";
}

/** Dòng dưới tên trong mục Tài khoản của Cài đặt. */
function accountLine(user?: AccountUser): string {
  if (user?.provider === "guest") return "Tài khoản khách, chỉ có trên trình duyệt này";
  if (user?.provider === "google") return "Đăng nhập bằng Google";
  return `${user?.username ? `@${user.username} · ` : ""}Đăng nhập bằng Discord`;
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

// Old messages keep their rendered Markdown while the draft or current reply changes.
function EditIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/></svg>; }
function PinIcon() { return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path className="pin-head" d="m14 3 7 7-4 1-4 5-5-5 5-4z"/><path d="m10.5 13.5-7 7"/></svg>; }
function SearchIcon() { return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>; }

const ChatMessage = memo(function ChatMessage({ message, live, writing, onPreview, onEdit, actionsDisabled, editor }: {
  message: Message; live: boolean; writing: boolean;
  actionsDisabled?: boolean; editor?: ReactNode;
  onPreview: (item: { id: string; version: number }) => void;
  onEdit: (item: { id: string; version: number }) => void;
}) {
  const text = message.content ? normalizeMath(message.content) : "";
  const { remarkPlugins, rehypePlugins } = useMarkdownPlugins(text);
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
                <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={{
                  table: ({children}) => <div className="table-scroll" tabIndex={0} role="region" aria-label="Bảng nội dung"><table>{children}</table></div>,
                  a: ({children, href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
                  pre: ({node, children}) => {
                    const code = node?.children?.[0];
                    const names = code?.type === "element" && Array.isArray(code.properties?.className)
                      ? code.properties.className.map(String) : [];
                    const tag = names.find((name) => name.startsWith("language-"));
                    return <CodeBlock language={tag ? tag.slice("language-".length) : ""}>{children}</CodeBlock>;
                  },
                }}>{text}</Markdown>
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

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [guestBusy, setGuestBusy] = useState(false);
  // Liên kết do peto login in ra mang ?agent_code=; mã được giữ qua lúc đăng nhập chuyển hướng.
  const [agentCode, setAgentCode] = useState<string | null>(takeAgentCode);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [conversationMenu, setConversationMenu] = useState<{item:Conversation; left:number; top:number} | null>(null);
  const [versions, setVersions] = useState<Conversation[]>([]);
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
  const [renameText, setRenameText] = useState('');
  const [editTarget, setEditTarget] = useState<Message | null>(null);
  const [editText, setEditText] = useState('');
  const [retryAvailable, setRetryAvailable] = useState(false);
  const retryRevision = useRef<{ target: Message; text: string } | undefined>(undefined);
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [documentRequest, setDocumentRequest] = useState<DocumentDraftRequest | null>(null);
  const [documentSelection, setDocumentSelection] = useState<{ id: string; version: number; key: number } | null>(null);
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const [documentPanelOpen, setDocumentPanelOpen] = useState(false);
  const [documentPanelExpanded, setDocumentPanelExpanded] = useState(false);
  const [documentPreview, setDocumentPreview] = useState<DocumentPanelSelection | null>(null);
  const closeDocumentPanel = useCallback(() => { setDocumentPanelOpen(false); setDocumentPanelExpanded(false); }, []);
  const previewDocument = useCallback((item: { id: string; version: number }) => {
    setDocumentPreview({ id: item.id, version: item.version, key: Date.now() });
    setDocumentPanelOpen(true);
  }, []);
  const editDocument = useCallback((item: { id: string; version: number }) => {
    setDocumentSelection({ id: item.id, version: item.version, key: Date.now() });
  }, []);
  const [draftFiles, setDraftFiles] = useState<DraftFile[]>([]);
  const [effort, setEffort] = useState<Effort>(readStoredEffort);
  const [model, setModel] = useState<string>(readStoredModel);
  const [webSearch, setWebSearch] = useState<WebSearchMode>("auto");

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
  // Chế độ của hội thoại đang mở; hội thoại mới thì là lựa chọn trong menu dấu cộng, gửi tin đầu là chốt.
  const [persona, setPersona] = useState<Persona>("assistant");
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentBusy, setConsentBusy] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [showJump, setShowJump] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>(readStoredTheme);
  const [characterMotion, setCharacterMotion] = useState<CharacterMotion>(readCharacterMotion);
  const characters = useCharacters();
  const [characterPickerOpen, setCharacterPickerOpen] = useState(false);
  const [sceneRequest, setSceneRequest] = useState(0);
  const changeCharacterMotion = useCallback((value: CharacterMotion) => {
    setCharacterMotion(value);
    writeCharacterMotion(value);
  }, []);
  // Hộp Cài đặt: mở hay đóng, mục đang xem, và trên điện thoại đang ở danh sách mục hay trang của mục.
  const [settings, setSettings] = useState<SettingsView>(CLOSED_SETTINGS);
  const settingsOpen = settings.open;
  const closeSettings = useCallback(() => setSettings((current) => ({ ...current, open: false })), []);
  // Menu của ô tài khoản (như ChatGPT). Nó nằm ngoài thanh bên, vì thanh bên cắt phần tràn khi thu gọn còn 64px.
  const [accountMenu, setAccountMenu] = useState<AccountMenuPlace | null>(null);
  const accountRef = useRef<HTMLButtonElement>(null);
  // Mở Cài đặt từ menu thì đóng xong trả tiêu điểm về ô tài khoản: mục trong menu đã gỡ nên hộp thoại không tự trả được.
  const settingsReturn = useRef<HTMLElement | null>(null);
  const closeAccountMenu = useCallback((focusBack: boolean) => {
    setAccountMenu((current) => current && { ...current, closing: true });
    if (focusBack) accountRef.current?.focus();
  }, []);
  const dropAccountMenu = useCallback(() => setAccountMenu(null), []);
  const [view, setView] = useState<AppView>(() => {
    const hash = typeof window !== "undefined" ? window.location.hash : "";
    return hash === "#imagine" ? "imagine" : hash === "#companion" ? "companion" : "chat";
  });
  const [imageVisited, setImageVisited] = useState(view === "imagine");
  useEffect(() => {
    setDocumentPanelOpen(false); setDocumentPanelExpanded(false); setDocumentPreview(null); setDocumentSelection(null);
  }, [conversationId]);
  useEffect(() => {
    if (view !== 'chat') return;
    const shortcut = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && event.code === 'KeyB' && !document.querySelector('.document-workspace[open], .settings-dialog[open]')) {
        event.preventDefault(); setDocumentPanelOpen(value => !value); setDocumentPanelExpanded(false);
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [view]);
  const [companionVisited, setCompanionVisited] = useState(view === "companion");
  // Giọng nói dùng chung cho Companion và mục Giọng nói trong Cài đặt. Chỉ dò 127.0.0.1 sau khi đã mở
  // Companion hoặc lúc Cài đặt đang mở, để tab Trò chuyện không gọi gì ra máy.
  const localVoice = useLocalVoice(companionVisited || settingsOpen);
  // Thẻ đang mở của mục Giọng nói (Peto nói / Peto nghe); bảng Micro trong Companion mở thẳng thẻ Peto nghe.
  const [voiceTab, setVoiceTab] = useState<VoiceTab>("noi");
  // Nút "Xem" ở dòng "Peto vừa ghi nhớ" và đường dẫn trong bảng Micro mở thẳng mục của chúng, cả trên điện thoại.
  const openMemorySettings = useCallback(() => setSettings({ open: true, section: "tri-nho", page: true }), []);
  const openHearingSettings = useCallback(() => {
    setVoiceTab("nghe");
    setSettings({ open: true, section: "giong-noi", page: true });
  }, []);
  useEffect(() => {
    if (settingsOpen || !settingsReturn.current) return;
    settingsReturn.current.focus({ preventScroll: true });
    settingsReturn.current = null;
  }, [settingsOpen]);
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
  const consentDialogRef = useRef<HTMLDialogElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const chatDockRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const dock = chatDockRef.current;
    const chat = dock?.parentElement;
    if (!dock || !chat || typeof ResizeObserver === 'undefined') return;
    const measure = () => chat.style.setProperty('--chat-dock-height', `${dock.getBoundingClientRect().height}px`);
    const observer = new ResizeObserver(measure);
    observer.observe(dock);
    measure();
    return () => observer.disconnect();
  }, [auth?.authenticated, view]);
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
      localStorage.setItem(MODEL_KEY, model);
    } catch {}
  }, [model]);

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
    setDocumentRequest(null);
    setDocumentSelection(null);
    closeDocumentPanel(); setDocumentPreview(null);
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
    setSearchOpen(false);
    setConversationMenu(null);
    setVersions([]);
    setRenameTarget(null);
    setRenameText("");
    setEditTarget(null);
    setEditText("");
    setRetryAvailable(false);
    retryRevision.current = undefined;
    setConversationId(null);
    setDraft("");
    setNotice(null);
    setWebSearch("auto");
    setPersona("assistant");
    setConsentOpen(false);
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
    setSettings(CLOSED_SETTINGS);
    setAccountMenu(null);
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
        const page = await listConversations(all.length, 50, '');
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
    let active = true;
    setVersions([]);
    if (conversationId && !streaming) void conversationVersions(conversationId).then(rows => { if (active) setVersions(rows); }).catch(() => {});
    return () => { active = false; };
  }, [conversationId, streaming]);

  const waitingForTitle = conversations.some(item =>
    item.id === conversationId && (item.title_state === 'pending' ||
      (item.title_state === 'temporary' && (item.title_attempts || 0) < 3)));
  useEffect(() => {
    if (!auth?.authenticated || view !== 'chat' || streaming || !waitingForTitle) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const poll = async () => {
      try {
        const page = await listConversations();
        if (cancelled) return;
        setConversations(current => current.map(item => {
          const fresh = page.conversations.find(row => row.id === item.id);
          return fresh ? { ...item, title: fresh.title, title_state: fresh.title_state, title_attempts: fresh.title_attempts } : item;
        }));
      } catch { /* A later refresh can recover; do not interrupt typing. */ }
      if (!cancelled && ++attempts < 12) timer = setTimeout(poll, 2500);
    };
    timer = setTimeout(poll, 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [auth?.user?.id, auth?.authenticated, view, conversationId, streaming, waitingForTitle]);

  useEffect(() => {
    if (auth?.authenticated) void refreshConversations();
  }, [auth?.authenticated, refreshConversations]);

  // Ô chat đã hiện thì lúc rảnh tải sẵn Tạo ảnh, Companion và Cài đặt: lần mở đầu khỏi chờ tệp (khoảng 0,3 giây trên 4G
  // chậm, đo ngày 2026-09-27). Bỏ qua khi người dùng bật tiết kiệm dữ liệu hay mạng chỉ 2G.
  useEffect(() => {
    if (!auth?.authenticated) return;
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || /2g/.test(connection?.effectiveType ?? "")) return;
    let idle = 0;
    const warm = () => {
      preload(loadSettings)();
      preload(loadImagine)();
      preload(loadCompanion)();
    };
    const timer = window.setTimeout(() => {
      idle = window.requestIdleCallback ? window.requestIdleCallback(warm, { timeout: 5000 }) : window.setTimeout(warm, 0);
    }, 4000);
    return () => {
      window.clearTimeout(timer);
      if (window.cancelIdleCallback) window.cancelIdleCallback(idle);
      else window.clearTimeout(idle);
    };
  }, [auth?.authenticated]);

  useEffect(() => {
    if (nearBottom.current) bottomRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
    else setShowJump(true);
  }, [messages, streaming]);

  useEffect(() => {
    if (deleteTarget) deleteDialogRef.current?.showModal();
    else deleteDialogRef.current?.close();
  }, [deleteTarget]);

  useEffect(() => {
    if (consentOpen) consentDialogRef.current?.showModal();
    else consentDialogRef.current?.close();
  }, [consentOpen]);

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
  // Chế độ nhập vai chỉ dùng Peto (máy chủ cũng chặn), nên không hiện nút chọn model.
  const models = persona === "roleplay" ? [] : auth?.user?.models ?? [];
  const chosenModel = models.some((item) => item.key === model) ? model : "peto";
  const supportedEfforts = models.find(item => item.key === chosenModel)?.efforts ?? ['low', 'medium', 'high'];
  const effortOptions = EFFORTS.filter(item => item.value === 'auto' || supportedEfforts.includes(item.value));
  const effectiveEffort = effortOptions.some(item => item.value === effort) ? effort : 'auto';

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
    return <div className="boot" role="status" aria-label="Đang tải Peto"><span className="loading-spinner" aria-hidden="true" /></div>;
  }

  if (!auth.authenticated) {
    return (
      <div className="login">
        <div className="login-card">
          <PetoAvatar info={appInfo} big />
          <h1>{appInfo?.name ?? "Peto"}</h1>
          <p className="login-sub">
            Đăng nhập để Peto biết bạn là ai.
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
            Peto chỉ đọc tên và ảnh đại diện của bạn.
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
    setRetryAvailable(false);
    retryRevision.current = undefined;
    setNotice(null);
    setConversationId(id);
    setEditTarget(null);
    setPersona(conversations.find((item) => item.id === id)?.persona ?? "assistant");
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
    setEditTarget(null);
    setRetryAvailable(false);
    retryRevision.current = undefined;
    loadRef.current?.abort();
    loadVersion.current += 1;
    setLoadingConversation(false);
    setLoadFailed(false);
    nearBottom.current = true;
    setShowJump(false);
    setConversationId(null);
    setPersona("assistant");
    setMessages([]);
    setError(null);
    setNotice(null);
    setSidebarOpen(false);
    textareaRef.current?.focus();
  }

  /** Bật/tắt chế độ nhập vai cho hội thoại chưa bắt đầu. Lần đầu bật thì hỏi xác nhận đủ 18 tuổi. */
  function toggleRoleplay() {
    if (conversationId || abortRef.current) return;
    if (persona === "roleplay") {
      setPersona("assistant");
    } else if (auth?.user?.roleplay_confirmed) {
      setPersona("roleplay");
    } else {
      setConsentError(null);
      setConsentOpen(true);
    }
  }

  async function confirmRoleplay() {
    setConsentBusy(true);
    setConsentError(null);
    try {
      await confirmRoleplayAge();
      setAuth((prev) => (prev?.user ? { ...prev, user: { ...prev.user, roleplay_confirmed: true } } : prev));
      setPersona("roleplay");
      setConsentOpen(false);
    } catch (err) {
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setConsentError(err instanceof Error ? err.message : "Chưa lưu được xác nhận. Thử lại nhé.");
    } finally {
      setConsentBusy(false);
    }
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

  async function submit(revision?: { target: Message; text: string }) {
    const text = revision ? revision.text.trim() : draft.trim();
    const hasAttachments = revision ? Boolean(revision.target.attachments?.length) : draftFiles.length > 0;
    if ((!text && !hasAttachments) || abortRef.current || loadingConversation || loadFailed) return;

    const pending = revision ? [] : draftFiles;
    const previousMessages = messages;
    const revisionIndex = revision ? messages.findIndex(m => m.id === revision.target.id) : -1;
    if (revision && revisionIndex < 0) {
      setRetryAvailable(false);
      setError("Hãy mở lại cuộc trò chuyện trước khi sửa hoặc tạo lại câu trả lời này.");
      return;
    }
    const prefix = revision ? messages.slice(0, revisionIndex) : messages;
    setRetryAvailable(false);
    retryRevision.current = revision;
    setEditTarget(null);
    setError(null);
    setNotice(null);
    // Tin đầu của cuộc mới: nhớ chỗ ô nhắn đang đứng để trượt nó xuống đáy.
    if (emptyChat) composerFrom.current = composerBoxRef.current?.getBoundingClientRect().top ?? null;
    setStreaming(true);
    setStopping(false);
    nearBottom.current = true;
    setShowJump(false);


    const optimistic: ChatAttachment[] = pending.map((item) => ({
      id: item.id,
      name: item.file.name,
      mime: item.file.type || "application/octet-stream",
      kind: isImageFile(item.file) ? "image" : "file",
      size: item.file.size,
      url: item.previewUrl || "",
    }));

    setMessages([
      ...prefix,
      { role: "user", content: text, attachments: revision?.target.attachments || optimistic },
      { role: "assistant", content: "", workSteps: [{id:'connection',label:'Đang gửi và chờ máy chủ…',live:true}] },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    let activeId = conversationId;
    let accepted = false;
    let completed = false;
    // Mỗi lần Peto tìm/đọc trong tệp là một dòng riêng trong danh sách "Đang làm…".
    let fileLookups = 0;
    let writingPhase = false;
    const session = authVersion.current;
    const startedAt = performance.now();

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

    const addWorkStep = (id: string, label: string, live = false) => {
      if (session !== authVersion.current) return;
      if (live && id !== 'prepare') writingPhase = false;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role !== "assistant") return prev;
        const steps = (last.workSteps ?? []).map(step => live ? { ...step, live:false, label:step.id === 'think' ? 'Đã suy nghĩ' : step.label } : step);
        const index = steps.findIndex((step) => step.id === id);
        const step = { id, label, live };
        if (index >= 0) steps[index] = step;
        else steps.push(step);
        return [...prev.slice(0, -1), { ...last, workSteps: steps }];
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
          branchMessageId: revision?.target.id,
          effort: effectiveEffort,
          webSearch,
          attachments,
          persona,
          model: chosenModel,
        },
        {
          onMeta: (id, _usedEffort, storedMessage) => {
            if (session !== authVersion.current) return;
            accepted = true;
            activeId = id;
            setConversationId(id);
            if (!revision) { setDraft(""); setDraftFiles([]); }
            if (storedMessage) retryRevision.current = {target:storedMessage, text:storedMessage.content};
            addWorkStep('connection', 'Đã kết nối', false);
            addWorkStep('prepare', 'Đang chuẩn bị câu trả lời…', true);
            updateSearch({ reading: undefined });
            if (storedMessage) setMessages((prev) => [...prev.slice(0, -2), storedMessage, prev[prev.length - 1]]);
          },
          onDelta: (chunk) => { if (!writingPhase) { addWorkStep('prepare', 'Đang trả lời…', true); writingPhase = true; } appendToReply(chunk); },
          onReplace: () => {
            if (session !== authVersion.current) return;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role !== "assistant") return prev;
              return [...prev.slice(0, -1), { ...last, content: "" }];
            });
          },
          onThinking: () => addWorkStep("think", "Đang suy nghĩ…", true),
          onReading: (text) => {
            updateSearch({ reading: text || undefined });
            addWorkStep("reading", text || "Đã đọc tài liệu", Boolean(text));
          },
          onSearch: (status) => {
            updateSearch({ search_status: status });
            addWorkStep(
              "search",
              status === "searching" ? "Đang tìm trên web…" : "Đã tìm trên web",
              status === "searching",
            );
          },
          onSources: (sources) => updateSearch({ sources: safeSources(sources) }),
          onDocumentStatus: (text) => {
            updateSearch({ document_status: text || undefined });
            if (text) addWorkStep("document", text, true);
          },
          onFileLookup: (text, live) => {
            if (live) fileLookups += 1;
            addWorkStep(`file-${fileLookups}`, text, live);
          },
          onArtifact: (artifact) => {
            if (session !== authVersion.current || controller.signal.aborted) return;
            setMessages(previous => {
              const last = previous[previous.length - 1];
              if (last?.role !== 'assistant') return previous;
              const artifacts = [...(last.artifacts || []).filter(item => item.id !== artifact.id || item.version !== artifact.version), artifact];
              const steps = [...(last.workSteps ?? [])];
              const index = steps.findIndex((step) => step.id === "document");
              const label = artifact.filename ? `Đã tạo ${artifact.filename}` : "Đã tạo tệp";
              const step = { id: "document", label, live: false };
              if (index >= 0) steps[index] = step;
              else steps.push(step);
              return [...previous.slice(0, -1), { ...last, artifacts, document_status: undefined, workSteps: steps }];
            });
            setDocumentRefresh(value => value + 1);
          },
          onError: (message) => {
            if (session !== authVersion.current) return;
            setError(message);
            setRetryAvailable(true);
          },
          onDone: () => {
            completed = true;
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        handleUnauthorized();
      } else if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : "Mất kết nối tới máy chủ";
        setError(accepted ? message : `${message} Bản nháp được giữ lại; kiểm tra lịch sử trước khi gửi lại nếu kết nối bị ngắt.`);
        setRetryAvailable(true);
      }
    } finally {
      if (session === authVersion.current) {
        if (!accepted) setMessages(previousMessages);
        else {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role !== "assistant") return prev;
            return last.content || last.artifacts?.length
              ? [...prev.slice(0, -1), {
                  ...last,
                  document_status: undefined,
                  status: completed ? "complete" : "incomplete",
                  workedMs: Math.round(performance.now() - startedAt),
                  workSteps: (last.workSteps ?? []).map((step) => ({ ...step, live: false, label: step.label.startsWith('Đang ') ? (completed ? step.label.replace('Đang ', 'Đã ') : 'Đã dừng: ' + step.label.slice(5)) : step.label })),
                }]
              : prev.slice(0, -1);
          });
        }
        if (controller.signal.aborted) setNotice(accepted ? "Đã dừng. Phần đã trả lời được giữ lại." : "Đã dừng gửi. Bản nháp vẫn được giữ lại.");
        if (activeId || !accepted) void refreshConversations();
        if (revision && accepted && activeId) {
          // Fetch stable IDs for edit/regenerate; preserve the local progress log.
          try {
            const stored = await getMessages(activeId);
            if (session === authVersion.current) setMessages(current => current.map((row, i) => ({...row, id:stored[i]?.id})));
          } catch { setMessages(current => current.map(row => ({...row,id:undefined}))); }
        }
      }
      if (accepted) for (const item of pending) if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      setStreaming(false);
      setStopping(false);
      abortRef.current = null;
      textareaRef.current?.focus();
    }
  }

  function stop() {
    setStopping(true);
    abortRef.current?.abort();
  }

  async function changeConversation(item: Conversation, change: {title?: string; pinned?: boolean}) {
    if (metadataBusy) return;
    setMetadataBusy(true);
    try {
      await updateConversation(item.id, change);
      setRenameTarget(null);
      await refreshConversations();
    } catch (err) {
      if (err instanceof UnauthorizedError) handleUnauthorized();
      else setError(err instanceof Error ? err.message : 'Chưa lưu được thay đổi');
    } finally { setMetadataBusy(false); }
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
    if (next === "companion") setCompanionVisited(true);
    setView(next);
    setSidebarOpen(false);
    const url = next === "chat" ? `${window.location.pathname}${window.location.search}` : `#${next}`;
    window.history.replaceState(null, "", url);
  }

  function toggleAccountMenu() {
    if (accountMenu && !accountMenu.closing) closeAccountMenu(false);
    else if (accountRef.current) setAccountMenu(placeAccountMenu(accountRef.current));
  }

  function openFromAccountMenu(section: SettingsSection, page: boolean) {
    settingsReturn.current = accountRef.current;
    closeAccountMenu(false);
    setSidebarOpen(false);
    setSettings({ open: true, section, page });
  }

  const guestAccount = auth.user?.provider === "guest";
  const settingsLoading = (
    <div className="settings-loading" role="status" aria-label="Đang tải cài đặt"><span className="loading-spinner" aria-hidden="true" /></div>
  );
  // Mỗi mục tải tệp riêng và có lớp chờ riêng: mục Giao diện không phải đợi tệp của mục Giọng nói.
  // `active`: mục đang được xem trong hộp đang mở; các mục chỉ tải dữ liệu lúc đó.
  const renderSettings = (section: SettingsSection, active: boolean): ReactNode => {
    switch (section) {
      case "giao-dien":
        return (
          <SettingsGroup>
            <SettingsRow label="Chủ đề" desc="Nền sáng, nền tối, hoặc theo cài đặt của máy.">
              <Segmented label="Chủ đề" value={theme} options={THEMES} onChange={setTheme} />
            </SettingsRow>
            <LazyBoundary><Suspense fallback={null}>
              <CharacterSettings value={characterMotion} onChange={changeCharacterMotion}
                onOpenCharacters={() => setCharacterPickerOpen(true)} selectedName={characters.selected.name} />
            </Suspense></LazyBoundary>
          </SettingsGroup>
        );
      case "ho-so":
        return (
          <LazyBoundary><Suspense fallback={settingsLoading}>
            <ProfileSettings
              open={active}
              avatar={<AccountAvatar user={auth.user} size={36} />}
              avatarNote={guestAccount ? undefined : `Theo tài khoản ${auth.user?.provider === "google" ? "Google" : "Discord"}`}
              onUnauthorized={handleUnauthorized}
              onSaved={(profile) => setAuth((prev) => (prev?.user
                ? { ...prev, user: { ...prev.user, nickname: profile.nickname } }
                : prev))}
            />
          </Suspense></LazyBoundary>
        );
      case "tai-khoan":
        return (
          <SettingsGroup>
            <div className="settings-row settings-account">
              <AccountAvatar user={auth.user} size={40} />
              <div className="account-name">
                <strong>{auth.user?.display_name}</strong>{" "}
                <span>{accountLine(auth.user)}</span>
              </div>
            </div>
            <SettingsRow label="Hướng dẫn Peto" desc="Cách dùng Trò chuyện, Companion và Peto Agent.">
              <a className="settings-button settings-link" href="/docs/" target="_blank" rel="noreferrer">
                Mở hướng dẫn <SettingsIcon name="external" size={14} />
              </a>
            </SettingsRow>
            <SettingsRow
              label="Đăng xuất"
              desc={guestAccount
                ? "Khách không đăng nhập lại được: đăng xuất rồi thì không mở lại được các hội thoại này."
                : "Thoát tài khoản trên trình duyệt này. Hội thoại vẫn còn khi bạn đăng nhập lại."}
            >
              <button
                type="button"
                className="settings-button danger"
                disabled={streaming}
                onClick={() => {
                  closeSettings();
                  void signOut();
                }}
              >
                Đăng xuất
              </button>
            </SettingsRow>
          </SettingsGroup>
        );
      case "agent":
        return (
          <LazyBoundary><Suspense fallback={settingsLoading}>
            <AgentSettings open={active} isGuest={guestAccount} onUnauthorized={handleUnauthorized} />
          </Suspense></LazyBoundary>
        );
      case "giong-noi":
        return (
          <LazyBoundary><Suspense fallback={settingsLoading}>
            <VoiceSettings voice={localVoice} open={active} tab={voiceTab} onTab={setVoiceTab} />
          </Suspense></LazyBoundary>
        );
      case "tri-nho":
        return (
          <LazyBoundary><Suspense fallback={settingsLoading}>
            <MemorySettings open={active} onUnauthorized={handleUnauthorized} />
          </Suspense></LazyBoundary>
        );
      case "tra-web":
        return (
          <LazyBoundary><Suspense fallback={settingsLoading}>
            <SearchSettings />
          </Suspense></LazyBoundary>
        );
    }
  };

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
          <button type="button" className="sidebar-search-button" aria-label="Tìm kiếm hội thoại" title="Tìm kiếm hội thoại" disabled={streaming} onClick={() => setSearchOpen(true)}><SearchIcon /></button>
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
            onPointerEnter={preload(loadImagine)}
            onFocus={preload(loadImagine)}
          >
            <ImageIcon />
            <span className="nav-label">Tạo ảnh</span>
          </button>
          <button
            type="button"
            className={view === "companion" ? "nav-item on" : "nav-item"}
            aria-current={view === "companion" ? "page" : undefined}
            title={collapsed ? "Companion" : undefined}
            onClick={() => go("companion")}
            onPointerEnter={preload(loadCompanion)}
            onFocus={preload(loadCompanion)}
          >
            <CompanionIcon />
            <span className="nav-label">Companion</span>
          </button>
          {view === "companion" && <div className="mobile-companion-nav">
            <button type="button" className="nav-item" onClick={() => { setSidebarOpen(false); setSceneRequest(n => n + 1); }}><ImageIcon /><span>Bối cảnh</span></button>
            <button type="button" className="nav-item" onClick={() => { setSidebarOpen(false); setCharacterPickerOpen(true); }}><span aria-hidden="true">◇</span><span>Nhân vật</span></button>
          </div>}
        </nav>
        {view === "imagine" && (
          <div className="sidebar-section">
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
                <span className="conv-title">{conversation.title || "Chưa có tiêu đề"}</span>
                {conversation.persona === "roleplay" && <span className="conv-persona">· Nhập vai</span>}
              </button>
              <div className="conv-hover-actions">
                <button type="button" aria-label={`Tùy chọn ${conversation.title}`} title="Tùy chọn hội thoại" disabled={streaming || deleting} onClick={e => { const r=e.currentTarget.getBoundingClientRect(); setConversationMenu({item:conversation,left:Math.max(8,Math.min(r.left,window.innerWidth-192)),top:Math.max(8,Math.min(r.bottom+6,window.innerHeight-158))}); }}>⋯</button>
                <button type="button" aria-label={conversation.pinned ? 'Bỏ ghim' : 'Ghim'} title={conversation.pinned ? 'Bỏ ghim' : 'Ghim'} aria-pressed={Boolean(conversation.pinned)} disabled={metadataBusy} onClick={() => void changeConversation(conversation,{pinned:!conversation.pinned})}><PinIcon /></button>
              </div>
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

        {/* Ô tài khoản gọn như ChatGPT (chủ web chọn ngày 2026-09-29): bấm vào mở menu tài khoản. */}
        <div className="sidebar-foot">
          <button
            ref={accountRef}
            type="button"
            className="account"
            aria-haspopup="menu"
            aria-expanded={Boolean(accountMenu && !accountMenu.closing)}
            aria-label={`Tài khoản · ${auth.user?.display_name}`}
            title={collapsed ? auth.user?.display_name : undefined}
            onClick={toggleAccountMenu}
            onPointerEnter={preload(loadSettings)}
            onFocus={preload(loadSettings)}
          >
            <AccountAvatar user={auth.user} size={24} />
            <span className="account-name">
              <strong>{auth.user?.display_name}</strong>{" "}
              <span>{accountSubtitle(auth.user)}</span>
            </span>
          </button>
        </div>
      </aside>

      {/* Imagine và Companion nằm cạnh nhau trong cùng một danh sách con, nên key phải khác nhau. Trùng
          key thì React nhân đôi tab, và mỗi bản Imagine mới lại tải danh sách ảnh, lặp mãi không dừng. */}
      {imageVisited && (
        <LazyBoundary>
        <Suspense fallback={view === "imagine" ? <ViewLoading label="Đang mở Tạo ảnh" /> : null}>
        <Imagine
          key={`imagine-${auth.user?.id}`}
          active={view === "imagine"}
          onUnauthorized={handleUnauthorized}
          onOpenSidebar={() => setSidebarOpen(true)}
          onJobsChange={setImagineJobs}
          focusJobId={focusJobId}
          onFocusHandled={clearFocusJob}
        />
        </Suspense>
        </LazyBoundary>
      )}
      {companionVisited && (
        <LazyBoundary>
        <Suspense fallback={view === "companion" ? <ViewLoading label="Đang mở Companion" /> : null}>
        <Companion
          key={`companion-${auth.user?.id}`}
          active={view === "companion"}
          appInfo={appInfo}
          voice={localVoice}
          sceneRequest={sceneRequest}
          characterMotion={characterMotion}
          character={characters.selected}
          onCharacterPreview={characters.savePreview}
          onOpenCharacters={() => setCharacterPickerOpen(true)}
          onUnauthorized={handleUnauthorized}
          onOpenSidebar={() => setSidebarOpen(true)}
          onOpenHearingSettings={openHearingSettings}
          onOpenMemorySettings={openMemorySettings}
        />
        </Suspense>
        </LazyBoundary>
      )}
      <div className={`chat-layout${documentPanelOpen ? ' documents-open' : ''}${documentPanelOpen && documentPanelExpanded ? ' documents-expanded' : ''}`} hidden={view !== 'chat'}>
      <main className={emptyChat ? "chat empty-state" : "chat"}>
        <div className="chat-tools">
        <button
          type="button"
          className="menu-btn chat-menu"
          aria-label="Mở danh sách hội thoại"
          onClick={() => setSidebarOpen(true)}
        >
          <MenuIcon />
        </button>
        <button type="button" className="artifact-icon document-panel-toggle" aria-label={documentPanelOpen ? 'Đóng bảng tài liệu' : 'Mở bảng tài liệu'} aria-expanded={documentPanelOpen} aria-controls="document-panel" title="Tài liệu · Ctrl+Alt+B" onClick={() => { setDocumentPanelOpen(value => !value); setDocumentPanelExpanded(false); }}><RightPanelIcon /></button>
        </div>

        <div className="messages" ref={messagesRef} onClick={e => {
          const button = (e.target as Element).closest<HTMLButtonElement>('button[data-revise]');
          if (!button || streaming || loadingConversation) return;
          const id = Number(button.dataset.revise);
          const target = messages.find(m => m.id === id && m.role === 'user');
          if (!target) return;
          setEditTarget(target); setEditText(target.content);
        }} onScroll={() => {
          const element = messagesRef.current;
          if (!element) return;
          nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
          setShowJump(!nearBottom.current);
        }}>
          {loadingConversation && <div className="loading-chat" role="status" aria-label="Đang mở hội thoại"><span className="loading-spinner" aria-hidden="true" /></div>}
          {loadFailed && <div className="loading-chat" role="alert">
            <p>Chưa tải được nội dung hội thoại.</p>
            <button className="load-more" onClick={() => conversationId && void openConversation(conversationId)}>Thử mở lại</button>
          </div>}
          {emptyChat && (
            <div className="welcome">
              <PetoAvatar info={appInfo} big />
              <Greeting name={auth.user?.nickname?.trim() || auth.user?.display_name || "bạn"} />
            </div>
          )}

          {versions.length > 1 && <label className="conversation-versions">Phiên bản hội thoại <select aria-label="Phiên bản hội thoại" value={conversationId || ''} disabled={streaming || loadingConversation} onChange={e => void openConversation(e.target.value)}>
            {versions.map((item, i) => <option value={item.id} key={item.id}>Bản {i + 1} · {new Date(item.created_at * 1000).toLocaleString('vi-VN')}</option>)}
          </select></label>}
          {messages.map((message, index) => (
            <ChatMessage key={index} message={message}
              actionsDisabled={streaming || loadingConversation || loadFailed}
              editor={editTarget?.id === message.id && editTarget ? <form className="inline-message-editor" onSubmit={e => {e.preventDefault(); void submit({target:editTarget,text:editText});}}>
                <textarea autoFocus aria-label="Sửa tin nhắn" value={editText} onChange={e => setEditText(e.target.value)} rows={Math.min(12,Math.max(3,editText.split('\n').length))} onKeyDown={e => {if(e.key==='Escape') setEditTarget(null);}}/>
                <div><button type="button" onClick={() => setEditTarget(null)}>Hủy</button><button type="submit" disabled={streaming || (!editText.trim() && !editTarget.attachments?.length)}>Gửi</button></div>
              </form> : undefined}
              live={streaming && !stopping && index === messages.length - 1}
              writing={streaming && index === messages.length - 1}
              onPreview={previewDocument} onEdit={editDocument} />
          ))}
          <div ref={bottomRef} />
        </div>

        {showJump && <button type="button" className="jump-latest" aria-label="Tin mới nhất" title="Tin mới nhất" onClick={() => {
          nearBottom.current = true;
          setShowJump(false);
          bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
        }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 4v16m-7-7 7 7 7-7" /></svg></button>}

        <div className="chat-dock" ref={chatDockRef}>
        {error && (
          <div className="error" role="alert">
            {error}
            {retryAvailable && <button type="button" disabled={streaming || loadingConversation} onClick={() => void submit(retryRevision.current)}>Thử lại</button>}
            <button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => { setError(null); setRetryAvailable(false); }}>×</button>
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
          effort={effectiveEffort}
          efforts={effortOptions}
          onEffortChange={setEffort}
          webSearch={webSearch}
          onToggleWeb={() => setWebSearch((mode) => (mode === "off" ? "auto" : "off"))}
          persona={persona}
          roleplay={view === "chat" && !conversationId ? {
            active: persona === "roleplay",
            unavailable: auth?.user?.provider === "guest" ? "Cần tài khoản Discord hoặc Google" : null,
            onToggle: toggleRoleplay,
          } : undefined}
          menuDisabled={streaming || view !== "chat"}
          model={chosenModel}
          models={models}
          onModelChange={setModel}
          formRef={composerRef}
          boxRef={composerBoxRef}
          textareaRef={textareaRef}
          fileRef={fileRef}
        />
        </div>
      </main>
      <DocumentPanel key={`${auth.user?.id}-${conversationId}`} conversationId={conversationId} open={documentPanelOpen && view === 'chat'} expanded={documentPanelExpanded} selection={documentPreview} refreshKey={documentRefresh} onClose={closeDocumentPanel} onExpand={() => setDocumentPanelExpanded(value => !value)} onEdit={item => setDocumentSelection({ ...item, key: Date.now() })} onUnauthorized={handleUnauthorized} />
      </div>
      <DocumentWorkspace key={auth.user?.id || 'session'} request={documentRequest} selection={documentSelection} onUnauthorized={handleUnauthorized} onChanged={item => {
        setDocumentRefresh(value => value + 1);
        if (item?.conversation_id === conversationId) setDocumentPreview({ id: item.id, version: item.version, key: Date.now() });
      }} />
      {accountMenu && (
        <AccountMenu
          place={accountMenu}
          avatar={<AccountAvatar user={auth.user} size={24} />}
          name={auth.user?.display_name ?? ""}
          subtitle={accountSubtitle(auth.user)}
          signOutDisabled={streaming}
          onClose={closeAccountMenu}
          onExited={dropAccountMenu}
          onOpenSettings={openFromAccountMenu}
          onSignOut={() => {
            closeAccountMenu(false);
            setSidebarOpen(false);
            void signOut();
          }}
        />
      )}
      <SettingsDialog view={settings} onView={setSettings} onClose={closeSettings} render={renderSettings} />
      {characterPickerOpen && <LazyBoundary><Suspense fallback={null}><CharacterPicker library={characters} onClose={() => setCharacterPickerOpen(false)} /></Suspense></LazyBoundary>}
      {agentCode && <AgentConnectDialog code={agentCode} isGuest={auth.user?.provider === "guest"}
        onClose={() => { forgetAgentCode(); setAgentCode(null); }} onUnauthorized={handleUnauthorized} />}
      {renameTarget && <TextEditDialog title="Đổi tên hội thoại" value={renameText} onChange={setRenameText} busy={metadataBusy} onClose={() => setRenameTarget(null)} onSave={() => void changeConversation(renameTarget, {title:renameText})}/>}
      {searchOpen && <HistorySearch onClose={() => setSearchOpen(false)} onUnauthorized={handleUnauthorized} onSelect={id => {setSearchOpen(false); go('chat'); void openConversation(id);}}/>}
      {conversationMenu && <ConversationMenu left={conversationMenu.left} top={conversationMenu.top} onClose={() => setConversationMenu(null)}>
        <button onClick={() => {setRenameTarget(conversationMenu.item);setRenameText(conversationMenu.item.title);setConversationMenu(null);}}><EditIcon />Đổi tên</button>
        <button disabled={metadataBusy} onClick={() => {void changeConversation(conversationMenu.item,{pinned:!conversationMenu.item.pinned});setConversationMenu(null);}}><PinIcon />{conversationMenu.item.pinned ? 'Bỏ ghim' : 'Ghim'}</button>
        <button className="danger-button" onClick={() => {setDeleteTarget(conversationMenu.item);setConversationMenu(null);}}>Xóa hội thoại</button>
      </ConversationMenu>}
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
      <dialog ref={consentDialogRef} className="confirm-dialog" aria-labelledby="roleplay-consent-title" onCancel={(event) => {
        event.preventDefault();
        if (!consentBusy) setConsentOpen(false);
      }}>
        <h2 id="roleplay-consent-title">Bật chế độ nhập vai?</h2>
        <p>Ở chế độ này có thể có nội dung người lớn (18+). Chế độ gắn với hội thoại mới này; muốn quay lại thì mở hội thoại mới.</p>
        {consentError && <p className="consent-error" role="alert">{consentError}</p>}
        <div className="dialog-actions">
          <button autoFocus disabled={consentBusy} onClick={() => setConsentOpen(false)}>Để sau</button>
          <button className="primary-button" disabled={consentBusy} onClick={() => void confirmRoleplay()}>{consentBusy ? "Đang lưu…" : "Tôi đủ 18 tuổi"}</button>
        </div>
      </dialog>
    </div>
  );
}
