import { Suspense, type Dispatch, type ReactNode, type RefObject, type SetStateAction } from 'react';
import type { Location, NavigateFunction } from 'react-router';
import { FolderIcon } from '../features/projects/ProjectSidebar';
import { SettingsIcon } from '../features/settings/settingsUi';
import type { AppInfo, AuthState, Conversation, ImagineJob } from '../shared/api/api';
import { EditIcon } from '../shared/ui/EditIcon';
import LazyBoundary from '../shared/ui/LazyBoundary';
import { LoadingIndicator } from '../shared/ui/LoadingIndicator';
import TextEditDialog from '../shared/ui/TextEditDialog';
import ConversationMenu from './ConversationMenu';
import HistorySearch from './HistorySearch';
import { AdminDashboard, Companion, CompanionSettings, Imagine } from './lazyViews';
import { PinIcon } from './navigationIcons';
import type { AppView } from './preferences';
import { appPath, companionCardId, companionCardRoute, companionProviderId, companionProviderRoute, companionSettingsRoute,
  VIEW_PATHS, type CompanionSettingsPage } from './routes';
import type { useCompanionShell } from './useCompanionShell';

// Các tab tải lười (Tạo ảnh, Companion, trang cài đặt Companion, Quản trị) và các hộp thoại của hội thoại. Tách khỏi
// App.tsx (G3.3, 13/11/2026): vẫn là hàm vẽ chứ không phải component, nên cây React giữ nguyên.

type SetState<T> = Dispatch<SetStateAction<T>>;
type Shell = ReturnType<typeof useCompanionShell>;
export type FeatureViewsContext = Pick<Shell, 'companionVisited' | 'localVoice' | 'sceneRequest' | 'playerRequest' | 'characterMotion'
  | 'characters' | 'characterIds' | 'openCharacters' | 'openHearingSettings' | 'openCompanionSettings' | 'openCompanionCards'
  | 'changeCharacterMotion'> & {
  imageVisited: boolean;
  view: AppView;
  auth: AuthState;
  appInfo: AppInfo | null;
  companionSettingsView: CompanionSettingsPage | null;
  handleUnauthorized: () => void;
  setSidebarOpen: SetState<boolean>;
  setImagineJobs: SetState<ImagineJob[]>;
  imagineLibraryRequest: number;
  focusJobId: string | null;
  clearFocusJob: () => void;
  location: Location;
  navigate: NavigateFunction;
  leaveAdmin: () => void;
};

type ConversationChange = { title?: string; pinned?: boolean; archived?: boolean };
export type ConversationDialogsContext = {
  renameTarget: Conversation | null;
  renameText: string;
  setRenameText: (value: string) => void;
  setRenameTarget: SetState<Conversation | null>;
  metadataBusy: boolean;
  changeConversation: (item: Pick<Conversation, 'id' | 'project_id'>, change: ConversationChange) => Promise<void>;
  searchOpen: boolean;
  setSearchOpen: SetState<boolean>;
  auth: AuthState;
  handleUnauthorized: () => void;
  openConversation: (id: string) => Promise<void>;
  conversationMenu: { item: Conversation; left: number; top: number } | null;
  setConversationMenu: SetState<{ item: Conversation; left: number; top: number } | null>;
  setMoveTarget: SetState<Conversation | null>;
  setProjectError: SetState<string>;
  refreshProjects: () => Promise<unknown>;
  streaming: boolean;
  deleting: boolean;
  setDeleteTarget: SetState<Conversation | null>;
  deleteDialogRef: RefObject<HTMLDialogElement | null>;
  deleteTarget: Conversation | null;
  removeConversation: (id: string) => Promise<void>;
};

export function renderFeatureViews(ctx: FeatureViewsContext) {
  const { imageVisited, view, auth, handleUnauthorized, setSidebarOpen, setImagineJobs, imagineLibraryRequest,
    focusJobId, clearFocusJob, companionVisited, companionSettingsView, appInfo, localVoice, sceneRequest,
    playerRequest, characterMotion, characters, characterIds, openCharacters, openHearingSettings,
    openCompanionSettings, openCompanionCards, location, navigate, changeCharacterMotion, leaveAdmin } = ctx;
  return <>
  {(imageVisited || view === 'imagine') && (
    <LazyBoundary key={`imagine-${auth.user?.id}`}>
    <Suspense fallback={view === "imagine" ? <LoadingIndicator variant="screen" label="Loading" /> : null}>
    <Imagine
      key={`imagine-${auth.user?.id}`}
      active={view === "imagine"}
      onUnauthorized={handleUnauthorized}
      onOpenSidebar={() => setSidebarOpen(true)}
      onJobsChange={setImagineJobs}
      libraryRequest={imagineLibraryRequest}
      focusJobId={focusJobId}
      onFocusHandled={clearFocusJob}
    />
    </Suspense>
    </LazyBoundary>
  )}
  {(companionVisited || view === 'companion') && (
    <LazyBoundary key={`companion-${auth.user?.id}`}>
    <Suspense fallback={view === "companion" ? <LoadingIndicator variant="screen" label="Loading" /> : null}>
    <Companion
      key={`companion-${auth.user?.id}`}
      ownerId={auth.user?.id}
      active={view === "companion" && !companionSettingsView}
      appInfo={appInfo}
      voice={localVoice}
      sceneRequest={sceneRequest}
      playerRequest={playerRequest}
      characterMotion={characterMotion}
      character={characters.selected}
      characterLoading={characters.loading}
      characterIds={characterIds}
      onSelectCharacter={characters.select}
      onCharacterPreview={characters.savePreview}
      onOpenCharacters={openCharacters}
      onUnauthorized={handleUnauthorized}
      onOpenSidebar={() => setSidebarOpen(true)}
      onOpenHearingSettings={openHearingSettings}
      onOpenSettings={openCompanionSettings}
      onOpenCards={openCompanionCards}
    />
    </Suspense>
    </LazyBoundary>
  )}
  {companionSettingsView && (
    <LazyBoundary key={`companion-settings-${auth.user?.id}`}>
    <Suspense fallback={<LoadingIndicator variant="screen" label="Loading" />}>
    <CompanionSettings
      key={`companion-settings-${auth.user?.id}`}
      page={companionSettingsView}
      providerId={companionProviderId(appPath(location))}
      cardId={companionCardId(appPath(location))}
      ownerId={auth.user?.id}
      onNavigate={(page, id) => navigate(page === 'provider' ? companionProviderRoute(id ?? '')
        : page === 'card' || page === 'card-edit' ? companionCardRoute(id ?? '', page === 'card-edit')
        : companionSettingsRoute(page))}
      onExit={() => navigate(VIEW_PATHS.companion)}
      voice={localVoice}
      library={characters}
      motion={characterMotion}
      onMotionChange={changeCharacterMotion}
      fallbackUrl={appInfo?.avatar_url ?? undefined}
      onUnauthorized={handleUnauthorized}
    />
    </Suspense>
    </LazyBoundary>
  )}
  {view === 'admin' && auth.user?.is_owner && (
    <LazyBoundary key={`admin-${auth.user?.id}`}>
    <Suspense fallback={<LoadingIndicator variant="screen" label="Loading" />}>
    <AdminDashboard onUnauthorized={handleUnauthorized} onForbidden={leaveAdmin} onOpenSidebar={() => setSidebarOpen(true)} />
    </Suspense>
    </LazyBoundary>
  )}
  </>;
}

/** Hộp đổi tên, tìm hội thoại, menu của một hội thoại, các hộp dự án (truyền vào) và hộp xác nhận xóa. */
export function renderConversationDialogs(ctx: ConversationDialogsContext, projectDialogs: ReactNode) {
  const { renameTarget, renameText, setRenameText, metadataBusy, setRenameTarget, changeConversation, searchOpen,
    auth, setSearchOpen, handleUnauthorized, openConversation, conversationMenu, setConversationMenu, setMoveTarget,
    setProjectError, refreshProjects, streaming, deleting, setDeleteTarget, deleteDialogRef, deleteTarget,
    removeConversation } = ctx;
  return <>
  {renameTarget && <TextEditDialog title="Đổi tên hội thoại" value={renameText} onChange={setRenameText} busy={metadataBusy} onClose={() => setRenameTarget(null)} onSave={() => void changeConversation(renameTarget, {title:renameText})}/>}
  {searchOpen && <HistorySearch key={`history-search:${auth.user?.id ?? 'anonymous'}`} onClose={() => setSearchOpen(false)} onUnauthorized={handleUnauthorized} onSelect={id => {setSearchOpen(false); void openConversation(id);}}/>}
  {conversationMenu && <ConversationMenu left={conversationMenu.left} top={conversationMenu.top} onClose={() => setConversationMenu(null)}>
    <button onClick={() => {setRenameTarget(conversationMenu.item);setRenameText(conversationMenu.item.title);setConversationMenu(null);}}><EditIcon />Đổi tên</button>
    <button disabled={metadataBusy} onClick={() => {void changeConversation(conversationMenu.item,{pinned:!conversationMenu.item.pinned});setConversationMenu(null);}}><PinIcon />{conversationMenu.item.pinned ? 'Bỏ ghim' : 'Ghim'}</button>
    <button disabled={metadataBusy} onClick={()=>{setMoveTarget(conversationMenu.item);setProjectError('');setConversationMenu(null);void refreshProjects();}}><FolderIcon/>Chuyển vào dự án</button>
    <button disabled={metadataBusy || streaming || deleting} onClick={() => {void changeConversation(conversationMenu.item, {archived:true}); setConversationMenu(null);}}><SettingsIcon name="archive"/>Lưu trữ</button>
    <div className="popup-menu-sep" role="separator" />
    <button className="danger-button" onClick={() => {setDeleteTarget(conversationMenu.item);setConversationMenu(null);}}><SettingsIcon name="trash"/>Xóa hội thoại</button>
  </ConversationMenu>}
  {projectDialogs}
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
  </>;
}
