import type { Persona } from '../../shared/api/api';
import type { DraftFile } from './files';

export const CHAT_DRAFT_PREFIX = 'peto.chat-draft.v1:';
export type NewChatContext = { ownerId: string; projectId: string | null; persona: Persona };
export type DraftScope = { ownerId: string; conversationId: string | null; projectId: string | null; persona: Persona };
type Draft = { text: string; files: DraftFile[]; revision: number };
export type DraftSnapshot = { key: string; revision: number; fileIds: string[] };

export function draftKey(scope: DraftScope): string {
  return CHAT_DRAFT_PREFIX + JSON.stringify(scope.conversationId
    ? [scope.ownerId, 'conversation', scope.conversationId]
    : [scope.ownerId, 'new', scope.projectId, scope.persona]);
}

export function newChatContext(state: unknown, ownerId: string, roleplayConfirmed: boolean): NewChatContext {
  const value = (state as { chatDraftContext?: NewChatContext } | null)?.chatDraftContext;
  if (value?.ownerId === ownerId && (value.projectId === null || typeof value.projectId === 'string')
    && (value.persona === 'assistant' || (value.persona === 'roleplay' && roleplayConfirmed))) return value;
  return { ownerId, projectId: null, persona: 'assistant' };
}

/** Chỉ lưu chữ; File và URL xem trước thuộc bộ nhớ của tab, không đi vào storage. */
export class ChatDraftStore {
  private drafts = new Map<string, Draft>();
  private dirty = new Set<string>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private owner: string | null = null;
  constructor(private storage: () => Storage = () => sessionStorage) {}

  get(key: string): Draft {
    let draft = this.drafts.get(key);
    if (!draft) {
      let text = '';
      try {
        const saved: unknown = JSON.parse(this.storage().getItem(key) ?? 'null');
        if (saved && typeof saved === 'object' && 'text' in saved && typeof saved.text === 'string') text = saved.text;
      } catch { /* Storage bị chặn hoặc dữ liệu hỏng: vẫn dùng được ô soạn. */ }
      draft = { text, files: [], revision: 0 };
      this.drafts.set(key, draft);
    }
    return draft;
  }

  setOwner(owner: string | null) {
    if (this.owner && this.owner !== owner) this.remove(key => this.parts(key)?.[0] === this.owner);
    this.owner = owner;
    this.removeStored(key => !owner || this.parts(key)?.[0] !== owner);
  }

  setText(key: string, text: string) {
    const draft = this.get(key);
    if (draft.text === text) return;
    draft.text = text;
    draft.revision++;
    this.dirty.add(key);
    if (this.timer === undefined) this.timer = setTimeout(() => this.flush(), 250);
  }

  setFiles(key: string, update: DraftFile[] | ((files: DraftFile[]) => DraftFile[])) {
    const draft = this.get(key);
    draft.files = typeof update === 'function' ? update(draft.files) : update;
  }

  snapshot(key: string): DraftSnapshot {
    const draft = this.get(key);
    return { key, revision: draft.revision, fileIds: draft.files.map(file => file.id) };
  }

  accept(snapshot: DraftSnapshot, conversationId?: string) {
    // Không đọc lại storage ở đây: callback của phiên đã đóng không được hồi sinh nháp.
    const draft = this.drafts.get(snapshot.key);
    if (!draft) return;
    if (draft.revision === snapshot.revision) {
      draft.text = '';
      draft.revision++;
      this.dirty.add(snapshot.key);
    }
    draft.files = draft.files.filter(file => !snapshot.fileIds.includes(file.id));
    const parts = this.parts(snapshot.key);
    if (conversationId && parts?.[1] === 'new' && typeof parts[0] === 'string') {
      const targetKey = draftKey({ ownerId: parts[0], conversationId, projectId: null, persona: 'assistant' });
      const target = this.get(targetKey);
      // Chữ gõ sau lần gửi đầu đi theo ID vừa cấp; không đè một bản nháp đích đã có.
      if (!target.text && !target.files.length) {
        target.text = draft.text;
        target.files = draft.files;
        target.revision++;
        draft.text = '';
        draft.files = [];
        draft.revision++;
        this.dirty.add(targetKey);
        this.dirty.add(snapshot.key);
      }
    }
    // URL của tệp vừa gửi còn được tin nhắn tạm dùng; App thu hồi khi lượt gửi kết thúc.
    this.flush();
  }

  removeConversation(id: string) { this.remove(key => this.parts(key)?.[1] === 'conversation' && this.parts(key)?.[2] === id); }
  removeProject(id: string) { this.remove(key => this.parts(key)?.[1] === 'new' && this.parts(key)?.[2] === id); }
  clear() { this.remove(() => true); }

  flush() {
    clearTimeout(this.timer);
    this.timer = undefined;
    for (const key of this.dirty) {
      const draft = this.drafts.get(key);
      try {
        if (draft?.text) this.storage().setItem(key, JSON.stringify({ text: draft.text }));
        else this.storage().removeItem(key);
      } catch { /* Hết dung lượng hoặc storage bị chặn: giữ nháp trong bộ nhớ. */ }
    }
    this.dirty.clear();
  }

  releaseFiles() {
    for (const draft of this.drafts.values()) {
      for (const file of draft.files) if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
      draft.files = [];
    }
  }

  private parts(key: string): unknown[] | null {
    try { const value: unknown = JSON.parse(key.slice(CHAT_DRAFT_PREFIX.length)); return Array.isArray(value) ? value : null; }
    catch { return null; }
  }

  private removeStored(matches: (key: string) => boolean) {
    try {
      const storage = this.storage();
      const keys = Array.from({ length: storage.length }, (_, i) => storage.key(i));
      for (const key of keys) if (key?.startsWith(CHAT_DRAFT_PREFIX) && matches(key)) storage.removeItem(key);
    } catch { /* Không để storage ảnh hưởng đăng nhập/đăng xuất. */ }
  }

  private remove(matches: (key: string) => boolean) {
    for (const [key, draft] of this.drafts) if (matches(key)) {
      for (const file of draft.files) if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
      this.drafts.delete(key);
      this.dirty.delete(key);
    }
    this.removeStored(matches);
    if (!this.dirty.size) { clearTimeout(this.timer); this.timer = undefined; }
  }
}
