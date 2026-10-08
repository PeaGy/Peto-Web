import { usePreferencesPersistence } from './usePreferencesPersistence';
import LoginScreen from './LoginScreen';
import { EditIcon } from '../shared/ui/EditIcon';
import Sidebar from './Sidebar';
import { useProjects } from '../features/projects/useProjects';
import ProjectSidebar, { FolderIcon } from '../features/projects/ProjectSidebar';
import { createProject, deleteProject, updateProject, type Project } from '../features/projects/projectApi';
import { ProjectConfirm } from '../features/projects/ProjectControls';
import MoveConversationDialog from '../features/projects/MoveConversationDialog';
import ProjectChatHeader from '../features/projects/ProjectChatHeader';
import { ChatMessage } from '../features/chat/ChatMessage';
import { disconnectStream, networkInterrupted, useReplyRecovery } from '../features/chat/useReplyRecovery';
import { ReplyRecoveryNotice } from '../features/chat/ReplyRecoveryNotice';
import { Greeting } from '../features/chat/Greeting';
import { LoadingIndicator } from '../shared/ui/LoadingIndicator';
import { MenuIcon, PinIcon } from './navigationIcons';
import { PetoAvatar, AccountAvatar, accountLine, accountSubtitle } from './accountUi';
import { EFFORTS, THEMES, readStoredModel, readStoredEffort, readStoredTheme, readStoredCollapsed, type ThemeChoice, type AppView } from './preferences';
import { MAX_FILES, MAX_MEDIA_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, isImageFile, isMediaFile, fileToBase64 } from '../features/chat/attachments';
import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import '../shared/styles/styles.css';
import { DiagramContext } from "../features/diagrams/DiagramCard";
import { diagramBlocks } from "../features/diagrams/diagrams";
import { diagramPanel } from "../features/diagrams/diagramPanelLazy";
import LazyBoundary from "../shared/ui/LazyBoundary";
import { preloadable } from "../shared/ui/preloadable";
import { useLocalVoice } from "../features/companion/speech/LocalVoice";
import type { VoiceTab } from "../features/companion/speech/VoiceSettings";
import AgentConnectDialog, { forgetAgentCode, takeAgentCode } from "../features/settings/AgentConnectDialog";
import AccountMenu, { placeAccountMenu, type AccountMenuPlace } from "./AccountMenu";
import SettingsDialog, { CLOSED_SETTINGS, type SettingsSection, type SettingsView } from "../features/settings/SettingsDialog";
import { Segmented, SettingsGroup, SettingsIcon, SettingsRow } from "../features/settings/settingsUi";
import { useCharacters } from '../features/companion/characters/useCharacters';
const CharacterPicker = lazy(() => import('../features/companion/characters/CharacterPicker'));
import { readCharacterMotion, writeCharacterMotion, type CharacterMotion } from "../features/companion/characters/characterView";
import Composer from "../features/chat/Composer";
import TextEditDialog from '../shared/ui/TextEditDialog';
import HistorySearch from './HistorySearch';
import ConversationMenu from './ConversationMenu';
import DocumentWorkspace from '../features/documents/DocumentWorkspace';
import DocumentPanel, { RightPanelIcon, type DocumentPanelSelection } from '../features/documents/DocumentPanel';
import type { DocumentDraftRequest } from '../features/documents/documentApi';
import { takeConnectorResult } from '../features/connectors/connectorApi';
import { type DraftFile } from "../features/chat/files";
import { safeSources } from "../features/chat/WebSources";
import { closeWork } from "../features/chat/WorkTimeline";
import {
  UnauthorizedError,
  confirmRoleplayAge,
  deleteConversation,
  getAppInfo,
  getAuthState,
  getMessages,
  listConversations,
  updateConversation,
  logout,
  sendMessage,
  type AppInfo,
  type AuthState,
  type ChatAttachment,
  type Conversation,
  type Effort,
  type ImagineJob,
  type Message,
  type OutgoingAttachment,
  type Persona,
  type WebSearchMode,
  type WorkStep,
} from "../shared/api/api";

// Tạo ảnh, Companion và nội dung Cài đặt tải riêng lúc mở lần đầu: phần lớn lượt vào chỉ để chat, và tệp JS chính càng
// nhỏ thì điện thoại càng sớm thấy ô chat (đo ngày 2026-09-27). preload* gọi lúc rê chuột hay chạm vào nút mở.
const imagine = preloadable(() => import("../features/imagine/Imagine"));
const companion = preloadable(() => import("../features/companion/Companion"));
const profileSettings = preloadable(() => import("../features/settings/ProfileSettings"));
const voiceSettings = preloadable(() => import("../features/companion/speech/VoiceSettings"));
const memorySettings = preloadable(() => import("../features/settings/MemorySettings"));
const searchSettings = preloadable(() => import("../features/settings/SearchSettings"));
const agentSettings = preloadable(() => import("../features/settings/AgentSettings"));
const archiveSettings = preloadable(() => import("../features/settings/ArchivedConversations"));
const characterSettings = preloadable(() => import("../features/companion/characters/CharacterSettings"));
const connectorSettings = preloadable(() => import('../features/connectors/ConnectorSettings'));
const loadImagine = imagine.preload;
const loadCompanion = companion.preload;
const loadSettings = () => Promise.all([
  profileSettings.preload(), voiceSettings.preload(), memorySettings.preload(), searchSettings.preload(),
  agentSettings.preload(), characterSettings.preload(), archiveSettings.preload(), connectorSettings.preload(),
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
const ArchivedConversations = archiveSettings.View;
const CharacterSettings = characterSettings.View;
const ConnectorSettings = connectorSettings.View;

// Old messages keep their rendered Markdown while the draft or current reply changes.
export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  // Liên kết do peto login in ra mang ?agent_code=; mã được giữ qua lúc đăng nhập chuyển hướng.
  const [agentCode, setAgentCode] = useState<string | null>(takeAgentCode);
  const [connectorResult] = useState<string | null>(takeConnectorResult);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string|null>(null);
  const activeProjectRef = useRef(activeProjectId);
  activeProjectRef.current = activeProjectId;
  const [projectEdit, setProjectEdit] = useState<Project|'create'|null>(null);
  const [projectName, setProjectName] = useState('');
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState('');
  const [projectMenu, setProjectMenu] = useState<{item:Project;left:number;top:number}|null>(null);
  const [projectDelete, setProjectDelete] = useState<Project|null>(null);
  const [moveTarget, setMoveTarget] = useState<Conversation|null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [conversationMenu, setConversationMenu] = useState<{item:Conversation; left:number; top:number} | null>(null);
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
  const [renameText, setRenameText] = useState('');
  const [editTarget, setEditTarget] = useState<Message | null>(null);
  const [editText, setEditText] = useState('');
  const [retryAvailable, setRetryAvailable] = useState(false);
  const retryRevision = useRef<{ target: Message; text: string } | undefined>(undefined);
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;
  const [archived, setArchived] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [documentRequest, setDocumentRequest] = useState<DocumentDraftRequest | null>(null);
  const [documentSelection, setDocumentSelection] = useState<{ id: string; version: number; key: number } | null>(null);
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const [documentPanelOpen, setDocumentPanelOpen] = useState(false);
  const [documentPanelExpanded, setDocumentPanelExpanded] = useState(false);
  const [documentPreview, setDocumentPreview] = useState<DocumentPanelSelection | null>(null);
  const closeDocumentPanel = useCallback(() => { setDocumentPanelOpen(false); setDocumentPanelExpanded(false); }, []);
  // Sơ đồ đang mở ở bảng bên phải (mã Mermaid đã chuẩn hóa). Bảng sơ đồ và bảng tài liệu dùng chung chỗ bên phải, nên mở
  // bảng này thì đóng bảng kia.
  const [diagram, setDiagram] = useState<string | null>(null);
  const closeDiagram = useCallback(() => setDiagram(null), []);
  const diagramApi = useMemo(() => ({
    current: diagram,
    open: (code: string) => { setDocumentPanelOpen(false); setDocumentPanelExpanded(false); setDiagram(code); },
  }), [diagram]);
  const previewDocument = useCallback((item: { id: string; version: number }) => {
    setDocumentPreview({ id: item.id, version: item.version, key: Date.now() });
    setDiagram(null);
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
  useEffect(() => {
    if (auth?.authenticated && connectorResult) setSettings({ open: true, section: 'ket-noi', page: true });
  }, [auth?.authenticated, connectorResult]);
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
    setDiagram(null);
  }, [conversationId]);
  useEffect(() => {
    if (view !== 'chat') return;
    const shortcut = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && event.code === 'KeyB' && !document.querySelector('.document-workspace[open], .settings-dialog[open]')) {
        event.preventDefault(); setDocumentPanelOpen(value => !value); setDocumentPanelExpanded(false); setDiagram(null);
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

  usePreferencesPersistence({ effort, model, collapsed, theme });

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
    closeDocumentPanel(); setDocumentPreview(null); setDiagram(null);
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
    setActiveProjectId(null); setProjectEdit(null); setProjectDelete(null); setProjectMenu(null); setMoveTarget(null);setProjectError('');setProjectBusy(false);setMetadataBusy(false);
    setSearchOpen(false);
    setConversationMenu(null);
    setRenameTarget(null);
    setRenameText("");
    setEditTarget(null);
    setEditText("");
    setRetryAvailable(false);
    retryRevision.current = undefined;
    setConversationId(null);
    setArchived(false);
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

  const projectState = useProjects(auth?.authenticated ? auth.user?.id ?? 'authenticated' : null, handleUnauthorized);
  const refreshProjects = projectState.refresh;
  const refreshProjectChats = projectState.refreshChats;
  const refreshConversations = useCallback(async () => {
    const version = ++listVersion.current;
    setLoadingList(true);
    try {
      const all: Conversation[] = [];
      let more = true;
      while (more && all.length < listCount.current) {
        const page = await listConversations(all.length, 50, '', {unassigned:true});
        if (version !== listVersion.current) return;
        all.push(...page.conversations);
        more = page.has_more;
        if (!page.conversations.length) break;
      }
      setConversations(all);
      setHasMore(more);
      void refreshProjects();
      if (activeProjectRef.current) void refreshProjectChats(activeProjectRef.current);
    } catch (err) {
      if (version !== listVersion.current) return;
      if (err instanceof UnauthorizedError) handleUnauthorized();
      else setError("Không tải được danh sách hội thoại. Thử tải lại nhé.");
    } finally {
      if (version === listVersion.current) setLoadingList(false);
    }
  }, [handleUnauthorized,refreshProjects,refreshProjectChats]);

  const recovery = useReplyRecovery({
    scope: auth?.authenticated ? auth.user?.id ?? 'authenticated' : null,
    conversationId, enabled: Boolean(auth?.authenticated) && view === 'chat',
    busy: streaming || loadingConversation,
    onDisconnect: () => disconnectStream(abortRef.current),
    onUnauthorized: handleUnauthorized,
    onRecovered: (stored, complete) => {
      setMessages(stored);
      setError(null);
      setRetryAvailable(!complete);
      void refreshConversations();
    },
  });

  const allConversations = [...conversations,...projectState.projects.flatMap(project => projectState.chats[project.id]?.items ?? [])];
  const waitingForTitle = allConversations.some(item =>
    item.id === conversationId && (item.title_state === 'pending' ||
      (item.title_state === 'temporary' && (item.title_attempts || 0) < 3)));
  useEffect(() => {
    if (!auth?.authenticated || view !== 'chat' || streaming || !waitingForTitle) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const poll = async () => {
      try {
        const page = await listConversations(0,50,'',activeProjectId ? {projectId:activeProjectId} : {unassigned:true});
        if (cancelled) return;
        setConversations(current => current.map(item => {
          const fresh = page.conversations.find(row => row.id === item.id);
          return fresh ? { ...item, title: fresh.title, title_state: fresh.title_state, title_attempts: fresh.title_attempts } : item;
        }));
        if (activeProjectId) void refreshProjectChats(activeProjectId);
      } catch { /* A later refresh can recover; do not interrupt typing. */ }
      if (!cancelled && ++attempts < 12) timer = setTimeout(poll, 2500);
    };
    timer = setTimeout(poll, 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [auth?.user?.id, auth?.authenticated, view, conversationId, streaming, waitingForTitle,activeProjectId,refreshProjectChats]);

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
          setError(`Mỗi tin chỉ gửi tối đa ${MAX_MEDIA_FILES} ảnh, PDF, Word hoặc Excel`);
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

  // Cuộc trò chuyện còn trống thì lời chào và ô nhắn đứng chung giữa màn hình như
  // Claude; có tin nhắn là ô nhắn về đáy (CSS .chat.empty-state).
  const emptyChat = messages.length === 0 && !streaming && !loadingConversation && !loadFailed;
  // Các sơ đồ của hội thoại theo thứ tự, để bảng sơ đồ chuyển qua lại; tin đang viết dở chưa tính.
  const diagramCodes = useMemo(() => messages.flatMap((message, index) =>
    message.role === 'assistant' && !(streaming && index === messages.length - 1) ? diagramBlocks(message.content) : []),
  [messages, streaming]);
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
    return <LoadingIndicator variant="screen" label="Loading" />;
  }

  if (!auth.authenticated) {
    return <LoginScreen auth={auth} appInfo={appInfo} authError={authError} />;
  }

  async function openConversation(id: string) {
    if (abortRef.current || deleting) return;
    recovery.cancel();
    loadRef.current?.abort();
    const controller = new AbortController();
    loadRef.current = controller;
    const version = ++loadVersion.current;
    setError(null);
    setRetryAvailable(false);
    retryRevision.current = undefined;
    setNotice(null);
    setConversationId(id);
    setArchived(Boolean(allConversations.find(item => item.id === id)?.archived));

    setActiveProjectId(allConversations.find(item => item.id === id)?.project_id ?? null);
    go('chat');
    setEditTarget(null);
    setPersona(allConversations.find((item) => item.id === id)?.persona ?? "assistant");
    setMessages([]);
    setLoadingConversation(true);
    setLoadFailed(false);
    nearBottom.current = true;
    setShowJump(false);
    setSidebarOpen(false);
    try {
      const loaded = await getMessages(id, controller.signal, settings => {
        if (version !== loadVersion.current) return;
        setActiveProjectId(settings.project_id ?? null);
        setPersona(settings.persona ?? 'assistant');
        setArchived(Boolean(settings.archived));
      });
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
    recovery.cancel();
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
    setArchived(false);
    setActiveProjectId(null);
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
    const projectId = allConversations.find(item => item.id === id)?.project_id;
    setDeleting(true);
    try {
      await deleteConversation(id);
      if (id === conversationId) newConversation();
      setDeleteTarget(null);
      await refreshConversations();
      if (projectId && projectId !== activeProjectRef.current) void refreshProjectChats(projectId);
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
    if ((!text && !hasAttachments) || archived || abortRef.current || loadingConversation || loadFailed || !recovery.online || recovery.pending) return;

    const pending = revision ? [] : draftFiles;
    const previousMessages = messages;
    const revisionIndex = revision ? messages.findIndex(m => m.id === revision.target.id) : -1;
    if (revision && revisionIndex < 0) {
      setRetryAvailable(false);
      setError("Hãy mở lại cuộc trò chuyện trước khi sửa hoặc tạo lại câu trả lời này.");
      return;
    }
    const prefix = revision ? messages.slice(0, revisionIndex) : messages;
    recovery.cancel();
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

    const startedAt = performance.now();
    setMessages([
      ...prefix,
      { role: "user", content: text, attachments: revision?.target.attachments || optimistic },
      // Bước "chờ" chỉ có ở trình duyệt: bước đầu tiên máy chủ gửi thay nó.
      { role: "assistant", content: "", workStartedAt: startedAt,
        work: { ms: 0, steps: [{ id: 'wait', kind: 'wait', label: 'Đang gửi và chờ máy chủ…', state: 'live', start: 0 }] } },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    let activeId = conversationId;
    let accepted = false;
    let completed = false;
    let interrupted = false;
    // Máy chủ đã gửi bản chốt của nhật ký "Đang làm" (sự kiện "work").
    let finalWork = false;
    let storedUserId: number | undefined;
    const session = authVersion.current;

    // Câu trả lời đang viết luôn là tin cuối.
    const updateReply = (change: (last: Message) => Message) => {
      if (session !== authVersion.current) return;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        return last?.role === "assistant" ? [...prev.slice(0, -1), change(last)] : prev;
      });
    };
    // Bước tới sau khi bấm Dừng thì bỏ: nhật ký đã chốt ở lúc dừng.
    const updateSteps = (change: (steps: WorkStep[]) => WorkStep[]) => {
      if (controller.signal.aborted) return;
      updateReply(last => ({
        ...last, work: { ms: 0, ...last.work, steps: change((last.work?.steps ?? []).filter(step => step.kind !== 'wait')) },
      }));
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
          projectId:activeProjectId,
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
            storedUserId = storedMessage?.id;
            activeId = id;
            setConversationId(id);
            if (!revision) { setDraft(""); setDraftFiles([]); }
            if (storedMessage) retryRevision.current = {target:storedMessage, text:storedMessage.content};
            if (storedMessage) setMessages((prev) => [...prev.slice(0, -2), storedMessage, prev[prev.length - 1]]);
            // Máy chủ đã nhận tin: bước chờ (nếu chưa có bước nào thay) đổi chữ cho đúng.
            updateReply(last => last.work ? { ...last, work: { ...last.work, steps: last.work.steps.map(step =>
              step.kind === 'wait' ? { ...step, label: 'Đang chuẩn bị câu trả lời…' } : step) } } : last);
          },
          onDelta: (chunk) => updateReply(last => ({ ...last, content: last.content + chunk })),
          onReplace: (rest) => updateReply(last => ({ ...last, content: rest })),
          // Nhật ký "Đang làm" do máy chủ dựng (features/chat/work_log.py): mỗi bước tới là thêm hoặc thay theo id.
          onStep: (step) => updateSteps(steps => {
            const index = steps.findIndex(item => item.id === step.id);
            if (index < 0) return [...steps, step];
            const next = [...steps];
            next[index] = { ...step, summary: step.summary ?? steps[index].summary };
            return next;
          }),
          onThinking: (piece, id) => updateSteps(steps => steps.map(step => step.id === id ? { ...step, summary: (step.summary ?? '') + piece } : step)),
          onWork: (work) => {
            if (controller.signal.aborted) return;
            finalWork = true;
            updateReply(last => ({ ...last, work }));
          },
          onSources: (sources) => {
            if (!controller.signal.aborted) updateReply(last => ({ ...last, sources: safeSources(sources) }));
          },
          onArtifact: (artifact) => {
            if (controller.signal.aborted) return;
            // Peto sửa cùng một tệp vài lần trong một lượt: bản mới thay thẻ của bản trước ngay tại chỗ, như máy chủ lưu.
            updateReply(last => {
              const artifacts = [...(last.artifacts || [])];
              const index = artifacts.findIndex(item => item.id === artifact.id);
              if (index >= 0) artifacts[index] = artifact;
              else artifacts.push(artifact);
              return { ...last, artifacts };
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
        interrupted = true;
        const message = err instanceof Error ? err.message : "Mất kết nối tới máy chủ";
        setError(accepted ? message : `${message} Bản nháp được giữ lại; kiểm tra lịch sử trước khi gửi lại nếu kết nối bị ngắt.`);
        setRetryAvailable(true);
      }
    } finally {
      const stoppedByUser = controller.signal.aborted && !networkInterrupted(controller) && !completed;
      if (session === authVersion.current) {
        if (!accepted) setMessages(previousMessages);
        else {
          const elapsed = Math.round(performance.now() - startedAt);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role !== "assistant") return prev;
            const work = finalWork ? last.work : closeWork(last.work, completed, elapsed);
            // Máy chủ chỉ lưu câu trả lời có chữ hay có tệp. Lượt hỏng trước khi có chữ vẫn giữ bong bóng với nhật ký
            // ở trình duyệt, để thấy Peto đã thử gì (trước đây bong bóng biến mất, chỉ còn dòng báo lỗi). Lượt bị dừng
            // luôn giữ bong bóng, kể cả chưa có gì, để ghi "Đã dừng" ngay chỗ câu trả lời thay vì dòng báo trên ô nhắn.
            const stored = Boolean(last.content || last.artifacts?.length);
            if (!stored && !work?.steps.length && !stoppedByUser) return prev.slice(0, -1);
            return [...prev.slice(0, -1), { ...last, work, workStartedAt: undefined, local: stored ? undefined : true,
              status: completed ? "complete" : "incomplete", stopped: stoppedByUser || undefined }];
          });
        }
        // Dừng sau khi máy chủ đã nhận tin thì bong bóng tự ghi "Đã dừng"; chỉ lượt chưa kịp gửi mới cần dòng báo.
        if (stoppedByUser && !accepted) setNotice("Đã dừng gửi. Bản nháp vẫn được giữ lại.");
        if (activeId || !accepted) void refreshConversations();
        if (revision && accepted && activeId) {
          // Fetch stable IDs for edit/regenerate; preserve the local progress log.
          try {
            const stored = await getMessages(activeId);
            // Bong bóng chỉ có ở trình duyệt (lượt hỏng) không có trong danh sách đã lưu: bỏ qua khi khớp thứ tự.
            if (session === authVersion.current) setMessages(current => {
              let index = 0;
              return current.map(row => row.local ? row : { ...row, id: stored[index++]?.id });
            });
          } catch { setMessages(current => current.map(row => ({...row,id:undefined}))); }
        }
        if ((interrupted || networkInterrupted(controller)) && accepted && activeId && storedUserId !== undefined) {
          recovery.interrupt({ conversationId: activeId, userMessageId: storedUserId });
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

  async function changeConversation(item: Pick<Conversation, 'id' | 'project_id'>, change: {title?: string; pinned?: boolean; archived?: boolean}) {
    if (metadataBusy || (change.archived !== undefined && abortRef.current)) return;
    const session = authVersion.current;
    setMetadataBusy(true);
    try {
      await updateConversation(item.id, change);
      if (session !== authVersion.current) return;
      if (item.id === conversationIdRef.current && change.archived !== undefined) {
        if (change.archived) newConversation();
        else setArchived(false);
      }
      setRenameTarget(null);
      await refreshConversations();
      if (item.project_id && item.project_id !== activeProjectRef.current) void refreshProjectChats(item.project_id);
    } catch (err) {
      if (session !== authVersion.current) return;
      if (err instanceof UnauthorizedError) handleUnauthorized();
      else setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa lưu được thay đổi. Hãy thử lại.');
    } finally { if (session === authVersion.current) setMetadataBusy(false); }
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

  const canSend = (draft.trim().length > 0 || draftFiles.length > 0) && !streaming && !loadingConversation && !loadFailed && recovery.online && !recovery.pending;

  function menuPosition(rect:DOMRect) {return {left:Math.max(8,Math.min(rect.left,window.innerWidth-192)),top:Math.max(8,Math.min(rect.bottom+6,window.innerHeight-242))};}
  function newProjectChat(id:string) {
    if (abortRef.current || deleting) return;
    newConversation();setActiveProjectId(id);go('chat');setSidebarOpen(false);
    void refreshProjectChats(id);
  }
  async function saveProject() {
    if (!projectEdit || projectBusy) return;
    const session=authVersion.current;
    setProjectBusy(true);setProjectError('');
    try {
      if (projectName.trim().length>100) throw new Error('Tên dự án tối đa 100 ký tự.');
      if(projectEdit==='create') {const created=await createProject(projectName);if(session!==authVersion.current)return;newProjectChat(created.id);}
      else {await updateProject(projectEdit.id,{name:projectName});if(session!==authVersion.current)return;}
      setProjectEdit(null);await refreshProjects();
    } catch(err) {if(session===authVersion.current) {if(err instanceof UnauthorizedError)handleUnauthorized();else setProjectError(err instanceof Error ? err.message : 'Chưa lưu được dự án.');}}
    finally {if(session===authVersion.current)setProjectBusy(false);}
  }
  async function removeProject() {
    if(!projectDelete || projectBusy)return;
    const session=authVersion.current, id=projectDelete.id;
    setProjectBusy(true);setProjectError('');
    try {await deleteProject(id);if(session!==authVersion.current)return;if(activeProjectId===id)setActiveProjectId(null);setProjectDelete(null);await refreshConversations();}
    catch(err){if(session===authVersion.current){if(err instanceof UnauthorizedError)handleUnauthorized();else setProjectError(err instanceof Error ? err.message : 'Chưa xóa được dự án.');}}
    finally{if(session===authVersion.current)setProjectBusy(false);}
  }
  async function createProjectForMove(name:string):Promise<Project|null> {
    if (!moveTarget || metadataBusy) return null;
    const session=authVersion.current;
    setMetadataBusy(true);setProjectError('');
    try {
      const project=await createProject(name);
      if (session!==authVersion.current) return null;
      void refreshProjects();
      return project;
    } catch(err) {
      if(session===authVersion.current) {
        if(err instanceof UnauthorizedError)handleUnauthorized();
        else setProjectError(err instanceof Error ? err.message : 'Chưa tạo được dự án.');
      }
      return null;
    } finally {if(session===authVersion.current)setMetadataBusy(false);}
  }
  async function moveConversation(id:string|null) {
    if(!moveTarget || metadataBusy)return;
    const session=authVersion.current;
    setMetadataBusy(true);setProjectError('');
    try {await updateConversation(moveTarget.id,{project_id:id});if(session!==authVersion.current)return;if(conversationId===moveTarget.id){setActiveProjectId(id);}const old=moveTarget.project_id;setMoveTarget(null);await refreshConversations();if(old)void refreshProjectChats(old);if(id)void refreshProjectChats(id);}
    catch(err){if(session===authVersion.current){if(err instanceof UnauthorizedError)handleUnauthorized();else setProjectError(err instanceof Error ? err.message : 'Chưa chuyển được hội thoại.');}}
    finally{if(session===authVersion.current)setMetadataBusy(false);}
  }

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

  const settingsLoading = (
    <div className="settings-loading"><LoadingIndicator label="Đang tải cài đặt" /></div>
  );
  // Mỗi mục tải tệp riêng và có lớp chờ riêng: mục Giao diện không phải đợi tệp của mục Giọng nói.
  // `active`: mục đang được xem trong hộp đang mở; các mục chỉ tải dữ liệu lúc đó.
  const renderSettings = (section: SettingsSection, active: boolean): ReactNode => {
    switch (section) {
      case 'ket-noi':
        return <LazyBoundary><Suspense fallback={settingsLoading}>
          <ConnectorSettings key={auth.user?.id} open={active} result={connectorResult} onUnauthorized={handleUnauthorized} />
        </Suspense></LazyBoundary>;
      case 'luu-tru':
        return <LazyBoundary><Suspense fallback={settingsLoading}>
          <ArchivedConversations key={auth.user?.id} open={active} disabled={streaming || deleting || metadataBusy}
            onUnauthorized={handleUnauthorized} onOpen={id => {closeSettings(); void openConversation(id);}}
            onChanged={(item, deleted) => {
              if (item.id === conversationIdRef.current) {
                if (deleted) newConversation();
                else setArchived(false);
              }
              void refreshConversations();
              if (item.project_id && item.project_id !== activeProjectRef.current) void refreshProjectChats(item.project_id);
            }}/>
        </Suspense></LazyBoundary>;
      case "giao-dien":
        return (
          <SettingsGroup>
            <SettingsRow label="Chủ đề" desc="Nền sáng, nền tối, hoặc theo cài đặt của máy.">
              <Segmented label="Chủ đề" value={theme} options={THEMES} onChange={setTheme} />
            </SettingsRow>
          </SettingsGroup>
        );
      case "nhan-vat":
        return (
          <SettingsGroup>
            <LazyBoundary><Suspense fallback={settingsLoading}>
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
              avatarNote={`Theo tài khoản ${{ google: "Google", github: "GitHub", discord: "Discord" }[auth.user?.provider ?? "discord"]}`}
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
              desc="Thoát tài khoản trên trình duyệt này. Hội thoại vẫn còn khi bạn đăng nhập lại."
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
            <AgentSettings open={active} onUnauthorized={handleUnauthorized} />
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

      <Sidebar
        projects={<ProjectSidebar key={auth.user?.id} state={projectState} activeId={activeProjectId} conversationId={conversationId} disabled={streaming || deleting || projectBusy}
          onCreate={() => {setProjectEdit('create');setProjectName('');setProjectError('');}} onNewChat={newProjectChat} onChat={id => void openConversation(id)}
          onMenu={(item,rect) => setProjectMenu({item,...menuPosition(rect)})} onConversationMenu={(item,rect) => setConversationMenu({item,...menuPosition(rect)})}/>}
        sidebarOpen={sidebarOpen} collapsed={collapsed} streaming={streaming} deleting={deleting}
        appInfo={appInfo} auth={auth} view={view} imagineJobs={imagineJobs}
        conversations={conversations.filter(item => !item.project_id)} conversationId={conversationId} loadingList={loadingList} hasMore={hasMore}
        accountRef={accountRef} accountMenu={accountMenu} setSearchOpen={setSearchOpen}
        onToggleCollapsed={() => setCollapsed(value => !value)} goChat={goChat} go={go}
        preloadImagine={preload(loadImagine)} preloadCompanion={preload(loadCompanion)} preloadSettings={preload(loadSettings)}
        setSidebarOpen={setSidebarOpen} setSceneRequest={setSceneRequest} setCharacterPickerOpen={setCharacterPickerOpen}
        setFocusJobId={setFocusJobId} openConversation={openConversation} setConversationMenu={setConversationMenu}
        onLoadMore={() => { listCount.current = conversations.length + 50; void refreshConversations(); }}
        toggleAccountMenu={toggleAccountMenu}
      />

      {/* Imagine và Companion nằm cạnh nhau trong cùng một danh sách con, nên key phải khác nhau. Trùng
          key thì React nhân đôi tab, và mỗi bản Imagine mới lại tải danh sách ảnh, lặp mãi không dừng. */}
      {imageVisited && (
        <LazyBoundary>
        <Suspense fallback={view === "imagine" ? <LoadingIndicator variant="screen" label="Loading" /> : null}>
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
        <Suspense fallback={view === "companion" ? <LoadingIndicator variant="screen" label="Loading" /> : null}>
        <Companion
          key={`companion-${auth.user?.id}`}
          active={view === "companion"}
          appInfo={appInfo}
          voice={localVoice}
          sceneRequest={sceneRequest}
          characterMotion={characterMotion}
          character={characters.selected}
          characterLoading={characters.loading}
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
      <DiagramContext.Provider value={diagramApi}>
      <div className={`chat-layout${documentPanelOpen || diagram ? ' documents-open' : ''}${documentPanelOpen && documentPanelExpanded ? ' documents-expanded' : ''}`} hidden={view !== 'chat'}>
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
        {activeProjectId && <ProjectChatHeader name={projectState.projects.find(project=>project.id===activeProjectId)?.name}/>}
        <button type="button" className="artifact-icon document-panel-toggle" aria-label={documentPanelOpen ? 'Đóng bảng tài liệu' : 'Mở bảng tài liệu'} aria-expanded={documentPanelOpen} aria-controls="document-panel" title="Tài liệu · Ctrl+Alt+B" onClick={() => { setDocumentPanelOpen(value => !value); setDocumentPanelExpanded(false); setDiagram(null); }}><RightPanelIcon /></button>
        </div>

        <div className="messages" ref={messagesRef} onClick={e => {
          const button = (e.target as Element).closest<HTMLButtonElement>('button[data-revise]');
          if (!button || archived || streaming || loadingConversation) return;
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
          {loadingConversation && <div className="loading-chat"><LoadingIndicator label="Đang mở hội thoại" /></div>}
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

          {messages.map((message, index) => (
            <ChatMessage key={index} message={message}
              actionsDisabled={archived || streaming || loadingConversation || loadFailed}
              editor={editTarget?.id === message.id && editTarget ? <form className="inline-message-editor" onSubmit={e => {e.preventDefault(); void submit({target:editTarget,text:editText});}}>
                <textarea autoFocus aria-label="Sửa tin nhắn" value={editText} onChange={e => setEditText(e.target.value)} rows={Math.min(12,Math.max(3,editText.split('\n').length))} onKeyDown={e => {if(e.key==='Escape') setEditTarget(null);}}/>
                <div><button type="button" onClick={() => setEditTarget(null)}>Hủy</button><button type="submit" disabled={streaming || (!editText.trim() && !editTarget.attachments?.length)}>Gửi</button></div>
              </form> : undefined}
              live={streaming && !stopping && index === messages.length - 1}
              writing={streaming && index === messages.length - 1}
              // Lượt cuối bị dừng: "Thử lại" gửi lại câu hỏi ngay trong hội thoại này (máy chủ thay câu trả lời dở).
              onRetry={message.stopped && index === messages.length - 1 && messages[index - 1]?.role === 'user' && messages[index - 1]?.id
                ? () => void submit({ target: messages[index - 1], text: messages[index - 1].content }) : undefined}
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
        <ReplyRecoveryNotice recovery={recovery} />
        {error && !recovery.pending && recovery.status !== 'failed' && (
          <div className="error chat-error" role="alert">
            <span className="chat-error-message">{error}</span>
            {retryAvailable && <button type="button" className="chat-error-retry" disabled={streaming || loadingConversation} onClick={() => void submit(retryRevision.current)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 7a7 7 0 0 1 11.7-1.1L20 9M4 15l2.2 3.1A7 7 0 0 0 17.9 17"/></svg>
              Thử lại
            </button>}
            <button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => { setError(null); setRetryAvailable(false); }}>×</button>
          </div>
        )}

        {notice && <div className="error notice" role="status">
          {notice}
          <button type="button" className="dismiss-error" aria-label="Đóng thông báo trạng thái" onClick={() => setNotice(null)}>×</button>
        </div>}

        {archived ? <div className="archived-chat-notice" role="status">
          <span>Hội thoại đã lưu trữ</span>
          <button type="button" disabled={metadataBusy || loadingConversation || loadFailed} onClick={() => conversationId && void changeConversation({id:conversationId, project_id:activeProjectId}, {archived:false})}>Khôi phục để tiếp tục</button>
        </div> : <Composer
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
            unavailable: null,
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
        />}
        </div>
      </main>
      <DocumentPanel key={`${auth.user?.id}-${conversationId}`} conversationId={conversationId} open={documentPanelOpen && view === 'chat'} expanded={documentPanelExpanded} selection={documentPreview} refreshKey={documentRefresh} onClose={closeDocumentPanel} onExpand={() => setDocumentPanelExpanded(value => !value)} onEdit={item => setDocumentSelection({ ...item, key: Date.now() })} onUnauthorized={handleUnauthorized} />
      {diagram && view === 'chat' && (
        <LazyBoundary><Suspense fallback={null}>
          <diagramPanel.View codes={diagramCodes} current={diagram} onPick={setDiagram} onClose={closeDiagram} />
        </Suspense></LazyBoundary>
      )}
      </div>
      </DiagramContext.Provider>
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
      {agentCode && <AgentConnectDialog code={agentCode}
        onClose={() => { forgetAgentCode(); setAgentCode(null); }} onUnauthorized={handleUnauthorized} />}
      {renameTarget && <TextEditDialog title="Đổi tên hội thoại" value={renameText} onChange={setRenameText} busy={metadataBusy} onClose={() => setRenameTarget(null)} onSave={() => void changeConversation(renameTarget, {title:renameText})}/>}
      {searchOpen && <HistorySearch onClose={() => setSearchOpen(false)} onUnauthorized={handleUnauthorized} onSelect={id => {setSearchOpen(false); go('chat'); void openConversation(id);}}/>}
      {conversationMenu && <ConversationMenu left={conversationMenu.left} top={conversationMenu.top} onClose={() => setConversationMenu(null)}>
        <button onClick={() => {setRenameTarget(conversationMenu.item);setRenameText(conversationMenu.item.title);setConversationMenu(null);}}><EditIcon />Đổi tên</button>
        <button disabled={metadataBusy} onClick={() => {void changeConversation(conversationMenu.item,{pinned:!conversationMenu.item.pinned});setConversationMenu(null);}}><PinIcon />{conversationMenu.item.pinned ? 'Bỏ ghim' : 'Ghim'}</button>
        <button disabled={metadataBusy} onClick={()=>{setMoveTarget(conversationMenu.item);setProjectError('');setConversationMenu(null);void refreshProjects();}}><FolderIcon/>Chuyển vào dự án</button>
        <button disabled={metadataBusy || streaming || deleting} onClick={() => {void changeConversation(conversationMenu.item, {archived:true}); setConversationMenu(null);}}><SettingsIcon name="archive"/>Lưu trữ</button>
        <button className="danger-button" onClick={() => {setDeleteTarget(conversationMenu.item);setConversationMenu(null);}}>Xóa hội thoại</button>
      </ConversationMenu>}
      {projectMenu && <ConversationMenu label="Tùy chọn dự án" left={projectMenu.left} top={projectMenu.top} onClose={()=>setProjectMenu(null)}>
        <button onClick={()=>{setProjectEdit(projectMenu.item);setProjectName(projectMenu.item.name);setProjectError('');setProjectMenu(null);}}><EditIcon/>Đổi tên dự án</button>
        <button className="danger-button" onClick={()=>{setProjectDelete(projectMenu.item);setProjectError('');setProjectMenu(null);}}>Xóa dự án</button>
      </ConversationMenu>}
      {projectEdit && <><TextEditDialog title={projectEdit==='create' ? 'Tạo dự án' : 'Đổi tên dự án'} description={projectError || 'Gom hội thoại cùng một công việc.'} value={projectName} onChange={setProjectName} busy={projectBusy} onClose={()=>setProjectEdit(null)} onSave={()=>void saveProject()}/></>}
      {projectDelete && <ProjectConfirm title="Xóa dự án này?" busy={projectBusy} onClose={()=>setProjectDelete(null)} onConfirm={()=>void removeProject()}><p>“{projectDelete.name}” cùng hướng dẫn và tài liệu chung sẽ bị xóa. Các hội thoại được giữ và trở về Gần đây.</p>{projectError && <p role="alert">{projectError}</p>}</ProjectConfirm>}
      {moveTarget && <MoveConversationDialog item={moveTarget} projects={projectState.projects} busy={metadataBusy} error={projectError} loading={projectState.loading} loadError={projectState.error} onRetry={()=>void refreshProjects()} onCreate={createProjectForMove} onClose={()=>setMoveTarget(null)} onSave={id=>void moveConversation(id)}/>}
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
