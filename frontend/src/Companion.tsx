import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  UnauthorizedError,
  deleteConversation,
  getCompanion,
  sendMessage,
  type AppInfo,
  type Message,
} from "./api";
import { SendIcon } from "./Composer";
import { SpeakButton, SpeakerIcon, SpeakerOffIcon, type LocalVoice } from "./LocalVoice";
import type { CharacterMotion } from "./characterView";
import { DEFAULT_CHARACTER, type CharacterModel } from './characterLibrary';
import type { CompanionActivity } from './companionMotion';
import { SceneBackdrop, ScenePicker, useCompanionScene } from './CompanionScenes';

const MUTED_KEY = "peto-companion-muted";
const Live2DStage = lazy(() => import("./Live2DStage"));
const VRMStage = lazy(() => import('./VRMStage'));
/** Khóa đọc của Companion có tiền tố riêng, để câu nghe thử trong Cài đặt không làm đổi trạng thái ở đây. */
const SPEECH_PREFIX = "companion-";

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

function RestartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 3v5h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Tab Companion: Peto trả lời một hai câu bằng tiếng Anh như bạn bè nhắn tin, rồi tự nói thành tiếng
 * bằng âm thanh từ máy tạo giọng chuyển qua VPS. Chỉ có một mạch trò chuyện, tách khỏi danh sách Trò chuyện.
 *
 * Sân khấu bên trái hiển thị Live2D và ghi công model. Mọi thứ
 * để nhắn và nghe nằm ở cột chat; bật giọng nói và chọn giọng nằm trong Cài đặt (`VoiceSettings.tsx`).
 * Trên điện thoại, nhân vật phủ cả màn hình; tiêu đề, tin nhắn và ô nhắn nổi trong suốt bên trên như AIRI.
 *
 * Được giữ mounted như Imagine (prop `active`) để câu trả lời đang về không bị cắt khi đổi tab;
 * rời tab thì Peto thôi đọc và giải phóng renderer nhân vật.
 */
export default function Companion({ active, appInfo, voice, characterMotion, character = DEFAULT_CHARACTER, onCharacterPreview, onOpenCharacters, onUnauthorized, onOpenSidebar }: {
  active: boolean;
  appInfo: AppInfo | null;
  voice: LocalVoice;
  characterMotion: CharacterMotion;
  character?: CharacterModel;
  onCharacterPreview?: (id: string, image: string) => void;
  onOpenCharacters?: () => void;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
}) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [expressionReply, setExpressionReply] = useState<{ text: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(readMuted);
  const [confirmReset, setConfirmReset] = useState(false);
  const [scenesOpen, setScenesOpen] = useState(false);
  const scene = useCompanionScene(character.id);
  const [resetting, setResetting] = useState(false);
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

  // Giọng nói sống ở App, lâu hơn tab này (đăng xuất thì tab bị gỡ), nên gỡ tab thì cũng thôi đọc.
  useEffect(() => () => stopVoice(), [stopVoice]);

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

  function reportSpeechError(err: unknown) {
    setError(err instanceof Error ? err.message : "Chưa đọc được tin này.");
  }

  async function send() {
    const text = draft.trim();
    if (!text || abortRef.current || loading || loadFailed) return;
    stopVoice();
    setError(null);
    setExpressionReply(null);
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
    if (completed && reply.trim() && now.active) setExpressionReply({ text: reply });
    if (completed && reply.trim() && now.active && !now.muted && now.voice.status === "ready") {
      now.voice.speak(`${SPEECH_PREFIX}${replyIndex}`, reply).catch(reportSpeechError);
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
      setExpressionReply(null);
      setConfirmReset(false);
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Chưa bắt đầu lại được");
      setConfirmReset(false);
    } finally {
      setResetting(false);
    }
  }

  const name = appInfo?.name ?? "Peto";
  const speech = voice.speaking?.key.startsWith(SPEECH_PREFIX) ? voice.speaking : null;
  const expressionSpeechKey = useRef<string | null>(null);
  useEffect(() => {
    if (!speech) {
      if (expressionSpeechKey.current) setExpressionReply(null);
      expressionSpeechKey.current = null;
      return;
    }
    if (speech.phase !== 'playing' || expressionSpeechKey.current === speech.key) return;
    expressionSpeechKey.current = speech.key;
    const index = Number(speech.key.slice(SPEECH_PREFIX.length));
    const message = messages[index];
    if (message?.role === 'assistant') setExpressionReply({ text: message.content });
  }, [speech?.key, speech?.phase, messages]);
  const activity: CompanionActivity = speech?.phase === 'playing' ? 'speaking'
    : streaming || speech?.phase === 'loading' ? 'thinking' : draft.trim() ? 'listening' : 'idle';
  const stateText = speech?.phase === "playing" ? "Đang nói…"
    : speech?.phase === "loading" ? "Sắp nói…"
      : streaming ? "Đang nhắn…" : "Trả lời ngắn bằng tiếng Anh";
  const canSend = draft.trim().length > 0 && !streaming && !loading && !loadFailed;

  return (
    <main className={`companion${scene.selected.url ? ' companion-with-scene' : ''}`} hidden={!active}>
      {active && scenesOpen && <ScenePicker scene={scene} onClose={() => setScenesOpen(false)} />}
      <SceneBackdrop scene={scene} />
      <section className="companion-stage" aria-label={name}>
        <button className="companion-character-button" onClick={onOpenCharacters} aria-label="Chọn nhân vật">◇ <span>Nhân vật</span></button>
        {active && <Suspense fallback={<p role="status">Đang tải nhân vật…</p>}>
          {character.format === 'vrm'
            ? <VRMStage key={character.id} character={character} motion={characterMotion} onPreview={onCharacterPreview} activity={activity} />
            : <Live2DStage key={character.id} character={character} fallbackUrl={appInfo?.avatar_url ?? undefined} name={name} motion={characterMotion} onPreview={onCharacterPreview} reply={expressionReply} activity={activity} />}
        </Suspense>}
      </section>

      <section className="companion-panel" aria-label="Trò chuyện trong Companion">
        <header className="companion-head">
          <button type="button" className="menu-btn companion-menu" aria-label="Mở menu" onClick={onOpenSidebar}>
            <MenuIcon />
          </button>
          <button
            type="button"
            className="companion-title"
            aria-label={`Đổi nhân vật ${name}`}
            aria-haspopup="dialog"
            title="Đổi nhân vật"
            onClick={onOpenCharacters}
          >
            <strong>
              {name}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </strong>
            <span aria-live="polite">{stateText}</span>
          </button>
          <div className="companion-tools">
            {voice.status === "ready" && (
              <button
                type="button"
                className="companion-tool"
                aria-label="Tắt tiếng"
                aria-pressed={muted}
                title={muted ? "Bật tiếng" : "Tắt tiếng"}
                onClick={() => setMuted((value) => !value)}
              >
                {muted ? <SpeakerOffIcon /> : <SpeakerIcon />}
              </button>
            )}
            <button
              type="button"
              className="companion-tool"
              aria-label="Bắt đầu lại"
              title="Bắt đầu lại"
              disabled={!conversationId || streaming || resetting}
              onClick={() => setConfirmReset(true)}
            >
              <RestartIcon />
            </button>
          </div>
        </header>

        {voice.status === "missing" && (
          <div className="companion-notice">
            <span>Chưa thấy máy chủ giọng nói, Peto chỉ nhắn chữ.</span>
            <button type="button" onClick={voice.recheck}>Kiểm tra lại</button>
          </div>
        )}

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
            if (message.role === "user") {
              return (
                <article key={index} className="bubble user">
                  <p>{message.content}</p>
                </article>
              );
            }
            const live = streaming && index === messages.length - 1;
            const key = `${SPEECH_PREFIX}${index}`;
            return (
              <article key={index} className="bubble assistant companion-reply">
                {message.content
                  ? <p>{message.content}</p>
                  : live && <p className="companion-typing" aria-hidden="true">…</p>}
                {message.content && !live && voice.status === "ready" && (
                  <SpeakButton
                    phase={voice.speaking?.key === key ? voice.speaking.phase : null}
                    onSpeak={() => { setExpressionReply({ text: message.content }); void voice.speak(key, message.content).catch(reportSpeechError); }}
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
          <div className="composer">
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
            <div className="composer-bar">
              {streaming ? (
                <button type="button" className="stop" disabled={stopping} onClick={stop}>
                  {stopping ? "Đang dừng…" : "Dừng"}
                </button>
              ) : (
                <button type="submit" className="send" disabled={!canSend} aria-label="Gửi">
                  <span className="send-text">Gửi</span> <SendIcon />
                </button>
              )}
            </div>
          </div>
        </form>
      </section>

      <div className="companion-scene-tools">
        <button type="button" className="companion-scene-button" aria-label="Bối cảnh" title="Bối cảnh" aria-haspopup="dialog" onClick={() => setScenesOpen(true)}>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.7" /><circle cx="9" cy="8" r="2" stroke="currentColor" strokeWidth="1.7" /><path d="m4 18 5-5 3 3 4-6 5 8" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>
          <span>Bối cảnh</span>
        </button>
      </div>
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
