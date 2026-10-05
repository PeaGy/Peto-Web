export type Role = "user" | "assistant";
export type Effort = "auto" | "none" | "low" | "medium" | "high" | "xhigh" | "max";
export type WebSearchMode = "auto" | "on" | "off";
/** Tab gửi tin: Companion có persona trả lời ngắn bằng tiếng Anh và mạch trò chuyện riêng. */
export type ConversationMode = "chat" | "companion";
export interface WebSource { url: string; title: string; kind?: 'citation' | 'result' }
export interface DocumentArtifact {
  id: string; title: string; filename: string; version: number;
  format: 'docx' | 'pdf' | 'pptx' | 'xlsx'; style: 'report' | 'essay' | 'clean' | 'academic' | 'bold' | 'sheet' | 'workbook'; pages: number;
  /** Tệp Excel người dùng gửi mà Peto đã sửa (style 'workbook'): các dòng thay đổi, như 'Lương'!A9:F9: ghi 6 ô. Máy chủ
   * chỉ gửi 20 dòng đầu; ``change_count`` là tổng số dòng, gồm cả các lần sửa trước của tệp này trong cùng lượt. */
  changes?: string[];
  change_count?: number;
}

export interface ChatAttachment {
  id: string;
  name: string;
  mime: string;
  kind: "image" | "file";
  size: number;
  url: string;
  document?: {
    status: "ready" | "partial" | "no_text" | "encrypted" | "unreadable" | "timeout";
    notice: string;
    characters: number;
    pages?: number;
    pages_processed?: number;
      pages_read?: number;
      ocr_pages?: number;
      reading_method?: "text" | "ocr" | "mixed";
      /** Bảng tính Excel: số trang tính, số trang tính đã đọc, số hàng có dữ liệu. */
      sheets?: number;
      sheets_read?: number;
      rows?: number;
  } | null;
}

export interface OutgoingAttachment {
  name: string;
  mime: string;
  data: string;
}

export interface EmotionCue { emotion: string; offset: number }

export interface Message {
  id?: number;
  role: Role;
  content: string;
  status?: "complete" | "incomplete";
  created_at?: number;
  attachments?: ChatAttachment[];
  sources?: WebSource[];
  artifacts?: DocumentArtifact[];
  /** Nhật ký "Đang làm" (features/chat/work_log.py): máy chủ gửi từng bước khi đang trả lời, lưu cùng câu trả lời. */
  work?: WorkLog;
  /** Mốc performance.now() lúc gửi, cho đồng hồ chạy khi câu trả lời còn đang viết. */
  workStartedAt?: number;
  /** Bong bóng chỉ có ở trình duyệt (lượt hỏng trước khi có chữ, máy chủ không lưu): giữ lại để thấy Peto đã thử gì. */
  local?: boolean;
  /** Cảm xúc Peto tự chọn cho câu trả lời Companion (emotion_tags.py), để nghe lại tin cũ thì nhân vật làm đúng mặt. */
  emotion?: string | null;
  /** Cảm xúc của câu ở vị trí 0; tin cũ có thể còn nhiều mốc UTF-16, Companion chỉ dùng mặt đầu tiên. */
  emotion_cues?: EmotionCue[];
}

/** Một bước trong nhật ký "Đang làm". ``start``/``end`` là mili giây tính từ đầu lượt, theo đồng hồ máy chủ. */
export interface WorkStep {
  id: string;
  kind: 'wait' | 'read' | 'think' | 'note' | 'compose' | 'tool' | 'lookup' | 'github' | 'search';
  label: string;
  state: 'live' | 'done' | 'failed' | 'stopped';
  start: number;
  end?: number;
  detail?: string;
  /** Tóm tắt suy nghĩ Grok gửi về (bước think). */
  summary?: string;
  /** Lỗi từng dòng (sửa tệp bị từ chối) hoặc mục chưa đọc được (GitHub). */
  problems?: string[];
}

export interface WorkLog {
  ms: number;
  steps: WorkStep[];
  /** false khi lượt dừng giữa chừng (lỗi, hết giờ, bấm Dừng). */
  complete?: boolean;
}

/** Cách Peto trả lời trong một hội thoại: trợ lý AI (mặc định) hoặc nhập vai. Chọn lúc bắt đầu, giữ cả hội thoại. */
export type Persona = "assistant" | "roleplay";

export interface Conversation {
  archived?: boolean;
  project_id?: string | null;
  pinned?: boolean;
  title_state?: 'temporary' | 'pending' | 'generated' | 'locked';
  title_attempts?: number;
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  /** Máy chủ cũ chưa trả trường này thì coi như trợ lý. */
  persona?: Persona;
}

type ChatEvent =
  | { type: "meta"; conversation_id: string; effort: string; message?: Message; voice_stream?: boolean }
  | { type: "delta"; text: string }
  | { type: "emotion"; emotion: string; offset?: number }
  | { type: "replace"; text?: string }
  | { type: "thinking"; text: string; step?: string }
  | { type: "step"; step: WorkStep }
  | { type: "work"; work: WorkLog }
  | { type: "reading"; text: string }
  | { type: "search"; status: "searching" | "completed" }
  | { type: "sources"; sources: WebSource[] }
  | { type: 'artifact'; artifact: DocumentArtifact }
  | { type: 'document_status'; text: string }
  | { type: "file_lookup"; text: string; live: boolean }
  | { type: "connector_lookup"; text: string; live: boolean }
  | { type: "error"; message: string }
  | { type: "done" };

interface ChatHandlers {
  onMeta?: (conversationId: string, effort: string, message?: Message, voiceStream?: boolean) => void;
  onDelta?: (text: string) => void;
  /** Chỉ lượt Companion: cảm xúc Peto chọn, tới trước chữ để nhân vật đổi nét mặt ngay khi bắt đầu trả lời. */
  onEmotion?: (emotion: string, offset?: number) => void;
  /** Thay cả chữ đang hiện: ``text`` là phần còn lại (bỏ bản nháp trước khi tra web, hay câu dẫn đã vào nhật ký). */
  onReplace?: (text: string) => void;
  /** Tóm tắt suy nghĩ của Grok, nối vào bước ``step`` của nhật ký. */
  onThinking?: (text: string, step?: string) => void;
  /** Một bước của nhật ký "Đang làm" mới bắt đầu hoặc vừa đổi (thay theo id). */
  onStep?: (step: WorkStep) => void;
  /** Bản chốt của nhật ký lúc hết lượt, đúng như bản lưu cùng tin nhắn. */
  onWork?: (work: WorkLog) => void;
  onReading?: (text: string) => void;
  onSearch?: (status: "searching" | "completed") => void;
  onSources?: (sources: WebSource[]) => void;
  onArtifact?: (artifact: DocumentArtifact) => void;
  onDocumentStatus?: (text: string) => void;
  /** Peto tìm hoặc đọc thêm trong tệp đã gửi: live khi đang làm, rồi một lần nữa với kết quả. */
  onFileLookup?: (text: string, live: boolean) => void;
  onConnectorLookup?: (text: string, live: boolean) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export type AuthProvider = "discord" | "google" | "guest";

export interface AccountUser {
  /** Mã băm ổn định do server sinh. KHÔNG phải khóa owner. */
  id: string;
  provider: AuthProvider;
  username: string;
  display_name: string;
  avatar_url: string;
  /** Tên tự đặt trong Cài đặt → Hồ sơ; rỗng nếu chưa đặt. */
  nickname?: string;
  /** Đã xác nhận đủ 18 tuổi để bật chế độ nhập vai. */
  roleplay_confirmed?: boolean;
  /** Model tài khoản này chọn được ở nút cạnh nút Gửi; chỉ một model thì ẩn nút. */
  models?: ModelOption[];
}

export interface ModelOption {
  efforts?: Exclude<Effort, 'auto'>[];
  key: string;
  label: string;
  description: string;
  step_cost: number;
}

export interface AuthState {
  authenticated: boolean;
  login_configured: boolean;
  /** Cách đăng nhập nào đang dùng được. Thiếu cấu hình thì nút tự ẩn. */
  providers?: Record<AuthProvider, boolean>;
  user?: AccountUser;
}

/** Ném ra khi phiên hết hạn — giao diện quay lại màn hình đăng nhập. */
export class UnauthorizedError extends Error {
  constructor() {
    super("Phiên đăng nhập đã hết hạn.");
  }
}

async function json<T>(response: Response): Promise<T> {
  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `Yêu cầu không hợp lệ (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export async function getAuthState(): Promise<AuthState> {
  const response = await fetch("/api/auth/me");
  return json<AuthState>(response);
}

export async function logout(): Promise<void> {
  await json(await fetch("/api/auth/logout", { method: "POST" }));
}

export const DISCORD_LOGIN_URL = "/api/auth/discord/login";
export const GOOGLE_LOGIN_URL = "/api/auth/google/login";

/** Vào thẳng, không qua nhà cung cấp nào. Server tự tạo owner mới mỗi lần. */
export async function guestLogin(): Promise<void> {
  await json(await fetch("/api/auth/guest", { method: "POST" }));
}

/** Hồ sơ người dùng tự điền trong Cài đặt. Máy chủ ghép nó vào mọi lượt chat. */
export interface Profile {
  full_name: string;
  nickname: string;
  occupation: string;
  instructions: string;
}

export interface ProfileData {
  profile: Profile;
  occupations: { value: string; label: string }[];
  limits: { full_name: number; nickname: number; instructions: number };
}

export async function getProfile(): Promise<ProfileData> {
  return json<ProfileData>(await fetch("/api/profile"));
}

/** Lưu và trả về hồ sơ ĐÃ chuẩn hóa (máy chủ gộp khoảng trắng, cắt ký tự lạ). */
export async function saveProfile(profile: Profile): Promise<Profile> {
  const response = await fetch("/api/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  return (await json<{ profile: Profile }>(response)).profile;
}

/** Lưu xác nhận đủ 18 tuổi cho tài khoản, để bật được chế độ nhập vai. Tài khoản khách bị từ chối. */
export async function confirmRoleplayAge(): Promise<void> {
  await json(await fetch("/api/profile/roleplay-consent", { method: "POST" }));
}

export function browserTimezone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

export interface AppInfo {
  name: string;
  avatar_url: string | null;
}

/** Tên và avatar của Peto, lấy từ Discord application ở phía máy chủ. */
export async function getAppInfo(): Promise<AppInfo> {
  const response = await fetch("/api/app-info");
  if (!response.ok) return { name: "Peto", avatar_url: null };
  return (await response.json()) as AppInfo;
}

export async function listConversations(offset = 0, limit = 50, query = '', filter?: {projectId?: string; unassigned?: boolean; archived?: boolean}, signal?: AbortSignal): Promise<{
  conversations: Conversation[]; has_more: boolean;
}> {
  const scope = filter?.projectId ? `&project_id=${encodeURIComponent(filter.projectId)}` : filter?.unassigned ? '&unassigned=true' : '';
  const response = await fetch(`/api/conversations?offset=${offset}&limit=${limit}&q=${encodeURIComponent(query)}${scope}${filter?.archived ? '&archived=true' : ''}`, {signal});
  return json(response);
}

export async function updateConversation(id: string, change: { title?: string; pinned?: boolean; project_id?: string | null; archived?: boolean }): Promise<void> {
  await json(await fetch(`/api/conversations/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(change)}));
}

export async function conversationVersions(id: string): Promise<Conversation[]> {
  const data = await json<{versions:Conversation[]}>(await fetch(`/api/conversations/${id}/versions`));
  return data.versions;
}

export async function getMessages(conversationId: string, signal?: AbortSignal, onSettings?: (settings: {project_id?: string | null; persona?: Persona; archived?: boolean}) => void): Promise<Message[]> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, { signal });
  const data = await json<{ messages: Message[]; project_id?: string | null; persona?: Persona; archived?: boolean }>(response);
  onSettings?.(data);
  return data.messages;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
  });
  await json<{ deleted: boolean }>(response);
}

/** Một điều Peto tự ghi nhớ từ lời người dùng kể trong Companion (Cài đặt → Trí nhớ Companion). */
export interface CompanionMemory {
  id: number;
  text: string;
  created_at: number;
  updated_at: number;
}

export interface CompanionMemoryState {
  /** false khi chủ web tắt trí nhớ trên cả máy chủ. */
  available: boolean;
  enabled: boolean;
  /** Còn đang ghi nhớ lượt vừa xong: hỏi lại sau vài giây. */
  pending: boolean;
  limit: number;
  memories: CompanionMemory[];
}

export async function getCompanionMemory(signal?: AbortSignal): Promise<CompanionMemoryState> {
  return json(await fetch("/api/companion/memory", { signal }));
}

export async function setCompanionMemoryEnabled(enabled: boolean): Promise<void> {
  await json(await fetch("/api/companion/memory/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  }));
}

export async function deleteCompanionMemory(id: number): Promise<void> {
  await json(await fetch(`/api/companion/memory/${id}`, { method: "DELETE" }));
}

export async function clearCompanionMemory(): Promise<void> {
  await json(await fetch("/api/companion/memory", { method: "DELETE" }));
}

/** Mạch trò chuyện của tab Companion; chưa nhắn lần nào thì conversation_id là null. */
export async function getCompanion(signal?: AbortSignal): Promise<{
  conversation_id: string | null; messages: Message[];
}> {
  return json(await fetch("/api/companion", { signal }));
}

export type ImagineQuality = "low" | "medium";
export type ImagineResolution = "1k" | "2k";

export interface ImagineImage {
  id: string;
  mime: string;
  /** Chỉ ảnh kết quả mới có; ảnh gốc của lượt sửa không thích được. */
  liked?: boolean;
  url: string;
}

export interface ImagineJob {
  id: string;
  prompt: string;
  quality: ImagineQuality;
  resolution: ImagineResolution;
  aspect_ratio: string;
  created_at: number | null;
  images: ImagineImage[];
  source_image?: ImagineImage | null;
}

export async function listImagineJobs(): Promise<ImagineJob[]> {
  const response = await fetch("/api/imagine");
  const data = await json<{ jobs: ImagineJob[] }>(response);
  return data.jobs;
}

export async function createImagineJob(payload: {
  prompt: string;
  quality: ImagineQuality;
  resolution: ImagineResolution;
  aspect_ratio: string;
  n: number;
  source_image?: { data: string };
  source_image_id?: string;
}): Promise<ImagineJob> {
  const response = await fetch("/api/imagine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await json<{ job: ImagineJob }>(response);
  return data.job;
}

export async function deleteImagineJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/imagine/${jobId}`, { method: "DELETE" });
  await json<{ deleted: boolean }>(response);
}

/** Xóa một ảnh trong thư viện. `job_deleted` báo đó là ảnh cuối nên cả lượt bị xóa theo. */
export async function deleteImagineImage(imageId: string): Promise<{ job_deleted: boolean }> {
  const response = await fetch(`/api/imagine/images/${imageId}`, { method: "DELETE" });
  return json<{ deleted: boolean; job_deleted: boolean }>(response);
}

export async function setImagineImageLiked(imageId: string, liked: boolean): Promise<boolean> {
  const response = await fetch(`/api/imagine/images/${imageId}/like`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ liked }),
  });
  const data = await json<{ liked: boolean }>(response);
  return data.liked;
}

/** Máy đang chờ được cho phép dùng Peto Agent, theo mã mà lệnh peto login in ra. */
export interface AgentDevicePending {
  user_code: string;
  name: string;
  expires_in: number;
}

export interface AgentDevice {
  id: string;
  name: string;
  created_at: number;
  last_used_at: number;
}

export interface AgentDevices {
  devices: AgentDevice[];
  steps_used: number;
  steps_limit: number;
}

export async function getAgentDevice(userCode: string, signal?: AbortSignal): Promise<AgentDevicePending> {
  return json<AgentDevicePending>(await fetch(`/api/agent/device/${encodeURIComponent(userCode)}`, { signal }));
}

export async function answerAgentDevice(userCode: string, allow: boolean): Promise<void> {
  await json(await fetch(`/api/agent/device/${encodeURIComponent(userCode)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allow }),
  }));
}

export async function listAgentDevices(): Promise<AgentDevices> {
  return json<AgentDevices>(await fetch("/api/agent/devices"));
}

export async function revokeAgentDevice(deviceId: string): Promise<void> {
  await json(await fetch(`/api/agent/devices/${encodeURIComponent(deviceId)}`, { method: "DELETE" }));
}

/**
 * Gửi tin nhắn và đọc SSE từ backend.
 *
 * Dùng fetch chứ không dùng EventSource vì endpoint là POST. `signal` cho phép
 * người dùng bấm dừng giữa chừng.
 */
export async function sendMessage(
  payload: {
    projectId?: string | null;
    branchMessageId?: number;
    message: string;
    conversationId: string | null;
    effort: Effort;
    webSearch?: WebSearchMode;
    attachments?: OutgoingAttachment[];
    mode?: ConversationMode;
    persona?: Persona;
    /** Model cho tin này; máy chủ kiểm quyền, thiếu thì dùng Peto. */
    model?: string;
  },
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      branch_message_id: payload.branchMessageId,
      message: payload.message,
      project_id: payload.projectId,
      conversation_id: payload.conversationId,
      effort: payload.effort,
      web_search: payload.webSearch ?? "auto",
      timezone: browserTimezone(),
      attachments: payload.attachments ?? [],
      mode: payload.mode ?? "chat",
      persona: payload.persona ?? "assistant",
      model: payload.model ?? "peto",
    }),
    signal,
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    handlers.onError?.(typeof detail?.detail === "string" ? detail.detail : `Yêu cầu không hợp lệ (${response.status}).`);
    return;
  }
  if (!response.body) {
    handlers.onError?.("Trình duyệt không đọc được luồng trả lời.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  let ended = false;
  try {
    while (!ended) {
      signal?.throwIfAborted();
      const { done, value } = await reader.read();
      signal?.throwIfAborted();
      if (done) throw new Error("Kết nối bị ngắt trước khi Peto trả lời xong.");
      buffer += decoder.decode(value, { stream: true });

      // Mỗi sự kiện SSE kết thúc bằng một dòng trống.
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        signal?.throwIfAborted();
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");

        const line = raw.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;

        const event = JSON.parse(line.slice(6)) as ChatEvent;
        if (event.type === "meta") {
          handlers.onMeta?.(event.conversation_id, event.effort, event.message, event.voice_stream === true);
        } else if (event.type === "delta") {
          handlers.onDelta?.(event.text);
        } else if (event.type === "emotion") {
          handlers.onEmotion?.(event.emotion, event.offset);
        } else if (event.type === "replace") {
          handlers.onReplace?.(event.text ?? "");
        } else if (event.type === "thinking") {
          handlers.onThinking?.(event.text, event.step);
        } else if (event.type === "step") {
          handlers.onStep?.(event.step);
        } else if (event.type === "work") {
          handlers.onWork?.(event.work);
        } else if (event.type === "reading") {
          handlers.onReading?.(event.text);
        } else if (event.type === "search") {
          handlers.onSearch?.(event.status);
        } else if (event.type === "sources") {
          handlers.onSources?.(event.sources);
        } else if (event.type === 'artifact') {
          handlers.onArtifact?.(event.artifact);
        } else if (event.type === 'document_status') {
          handlers.onDocumentStatus?.(event.text);
        } else if (event.type === "file_lookup") {
          handlers.onFileLookup?.(event.text, event.live);
        } else if (event.type === "connector_lookup") {
          handlers.onConnectorLookup?.(event.text, event.live);
        } else if (event.type === "error") {
          handlers.onError?.(event.message);
          ended = true;
        } else if (event.type === "done") {
          handlers.onDone?.();
          ended = true;
        }
        if (ended) break;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
