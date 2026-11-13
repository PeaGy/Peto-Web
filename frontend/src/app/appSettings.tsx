import { Suspense, type Dispatch, type ReactNode, type RefObject, type SetStateAction } from 'react';
import DiscordMemorySettings from '../features/settings/DiscordMemorySettings';
import type { SettingsSection } from '../features/settings/SettingsDialog';
import { Segmented, SettingsGroup, SettingsIcon, SettingsRow } from '../features/settings/settingsUi';
import type { AuthState } from '../shared/api/api';
import type { MotionChoice } from '../shared/motion';
import LazyBoundary from '../shared/ui/LazyBoundary';
import { LoadingIndicator } from '../shared/ui/LoadingIndicator';
import { AccountAvatar, accountLine } from './accountUi';
import { AgentSettings, ArchivedConversations, ConnectorSettings, MemorySettings, ProfileSettings } from './lazyViews';
import { MOTIONS, THEMES, type ThemeChoice } from './preferences';

// Nội dung từng mục của hộp Cài đặt chung. Tách khỏi App.tsx (G3.3, 13/11/2026): vẫn là hàm vẽ, không phải component,
// nên cây React giữ nguyên như trước.

export type AppSettingsContext = {
  auth: AuthState;
  connectorResult: string | null;
  handleUnauthorized: () => void;
  streaming: boolean;
  deleting: boolean;
  metadataBusy: boolean;
  closeSettings: () => void;
  openConversation: (id: string) => Promise<void>;
  removeConversationDraft: (id: string) => void;
  conversationIdRef: RefObject<string | null>;
  newConversation: () => void;
  setArchived: Dispatch<SetStateAction<boolean>>;
  refreshConversations: () => Promise<void>;
  activeProjectRef: RefObject<string | null>;
  refreshProjectChats: (id: string) => unknown;
  theme: ThemeChoice;
  setTheme: (value: ThemeChoice) => void;
  motion: MotionChoice;
  setMotion: (value: MotionChoice) => void;
  setAuth: Dispatch<SetStateAction<AuthState | null>>;
  signOut: () => Promise<void>;
};

const settingsLoading = (
  <div className="settings-loading"><LoadingIndicator label="Đang tải cài đặt" /></div>
);
// Mỗi mục tải tệp riêng và có lớp chờ riêng: mục Giao diện không phải đợi tệp của mục Giọng nói.
// `active`: mục đang được xem trong hộp đang mở; các mục chỉ tải dữ liệu lúc đó.
export function renderAppSettings(section: SettingsSection, active: boolean, ctx: AppSettingsContext): ReactNode {
  const { auth, connectorResult, handleUnauthorized, streaming, deleting, metadataBusy, closeSettings, openConversation, removeConversationDraft,
    conversationIdRef, newConversation, setArchived, refreshConversations, activeProjectRef, refreshProjectChats, theme, setTheme, motion, setMotion, setAuth, signOut } = ctx;
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
            if (deleted) removeConversationDraft(item.id);
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
          <SettingsRow label="Chuyển động"
            desc="Hiệu ứng khi mở menu, chuyển trang, hiện câu trả lời và các phần khác. Mượt thì luôn có hiệu ứng, kể cả khi thiết bị bật giảm chuyển động.">
            <Segmented label="Chuyển động" value={motion} options={MOTIONS} onChange={setMotion} />
          </SettingsRow>
        </SettingsGroup>
      );
    case "ho-so":
      return (
        <LazyBoundary><Suspense fallback={settingsLoading}>
          <ProfileSettings
            key={auth.user?.id}
            open={active}
            avatar={<AccountAvatar user={auth.user} size={48} />}
            customAvatar={auth.user?.custom_avatar}
            onAvatarChanged={avatar => setAuth(prev => prev?.user ? { ...prev, user: { ...prev.user, ...avatar } } : prev)}
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
          {auth.user?.provider === 'discord' && <DiscordMemorySettings key={`discord-memory:${auth.user.id}`} open={active} onUnauthorized={handleUnauthorized} />}
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
    case "tri-nho":
      return (
        <LazyBoundary><Suspense fallback={settingsLoading}>
          <MemorySettings open={active} onUnauthorized={handleUnauthorized} />
        </Suspense></LazyBoundary>
      );
  }
}
