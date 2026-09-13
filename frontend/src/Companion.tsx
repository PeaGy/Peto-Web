import { useCallback, useEffect, useRef, useState } from "react";
import {
  UnauthorizedError,
  deleteConversation,
  getCompanion,
  sendMessage,
  type AppInfo,
  type Message,
} from "./api";
import { SpeakButton, VoiceControls, useLocalVoice } from "./LocalVoice";

const MUTED_KEY = "peto-companion-muted";

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) === "1";
  } catch {
    return false;
  }
}

export function CompanionIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z" stroke="currentColor" strokeWidth="2" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Tab Companion: Peto trả lời một hai câu bằng tiếng Anh như bạn bè nhắn tin, rồi tự nói thành tiếng
 * bằng giọng chạy trên máy người dùng. Chỉ có một mạch trò chuyện, tách khỏi danh sách Trò chuyện.
 *
 * Được giữ mounted như Imagine (prop `active`) để câu trả lời đang về không bị cắt khi đổi tab;
 * rời tab thì Peto thôi đọc.
 */
export default function Companion({ active, appInfo, onUnauthorized, onOpenSidebar }: {
  active: boolean;
  appInfo: AppInfo | null;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
}) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(readMuted);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const voice = useLocalVoice(setError);
  const stopVoice = voice.stop;
  const loadVersion = useRef(0);
  const loadRef = useRef<AbortController | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const resetRef = useRef<HTMLDialogElement>(null);
  // Câu trả lời về xong mới quyết định có đọc không, nên đọc trạng thái mới nhất qua ref.
  const latest = useRef({ active, muted, voice });

  useEffect(() => {
    latest.current = { active, muted, voice };
  });

  const load = useCallback(async () => {
    loadRef.current?.abort();
    const controller = new AbortController();
    loadRef.current = controller;
    const version = ++loadVersion.current;
    setLoading(true);
    setLoadFailed(false);
    try {
      const thread = await getCompanion(controller.signal);
      if (version !== loadVersion.current) return;
      setConversationId(thread.conversation_id);
      setMessages(thread.messages);
    } catch (err) {
      if (version !== loadVersion.current || controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setLoadFailed(true);
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }, [onUnauthorized]);

  useEffect(() => {
    void load();
    return () => {
      loadVersion.current += 1;
      loadRef.current?.abort();
      abortRef.current?.abort();
    };
  }, [load]);

  useEffect(() => {
    if (!active) stopVoice();
  }, [active, stopVoice]);

  useEffect(() => {
    try {
      localStorage.setItem(MUTED_KEY, muted ? "1" : "0");
    } catch {}
    if (muted) stopVoice();
  }, [muted, stopVoice]);

  useEffect(() => {
    if (active && confirmReset) resetRef.current?.showModal();
    else resetRef.current?.close();
  }, [active, confirmReset]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function send() {
    const text = draft.trim();
    if (!text || abortRef.current || loading || loadFailed) return;
    stopVoice();
    setError(null);
    const previous = messages;
    const replyIndex = previous.length + 1;
    setMessages([...previous, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setStreaming(true);
    setStopping(false);
    const controller = new AbortController();
    abortRef.current = controller;
    let accepted = false;
    let completed = false;
    let reply = "";
    try {
      await sendMessage(
        { message: text, conversationId, effort: "low", webSearch: "off", mode: "companion" },
        {
          onMeta: (id, _effort, stored) => {
            accepted = true;
            setConversationId(id);
            setDraft("");
            if (stored) setMessages((prev) => [...prev.slice(0, -2), stored, prev[prev.length - 1]]);
          },
          onDelta: (chunk) => {
            reply += chunk;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role !== "assistant") return prev;
              return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
            });
          },
          onError: setError,
          onDone: () => {
            completed = true;
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized();
      } else if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Mất kết nối tới máy chủ");
      }
    } finally {
      // Giữ bản nháp tới khi máy chủ nhận tin, như tab Trò chuyện.
      if (!accepted) {
        setMessages(previous);
      } else {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role !== "assistant") return prev;
          return last.content
            ? [...prev.slice(0, -1), { ...last, status: completed ? "complete" : "incomplete" }]
            : prev.slice(0, -1);
        });
      }
      setStreaming(false);
      setStopping(false);
      abortRef.current = null;
    }
    const now = latest.current;
    if (completed && reply.trim() && now.active && !now.muted && now.voice.status === "ready") {
      now.voice.speak(String(replyIndex), reply);
    }
  }

  function stop() {
    setStopping(true);
    abortRef.current?.abort();
  }

  async function reset() {
    if (!conversationId || resetting) return;
    setResetting(true);
    try {
      await deleteConversation(conversationId);
      stopVoice();
      loadVersion.current += 1;
      setConversationId(null);
      setMessages([]);
      setConfirmReset(false);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Chưa bắt đầu lại được");
      setConfirmReset(false);
    } finally {
      setResetting(false);
    }
  }

  const phase = voice.speaking?.phase;
  const stageText = phase === "playing" ? "Peto đang nói…"
    : phase === "loading" ? "Peto sắp nói…"
      : streaming ? "Peto đang nhắn…" : "Peto đang nghe";
  const canSend = draft.trim().length > 0 && !streaming && !loading && !loadFailed;

  return (
    <main className="companion" hidden={!active}>
      <button type="button" className="menu-btn companion-menu" aria-label="Mở menu" onClick={onOpenSidebar}>
        <MenuIcon />
      </button>

      <section className="companion-stage" aria-label="Peto">
        <div className={phase === "playing" ? "companion-portrait speaking" : "companion-portrait"}>
          {appInfo?.avatar_url
            ? <img src={appInfo.avatar_url} alt="" />
            : <span aria-hidden="true">{(appInfo?.name ?? "Peto").charAt(0)}</span>}
        </div>
        <p className="companion-state" aria-live="polite">{stageText}</p>
        <VoiceControls voice={voice} muted={muted} onToggleMute={() => setMuted((value) => !value)} />
      </section>

      <section className="companion-panel" aria-label="Trò chuyện trong Companion">
        <header className="companion-head">
          <div>
            <strong>{appInfo?.name ?? "Peto"}</strong>
            <span>Trả lời ngắn bằng tiếng Anh</span>
          </div>
          <button
            type="button"
            className="companion-button"
            disabled={!conversationId || streaming || resetting}
            onClick={() => setConfirmReset(true)}
          >
            Bắt đầu lại
          </button>
        </header>

        <div className="companion-messages">
          {loading && <p className="loading-chat" role="status">Đang mở Companion…</p>}
          {loadFailed && (
            <div className="loading-chat">
              <p>Chưa tải được cuộc trò chuyện.</p>
              <button type="button" className="load-more" onClick={() => void load()}>Thử lại</button>
            </div>
          )}
          {!loading && !loadFailed && messages.length === 0 && (
            <p className="companion-empty">
              Chào Peto một câu đi. Ở đây Peto trả lời ngắn bằng tiếng Anh, như bạn bè nhắn tin.
            </p>
          )}
          {messages.map((message, index) => {
            const live = streaming && index === messages.length - 1;
            return (
              <article key={index} className={`companion-bubble ${message.role}`}>
                <p>{message.content || (live ? "…" : "")}</p>
                {message.role === "assistant" && message.content && !live && voice.status === "ready" && (
                  <SpeakButton
                    phase={voice.speaking?.key === String(index) ? voice.speaking.phase : null}
                    onSpeak={() => voice.speak(String(index), message.content)}
                    onStop={stopVoice}
                  />
                )}
                {message.status === "incomplete" && <span className="message-status">Chưa trả lời xong</span>}
              </article>
            );
          })}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
            <button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button>
          </div>
        )}

        <form
          className="companion-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <textarea
            value={draft}
            rows={1}
            placeholder="Nhắn cho Peto…"
            aria-label="Nhắn cho Peto trong Companion"
            disabled={streaming}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send();
              }
            }}
          />
          {streaming ? (
            <button type="button" className="companion-button" disabled={stopping} onClick={stop}>
              {stopping ? "Đang dừng…" : "Dừng"}
            </button>
          ) : (
            <button type="submit" className="companion-send" disabled={!canSend}>Gửi</button>
          )}
        </form>
      </section>

      <dialog
        ref={resetRef}
        className="confirm-dialog"
        aria-labelledby="companion-reset-title"
        onCancel={(event) => {
          event.preventDefault();
          if (!resetting) setConfirmReset(false);
        }}
      >
        <h2 id="companion-reset-title">Bắt đầu lại với Peto?</h2>
        <p>Toàn bộ mạch trò chuyện trong Companion sẽ bị xóa. Không thể hoàn tác.</p>
        <div className="dialog-actions">
          <button type="button" disabled={resetting} onClick={() => setConfirmReset(false)}>Giữ lại</button>
          <button type="button" className="danger-button" disabled={resetting} onClick={() => void reset()}>
            {resetting ? "Đang xóa…" : "Xóa và bắt đầu lại"}
          </button>
        </div>
      </dialog>
    </main>
  );
}
