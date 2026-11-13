import { useEffect } from 'react';
import { preloadable } from '../shared/ui/preloadable';

// Tạo ảnh, Companion và nội dung Cài đặt tải riêng lúc mở lần đầu: phần lớn lượt vào chỉ để chat, và tệp JS chính càng
// nhỏ thì điện thoại càng sớm thấy ô chat (đo ngày 2026-09-27). preload* gọi lúc rê chuột hay chạm vào nút mở.
const imagine = preloadable(() => import('../features/imagine/Imagine'));
const companion = preloadable(() => import('../features/companion/Companion'));
// Trang cài đặt riêng của Companion (/companion/settings/, chủ web chốt ngày 13/10/2026); hộp Cài đặt chung không còn
// nhóm Companion.
const companionSettings = preloadable(() => import('../features/companion/settings/CompanionSettings'));
const profileSettings = preloadable(() => import('../features/settings/ProfileSettings'));
const memorySettings = preloadable(() => import('../features/settings/MemorySettings'));
const agentSettings = preloadable(() => import('../features/settings/AgentSettings'));
const archiveSettings = preloadable(() => import('../features/settings/ArchivedConversations'));
const connectorSettings = preloadable(() => import('../features/connectors/ConnectorSettings'));
// Trang Quản trị chỉ chủ web mở; tải riêng nên người dùng thường không phải tải mã biểu đồ.
const adminDashboard = preloadable(() => import('../features/admin/AdminDashboard'));

export const AdminDashboard = adminDashboard.View;
export const loadImagine = imagine.preload;
export const loadCompanion = companion.preload;
export const loadSettings = () => Promise.all([
  profileSettings.preload(), memorySettings.preload(), agentSettings.preload(), archiveSettings.preload(), connectorSettings.preload(),
]);
// Tải trước: lỗi ở đây bỏ qua, lần mở thật sẽ tải lại và LazyBoundary lo phần báo lỗi.
export const preload = (load: () => Promise<unknown>) => () => void load().catch(() => {});
export const Imagine = imagine.View;
export const Companion = companion.View;
export const CompanionSettings = companionSettings.View;
export const ProfileSettings = profileSettings.View;
export const MemorySettings = memorySettings.View;
export const AgentSettings = agentSettings.View;
export const ArchivedConversations = archiveSettings.View;
export const ConnectorSettings = connectorSettings.View;

/** Ô chat đã hiện thì lúc rảnh tải sẵn Tạo ảnh, Companion và Cài đặt: lần mở đầu khỏi chờ tệp (khoảng 0,3 giây trên 4G
 * chậm, đo ngày 2026-09-27). Bỏ qua khi người dùng bật tiết kiệm dữ liệu hay mạng chỉ 2G. */
export function usePreloadWhenIdle(authenticated: boolean | undefined) {
  useEffect(() => {
    if (!authenticated) return;
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || /2g/.test(connection?.effectiveType ?? '')) return;
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
  }, [authenticated]);
}
