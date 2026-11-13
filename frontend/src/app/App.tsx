import { usePreferencesPersistence } from './usePreferencesPersistence';
import LoginScreen from './LoginScreen';
import { forgetChatLogin, rememberChatLogin, takeChatLogin } from './chatLoginReturn';
import { BrowserRouter, useLocation, useNavigate } from 'react-router';
import { appPath, appView, chatId, chatRoute, companionSettingsPage, legacyPath, VIEW_PATHS } from './routes';
import Sidebar from './Sidebar';
import { useSidebarKeyboard } from './useSidebarKeyboard';
import { ChatReplyStatus } from '../features/chat/ChatReplyStatus';
import { useProjects } from '../features/projects/useProjects';
import ProjectSidebar from '../features/projects/ProjectSidebar';
import { projectActions, renderProjectDialogs, useProjectDialogs, type ProjectActionsContext } from '../features/projects/projectDialogs';
import ProjectChatHeader from '../features/projects/ProjectChatHeader';
import { ChatMessage } from '../features/chat/ChatMessage';
import { disconnectStream, useReplyRecovery } from '../features/chat/useReplyRecovery';
import { ReplyRecoveryNotice } from '../features/chat/ReplyRecoveryNotice';
import { Greeting } from '../features/chat/Greeting';
import { LoadingIndicator } from '../shared/ui/LoadingIndicator';
import { MenuIcon } from './navigationIcons';
import { PetoAvatar, AccountAvatar, accountSubtitle } from './accountUi';
import { EFFORTS, readStoredTheme, readStoredCollapsed, type ThemeChoice, type AppView } from './preferences';
import { isReducedMotion, readMotionChoice, type MotionChoice } from '../shared/motion';
import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import '../shared/styles/styles.css';
import { DiagramContext } from "../features/diagrams/DiagramCard";
import { diagramBlocks } from "../features/diagrams/diagrams";
import { diagramPanel } from "../features/diagrams/diagramPanelLazy";
import LazyBoundary from "../shared/ui/LazyBoundary";
import { loadCompanion, loadImagine, loadSettings, preload, usePreloadWhenIdle } from './lazyViews';
import AgentConnectDialog, { forgetAgentCode, takeAgentCode } from "../features/settings/AgentConnectDialog";
import AccountMenu from "./AccountMenu";
import SettingsDialog, { CLOSED_SETTINGS, type SettingsSection } from "../features/settings/SettingsDialog";
import { takeSettingsLink } from "../features/settings/settingsLink";
import { useCompanionShell } from './useCompanionShell';
import { useSearchShortcut } from './useSearchShortcut';
import { useSettingsMenu } from './useSettingsMenu';
import Composer from "../features/chat/Composer";
import ChatFileDropZone from '../features/chat/ChatFileDropZone';
import { useChatDrafts } from '../features/chat/useChatDrafts';
import { useChatPanels } from '../features/chat/useChatPanels';
import { useComposerDock } from '../features/chat/useComposerDock';
import { useDraftFileActions } from '../features/chat/useDraftFileActions';
import { editDraftNotice, useEditDraftCheck, type EditDraftNoticeContext } from '../features/chat/useEditDraftCheck';
import { CHAT_SELECTION_ERROR, useChatSelection } from '../features/chat/useChatSelection';
import { newChatContext, type NewChatContext } from '../features/chat/chatDrafts';
import { renderConversationDialogs, renderFeatureViews } from './appViews';
import { useConversationList, useRefreshConversations, useTitlePolling } from './useConversationList';
import { renderAppSettings, type AppSettingsContext } from './appSettings';
import DocumentWorkspace from '../features/documents/DocumentWorkspace';
import DocumentPanel, { RightPanelIcon } from '../features/documents/DocumentPanel';
import { takeConnectorResult } from '../features/connectors/connectorApi';
import SourcesPanel from '../features/chat/SourcesPanel';
import { sendChatTurn, stopChatTurn, type ActiveReply, type ChatRevision, type ChatTurnContext, type StopTicket } from '../features/chat/chatTurn';
import { QuoteSelection } from '../features/chat/QuotedFollowup';
import { validReplyVariants } from '../features/chat/replyVariants';
import type { DraftQuote } from '../features/chat/chatDrafts';
import TooltipLayer from '../shared/ui/TooltipLayer';
import {
  UnauthorizedError,
  deleteConversation,
  getAppInfo,
  getAuthState,
  getMessages,
  updateConversation,
  logout,
  type AppInfo,
  type AuthState,
  type Conversation,
  type ImagineJob,
  type Message,
  type ReplyVariant,
  type ReplyVariants,
  type WebSearchMode,
} from "../shared/api/api";


// Old messages keep their rendered Markdown while the draft or current reply changes.
export default function App() {
  // Đồng bộ URL cùng state của tab; các animation hiện có vẫn do component quản lý.
  return <BrowserRouter useTransitions={false}><AppContent /></BrowserRouter>;
}

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
  const view = appView(appPath(location));
  // Đang ở /companion/settings/…: tab vẫn là Companion (thanh bên sáng mục Companion), nhưng sân khấu nhường chỗ cho trang cài đặt.
  const companionSettingsView = view === 'companion' ? companionSettingsPage(appPath(location)) : null;
  const routedConversationId = chatId(location.pathname);
  const viewRef = useRef(view);
  viewRef.current = view;
  // URL cũ đổi ngay trên entry hiện tại; không dựng lại các tab khi đổi địa chỉ.
  useLayoutEffect(() => {
    const path = legacyPath(location);
    if (path) navigate({ pathname: path, search: window.location.search }, { replace: true, state: location.state });
  }, [location, navigate]);
  const [auth, setAuth] = useState<AuthState | null>(null);
  const authChecked = useRef(false);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  // Liên kết do peto login in ra mang ?agent_code=; mã được giữ qua lúc đăng nhập chuyển hướng.
  const [agentCode, setAgentCode] = useState<string | null>(takeAgentCode);
  const [connectorResult] = useState<string | null>(takeConnectorResult);
  // Liên kết ?settings=<mục> (Peto Agent bản desktop mở ?settings=agent): mở Cài đặt ở mục đó sau khi vào app.
  const [settingsLink, setSettingsLink] = useState<SettingsSection | null>(takeSettingsLink);

  const conversationList = useConversationList();
  const { conversations, hasMore, loadingList, listCount, resetList } = conversationList;
  const [activeProjectId, setActiveProjectId] = useState<string|null>(null);
  const activeProjectRef = useRef(activeProjectId);
  activeProjectRef.current = activeProjectId;
  const projectDialogs = useProjectDialogs();
  const { projectBusy, setProjectEdit, setProjectName, setProjectError, setProjectMenu, setMoveTarget, reset: resetProjectDialogs } = projectDialogs;
  const [searchOpen, setSearchOpen] = useState(false);
  const [conversationMenu, setConversationMenu] = useState<{item:Conversation; left:number; top:number} | null>(null);
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
  const [renameText, setRenameText] = useState('');
  const [editTarget, setEditTarget] = useState<Message | null>(null);
  const [editText, setEditText] = useState('');
  const [retryAvailable, setRetryAvailable] = useState(false);
  const retryRevision = useRef<ChatRevision | undefined>(undefined);
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;
  const [archived, setArchived] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const messageRowsRef = useRef(messages);
  messageRowsRef.current = messages;
  const submitRevisionRef = useRef<((revision: ChatRevision) => Promise<void>) | null>(null);
  const { sourcesIndex, setSourcesIndex, closeSources, openSources, documentRequest, documentSelection, setDocumentSelection,
    documentRefresh, setDocumentRefresh, documentPanelOpen, documentPanelExpanded, setDocumentPanelExpanded, documentPreview,
    setDocumentPreview, closeDocumentPanel, toggleDocumentPanel, diagram, setDiagram, closeDiagram, diagramApi, previewDocument,
    editDocument, resetPanels } = useChatPanels(view, conversationId);
  const [webSearch, setWebSearch] = useState<WebSearchMode>("auto");

  const [streaming, setStreaming] = useState(false);
  // Một luồng đang chạy giữ tin riêng khi Back mở hội thoại khác; không hủy yêu cầu AI.
  const replyRef = useRef<ActiveReply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  useSidebarKeyboard(sidebarOpen, sidebarRef, closeSidebar);
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Hội thoại nhập vai cũ đang mở: chế độ nhập vai bỏ ngày 2026-10-18, các hội thoại ấy chỉ còn để xem.
  const [legacyRoleplay, setLegacyRoleplay] = useState(false);
  const readOnly = archived || legacyRoleplay;
  const replyVisible = streaming && Boolean(replyRef.current && isSelectedReply(replyRef.current));
  const rootContext = newChatContext(location.state, auth?.user?.id ?? '');
  const draftConversationId = view === 'chat' ? routedConversationId : conversationId;
  const { draft, setDraft, draftFiles, setDraftFiles, draftQuote, setDraftQuote, editDrafts, saveEdit, resolveEdit,
    snapshotDraft, acceptDraft, clearDrafts,
    removeConversationDraft, removeProjectDraft } = useChatDrafts(auth?.authenticated && auth.user ? {
      ownerId: auth.user.id, conversationId: draftConversationId,
      projectId: view === 'chat' && !routedConversationId ? rootContext.projectId : activeProjectId,
    } : null, authChecked.current ? auth?.authenticated : undefined);
  const latestEdit = editDrafts.at(-1);
  const [showJump, setShowJump] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>(readStoredTheme);
  const [motion, setMotion] = useState<MotionChoice>(readMotionChoice);
  const { characterMotion, changeCharacterMotion, characters, characterIds, sceneRequest, playerRequest, setPlayerRequest,
    companionVisited, setCompanionVisited, localVoice, openHearingSettings, openCompanionSettings, openCompanionCards, openCharacters,
    openScenes, openPlayer } = useCompanionShell(view, navigate, companionSettingsView);
  const { settings, setSettings, settingsOpen, closeSettings, accountMenu, setAccountMenu, accountRef, closeAccountMenu, dropAccountMenu,
    toggleAccountMenu, openFromAccountMenu } = useSettingsMenu(auth?.authenticated, connectorResult, settingsLink, setSettingsLink,
    setSidebarOpen);
  const [imageVisited, setImageVisited] = useState(view === "imagine");
  useEffect(() => {
    if (view === 'imagine') setImageVisited(true);
    if (view === 'companion') setCompanionVisited(true);
    setSidebarOpen(false);
  }, [view]);
  useSearchShortcut(streaming, setSearchOpen);
  // Bản sao chỉ để vẽ cột trái; Imagine.tsx mới là nơi tạo, xóa và giữ danh sách.
  const [imagineJobs, setImagineJobs] = useState<ImagineJob[]>([]);
  const [imagineLibraryRequest, setImagineLibraryRequest] = useState(0);
  const [focusJobId, setFocusJobId] = useState<string | null>(null);
  const clearFocusJob = useCallback(() => setFocusJobId(null), []);

  const abortRef = useRef<AbortController | null>(null);
  const stopTicketRef = useRef<StopTicket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const loadRef = useRef<AbortController | null>(null);
  const loadVersion = useRef(0);
  const nearBottom = useRef(true);
  const messagesRef = useRef<HTMLDivElement>(null);
  const pendingMessageFocus = useRef<{ conversationId: string; messageId: number } | null>(null);
  const messageFocusTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const jumpToMessage = useCallback((id: number) => {
    if (!Number.isSafeInteger(id) || id <= 0) return;
    const target = messagesRef.current?.querySelector<HTMLElement>(`article[data-message-id="${id}"]`);
    if (!target) return;
    nearBottom.current = false;
    setShowJump(true); setSourcesIndex(null);
    target.scrollIntoView({ block: 'center', behavior: isReducedMotion() ? 'instant' : 'smooth' });
    target.tabIndex = -1; target.focus({ preventScroll: true });
    messagesRef.current?.querySelectorAll('.quote-target-highlight').forEach(node => node.classList.remove('quote-target-highlight'));
    target.classList.add('quote-target-highlight');
    clearTimeout(messageFocusTimer.current);
    messageFocusTimer.current = setTimeout(() => target.classList.remove('quote-target-highlight'), 1400);
  }, []);
  useEffect(() => () => clearTimeout(messageFocusTimer.current), []);
  const navigationBusy = useRef(false);
  navigationBusy.current = readOnly || streaming || loadingConversation || loadFailed || deleting;
  const openReplyVariant = useCallback((choice: ReplyVariant | undefined) => {
    if (!choice || navigationBusy.current) return;
    pendingMessageFocus.current = { conversationId: choice.conversation_id, messageId: choice.message_id };
    setSourcesIndex(null);
    navigate({ pathname: chatRoute(choice.conversation_id), search: window.location.search });
  }, [navigate]);
  const regenerateAnswer = useCallback((id: number) => {
    if (navigationBusy.current) return;
    const rows = messageRowsRef.current, index = rows.findIndex(row => row.id === id && row.role === 'assistant');
    const user = rows[index - 1];
    const answer = rows[index];
    if (index < 1 || !answer || answer.local || answer.stopped || answer.status === 'incomplete'
      || (answer.turn_state && answer.turn_state !== 'complete') || user?.role !== 'user' || !user.id) return;
    void submitRevisionRef.current?.({ target: user, text: user.content });
  }, []);
  const variantControls = useRef(new WeakMap<ReplyVariants, { index: number; count: number; onPrevious: () => void; onNext: () => void }>());
  const selectQuotedText = useCallback((quote: DraftQuote) => {
    if (navigationBusy.current || !messageRowsRef.current.some(row => row.id === quote.message_id && row.role === 'assistant'
      && !row.local && !row.stopped && row.status !== 'incomplete' && (!row.turn_state || row.turn_state === 'complete'))) return;
    setDraftQuote(quote);
    textareaRef.current?.focus({ preventScroll: true });
  }, [setDraftQuote]);
  const cancelEdit = () => {
    const id = editTarget?.id;
    setEditTarget(null);
    requestAnimationFrame(() => messagesRef.current?.querySelector<HTMLButtonElement>(`button[data-revise="${id}"]`)?.focus({ preventScroll: true }));
  };
  const deleteDialogRef = useRef<HTMLDialogElement>(null);
  const authVersion = useRef(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const message = params.get("auth_error");
    if (message) {
      setAuthError(message);
      params.delete('auth_error');
      navigate({ pathname: appPath(location), search: params.toString(), hash: legacyPath(location) ? '' : location.hash },
        { replace: true, state: location.state });
    }
  }, []);

  useEffect(() => {
    void getAuthState()
      .then(value => { authChecked.current = true; setAuth(value); })
      .catch(() => setAuth({ authenticated: false, login_configured: false }));
  }, []);

  // Avatar và tên lấy từ Discord application. Hỏng thì giữ chữ cái đầu, không
  // để ảnh hưởng tới việc đăng nhập hay chat.
  useEffect(() => {
    void getAppInfo()
      .then(setAppInfo)
      .catch(() => setAppInfo(null));
  }, []);

  usePreferencesPersistence({ collapsed, theme, motion });

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      loadRef.current?.abort();
    };
  }, []);

  /** Phiên hết hạn giữa chừng: quay về màn hình đăng nhập thay vì báo lỗi lạ. */
  const handleUnauthorized = useCallback(() => {
    authChecked.current = true;
    setPlayerRequest(0);
    resetPanels();
    authVersion.current += 1;
    loadVersion.current += 1;
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
    resetList();
    setActiveProjectId(null); resetProjectDialogs(); setMetadataBusy(false);
    setSearchOpen(false);
    setConversationMenu(null);
    setRenameTarget(null);
    setRenameText("");
    setEditTarget(null);
    setEditText("");
    setRetryAvailable(false);
    retryRevision.current = undefined;
    setConversationId(null);
    conversationIdRef.current = null;
    replyRef.current = null;
    setArchived(false);
    clearDrafts();
    setNotice(null);
    setWebSearch("auto");
    setLegacyRoleplay(false);
    setLoadingConversation(false);
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
    setAuthError("Phiên đăng nhập đã hết hạn hoặc tài khoản không còn được cho phép.");
  }, [clearDrafts, resetProjectDialogs, resetPanels, resetList]);

  const chatSelection = useChatSelection(auth?.authenticated ? auth.user?.id ?? 'authenticated' : null,
    auth?.user?.models ?? [], handleUnauthorized,
    message => setError(previous => message ?? (previous === CHAT_SELECTION_ERROR ? null : previous)),
    setNotice, view === 'chat' && !streaming && !loadingConversation && !loadFailed);
  const { model, effort, setModel, setEffort } = chatSelection;
  const projectState = useProjects(auth?.authenticated ? auth.user?.id ?? 'authenticated' : null, handleUnauthorized);
  const refreshProjects = projectState.refresh;
  const refreshProjectChats = projectState.refreshChats;
  const refreshConversations = useRefreshConversations(conversationList, { handleUnauthorized, refreshProjects, refreshProjectChats,
    activeProjectRef, setError });

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

  const { editCheck, canResumeEdit, checkAgain } = useEditDraftCheck({ latestEdit, routedConversationId, conversationId, view, auth,
    recovery, streaming, loadingConversation, editTarget, resolveEdit, navigate, refreshConversations, handleUnauthorized, authVersion,
    conversationIdRef, viewRef, setArchived, setActiveProjectId, setLegacyRoleplay, setMessages, setLoadFailed, setError });

  const allConversations = [...conversations,...projectState.projects.flatMap(project => projectState.chats[project.id]?.items ?? [])];
  const waitingForTitle = allConversations.some(item =>
    item.id === conversationId && (item.title_state === 'pending' ||
      (item.title_state === 'temporary' && (item.title_attempts || 0) < 3)));
  useTitlePolling(conversationList, { authenticated: auth?.authenticated, userId: auth?.user?.id, view, conversationId, streaming,
    waitingForTitle, activeProjectId, refreshProjectChats, refreshConversations });

  usePreloadWhenIdle(auth?.authenticated);

  useEffect(() => {
    if (nearBottom.current) bottomRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
    else setShowJump(true);
  }, [messages, streaming]);
  useLayoutEffect(() => {
    const pending = pendingMessageFocus.current;
    if (!pending || loadingConversation || pending.conversationId !== conversationId) return;
    if (messages.some(message => message.id === pending.messageId)) {
      pendingMessageFocus.current = null;
      jumpToMessage(pending.messageId);
    }
  }, [messages, loadingConversation, conversationId, jumpToMessage]);

  useEffect(() => {
    if (deleteTarget) deleteDialogRef.current?.showModal();
    else deleteDialogRef.current?.close();
  }, [deleteTarget]);

  const { addFiles, removeDraftFile } = useDraftFileActions(setDraftFiles, abortRef, setError);

  // Cuộc trò chuyện còn trống thì lời chào và ô nhắn đứng chung giữa màn hình như
  // Claude; có tin nhắn là ô nhắn về đáy (CSS .chat.empty-state).
  const emptyChat = messages.length === 0 && !replyVisible && !loadingConversation && !loadFailed;
  // Các sơ đồ của hội thoại theo thứ tự, để bảng sơ đồ chuyển qua lại; tin đang viết dở chưa tính.
  const diagramCodes = useMemo(() => messages.flatMap((message, index) =>
    message.role === 'assistant' && !(replyVisible && index === messages.length - 1) ? diagramBlocks(message.content) : []),
  [messages, replyVisible]);
  const models = auth?.user?.models ?? [];
  const chosenModel = models.some((item) => item.key === model) ? model : "peto";
  const supportedEfforts = models.find(item => item.key === chosenModel)?.efforts ?? ['low', 'medium', 'high'];
  const effortOptions = EFFORTS.filter(item => item.value === 'auto' || supportedEfforts.includes(item.value));
  const effectiveEffort = effortOptions.some(item => item.value === effort) ? effort : 'auto';

  const { composerRef, chatDockRef, composerBoxRef, composerFrom } = useComposerDock(emptyChat, auth?.authenticated, view);

  // /admin chỉ dành cho chủ web; tài khoản khác gõ thẳng địa chỉ thì về trang chủ (API cũng trả 404 cho họ).
  useEffect(() => {
    if (auth?.authenticated && view === 'admin' && !auth.user?.is_owner) navigate('/', { replace: true });
  }, [auth?.authenticated, auth?.user?.is_owner, view, navigate]);
  const leaveAdmin = useCallback(() => navigate('/', { replace: true }), [navigate]);

  // Callback đăng nhập về trang chủ thì mở lại bookmark chat đã yêu cầu.
  useEffect(() => {
    if (!auth?.authenticated) return;
    const path = takeChatLogin();
    if (path && window.location.pathname === '/') navigate(path, { replace: true });
  }, [auth?.authenticated, navigate]);

  // URL quyết định hội thoại cần mở. Quay lại cùng chat từ tab khác giữ nguyên tin và nháp.
  useLayoutEffect(() => {
    if (!auth?.authenticated || view !== 'chat') return;
    if (routedConversationId) {
      if (routedConversationId !== conversationIdRef.current) void loadConversation(routedConversationId);
    }
    else if (conversationIdRef.current !== null || activeProjectId !== rootContext.projectId) {
      newConversation(true);
    }
  }, [auth?.authenticated, auth?.user?.id, view, routedConversationId, location.key]);

  if (auth === null) {
    return <LoadingIndicator variant="screen" label="Loading" />;
  }

  if (!auth.authenticated) {
    return <LoginScreen auth={auth} appInfo={appInfo} authError={authError} onSignIn={rememberChatLogin} />;
  }

  async function openConversation(id: string) {
    if (abortRef.current || deleting) return;
    setSidebarOpen(false);
    if (chatId(window.location.pathname) === id && view === 'chat') {
      if (loadFailed) await loadConversation(id);
      return;
    }
    navigate({ pathname: chatRoute(id), search: window.location.search });
  }

  function restoreReply(live: ActiveReply) {
    chatSelection.restore(live.id, live.selection);
    setMessages(live.messages);
    setLegacyRoleplay(false);
    setActiveProjectId(live.projectId);
    retryRevision.current = live.retry;
    setError(live.error ?? null);
    setRetryAvailable(Boolean(live.error));
  }

  function isSelectedReply(reply: ActiveReply) {
    return conversationIdRef.current === reply.id && (reply.id !== null || activeProjectRef.current === reply.projectId);
  }

  async function loadConversation(id: string) {
    if (pendingMessageFocus.current?.conversationId !== id) pendingMessageFocus.current = null;
    setSourcesIndex(null);
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
    conversationIdRef.current = id;
    chatSelection.restore(id);
    setArchived(Boolean(allConversations.find(item => item.id === id)?.archived));

    setActiveProjectId(allConversations.find(item => item.id === id)?.project_id ?? null);
    setEditTarget(null);
    setLegacyRoleplay(allConversations.find((item) => item.id === id)?.persona === "roleplay");
    setMessages([]);
    setLoadingConversation(true);
    setLoadFailed(false);
    nearBottom.current = true;
    setShowJump(false);
    setSidebarOpen(false);
    try {
      const live = replyRef.current;
      if (abortRef.current && live?.id === id) {
        restoreReply(live);
        return;
      }
      await chatSelection.waitForSave(id);
      if (version !== loadVersion.current) return;
      const loaded = await getMessages(id, controller.signal, settings => {
        if (version !== loadVersion.current) return;
        setActiveProjectId(settings.project_id ?? null);
        setLegacyRoleplay(settings.persona === 'roleplay');
        setArchived(Boolean(settings.archived));
        chatSelection.restore(id, settings);
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

  function draftContextState(projectId: string | null) {
    const context: NewChatContext = { ownerId: auth?.user?.id ?? '', projectId };
    return { ...location.state, chatDraftContext: context };
  }

  function newConversation(fromRoute = false, projectId: string | null = null) {
    if (!fromRoute && abortRef.current) return;
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
    conversationIdRef.current = null;
    chatSelection.restore(null);
    setArchived(false);
    const context = fromRoute ? rootContext : { projectId };
    setActiveProjectId(context.projectId);
    setLegacyRoleplay(false);
    setMessages([]);
    setError(null);
    setNotice(null);
    setSidebarOpen(false);
    const live = replyRef.current;
    if (fromRoute && abortRef.current && live?.id === null
      && context.projectId === live.projectId) restoreReply(live);
    if (!fromRoute) navigate({ pathname: '/', search: window.location.search },
      { replace: window.location.pathname === '/', state: draftContextState(projectId) });
    textareaRef.current?.focus();
  }

  async function removeConversation(id: string) {
    if (abortRef.current || deleting) return;
    const session = authVersion.current;
    const projectId = allConversations.find(item => item.id === id)?.project_id;
    setDeleting(true);
    try {
      await deleteConversation(id);
      if (session !== authVersion.current) return;
      removeConversationDraft(id);
      if (id === conversationIdRef.current) newConversation();
      setDeleteTarget(null);
      await refreshConversations();
      if (projectId && projectId !== activeProjectRef.current) void refreshProjectChats(projectId);
    } catch (err) {
      if (session !== authVersion.current) return;
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setError(err instanceof Error ? err.message : "Không xóa được");
      setDeleteTarget(null);
    } finally {
      if (session === authVersion.current) setDeleting(false);
    }
  }


  function openEditor(target: Message) {
    const saved = editDrafts.find(edit => edit.messageId === target.id);
    if (saved && !canResumeEdit(saved)) {
      if (saved !== latestEdit) saveEdit(saved);
      return;
    }
    setEditTarget(target);
    setEditText(saved?.text ?? target.content);
  }

  const noticeContext: EditDraftNoticeContext = { messages, loadingConversation, deleting, recovery, loadFailed, readOnly,
    loadConversation, openEditor, resolveEdit, canResumeEdit, editCheck, checkAgain };

  const turn: ChatTurnContext = {
    abortRef, acceptDraft, activeProjectId, authVersion, canResumeEdit, chatSelection, chosenModel,
    composerBoxRef, composerFrom, conversationId, conversationIdRef, draft, draftFiles, editDrafts, effectiveEffort,
    emptyChat, handleUnauthorized, isSelectedReply, loadFailed, loadingConversation, messages, navigate, nearBottom,
    readOnly, recovery, refreshConversations, replyRef, resolveEdit, retryRevision, saveEdit, setConversationId,
    setDocumentRefresh, setEditTarget, setError, setMessages, setNotice, setRetryAvailable, setShowJump,
    setSourcesIndex, setStopping, setStreaming, snapshotDraft, stopTicketRef, textareaRef, viewRef, webSearch,
  };
  const submit = (revision?: ChatRevision) => sendChatTurn(turn, revision);
  const stop = () => stopChatTurn(turn);

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
      // URL chat/ảnh thuộc tài khoản vừa thoát. Để nguyên thì bấm đăng nhập sẽ ghi nhớ nó làm đích quay về, và
      // tài khoản khác đăng nhập vào gặp "Không tìm thấy hội thoại" (chủ web gặp khi đổi Google ↔ Discord, 2026-10-11).
      // Hết phiên giữa chừng (handleUnauthorized riêng) vẫn giữ URL để đăng nhập lại đúng chỗ.
      forgetChatLogin();
      navigate('/', { replace: true });
    } catch {
      setError("Chưa đăng xuất được. Thử lại nhé.");
    }
  }

  submitRevisionRef.current = submit;
  function replyControls(message: Message) {
    const family = validReplyVariants(message.reply_variants, conversationId, message.id);
    if (!family) return undefined;
    let controls = variantControls.current.get(family);
    if (!controls) {
      controls = {
        index: family.index, count: family.choices.length,
        onPrevious: () => openReplyVariant(family.choices[family.index - 1]),
        onNext: () => openReplyVariant(family.choices[family.index + 1]),
      };
      variantControls.current.set(family, controls);
    }
    return controls;
  }
  const canSend = (draft.trim().length > 0 || draftFiles.length > 0) && !streaming && !loadingConversation && !loadFailed && recovery.online && !recovery.pending;

  // Chừa đủ chỗ cho menu rộng 196px và cao tối đa ~250px (mục 44px trên màn cảm ứng), cách mép 8px.
  function menuPosition(rect:DOMRect) {return {left:Math.max(8,Math.min(rect.left,window.innerWidth-204)),top:Math.max(8,Math.min(rect.bottom+6,window.innerHeight-262))};}
  const projectContext: ProjectActionsContext = {
    dialogs: projectDialogs, authVersion, handleUnauthorized, abortRef, deleting, newConversation, setSidebarOpen, refreshProjects,
    refreshProjectChats, refreshConversations, removeProjectDraft, activeProjectId, setActiveProjectId, conversationId, navigate,
    draftContextState, metadataBusy, setMetadataBusy,
  };
  const projectHandlers = projectActions(projectContext);
  const { newProjectChat } = projectHandlers;

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
    setSidebarOpen(false);
    // Từ trang cài đặt Companion, bấm Companion trên thanh bên là về sân khấu.
    if (next === 'companion' && companionSettingsView) navigate(VIEW_PATHS.companion);
    else if (next !== view) navigate({ pathname: next === 'chat' && conversationIdRef.current
      ? chatRoute(conversationIdRef.current) : VIEW_PATHS[next], search: window.location.search },
      { state: draftContextState(activeProjectId) });
  }

  const settingsContext: AppSettingsContext = {
    auth, connectorResult, handleUnauthorized, streaming, deleting, metadataBusy, closeSettings, openConversation,
    removeConversationDraft, conversationIdRef, newConversation, setArchived, refreshConversations, activeProjectRef,
    refreshProjectChats, theme, setTheme, motion, setMotion, setAuth, signOut,
  };
  const renderSettings = (section: SettingsSection, active: boolean) => renderAppSettings(section, active, settingsContext);

  return (
    <div className="app">
      {view === 'chat' && !readOnly && <button className="chat-skip" type="button" onClick={() => textareaRef.current?.focus({ preventScroll: true })}>Đến ô nhắn</button>}
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
        sidebarRef={sidebarRef} sidebarOpen={sidebarOpen} collapsed={collapsed} streaming={streaming} deleting={deleting}
        appInfo={appInfo} auth={auth} view={view} imagineJobs={imagineJobs}
        conversations={conversations.filter(item => !item.project_id)} conversationId={conversationId} loadingList={loadingList} hasMore={hasMore}
        accountRef={accountRef} accountMenu={accountMenu} setSearchOpen={setSearchOpen}
        onToggleCollapsed={() => setCollapsed(value => !value)} onCollapsedChange={setCollapsed} goChat={goChat} go={go}
        preloadImagine={preload(loadImagine)} preloadCompanion={preload(loadCompanion)} preloadSettings={preload(loadSettings)}
        setSidebarOpen={setSidebarOpen} onOpenScenes={openScenes} onOpenCharacters={openCharacters} onOpenPlayer={openPlayer}
        setFocusJobId={setFocusJobId} openConversation={openConversation} setConversationMenu={setConversationMenu}
        onOpenImagineLibrary={() => { setSidebarOpen(false); setImagineLibraryRequest(value => value + 1); }}
        onLoadMore={() => { listCount.current = conversations.length + 50; void refreshConversations(); }}
        toggleAccountMenu={toggleAccountMenu}
      />

      {/* Key nằm ở lớp bọc ngoài cùng để thêm một tab đã ghé không khiến tab bên cạnh bị dựng lại. */}
      {renderFeatureViews({ imageVisited, view, auth, handleUnauthorized, setSidebarOpen, setImagineJobs, imagineLibraryRequest, focusJobId,
        clearFocusJob, companionVisited, companionSettingsView, appInfo, localVoice, sceneRequest, playerRequest, characterMotion,
        characters, characterIds, openCharacters, openHearingSettings, openCompanionSettings, openCompanionCards, location, navigate,
        changeCharacterMotion, leaveAdmin })}
      <DiagramContext.Provider value={diagramApi}>
      <ChatFileDropZone className={`chat-layout${documentPanelOpen || diagram ? ' documents-open' : ''}${documentPanelOpen && documentPanelExpanded ? ' documents-expanded' : ''}${sourcesIndex !== null ? ' sources-open' : ''}`} hidden={view !== 'chat'}
        enabled={!streaming && !loadingConversation && !loadFailed && !readOnly && !deleting && !settingsOpen && !searchOpen}
        contextKey={JSON.stringify([auth.user?.id, draftConversationId, rootContext.projectId])}
        onFiles={addFiles}>
      <main className={emptyChat ? "chat empty-state" : "chat"} aria-label="Trò chuyện với Peto">
        <ChatReplyStatus busy={replyVisible} stopping={stopping} scope={JSON.stringify([auth.user?.id, conversationId])} last={messages.at(-1)} />
        <div className="chat-tools">
        <button
          type="button"
          className="menu-btn chat-menu"
          aria-label="Mở danh sách hội thoại"
          aria-expanded={sidebarOpen} aria-controls="peto-sidebar"
          onClick={() => setSidebarOpen(true)}
        >
          <MenuIcon />
        </button>
        {activeProjectId && <ProjectChatHeader name={projectState.projects.find(project=>project.id===activeProjectId)?.name}/>}
        <button type="button" className="artifact-icon document-panel-toggle" aria-label={documentPanelOpen ? 'Đóng bảng tài liệu' : 'Mở bảng tài liệu'} aria-expanded={documentPanelOpen} aria-controls="document-panel" data-tip="Tài liệu" data-tip-kbd="Ctrl+Alt+B" aria-keyshortcuts="Control+Alt+B" onClick={toggleDocumentPanel}><RightPanelIcon /></button>
        </div>

        <div className="messages" role="region" aria-label="Nội dung hội thoại" tabIndex={0} ref={messagesRef} onClick={e => {
          const button = (e.target as Element).closest<HTMLButtonElement>('button[data-revise]');
          if (!button || readOnly || streaming || loadingConversation) return;
          const id = Number(button.dataset.revise);
          const target = messages.find(m => m.id === id && m.role === 'user');
          if (!target) return;
          openEditor(target);
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
              onRegenerate={regenerateAnswer} variants={replyControls(message)} onJumpQuote={jumpToMessage}
              sourcesExpanded={sourcesIndex === index} onOpenSources={openSources} sourceIndex={index}
              actionsDisabled={readOnly || streaming || loadingConversation || loadFailed}
              editor={editTarget?.id === message.id && editTarget ? <form className="inline-message-editor" onSubmit={e => {e.preventDefault(); void submit({target:editTarget,text:editText,inlineEdit:true});}}>
                <textarea autoFocus aria-label="Sửa tin nhắn" value={editText} onChange={e => setEditText(e.target.value)} rows={Math.min(12,Math.max(3,editText.split('\n').length))} onKeyDown={e => {if(e.key==='Escape') { e.preventDefault(); cancelEdit(); }}}/>
                <div><button type="button" onClick={cancelEdit}>Hủy</button><button type="submit" disabled={streaming || (!editText.trim() && !editTarget.attachments?.length)}>Gửi</button></div>
              </form> : undefined}
              live={replyVisible && !stopping && index === messages.length - 1}
              writing={replyVisible && index === messages.length - 1}
              // Lượt cuối đã dừng/hỏng và được lưu: chỉ thử lại khi người dùng bấm, bằng request ID mới.
              onRetry={(message.stopped || (message.id && message.status === 'incomplete' && message.turn_state !== 'running'))
                && index === messages.length - 1 && messages[index - 1]?.role === 'user' && messages[index - 1]?.id
                ? () => void submit({ target: messages[index - 1], text: messages[index - 1].content }) : undefined}
              onPreview={previewDocument} onEdit={editDocument} />
          ))}
          <div ref={bottomRef} />
          <QuoteSelection key={`${auth.user?.id}:${conversationId}`} containerRef={messagesRef}
            disabled={view !== 'chat' || readOnly || streaming || loadingConversation || loadFailed || settingsOpen || searchOpen || Boolean(editTarget) || !recovery.online || recovery.pending}
            onQuote={selectQuotedText} />
        </div>

        {showJump && <button type="button" className="jump-latest" aria-label="Tin mới nhất" data-tip onClick={event => {
          nearBottom.current = true;
          setShowJump(false);
          bottomRef.current?.scrollIntoView({ behavior: event.detail === 0 || isReducedMotion() ? 'instant' : 'smooth', block: "end" });
          if (event.detail === 0) messagesRef.current?.focus({ preventScroll: true });
        }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 4v16m-7-7 7 7 7-7" /></svg></button>}

        <div className="chat-dock" ref={chatDockRef}>
        <ReplyRecoveryNotice recovery={recovery} />
        {latestEdit && draftConversationId && !streaming && editTarget?.id !== latestEdit.messageId
          && editDraftNotice(latestEdit, draftConversationId, noticeContext)}
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
        </div> : legacyRoleplay ? <div className="archived-chat-notice" role="status">
          <span>Hội thoại nhập vai cũ chỉ còn để xem</span>
          <button type="button" disabled={streaming} onClick={() => newConversation()}>Bắt đầu hội thoại mới</button>
        </div> : <Composer
          contextKey={JSON.stringify([auth.user?.id, draftConversationId, rootContext.projectId])}
          quote={draftQuote} onRemoveQuote={() => setDraftQuote(null)} onJumpQuote={jumpToMessage}
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
          menuDisabled={streaming || loadingConversation || loadFailed || view !== "chat"}
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
      {sourcesIndex !== null && messages[sourcesIndex]?.role === 'assistant' && view === 'chat' ? (
        <SourcesPanel key={`${conversationId}-${sourcesIndex}`} sources={messages[sourcesIndex].sources}
          web={messages[sourcesIndex].work?.web} onClose={closeSources} />
      ) : null}
      <DocumentPanel key={`${auth.user?.id}-${conversationId}`} conversationId={conversationId} open={documentPanelOpen && view === 'chat'} expanded={documentPanelExpanded} selection={documentPreview} refreshKey={documentRefresh} onClose={closeDocumentPanel} onExpand={() => setDocumentPanelExpanded(value => !value)} onEdit={item => setDocumentSelection({ ...item, key: Date.now() })} onUnauthorized={handleUnauthorized} />
      {diagram && view === 'chat' && (
        <LazyBoundary><Suspense fallback={null}>
          <diagramPanel.View codes={diagramCodes} current={diagram} onPick={setDiagram} onClose={closeDiagram} />
        </Suspense></LazyBoundary>
      )}
      </ChatFileDropZone>
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
          onOpenAdmin={auth.user?.is_owner ? () => { closeAccountMenu(false); go('admin'); } : undefined}
          onSignOut={() => {
            closeAccountMenu(false);
            setSidebarOpen(false);
            void signOut();
          }}
        />
      )}
      <SettingsDialog view={settings} onView={setSettings} onClose={closeSettings} render={renderSettings} />
      {agentCode && <AgentConnectDialog code={agentCode}
        onClose={() => { forgetAgentCode(); setAgentCode(null); }} onUnauthorized={handleUnauthorized} />}
      {renderConversationDialogs({ renameTarget, renameText, setRenameText, metadataBusy, setRenameTarget, changeConversation, searchOpen,
        auth, setSearchOpen, handleUnauthorized, openConversation, conversationMenu, setConversationMenu, setMoveTarget, setProjectError,
        refreshProjects, streaming, deleting, setDeleteTarget, deleteDialogRef, deleteTarget, removeConversation },
        renderProjectDialogs(projectContext, projectHandlers, { projectState }))}
      <TooltipLayer />
    </div>
  );
}
