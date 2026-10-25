/**
 * Thẻ nhân vật Companion của tài khoản (như thẻ AIRI, chủ web chốt 25/10/2026): danh sách thẻ và thẻ đang dùng, lấy từ
 * máy chủ, dùng chung cho nút Profile ở Companion và các trang cài đặt. Thẻ nằm ở máy chủ nên đồng bộ giữa các máy;
 * model hiển thị thì vẫn nằm trong trình duyệt (thư viện nhân vật).
 */
import { useSyncExternalStore } from 'react';
import {
  UnauthorizedError,
  createCompanionCard,
  deleteCompanionCard,
  listCompanionCards,
  resetCompanionCard,
  setActiveCompanionCard,
  updateCompanionCard,
  type CompanionCard,
  type CompanionCardFields,
} from '../../../shared/api/api';

export interface CardsState {
  status: 'idle' | 'loading' | 'ready' | 'error';
  active: string;
  cards: CompanionCard[];
}

const IDLE: CardsState = { status: 'idle', active: 'peto', cards: [] };
let state = IDLE;
let owner: string | undefined;
let loading: Promise<CardsState> | null = null;
const listeners = new Set<() => void>();

function set(next: CardsState) {
  state = next;
  listeners.forEach(listener => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useCompanionCards(): CardsState {
  return useSyncExternalStore(subscribe, () => state, () => state);
}

export function getCompanionCards(): CardsState {
  return state;
}

export function activeCard(value: CardsState = state): CompanionCard | undefined {
  return value.cards.find(card => card.id === value.active);
}

/** Tải thẻ của ``account`` (một lần; ``force`` để hỏi lại). Đổi tài khoản thì bỏ thẻ của tài khoản cũ. */
export function loadCompanionCards(account: string | undefined, force = false): Promise<CardsState> {
  if (account !== owner) {
    owner = account;
    loading = null;
    set(IDLE);
  }
  if (loading && !force) return loading;
  const mine = account;
  if (state.status !== 'ready') set({ ...state, status: 'loading' });
  loading = Promise.resolve().then(() => listCompanionCards()).then(body => {
    // Máy chủ cũ (chưa có thẻ) hay câu trả lời lạ: coi như chưa tải được, Companion vẫn chạy với tên mặc định.
    if (!Array.isArray(body?.cards) || typeof body.active_card !== 'string') throw new Error('Không đọc được thẻ nhân vật.');
    if (mine === owner) set({ status: 'ready', active: body.active_card, cards: body.cards });
    return state;
  }).catch((error: unknown) => {
    if (mine === owner && state.status !== 'ready') set({ ...state, status: 'error' });
    loading = null;
    if (error instanceof UnauthorizedError) throw error;
    return state;
  });
  return loading;
}

/** Thẻ của mạch vừa mở (máy chủ đã đổi thẻ đang dùng): chỉ cập nhật trang, không gọi lại máy chủ. */
export function markActiveCard(cardId: string) {
  if (state.active !== cardId) set({ ...state, active: cardId });
}

/** Đổi thẻ đang dùng (Profile). Hỏng thì về lại thẻ cũ và báo lỗi cho nơi gọi. */
export async function pickCompanionCard(cardId: string): Promise<void> {
  const previous = state.active;
  markActiveCard(cardId);
  try {
    await setActiveCompanionCard(cardId);
  } catch (error) {
    markActiveCard(previous);
    throw error;
  }
}

/** "Lưu thành Profile mới": nhân bản thẻ đang dùng với tên mới, rồi dùng thẻ mới (profile-switcher-popover của AIRI). */
export async function saveCompanionCardAs(name: string): Promise<CompanionCard> {
  const current = activeCard();
  if (!current) throw new Error('Chưa tải được thẻ nhân vật.');
  const { id: _id, is_default: _default, modified: _modified, created_at: _created, updated_at: _updated, ...fields } = current;
  const card = await createCompanionCard({ ...fields, name });
  set({ ...state, cards: [...state.cards, card] });
  await pickCompanionCard(card.id);
  return card;
}

/** Ghi model hiển thị vào thẻ đang dùng (chọn nhân vật ở trang Nhân vật = đổi "Body / Display Model" của thẻ). */
export async function setActiveCardModel(modelId: string): Promise<void> {
  const current = activeCard();
  if (!current || current.display_model === modelId) return;
  const card = await updateCompanionCard(current.id, { display_model: modelId });
  set({ ...state, cards: state.cards.map(item => item.id === card.id ? card : item) });
}

function upsert(card: CompanionCard) {
  const exists = state.cards.some(item => item.id === card.id);
  set({ ...state, cards: exists ? state.cards.map(item => item.id === card.id ? card : item) : [...state.cards, card] });
}

/** Trang Thẻ nhân vật → Tạo thẻ mới. */
export async function createCard(fields: CompanionCardFields): Promise<CompanionCard> {
  const card = await createCompanionCard(fields);
  upsert(card);
  return card;
}

/** Trình sửa thẻ: chỉ gửi các trường đã đổi. */
export async function saveCard(cardId: string, fields: CompanionCardFields): Promise<CompanionCard> {
  const card = await updateCompanionCard(cardId, fields);
  upsert(card);
  return card;
}

/** Xóa thẻ tự tạo (máy chủ xóa luôn hội thoại của nó); thẻ đang dùng bị xóa thì máy chủ trả về thẻ Peto. */
export async function removeCard(cardId: string): Promise<number> {
  const result = await deleteCompanionCard(cardId);
  set({ ...state, active: result.active_card, cards: state.cards.filter(item => item.id !== cardId) });
  return result.conversations_deleted;
}

/** "Khôi phục bản gốc" của thẻ Peto mặc định. */
export async function resetDefaultCard(): Promise<CompanionCard> {
  const card = await resetCompanionCard();
  upsert(card);
  return card;
}

/** Chỉ cho test: về trạng thái ban đầu. */
export function resetCompanionCards() {
  owner = undefined;
  loading = null;
  state = IDLE;
}
