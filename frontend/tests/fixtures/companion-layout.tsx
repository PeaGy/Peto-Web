import { useState } from 'react';
import CharacterPicker from '../../src/CharacterPicker';
import { createRoot } from 'react-dom/client';
import Companion from '../../src/Companion';
import { DEFAULT_CHARACTER } from '../../src/characterLibrary';
import { saveScenePreference } from '../../src/sceneLibrary';
import '../../src/styles.css';
const character = { ...DEFAULT_CHARACTER, id: 'test-companion-layout' };
saveScenePreference(character.id, { id: 'room', dim: 10, blur: 0 });
const originalFetch = window.fetch.bind(window);
window.fetch = (input, init) => String(input) === '/api/companion'
  ? Promise.resolve(new Response(JSON.stringify({ conversation_id: 'preview', messages: [
    { role: 'user', content: 'Hello Peto!' }, { role: 'assistant', content: 'Hi Peargy! Welcome to our cozy little room.' },
    { role: 'user', content: 'The new background looks nice.' }, { role: 'assistant', content: 'Make yourself comfortable. What would you like to chat about?' },
  ] }), { headers: { 'Content-Type': 'application/json' } })) : originalFetch(input, init);
const noop = () => {};
function Preview() { const [open, setOpen] = useState(false); return <>{open && <CharacterPicker onClose={() => setOpen(false)} library={{ models: [character], selected: character, loading: false, error: '', select: noop, add: async () => {}, addPrepared: async () => {}, rename: async () => {}, remove: async () => {}, savePreview: async () => {} }} />}<div style={{ display: 'flex', height: '100dvh', width: '100%' }}><Companion active appInfo={null} character={character} characterMotion="always"
  onOpenCharacters={() => setOpen(true)} onUnauthorized={noop} onOpenSidebar={noop} voice={{ enabled: false, status: 'off', voices: [], voice: '', speaking: null, setEnabled: noop, setVoice: noop, recheck: noop, stop: noop, speak: async () => {} }} /></div></>; }
createRoot(document.getElementById('root')!).render(<Preview />);
