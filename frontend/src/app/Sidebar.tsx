import type { Dispatch, Ref, SetStateAction, ReactNode } from 'react';
import type { AppInfo, AuthState, Conversation, ImagineJob } from '../shared/api/api';
import type { AccountMenuPlace } from './AccountMenu';
import type { AppView } from './preferences';
import { PetoAvatar, AccountAvatar, accountSubtitle } from './accountUi';
import { SearchIcon, SidebarIcon, ComposeIcon, ImageIcon, CompanionIcon } from './navigationIcons';

type SidebarProps = {
  projects: ReactNode;
  sidebarOpen: boolean; collapsed: boolean; streaming: boolean; deleting: boolean;
  appInfo: AppInfo | null; auth: AuthState; view: AppView;
  imagineJobs: ImagineJob[]; conversations: Conversation[]; conversationId: string | null;
  loadingList: boolean; hasMore: boolean;
  accountRef: Ref<HTMLButtonElement>; accountMenu: AccountMenuPlace | null;
  setSearchOpen: (open: boolean) => void; onToggleCollapsed: () => void;
  goChat: () => void; go: (view: AppView) => void;
  preloadImagine: () => void; preloadCompanion: () => void; preloadSettings: () => void;
  setSidebarOpen: (open: boolean) => void; setSceneRequest: Dispatch<SetStateAction<number>>;
  setCharacterPickerOpen: (open: boolean) => void; setFocusJobId: (id: string) => void;
  openConversation: (id: string) => Promise<void>;
  setConversationMenu: (menu: {item: Conversation; left: number; top: number}) => void;
  onLoadMore: () => void; toggleAccountMenu: () => void;
};

export default function Sidebar({
  projects,
  sidebarOpen, collapsed, streaming, deleting, appInfo, auth, view, imagineJobs,
  conversations, conversationId, loadingList, hasMore, accountRef, accountMenu,
  setSearchOpen, onToggleCollapsed, goChat, go, preloadImagine, preloadCompanion,
  preloadSettings, setSidebarOpen, setSceneRequest, setCharacterPickerOpen,
  setFocusJobId, openConversation, setConversationMenu, onLoadMore, toggleAccountMenu,
}: SidebarProps) {
  return (
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
            onClick={() => onToggleCollapsed()}
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
            onPointerEnter={preloadImagine}
            onFocus={preloadImagine}
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
            onPointerEnter={preloadCompanion}
            onFocus={preloadCompanion}
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
        <div className="sidebar-section sidebar-history">
        {projects}
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
                <button type="button" aria-label={`Tùy chọn ${conversation.title}`} title="Tùy chọn hội thoại" disabled={streaming || deleting} onClick={e => { const r=e.currentTarget.getBoundingClientRect(); setConversationMenu({item:conversation,left:Math.max(8,Math.min(r.left,window.innerWidth-192)),top:Math.max(8,Math.min(r.bottom+6,window.innerHeight-208))}); }}>⋯</button>
              </div>
            </div>
          ))}
          {loadingList && <p className="empty-hint" role="status">Đang tải danh sách…</p>}
          {hasMore && <button className="load-more" disabled={loadingList || streaming} onClick={() => {
            onLoadMore();
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
            onPointerEnter={preloadSettings}
            onFocus={preloadSettings}
          >
            <AccountAvatar user={auth.user} size={24} />
            <span className="account-name">
              <strong>{auth.user?.display_name}</strong>{" "}
              <span>{accountSubtitle(auth.user)}</span>
            </span>
          </button>
        </div>
      </aside>
  );
}
