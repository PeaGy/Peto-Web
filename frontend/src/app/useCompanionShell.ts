import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { NavigateFunction } from 'react-router';
import { activeCard, setActiveCardModel, useCompanionCards } from '../features/companion/cards/companionCards';
import { readCharacterMotion, writeCharacterMotion, type CharacterMotion } from '../features/companion/characters/characterView';
import { useCharacters } from '../features/companion/characters/useCharacters';
import { useLocalVoice } from '../features/companion/speech/LocalVoice';
import { companionSettingsRoute, VIEW_PATHS } from './routes';

/** Phần App giữ cho Companion: nhân vật, chuyển động, giọng của thẻ đang dùng và các lối mở trang cài đặt của nó.
 * Tách khỏi App.tsx (G3.3, 13/11/2026); thân các hàm giữ nguyên. */
export function useCompanionShell(view: string, navigate: NavigateFunction, companionSettingsView: string | null) {
  const [characterMotion, setCharacterMotion] = useState<CharacterMotion>(readCharacterMotion);
  const characters = useCharacters();
  const characterIds = useMemo(() => characters.models.map(model => model.id), [characters.models]);
  // Model hiển thị thuộc thẻ nhân vật đang dùng ("Body / Display Model" của thẻ AIRI): người dùng đổi nhân vật (trang
  // Nhân vật, nhập model mới) thì ghi vào thẻ. Bỏ qua giá trị đầu tiên, để model của máy này không đè thẻ từ máy khác.
  const selectedCharacter = characters.selected.id;
  const lastCharacter = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (characters.loading) return;
    if (lastCharacter.current !== undefined && lastCharacter.current !== selectedCharacter) {
      void setActiveCardModel(selectedCharacter).catch(() => {});
    }
    lastCharacter.current = selectedCharacter;
  }, [selectedCharacter, characters.loading]);
  const [sceneRequest, setSceneRequest] = useState(0);
  const [playerRequest, setPlayerRequest] = useState(0);
  const changeCharacterMotion = useCallback((value: CharacterMotion) => {
    setCharacterMotion(value);
    writeCharacterMotion(value);
  }, []);
  const [companionVisited, setCompanionVisited] = useState(view === "companion");
  // Giọng nói dùng chung cho Companion và mục Giọng nói trong Cài đặt. Chỉ dò 127.0.0.1 sau khi đã mở
  // Companion hoặc lúc Cài đặt đang mở, để tab Trò chuyện không gọi gì ra máy.
  // Giọng nói dùng ở Companion và trang cài đặt của nó (cũng là tab Companion), nên chỉ dò sau khi đã mở Companion.
  // Thẻ nhân vật đang dùng có giọng riêng (Mô-đun của thẻ) thì Companion đọc bằng giọng đó.
  const companionCards = useCompanionCards();
  const cardVoiceChoice = activeCard(companionCards)?.modules.voice;
  const cardVoice = useMemo(() => (cardVoiceChoice?.source
    ? { source: cardVoiceChoice.source, model: cardVoiceChoice.model, voice: cardVoiceChoice.voice } : null),
  [cardVoiceChoice?.source, cardVoiceChoice?.model, cardVoiceChoice?.voice]);
  const localVoice = useLocalVoice(companionVisited, cardVoice);
  // Nút cài đặt trong bảng Micro mở thẳng trang Nghe của Cài đặt Companion.
  const openHearingSettings = useCallback(() => navigate(companionSettingsRoute('hearing')), [navigate]);
  const openCompanionSettings = useCallback(() => navigate(companionSettingsRoute('home')), [navigate]);
  // "Quản lý Profile" trong menu Profile: trang Thẻ nhân vật.
  const openCompanionCards = useCallback(() => navigate(companionSettingsRoute('cards')), [navigate]);
  // Đổi nhân vật (tên nhân vật, nút người cạnh sân khấu, mục Nhân vật trên thanh bên điện thoại): trang Cài đặt → Nhân vật.
  const openCharacters = useCallback(() => navigate(companionSettingsRoute('character')), [navigate]);
  // Mục Bối cảnh trên thanh bên điện thoại: ở sân khấu thì mở hộp Bối cảnh, ở trang cài đặt thì sang trang Bối cảnh.
  const openScenes = useCallback(() => {
    if (companionSettingsView) navigate(companionSettingsRoute('scene'));
    else setSceneRequest(value => value + 1);
  }, [companionSettingsView, navigate]);
  const openPlayer = useCallback(() => {
    navigate(VIEW_PATHS.companion);
    setPlayerRequest(value => value + 1);
  }, [navigate]);
  return { characterMotion, changeCharacterMotion, characters, characterIds, sceneRequest, playerRequest, setPlayerRequest,
    companionVisited, setCompanionVisited, localVoice, openHearingSettings, openCompanionSettings, openCompanionCards, openCharacters,
    openScenes, openPlayer };
}
