export type Role = "user" | "assistant";
export type Effort = "auto" | "low" | "medium" | "high";

export interface ChatAttachment {
  id: string;
  name: string;
  mime: string;
  kind: "image" | "file";
  size: number;
  url: string;
}

export interface OutgoingAttachment {
  name: string;
  mime: string;
  data: string;
}

export interface Message {
  role: Role;
  content: string;
  created_at?: number;
  attachments?: ChatAttachment[];
}

export interface Conversation {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
}

type ChatEvent =
  | { type: "meta"; conversation_id: string; effort: string }
  | { type: "delta"; text: string }
  | { type: "error"; message: string }
  | { type: "done" };

interface ChatHandlers {
  onMeta?: (conversationId: string, effort: string) => void;
  onDelta?: (text: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export interface DiscordUser {
  discord_id: string;
  username: string;
  display_name: string;
  avatar_url: string;
}

export interface AuthState {
  authenticated: boolean;
  login_configured: boolean;
  user?: DiscordUser;
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
    throw new Error(detail?.detail ?? `Lỗi ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function getAuthState(): Promise<AuthState> {
  const response = await fetch("/api/auth/me");
  return json<AuthState>(response);
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST" });
}

export const DISCORD_LOGIN_URL = "/api/auth/discord/login";

export async function listConversations(): Promise<Conversation[]> {
  const response = await fetch("/api/conversations");
  const data = await json<{ conversations: Conversation[] }>(response);
  return data.conversations;
}

export async function getMessages(conversationId: string): Promise<Message[]> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`);
  const data = await json<{ messages: Message[] }>(response);
  return data.messages;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
  });
  await json<{ deleted: boolean }>(response);
}

/**
 * Gửi tin nhắn và đọc SSE từ backend.
 *
 * Dùng fetch chứ không dùng EventSource vì endpoint là POST. `signal` cho phép
 * người dùng bấm dừng giữa chừng.
 */
export async function sendMessage(
  payload: {
    message: string;
    conversationId: string | null;
    effort: Effort;
    attachments?: OutgoingAttachment[];
  },
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: payload.message,
      conversation_id: payload.conversationId,
      effort: payload.effort,
      attachments: payload.attachments ?? [],
    }),
    signal,
  });

  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    handlers.onError?.(detail?.detail ?? `Lỗi ${response.status}`);
    return;
  }
  if (!response.body) {
    handlers.onError?.("Trình duyệt không đọc được luồng trả lời.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Mỗi sự kiện SSE kết thúc bằng một dòng trống.
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");

      const line = raw.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;

      const event = JSON.parse(line.slice(6)) as ChatEvent;
      if (event.type === "meta") {
        handlers.onMeta?.(event.conversation_id, event.effort);
      } else if (event.type === "delta") {
        handlers.onDelta?.(event.text);
      } else if (event.type === "error") {
        handlers.onError?.(event.message);
      } else if (event.type === "done") {
        handlers.onDone?.();
      }
    }
  }
}
