import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import {
  DISCORD_LOGIN_URL,
  UnauthorizedError,
  deleteConversation,
  getAuthState,
  getMessages,
  listConversations,
  logout,
  sendMessage,
  type AuthState,
  type Conversation,
  type Message,
} from "./api";

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Backend chuyển hướng về đây kèm ?auth_error=... khi đăng nhập hỏng.
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

  /** Phiên hết hạn giữa chừng: quay về màn hình đăng nhập thay vì báo lỗi lạ. */
  const handleUnauthorized = useCallback(() => {
    setAuth({ authenticated: false, login_configured: true });
    setMessages([]);
    setConversations([]);
    setConversationId(null);
    setAuthError("Phiên đăng nhập đã hết hạn. Đăng nhập lại nhé.");
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch (err) {
      if (err instanceof UnauthorizedError) handleUnauthorized();
      // Danh sách hội thoại hỏng không nên chặn việc chat.
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    if (auth?.authenticated) void refreshConversations();
  }, [auth?.authenticated, refreshConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  if (auth === null) {
    return <div className="boot">Đang tải…</div>;
  }

  if (!auth.authenticated) {
    return (
      <div className="login">
        <div className="login-card">
          <span className="avatar big">P</span>
          <h1>Peto</h1>
          <p className="login-sub">
            Đăng nhập bằng Discord để Peto biết cậu là ai.
          </p>

          {authError && (
            <div className="error" role="alert">
              {authError}
            </div>
          )}

          {auth.login_configured ? (
            <a className="discord-button" href={DISCORD_LOGIN_URL}>
              Đăng nhập bằng Discord
            </a>
          ) : (
            <div className="error">
              Máy chủ chưa cấu hình <code>DISCORD_CLIENT_ID</code> và{" "}
              <code>DISCORD_CLIENT_SECRET</code>.
            </div>
          )}

          <p className="login-note">
            Chỉ những tài khoản đã được cho phép mới vào được. Peto chỉ đọc tên
            và ảnh đại diện của cậu.
          </p>
        </div>
      </div>
    );
  }

  async function openConversation(id: string) {
    if (streaming) return;
    setError(null);
    setConversationId(id);
    try {
      setMessages(await getMessages(id));
    } catch (err) {
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setError(err instanceof Error ? err.message : "Không mở được hội thoại");
    }
  }

  function newConversation() {
    if (streaming) return;
    setConversationId(null);
    setMessages([]);
    setError(null);
    textareaRef.current?.focus();
  }

  async function removeConversation(id: string) {
    if (streaming) return;
    try {
      await deleteConversation(id);
      if (id === conversationId) newConversation();
      await refreshConversations();
    } catch (err) {
      if (err instanceof UnauthorizedError) return handleUnauthorized();
      setError(err instanceof Error ? err.message : "Không xóa được");
    }
  }

  async function submit() {
    const text = draft.trim();
    if (!text || streaming) return;

    setDraft("");
    setError(null);
    setStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    let activeId = conversationId;

    const appendToReply = (chunk: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + chunk };
        return next;
      });

    try {
      await sendMessage(
        text,
        conversationId,
        {
          onMeta: (id) => {
            activeId = id;
            setConversationId(id);
          },
          onDelta: appendToReply,
          onError: (message) => {
            setError(message);
            // Bỏ bong bóng trả lời rỗng để không để lại tin trắng.
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              return last?.role === "assistant" && !last.content
                ? prev.slice(0, -1)
                : prev;
            });
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        handleUnauthorized();
      } else if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Mất kết nối tới máy chủ");
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      if (activeId) void refreshConversations();
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  async function signOut() {
    await logout();
    setAuth({ authenticated: false, login_configured: true });
    setMessages([]);
    setConversations([]);
    setConversationId(null);
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <button className="new-chat" onClick={newConversation} disabled={streaming}>
          + Trò chuyện mới
        </button>
        <nav className="conversation-list">
          {conversations.length === 0 && (
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
                onClick={() => void openConversation(conversation.id)}
                disabled={streaming}
              >
                {conversation.title || "Chưa có tiêu đề"}
              </button>
              <button
                className="conv-delete"
                title="Xóa hội thoại"
                aria-label="Xóa hội thoại"
                onClick={() => void removeConversation(conversation.id)}
                disabled={streaming}
              >
                ×
              </button>
            </div>
          ))}
        </nav>

        <div className="account">
          <img
            className="account-avatar"
            src={auth.user?.avatar_url}
            alt=""
            width={32}
            height={32}
          />
          <div className="account-name">
            <strong>{auth.user?.display_name}</strong>
            <span>@{auth.user?.username}</span>
          </div>
          <button
            className="logout"
            onClick={() => void signOut()}
            disabled={streaming}
            title="Đăng xuất"
          >
            Thoát
          </button>
        </div>
      </aside>

      <main className="chat">
        <header className="chat-header">
          <span className="avatar">P</span>
          <div>
            <strong>Peto</strong>
            <span className="subtitle">Peto Web — chat chữ</span>
          </div>
        </header>

        <div className="messages">
          {messages.length === 0 && !streaming && (
            <div className="welcome">
              <h1>Chào {auth.user?.display_name}</h1>
              <p>Nhắn gì đó đi, Peto đang nghe đây.</p>
            </div>
          )}

          {messages.map((message, index) => (
            <article key={index} className={`bubble ${message.role}`}>
              {message.content ? (
                <Markdown>{message.content}</Markdown>
              ) : (
                <span className="typing">
                  <i />
                  <i />
                  <i />
                </span>
              )}
            </article>
          ))}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <textarea
            ref={textareaRef}
            value={draft}
            rows={1}
            placeholder="Nhắn cho Peto…"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
          />
          {streaming ? (
            <button type="button" className="stop" onClick={stop}>
              Dừng
            </button>
          ) : (
            <button type="submit" disabled={!draft.trim()}>
              Gửi
            </button>
          )}
        </form>
      </main>
    </div>
  );
}
