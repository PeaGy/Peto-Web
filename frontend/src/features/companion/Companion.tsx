import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  UnauthorizedError,
  deleteConversation,
  getCompanion,
  getCompanionMemory,
  sendMessage,
  type AppInfo,
  type Message,
  type EmotionCue,
} from "../../shared/api/api";
import { SendIcon } from "../chat/Composer";
import { LoadingIndicator } from '../../shared/ui/LoadingIndicator';
import { PlayerIcon } from '../../shared/ui/PlayerIcon';
import { usePlayerLayout } from './ytplayer/playerLayout';
import './ytplayer/companionPlayer.css';
import { fileToBase64 } from '../chat/attachments';
import { useCompanionImages } from './useCompanionImages';
import { CompanionImageDrafts, CompanionImageIcon, CompanionMessageImages } from './CompanionImages';
import { disconnectStream, networkInterrupted, useReplyRecovery } from '../chat/useReplyRecovery';
import { ReplyRecoveryNotice } from '../chat/ReplyRecoveryNotice';
import {
  beginHold,
  cancelHold,
  clearHearingMessage,
  endHold,
  flashHearingHint,
  getHearingState,
  HOLD_TOO_SHORT,
  joinSpeech,
  setHearingPaused,
  setHearingSink,
  startListening,
  stopListening,
  useHearing,
} from "./speech/hearingEngine";
import { HearingBar, HearingPopover, hearingPlaceholder, HoldControls, MicButton } from "./speech/HearingControls";
import { SpeakButton, SpeakerIcon, SpeakerOffIcon, type LocalVoice } from "./speech/LocalVoice";
import type { CharacterMotion } from "./characters/characterView";
import { DEFAULT_CHARACTER, type CharacterModel } from './characters/characterLibrary';
import { useCompanionActivity } from './characters/useCompanionActivity';
import { asStageEmotion, replyEmotion, type StageCue, type StageEmotion } from './characters/characterExpressions';
import { SceneBackdrop, ScenePicker, useCompanionScene } from './CompanionScenes';
import { GlobeIcon } from '../chat/WebSources';
import { readCompanionSearch } from './companionSearch';
import { brainRequest, useBrain, useModels } from './providers/brain';
import { useKeyConfigs } from './speech/voiceProviders';
import type { VoiceStream } from './speech/streamSpeech';
import { beginCompanionTiming, clearCompanionTimings, type HearingTiming, type TurnTiming } from './speech/companionTiming';

const MUTED_KEY = "peto-companion-muted";
const Live2DStage = lazy(() => import("./characters/Live2DStage"));
const VRMStage = lazy(() => import('./characters/VRMStage'));
const CompanionPlayer = lazy(() => import('./ytplayer/CompanionPlayer'));
/** Khóa đọc của Companion có tiền tố riêng, để câu nghe thử trong Cài đặt không làm đổi trạng thái ở đây. */
const SPEECH_PREFIX = "companion-";
/** Tự gửi chờ thêm chừng này sau câu vừa nghe, để kịp nói tiếp nếu chưa xong ý. */
const AUTO_SEND_DELAY = 700;
/**
 * Phần tử có việc riêng với phím Space (gõ chữ, bấm nút, chọn mục): giữ Space ở đó không phải giữ để nói. Như
 * KEY_OWNER_SELECTOR trong voice-hold.ts của AIRI. Nút micro và nút "Giữ để nói" tự xử lý Space của mình.
 */
const SPACE_OWNERS = [
  'input', 'textarea', 'select', 'button', 'a[href]', '[contenteditable]:not([contenteditable="false"])',
  '[role="button"]', '[role="textbox"]', '[role="menuitem"]', '[role="menuitemcheckbox"]', '[role="menuitemradio"]',
  '[role="option"]', '[role="checkbox"]', '[role="switch"]', '[role="slider"]', '[role="tab"]', '[role="combobox"]',
].join(', ');

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) === "1";
  } catch {
    return false;
  }
}

/** Cảm xúc của một câu trả lời: Peto tự chọn, tin cũ không có thì đoán theo từ khóa. */
function messageEmotion(message: Message): StageEmotion | null {
  return asStageEmotion(message.emotion)
    ?? asStageEmotion(message.emotion_cues?.find(item => asStageEmotion(item.emotion))?.emotion)
    ?? replyEmotion(message.content) ?? null;
}

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function SettingsGearIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
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
 * Tab Companion: Peto trò chuyện bằng chữ rồi tự nói thành tiếng
 * bằng âm thanh từ máy tạo giọng chuyển qua VPS. Chỉ có một mạch trò chuyện, tách khỏi danh sách Trò chuyện.
 *
 * Sân khấu bên trái hiển thị Live2D và ghi công model. Mọi thứ
 * để nhắn và nghe nằm ở cột chat; bật giọng nói, chọn giọng, nguồn nghe, tra web… nằm ở trang Cài đặt Companion
 * (/companion/settings/, nút bánh răng ở đầu cột chat; chủ web chốt ngày 13/10/2026).
 * Trên điện thoại, nhân vật phủ cả màn hình; tiêu đề, tin nhắn và ô nhắn nổi trong suốt bên trên như AIRI.
 *
 * Được giữ mounted như Imagine (prop `active`) để câu trả lời đang về không bị cắt khi đổi tab;
 * rời tab thì Peto thôi đọc và giải phóng renderer nhân vật.
 */
export default function Companion({ active, appInfo, voice, characterMotion, character = DEFAULT_CHARACTER, characterLoading = false, onCharacterPreview, onOpenCharacters, sceneRequest = 0, playerRequest = 0, onUnauthorized, onOpenSidebar, onOpenHearingSettings, onOpenSettings }: {
  active: boolean;
  sceneRequest?: number;
  playerRequest?: number;
  appInfo: AppInfo | null;
  voice: LocalVoice;
  characterMotion: CharacterMotion;
  character?: CharacterModel;
  characterLoading?: boolean;
  onCharacterPreview?: (id: string, image: string) => void;
  onOpenCharacters?: () => void;
  onUnauthorized: () => void;
  onOpenSidebar: () => void;
  /** Mở trang Nghe của Cài đặt Companion (từ bảng Micro). */
  onOpenHearingSettings?: () => void;
  /** Mở trang Cài đặt Companion (nút bánh răng ở đầu cột chat). */
  onOpenSettings?: () => void;
}) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  /** Cảm xúc nhân vật giữ suốt câu trả lời, nói xong một lúc thì về null. */
  const [stageEmotion, setStageEmotion] = useState<StageCue | null>(null);
  const cueKey = useRef(0);
  const releaseTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const cue = useCallback((emotion: StageEmotion | null | undefined) => {
    clearTimeout(releaseTimer.current);
    setStageEmotion(emotion ? { emotion, key: ++cueKey.current } : null);
  }, []);
  const releaseLater = useCallback((delay: number) => {
    clearTimeout(releaseTimer.current);
    releaseTimer.current = setTimeout(() => setStageEmotion(null), delay);
  }, []);
  useEffect(() => () => clearTimeout(releaseTimer.current), []);
  /** Số ghi nhớ đang có, hỏi lại lúc mở hộp "Bắt đầu lại": xóa mạch không xóa ghi nhớ, nên hộp nói rõ điều đó. */
  const [keptMemories, setKeptMemories] = useState(0);
  const [loading, setLoading] = useState(true);
  const [stageState, setStageState] = useState<{ id: string; status: 'loading' | 'ready' | 'error' } | null>(null);
  const onStageStatus = useCallback((status: 'loading' | 'ready' | 'error') => {
    setStageState({ id: character.id, status });
  }, [character.id]);
  useEffect(() => { if (!active) setStageState(null); }, [active]);
  // Giữ nguyên kích thước sân khấu khi chờ; chỉ mở giao diện sau khi model đã vẽ và lịch sử đã tải xong.
  const opening = active && (loading || characterLoading || stageState?.id !== character.id || stageState.status === 'loading');
  const [loadFailed, setLoadFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  /** Peto đang tra web cho câu trả lời này (Peto tự quyết; trang không hiện nguồn, theo phương án C chủ web chọn). */
  const [searching, setSearching] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const images = useCompanionImages(setError);
  const imageInput = useRef<HTMLInputElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const [muted, setMuted] = useState(readMuted);
  const [confirmReset, setConfirmReset] = useState(false);
  const [scenesOpen, setScenesOpen] = useState(false);
  const scene = useCompanionScene(character.id);
  useEffect(() => { if (sceneRequest > 0) setScenesOpen(true); }, [sceneRequest]);
  const [resetting, setResetting] = useState(false);
  const hearing = useHearing();
  const [player, setPlayer] = useState({ visited: false, open: false, hidden: false });
  // Sân khấu còn phải chừa thanh bên và cột chat: khung hẹp chuyển sang màn hình Player riêng.
  const mobilePlayer = usePlayerLayout('(max-width: 900px), (max-height: 520px) and (pointer: coarse)');
  const desktopPlayback = usePlayerLayout('(hover: hover) and (pointer: fine)');
  const playerModal = active && player.open && !player.hidden && mobilePlayer;
  const playerBounds = useRef<HTMLDivElement>(null);
  const playerButton = useRef<HTMLButtonElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const playerOwnsKey = useRef(false);
  const playerFocusBack = useRef(false);
  const handledPlayerRequest = useRef(0);
  const updatePlayerFocus = useCallback((ownsKey: boolean) => {
    playerOwnsKey.current = ownsKey;
    if (ownsKey && getHearingState().holding) cancelHold();
  }, []);
  const togglePlayer = useCallback(() => {
    if (getHearingState().holding) cancelHold();
    setPlayer(value => value.open && !value.hidden ? { ...value, hidden: true } : { visited: true, open: true, hidden: false });
  }, []);
  const closePlayer = useCallback(() => {
    playerOwnsKey.current = false;
    playerFocusBack.current = true;
    setPlayer(value => ({ ...value, open: false, hidden: false }));
  }, []);
  const hidePlayer = useCallback(() => {
    playerOwnsKey.current = false;
    playerFocusBack.current = true;
    setPlayer(value => ({ ...value, hidden: true }));
  }, []);
  useEffect(() => {
    if (playerRequest <= handledPlayerRequest.current) return;
    handledPlayerRequest.current = playerRequest;
    togglePlayer();
  }, [playerRequest, togglePlayer]);
  useEffect(() => {
    if (active) return;
    playerOwnsKey.current = false;
    playerFocusBack.current = false;
    if (!desktopPlayback) setPlayer(value => value.open ? { ...value, open: false, hidden: false } : value);
  }, [active, desktopPlayback]);
  useEffect(() => {
    if (!active || !playerFocusBack.current) return;
    playerFocusBack.current = false;
    const trigger = mobilePlayer && menuButton.current?.getClientRects().length ? menuButton.current : playerButton.current;
    trigger?.focus({ preventScroll: true });
  }, [active, player.open, player.hidden, mobilePlayer]);
  // Tên nhà cung cấp khi bộ não dùng khóa riêng, hiện dưới tên nhân vật; đổi trong Cài đặt thì cập nhật ngay.
  const brainChoice = useBrain();
  const providerModels = useModels();
  const providerKeys = useKeyConfigs();
  const brainLabel = useMemo(() => (brainChoice.provider === 'peto' ? '' : brainRequest(false)?.label ?? ''),
    [brainChoice, providerModels, providerKeys]);
  const [micOpen, setMicOpen] = useState(false);
  /** Lúc câu nghe được cuối cùng vào ô nhắn; tự gửi chỉ gửi chữ nghe được, không gửi chữ người dùng tự gõ. */
  const [heardAt, setHeardAt] = useState(0);
  const [hearingNeedsReview, setHearingNeedsReview] = useState(false);
  const draftVersion = useRef(0);
  const draftTiming = useRef<{ hearing: HearingTiming; source: string } | null>(null);
  const spokenTurn = useRef<{ cancelled: boolean; stream: VoiceStream | null; timing: TurnTiming } | null>(null);
  const micRef = useRef<HTMLButtonElement>(null);
  const stopVoice = voice.stop;
  const haltSpeech = useCallback(() => {
    if (spokenTurn.current) {
      spokenTurn.current.cancelled = true;
      spokenTurn.current.timing.finish('stopped');
    }
    stopVoice();
  }, [stopVoice]);
  const loadVersion = useRef(0);
  const loadRef = useRef<AbortController | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  /** Khung tin có đang ở cuối không, cập nhật mỗi lần cuộn. */
  const atBottom = useRef(true);
  const resetRef = useRef<HTMLDialogElement>(null);
  // Luồng chữ và tiếng đều đọc lựa chọn mới nhất, không dùng trạng thái cũ của lúc gửi.
  const foreground = useRef(document.visibilityState !== 'hidden');
  const latest = useRef({ active, muted, voice, foreground: foreground.current });
  const recovery = useReplyRecovery({
    scope: 'companion', conversationId, enabled: active, busy: streaming || loading || resetting,
    onDisconnect: () => { haltSpeech(); disconnectStream(abortRef.current); },
    onUnauthorized,
    onRecovered: (stored) => { setMessages(stored); setError(null); },
  });

  useEffect(() => {
    latest.current = { active, muted, voice, foreground: foreground.current };
  });

  useEffect(() => {
    const suspend = () => {
      foreground.current = false;
      latest.current.foreground = false;
      setHeardAt(0);
      haltSpeech();
      cue(null);
    };
    const visibility = () => {
      if (document.visibilityState === 'hidden') suspend();
      else { foreground.current = true; latest.current.foreground = true; }
    };
    const shown = () => visibility();
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', suspend);
    window.addEventListener('pageshow', shown);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', suspend);
      window.removeEventListener('pageshow', shown);
    };
  }, [haltSpeech, cue]);

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
    if (!active) haltSpeech();
  }, [active, haltSpeech]);

  const previousCharacter = useRef(character.id);
  useEffect(() => {
    if (previousCharacter.current === character.id) return;
    previousCharacter.current = character.id;
    haltSpeech();
    cue(null);
  }, [character.id, haltSpeech, cue]);

  // Giọng nói sống ở App, lâu hơn tab này (đăng xuất thì tab bị gỡ), nên gỡ tab thì cũng thôi đọc.
  useEffect(() => () => { haltSpeech(); clearCompanionTimings(); }, [haltSpeech]);

  useEffect(() => {
    try {
      localStorage.setItem(MUTED_KEY, muted ? "1" : "0");
    } catch {}
    if (muted) haltSpeech();
  }, [muted, haltSpeech]);

  useEffect(() => {
    if (active && confirmReset) resetRef.current?.showModal();
    else resetRef.current?.close();
  }, [active, confirmReset]);

  useEffect(() => {
    if (!confirmReset) return;
    const controller = new AbortController();
    getCompanionMemory(controller.signal).then((state) => setKeptMemories(state.memories.length), () => setKeptMemories(0));
    return () => controller.abort();
  }, [confirmReset]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  // Bàn phím điện thoại mở ra làm khung tin thấp lại mà vị trí cuộn giữ nguyên, nên tin mới nhất bị che và người dùng
  // thấy đoạn giữa hội thoại. Khung đang ở cuối thì bám lại cuối mỗi khi đổi cỡ; đã cuộn lên đọc tin cũ thì để yên.
  useEffect(() => {
    const list = bottomRef.current?.parentElement;
    if (!list || typeof ResizeObserver === "undefined") return;
    const track = () => { atBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 48; };
    const observer = new ResizeObserver(() => { if (atBottom.current) list.scrollTop = list.scrollHeight; });
    list.addEventListener("scroll", track, { passive: true });
    observer.observe(list);
    return () => {
      list.removeEventListener("scroll", track);
      observer.disconnect();
    };
  }, []);

  function reportSpeechError(err: unknown) {
    setError(err instanceof Error ? err.message : "Chưa đọc được tin này.");
  }

  async function send() {
    const text = draft.trim();
    const pendingImages = images.images;
    if ((!text && !pendingImages.length) || images.isPreparing() || getHearingState().interim || abortRef.current || loading || loadFailed || resetting || !recovery.online || recovery.pending) return;
    recovery.cancel();
    setHeardAt(0);
    setHearingNeedsReview(false);
    setMicOpen(false);
    haltSpeech();
    setError(null);
    cue(null);
    const previous = messages;
    const replyIndex = previous.length + 1;
    const optimisticImages = pendingImages.map(image => ({ id: image.id, name: image.file.name,
      mime: image.file.type, kind: 'image' as const, size: image.file.size, url: image.previewUrl ?? '' }));
    setMessages([...previous, { role: "user", content: text, attachments: optimisticImages }, { role: "assistant", content: "" }]);
    setStreaming(true);
    setStopping(false);
    const controller = new AbortController();
    abortRef.current = controller;
    const sentDraftVersion = draftVersion.current;
    const search = readCompanionSearch();
    // Bộ não dùng khóa riêng (Cài đặt Companion → Mô-đun → Bộ não); null là Peto.
    const brain = brainRequest(search);
    const heard = draftTiming.current;
    draftTiming.current = null;
    const timing = beginCompanionTiming({ input: heard ? 'voice' : 'text', hearing: heard?.hearing,
      hearingSource: heard?.source, voiceSource: voice.source, search });
    let speechEpoch = 0;
    const speechTiming = () => {
      const epoch = speechEpoch;
      return { onTextReady: () => { if (epoch === speechEpoch) timing.mark('textReady'); },
        onSynthesisStart: () => { if (epoch === speechEpoch) timing.mark('synthesis'); },
        onPlaying: () => { if (epoch === speechEpoch) timing.mark('playing'); },
        onStopped: () => { if (epoch === speechEpoch) timing.finish('stopped'); } };
    };
    const spoken = { cancelled: false, stream: null as VoiceStream | null, timing };
    spokenTurn.current = spoken;
    let emotionCues: EmotionCue[] = [];
    let expressionApplied = false;
    const showEmotion = (emotion: StageEmotion | null | undefined) => {
      if (!expressionApplied && emotion) { expressionApplied = true; cue(emotion); }
    };
    const expressions = { onEmotion: (value: string) => {
      if (spokenTurn.current === spoken && !spoken.cancelled && latest.current.active && latest.current.foreground && !latest.current.muted) {
        const emotion = asStageEmotion(value);
        showEmotion(emotion);
      }
    } };
    const current = () => abortRef.current === controller && !controller.signal.aborted;
    let earlyVoice = false;
    let accepted = false;
    let completed = false;
    let interrupted = false;
    let activeId = conversationId;
    let storedUserId: number | undefined;
    let reply = "";
    let turnEmotion: StageEmotion | undefined;
    try {
      const attachments = pendingImages.length ? await Promise.all(pendingImages.map(async image => ({
        name: image.file.name, mime: image.file.type, data: await fileToBase64(image.file),
      }))) : [];
      if (!current()) return;
      // Ảnh của tin đã gửi dùng dữ liệu riêng; gỡ ảnh nháp hoặc máy chủ nhận tin không làm hỏng bóng chat.
      if (attachments.length) setMessages(prev => prev.map((message, index) => index === replyIndex - 1
        ? { ...message, attachments: optimisticImages.map((image, i) => ({ ...image, url: `data:${attachments[i].mime || 'image/png'};base64,${attachments[i].data}` })) }
        : message));
      await sendMessage(
        { message: text, conversationId, attachments, effort: "low", webSearch: search ? "auto" : "off", mode: "companion",
          ...(brain ? { provider: brain.provider, providerKey: brain.providerKey, searchKey: brain.searchKey } : {}) },
        {
          onMeta: (id, _effort, stored, voiceStream) => {
            if (!current()) return;
            earlyVoice = voiceStream === true;
            accepted = true;
            activeId = id;
            storedUserId = stored?.id;
            setConversationId(id);
            if (draftVersion.current === sentDraftVersion) setDraft("");
            images.remove(pendingImages.map(image => image.id));
            if (stored) setMessages((prev) => [...prev.slice(0, -2), stored, prev[prev.length - 1]]);
          },
          onDelta: (chunk) => {
            if (!current()) return;
            if (chunk.trim()) timing.mark('firstText');
            reply += chunk;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role !== "assistant") return prev;
              return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
            });
            const now = latest.current;
            if (earlyVoice && !spoken.cancelled && now.active && now.foreground && !now.muted && now.voice.status === 'ready') {
              if (!spoken.stream) {
                const stream = now.voice.stream(`${SPEECH_PREFIX}${replyIndex}`, speechTiming(), { ...expressions, cues: emotionCues });
                spoken.stream = stream;
                stream.done.then(() => {
                  if (spoken.stream === stream) timing.finish(spoken.cancelled ? 'stopped' : 'complete');
                }).catch(err => {
                  if (spokenTurn.current === spoken && spoken.stream === stream && !spoken.cancelled) {
                    spoken.cancelled = true;
                    timing.finish('error');
                    reportSpeechError(err);
                  }
                });
                // Giọng vừa sẵn sàng giữa lượt: giữ cả phần chữ đã về trước đó.
                spoken.stream.push(reply);
              } else {
                spoken.stream.push(chunk);
              }
            }
          },
          // Chỉ chọn một mặt cho cả lượt; có giọng đọc thì chờ tiếng, tắt tiếng thì phản ứng theo chữ.
          onEmotion: (value, offset) => {
            if (!current()) return;
            const emotion = asStageEmotion(value);
            if (!emotion || turnEmotion) return;
            const position = offset ?? reply.length;
            if (!Number.isSafeInteger(position) || position < 0 || position > reply.length) return;
            turnEmotion = emotion;
            emotionCues.push({ emotion, offset: position });
            spoken.stream?.markEmotion(emotion, position);
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              return last?.role === "assistant" ? [...prev.slice(0, -1), {
                ...last, emotion: last.emotion ?? emotion, emotion_cues: [...emotionCues],
              }] : prev;
            });
            const now = latest.current;
            if (now.active && now.foreground && (offset === undefined || now.muted || now.voice.status !== 'ready' || spoken.cancelled)) showEmotion(emotion);
          },
          onSearch: (status) => { if (current()) setSearching(status === 'searching'); },
          // Peto viết vài chữ rồi mới quyết định tra web: máy chủ bỏ phần đó, trang cũng xóa để khỏi ghép hai câu.
          onReplace: () => {
            if (!current()) return;
            speechEpoch++;
            timing.replace();
            // Máy chủ thay bản nháp: bỏ hàng chờ cũ và chỉ đọc bản chốt sau khi lượt xong.
            earlyVoice = false;
            if (spoken.stream) {
              spoken.stream = null; latest.current.voice.stop();
            }
            reply = "";
            // Bản nháp bị bỏ nhưng cả lượt vẫn giữ mặt đầu tiên, không đổi sang mặt của câu chốt.
            turnEmotion = asStageEmotion(emotionCues[0]?.emotion) ?? turnEmotion;
            emotionCues = turnEmotion ? [{ emotion: turnEmotion, offset: 0 }] : [];
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              return last?.role === "assistant" ? [...prev.slice(0, -1), {
                ...last, content: "", emotion_cues: [...emotionCues], emotion: turnEmotion,
              }] : prev;
            });
          },
          onError: (message) => { if (current()) { timing.finish('error'); setError(message); } },
          onDone: () => {
            if (!current()) return;
            completed = true;
            timing.mark('replyDone');
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) {
        // Người dùng dừng: kết quả và lỗi đến muộn của lượt này không được chen vào lượt tiếp theo.
      } else if (err instanceof UnauthorizedError) {
        onUnauthorized();
      } else if (!controller.signal.aborted) {
        interrupted = true;
        setError(err instanceof Error ? err.message : "Mất kết nối tới máy chủ");
      }
    } finally {
      if (!completed) timing.finish(controller.signal.aborted ? 'stopped' : 'error');
      if (!completed) haltSpeech();
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
      setSearching(false);
      setStopping(false);
      abortRef.current = null;
      if ((interrupted || networkInterrupted(controller)) && accepted && activeId && storedUserId !== undefined) {
        recovery.interrupt({ conversationId: activeId, userMessageId: storedUserId });
      }
    }
    const now = latest.current;
    const speaking = completed && reply.trim() && !spoken.cancelled && now.active && now.foreground && !now.muted && now.voice.status === "ready";
    if (completed && reply.trim() && now.active && now.foreground) {
      // Peto quên gắn thẻ thì đoán theo từ khóa như trước. Không đọc thành tiếng thì giữ mặt vài giây để kịp thấy.
      if (!speaking) showEmotion(turnEmotion ?? replyEmotion(reply));
      else if (!emotionCues.length) showEmotion(replyEmotion(reply));
      if (!speaking) releaseLater(6000);
    } else if (!speaking) {
      releaseLater(1500);
    }
    if (speaking) {
      if (spoken.stream) spoken.stream.finish();
      else now.voice.speak(`${SPEECH_PREFIX}${replyIndex}`, reply, {
        timing: speechTiming(), expressions: { ...expressions, cues: emotionCues },
      })
        .then(() => timing.finish(spoken.cancelled ? 'stopped' : 'complete')).catch(err => {
        timing.finish('error');
        if (spokenTurn.current === spoken && !spoken.cancelled) reportSpeechError(err);
      });
    } else if (spoken.stream) {
      haltSpeech();
    } else {
      timing.finish('text-only');
    }
  }

  function stop() {
    setStopping(Boolean(abortRef.current));
    haltSpeech();
    abortRef.current?.abort();
    cue(null);
  }

  async function reset() {
    if (!conversationId || resetting) return;
    recovery.cancel();
    setResetting(true);
    try {
      await deleteConversation(conversationId);
      haltSpeech();
      loadVersion.current += 1;
      setConversationId(null);
      setMessages([]);
      cue(null);
      images.clear();
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
  // Giữ nét mặt của câu đang đọc suốt lúc Peto nói, nói xong thì về bình thường sau một chút.
  useEffect(() => {
    if (!speech) {
      if (expressionSpeechKey.current && !streaming) releaseLater(1500);
      expressionSpeechKey.current = null;
      return;
    }
    if (expressionSpeechKey.current === speech.key) return;
    expressionSpeechKey.current = speech.key;
    const index = Number(speech.key.slice(SPEECH_PREFIX.length));
    const message = messages[index];
    if (message?.role === 'assistant' && !message.emotion_cues?.length) cue(messageEmotion(message));
  }, [speech?.key, messages, streaming, cue, releaseLater]);
  // Chữ nghe được vào ô nhắn, nối sau chữ đang có.
  useEffect(() => {
    if (!active) return;
    // Peto thôi nói và thôi trả lời để nghe người dùng. Giữ nguyên bộ nghe và bản nháp để không mất âm đầu hay chữ đã gõ.
    const interrupt = () => {
      const now = latest.current;
      // Giọng nghe thử trong Cài đặt không phải lời Peto trong hội thoại.
      if (!now.active || (!abortRef.current && !now.voice.speaking?.key.startsWith(SPEECH_PREFIX))) return;
      setHeardAt(0);
      setMicOpen(false);
      setStopping(Boolean(abortRef.current));
      haltSpeech();
      abortRef.current?.abort();
      cue(null);
    };
    setHearingSink({
      onSpeechStart: () => {
        const hearing = getHearingState();
        if (hearing.bargeIn && hearing.listening && !hearing.testing) interrupt();
      },
      // Giữ để nói là người dùng chủ động muốn nói, nên luôn ngắt Peto, không cần bật "Cho phép nói chen".
      onHoldStart: interrupt,
      onFinal: (text, finalized = true, timing) => {
        draftTiming.current = finalized && timing ? { hearing: timing, source: getHearingState().source } : null;
        draftVersion.current++;
        setDraft((previous) => joinSpeech(previous, text));
        setHeardAt(finalized ? Date.now() : 0);
        if (!finalized) setHearingNeedsReview(true);
      },
    });
    return () => setHearingSink(null);
  }, [active, haltSpeech, cue]);

  // Micro chỉ mở khi đang ở Companion: rời tab hay gỡ tab thì thôi nghe (nghe thử trong Cài đặt thì để yên).
  useEffect(() => {
    if (active) return;
    setMicOpen(false);
    const current = getHearingState();
    if (current.listening && !current.testing) stopListening();
  }, [active]);
  useEffect(() => () => {
    const current = getHearingState();
    if (current.listening && !current.testing) stopListening();
    setHearingPaused(false);
  }, []);

  // Peto đang trả lời hay đang nói thì tạm không nghe, để Peto khỏi tự nghe giọng mình qua loa. Giữ để nói thì micro
  // chỉ mở lúc người dùng giữ, nên không cần tạm dừng.
  const replying = streaming || Boolean(speech);
  useEffect(() => {
    setHearingPaused(hearing.mode === 'always' && !hearing.bargeIn && hearing.pauseWhileSpeaking && replying);
  }, [hearing.mode, hearing.bargeIn, hearing.pauseWhileSpeaking, replying]);

  // Giữ để nói: giữ Space ở bất cứ đâu trong Companion, trừ lúc đang gõ chữ, đứng trên nút hay đang mở hộp thoại. Esc
  // trong lúc giữ thì bỏ. Mất tiêu điểm hay rời trang thì bộ nghe tự bỏ lần giữ (hearingEngine).
  const holdArmed = active && hearing.mode === 'hold' && hearing.listening && !hearing.testing;
  useEffect(() => {
    if (!holdArmed) return;
    const down = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && getHearingState().holding) {
        event.preventDefault();
        cancelHold();
        return;
      }
      if (event.code !== 'Space' || event.defaultPrevented || playerOwnsKey.current || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.target instanceof Element && event.target.closest('.yt-player')) return;
      if (event.target instanceof Element && event.target.closest(SPACE_OWNERS)) return;
      if (document.querySelector('dialog[open]')) return;
      // Trang thuộc về phím này khi đã bật Giữ để nói; không chặn thì Space cuộn trang.
      event.preventDefault();
      if (!event.repeat) beginHold();
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || !getHearingState().holding) return;
      event.preventDefault();
      if (endHold() === 'short') flashHearingHint(HOLD_TOO_SHORT);
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, [holdArmed]);

  // Tự gửi: câu nghe được đã vào ô nhắn, người dùng không nói tiếp một lúc thì gửi.
  const latestSend = useRef(send);
  useEffect(() => {
    latestSend.current = send;
  });
  // Giữ để nói: thả ra là đã nói xong, nên gửi ngay khi chữ đã chốt, không chờ thêm.
  useEffect(() => {
    if (!heardAt || hearingNeedsReview || !hearing.autoSend || !hearing.listening || hearing.testing) return;
    const hold = hearing.mode === 'hold';
    const settled = hold ? hearing.phase === 'ready' && !hearing.holding : hearing.phase === 'waiting';
    if (hearing.interim || !settled || replying || images.pending || !draft.trim()) return;
    const timer = window.setTimeout(() => void latestSend.current(), hold ? 0 : AUTO_SEND_DELAY);
    return () => window.clearTimeout(timer);
  }, [heardAt, hearingNeedsReview, hearing.autoSend, hearing.listening, hearing.testing, hearing.interim, hearing.phase,
    hearing.mode, hearing.holding, replying, draft, images.pending]);

  const closeMic = useCallback(() => setMicOpen(false), []);
  // Bảng Micro chỉ hiện trong lúc nghe: tắt bằng nút lớn hay dừng vì lỗi thì đóng luôn, để thấy câu báo lỗi.
  useEffect(() => {
    if (!hearing.listening) setMicOpen(false);
  }, [hearing.listening]);

  function toggleMic() {
    const current = getHearingState();
    if (current.listening && !current.testing) {
      stopListening({ keepInterim: true });
      setMicOpen(false);
      return;
    }
    clearHearingMessage();
    // Giữ để nói không mở bảng Micro: thanh "Giữ Space hoặc nút micro để nói" hiện ngay trên ô nhắn.
    if (current.mode !== 'hold') setMicOpen(true);
    void startListening();
  }

  const hearingOn = hearing.listening && !hearing.testing;
  // Giữ để nói đã bật nhưng chưa giữ thì micro còn đóng: không tô viền ô nhắn như đang nghe.
  const hearingLive = hearingOn && (hearing.mode === 'always' || hearing.holding || hearing.phase === 'transcribing');
  const interim = hearingOn ? hearing.interim : "";
  const { activity, noteTyping, typing } = useCompanionActivity(active, streaming, speech?.phase ?? null,
    hearingOn && (hearing.holding || hearing.phase === 'speaking' || hearing.phase === 'transcribing'));
  const stateText = speech?.phase === "playing" ? "Đang nói…"
    : speech?.phase === "buffering" ? "Đang chờ tiếng…"
      : speech?.phase === "loading" ? "Sắp nói…"
        : searching ? "Đang tra web…" : streaming ? "Đang nhắn…"
          : brainLabel;
  const canSend = (draft.trim().length > 0 || images.images.length > 0) && !images.pending && !interim && !streaming && !loading && !resetting && !loadFailed && recovery.online && !recovery.pending;

  function addImages(files: FileList | File[]) {
    if (loading || resetting) return;
    setHeardAt(0);
    void images.add(files);
  }

  return (
    <main className={`companion${scene.selected.url ? ' companion-with-scene' : ''}${opening ? ' companion-loading' : ''}`} hidden={!active}>
      {opening && <div className="companion-loading-screen"><LoadingIndicator variant="screen" label="Loading" /></div>}
      {active && scenesOpen && <ScenePicker scene={scene} onClose={() => setScenesOpen(false)} />}
      <SceneBackdrop scene={scene} />
      <section className="companion-stage" aria-label={name} inert={opening || playerModal} aria-hidden={opening || playerModal}>
        {active && !characterLoading && <Suspense fallback={null}>
          {character.format === 'vrm'
            ? <VRMStage key={character.id} character={character} motion={characterMotion} onPreview={onCharacterPreview} onStatusChange={onStageStatus} activity={activity} emotion={stageEmotion} thinking={streaming && !stopping} attention={{ typing, input: composerInput }} />
            : <Live2DStage key={character.id} character={character} fallbackUrl={appInfo?.avatar_url ?? undefined} name={name} motion={characterMotion} onPreview={onCharacterPreview} onStatusChange={onStageStatus} emotion={stageEmotion} activity={activity} thinking={streaming && !stopping} attention={{ typing, input: composerInput }} />}
        </Suspense>}
      </section>

      <section className="companion-panel" aria-label="Trò chuyện trong Companion" inert={opening || playerModal} aria-hidden={opening || playerModal}>
        <header className="companion-head">
          <button ref={menuButton} type="button" className="menu-btn companion-menu" aria-label="Mở menu" onClick={onOpenSidebar}>
            <MenuIcon />
          </button>
          <button
            type="button"
            className="companion-title"
            aria-label={`Đổi nhân vật ${name}`}
            data-tip="Đổi nhân vật"
            onClick={onOpenCharacters}
          >
            <strong>
              {name}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </strong>
            {stateText && <span aria-live="polite">{stateText}</span>}
          </button>
          <div className="companion-tools">
            {voice.status === "ready" && (
              <button
                type="button"
                className="companion-tool"
                aria-label="Tắt tiếng"
                aria-pressed={muted}
                data-tip={muted ? "Bật tiếng" : "Tắt tiếng"}
                onClick={() => setMuted((value) => !value)}
              >
                {muted ? <SpeakerOffIcon /> : <SpeakerIcon />}
              </button>
            )}
            {onOpenSettings && (
              <button type="button" className="companion-tool" aria-label="Cài đặt Companion" data-tip onClick={onOpenSettings}>
                <SettingsGearIcon />
              </button>
            )}
            <button
              type="button"
              className="companion-tool"
              aria-label="Bắt đầu lại"
              data-tip
              disabled={!conversationId || streaming || resetting}
              onClick={() => setConfirmReset(true)}
            >
              <RestartIcon />
            </button>
          </div>
        </header>

        {voice.notice && <div className="companion-notice" role="status">{voice.notice}</div>}
        {hearing.message && !hearing.testing && (
          <div className="companion-notice" role="alert">
            <span>{hearing.message}</span>
            <button type="button" onClick={clearHearingMessage}>Đóng</button>
          </div>
        )}
        {voice.status === "missing" && (
          <div className="companion-notice">
            <span>{voice.problem || "Chưa thấy máy chủ giọng nói."} Peto chỉ nhắn chữ.</span>
            {/* Thiếu khóa thì dò lại cũng vậy: phải vào Cài đặt Companion → Giọng nói. */}
            {(voice.source === "official" || voice.source === "home") && (
              <button type="button" onClick={voice.recheck}>Kiểm tra lại</button>
            )}
          </div>
        )}

        <div className="companion-messages">
          {loading && <div className="loading-chat"><LoadingIndicator label="Đang mở Companion" /></div>}
          {loadFailed && (
            <div className="loading-chat" role="alert">
              <p>Chưa tải được cuộc trò chuyện.</p>
              <button type="button" className="load-more" onClick={() => void load()}>Thử lại</button>
            </div>
          )}
          {messages.map((message, index) => {
            if (message.role === "user") {
              return (
                <article key={index} className="bubble user">
                  <CompanionMessageImages attachments={message.attachments} />
                  {message.content && <p>{message.content}</p>}
                </article>
              );
            }
            const live = streaming && index === messages.length - 1;
            const key = `${SPEECH_PREFIX}${index}`;
            return (
              <article key={index} className="bubble assistant companion-reply">
                {message.content
                  ? <p>{message.content}</p>
                  : live && (searching
                    ? <p className="companion-typing companion-searching" aria-hidden="true"><GlobeIcon /> Đang tra web…</p>
                    : <p className="companion-typing" aria-hidden="true">…</p>)}
                {message.content && !live && voice.status === "ready" && (
                  <SpeakButton
                    phase={voice.speaking?.key === key ? voice.speaking.phase : null}
                    onSpeak={() => {
                      haltSpeech();
                      // Tin cũ có nhiều mốc vẫn chỉ dùng mặt đầu tiên cho toàn bộ lời đọc.
                      const emotion = messageEmotion(message);
                      const cues = message.emotion_cues?.length && emotion ? [{ emotion, offset: 0 }] : undefined;
                      cue(cues?.length ? null : messageEmotion(message));
                      void voice.speak(key, message.content, { expressions: cues?.length ? {
                        cues, onEmotion: value => { if (latest.current.active) cue(asStageEmotion(value)); },
                      } : undefined }).catch(reportSpeechError);
                    }}
                    onStop={stop}
                  />
                )}
                {message.status === "incomplete" && <span className="message-status">Chưa trả lời xong</span>}
              </article>
            );
          })}
          <div ref={bottomRef} />
        </div>

        <ReplyRecoveryNotice recovery={recovery} />
        {error && !recovery.pending && recovery.status !== 'failed' && (
          <div className="error" role="alert">
            {error}
            <button type="button" className="dismiss-error" aria-label="Đóng thông báo" onClick={() => setError(null)}>×</button>
          </div>
        )}

        <form
          className="companion-composer"
          onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
          onDrop={event => {
            if (event.dataTransfer.files.length) { event.preventDefault(); addImages(event.dataTransfer.files); }
          }}
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          {micOpen && active && (
            <HearingPopover
              anchorRef={micRef}
              onClose={closeMic}
              onOpenSettings={onOpenHearingSettings ? () => { setMicOpen(false); onOpenHearingSettings(); } : undefined}
            />
          )}
          <HearingBar />
          {active && <HoldControls />}
          {images.pending > 0 && <p className="companion-image-status" role="status">Đang chuẩn bị ảnh…</p>}
          <div className={`composer${hearingLive ? ' listening' : ''}${images.images.length ? ' has-images' : ''}`}>
            <CompanionImageDrafts images={images.images} onRemove={id => { setHeardAt(0); images.remove([id]); }} />
            <input ref={imageInput} type="file" hidden multiple accept="image/jpeg,image/png,image/webp,image/gif"
              aria-label="Chọn ảnh cho Companion" onChange={event => {
                if (event.target.files) addImages(event.target.files);
                event.target.value = '';
              }} />
            <textarea
              ref={composerInput}
              value={interim ? joinSpeech(draft, interim) : draft}
              rows={1}
              placeholder={hearingPlaceholder(hearing) ?? "Nhắn cho Peto…"}
              aria-label="Nhắn cho Peto trong Companion"
              disabled={loading || resetting}
              readOnly={Boolean(interim)}
              onBlur={() => noteTyping(false)}
              onPaste={event => {
                if (event.clipboardData.files.length) { event.preventDefault(); addImages(event.clipboardData.files); }
              }}
              onChange={(event) => {
                setDraft(event.target.value);
                draftVersion.current++;
                draftTiming.current = null;
                noteTyping(Boolean(event.target.value.trim()));
                setHeardAt(0);
                setHearingNeedsReview(false);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  if (!interim) void send();
                }
              }}
            />
            <div className="composer-bar">
              <div className="companion-compose-tools">
                <button type="button" className="companion-image-button" aria-label="Đính kèm ảnh" data-tip
                  disabled={loading || resetting} onClick={() => imageInput.current?.click()}>
                  <CompanionImageIcon />
                </button>
                <MicButton onClick={toggleMic} buttonRef={micRef} />
              </div>
              {replying && (
                <button type="button" className="stop" disabled={stopping} onClick={stop}>
                  {stopping ? "Đang dừng…" : "Dừng"}
                </button>
              )}
              {!streaming && (
                <button type="submit" className="send" disabled={!canSend} aria-label="Gửi">
                  <span className="send-text">Gửi</span> <SendIcon />
                </button>
              )}
            </div>
          </div>
        </form>
      </section>

      <div ref={playerBounds} className="companion-player-area">
        {player.visited && <Suspense fallback={null}>
          <CompanionPlayer active={active} open={player.open} hidden={player.hidden || !active} mobileLayout={mobilePlayer}
            allowBackground={desktopPlayback} bounds={playerBounds}
            onClose={closePlayer} onHide={hidePlayer} onFocusChange={updatePlayerFocus} />
        </Suspense>}
      </div>
      <div className="companion-scene-tools" inert={opening || playerModal} aria-hidden={opening || playerModal}>
        <button type="button" className="companion-scene-button" aria-label="Bối cảnh" data-tip aria-haspopup="dialog" onClick={() => setScenesOpen(true)}>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.7" /><circle cx="9" cy="8" r="2" stroke="currentColor" strokeWidth="1.7" /><path d="m4 18 5-5 3 3 4-6 5 8" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>
        </button>
        <button type="button" className="companion-scene-button" onClick={onOpenCharacters} aria-label="Nhân vật" data-tip>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.7" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
        </button>
        <button ref={playerButton} type="button" className="companion-scene-button companion-player-button" aria-label="Player" data-tip
          aria-expanded={player.open && !player.hidden} aria-controls="companion-player" onClick={togglePlayer}>
          <PlayerIcon />
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
        {keptMemories > 0 && (
          <p>Những điều Peto ghi nhớ về bạn vẫn được giữ; muốn xóa thì vào Cài đặt → Trí nhớ.</p>
        )}
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
