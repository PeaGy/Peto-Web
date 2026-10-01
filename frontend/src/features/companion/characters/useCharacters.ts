import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DEFAULT_CHARACTER, SELECTED_CHARACTER_KEY, characterError, listCharacters, readSelectedCharacter,
  removeCharacter, saveCharacter, updateCharacter, writeSelectedCharacter, type CharacterFormat, type CharacterModel, type CharacterImport,
} from './characterLibrary';

export function useCharacters() {
  const [models, setModels] = useState<CharacterModel[]>([DEFAULT_CHARACTER]);
  const [selectedId, setSelectedId] = useState(readSelectedCharacter);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const modelsRef = useRef(models);
  modelsRef.current = models;
  const refresh = useCallback(async () => {
    const next = await listCharacters();
    setModels(next);
    const saved = readSelectedCharacter();
    const id = next.some(model => model.id === saved) ? saved : DEFAULT_CHARACTER.id;
    setSelectedId(id);
    if (id !== saved) writeSelectedCharacter(id);
  }, []);
  useEffect(() => {
    let alive = true;
    void listCharacters().then(next => {
      if (!alive) return;
      setModels(next);
      const saved = readSelectedCharacter();
      setSelectedId(next.some(model => model.id === saved) ? saved : DEFAULT_CHARACTER.id);
    }).catch(reason => { if (alive) setError(characterError(reason)); }).finally(() => { if (alive) setLoading(false); });
    const changed = (event: StorageEvent) => {
      if (event.key === SELECTED_CHARACTER_KEY) void refresh().catch(() => {});
    };
    window.addEventListener('storage', changed);
    return () => { alive = false; window.removeEventListener('storage', changed); };
  }, [refresh]);

  const select = useCallback((id: string) => {
    writeSelectedCharacter(id); setSelectedId(id);
  }, []);
  const addPrepared = async (data: CharacterImport) => {
    if (modelsRef.current.length >= 21) throw new Error('Bạn có thể giữ tối đa 20 model riêng. Hãy xóa bớt trước khi thêm.');
    await saveCharacter(data); // Chỉ chọn sau khi cả metadata và tài nguyên đã lưu thành công.
    await refresh();
    select(data.model.id);
    setError('');
  };
  const add = async (files: File[], format: CharacterFormat) => {
    const { importCharacter } = await import('./characterImport');
    await addPrepared(await importCharacter(files, format));
  };
  const rename = async (id: string, name: string) => {
    const model = modelsRef.current.find(item => item.id === id);
    if (!model || model.builtin) return;
    if (!name.trim()) throw new Error('Tên nhân vật không được để trống.');
    await updateCharacter(id, { name: name.trim().slice(0, 80) });
    await refresh();
  };
  const remove = async (id: string) => {
    await removeCharacter(id);
    if (readSelectedCharacter() === id) select(DEFAULT_CHARACTER.id);
    await refresh();
  };
  const savePreview = useCallback((id: string, preview: string) => {
    const model = modelsRef.current.find(item => item.id === id);
    if (!model) return;
    setModels(previous => previous.map(item => item.id === id ? { ...item, preview } : item));
    void updateCharacter(id, { preview }).catch(() => {});
  }, []);
  return { models, selected: models.find(model => model.id === selectedId) ?? DEFAULT_CHARACTER, loading, error, select, add, addPrepared, rename, remove, savePreview };
}
export type CharacterLibrary = ReturnType<typeof useCharacters>;
