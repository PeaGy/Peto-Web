import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  deviceChoiceSupported, DICTATION_LANGUAGES, languageOf, loadLanguage, loadMic, matchesLanguage, resolveMic, saveLanguage,
  saveMic,
} from '../src/features/chat/dictationPrefs';

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

it('remembers the language, falls back to Vietnamese for anything unknown', () => {
  expect(loadLanguage()).toBe('vi-VN');
  saveLanguage('ja-JP');
  expect(loadLanguage()).toBe('ja-JP');
  localStorage.setItem('peto-dictation-language', 'xx-YY');
  expect(loadLanguage()).toBe('vi-VN');
  expect(languageOf('en-GB').label).toBe('Tiếng Anh (Anh)');
  expect(DICTATION_LANGUAGES.slice(0, 3).map((item) => item.code)).toEqual(['vi-VN', 'en-US', 'en-GB']);
});

it('finds languages without accents and by code', () => {
  const names = (query: string) => DICTATION_LANGUAGES.filter((item) => matchesLanguage(item, query)).map((item) => item.label);
  expect(names('tieng anh')).toEqual(['Tiếng Anh (Mỹ)', 'Tiếng Anh (Anh)']);
  expect(names('Đức')).toEqual(['Tiếng Đức']);
  expect(names('duc')).toEqual(['Tiếng Đức']);
  expect(names('ja')).toEqual(['Tiếng Nhật']);
  expect(names('')).toHaveLength(DICTATION_LANGUAGES.length);
});

it('remembers the microphone by id and name; the default one is not stored', () => {
  expect(loadMic()).toEqual({ id: '', label: '' });
  saveMic({ id: 'abc', label: 'Headset' });
  expect(loadMic()).toEqual({ id: 'abc', label: 'Headset' });
  saveMic({ id: 'default', label: 'Default' });
  expect(loadMic()).toEqual({ id: '', label: '' });
  localStorage.setItem('peto-dictation-mic', 'not json');
  expect(loadMic()).toEqual({ id: '', label: '' });
});

it('finds the chosen microphone again when its id changed, else gives up for the default one', () => {
  const devices = [{ deviceId: 'default', label: 'Default' }, { deviceId: 'new-id', label: 'Headset' }];
  expect(resolveMic({ id: 'new-id', label: 'Headset' }, devices)).toBe('new-id');
  expect(resolveMic({ id: 'old-id', label: 'Headset' }, devices)).toBe('new-id');
  expect(resolveMic({ id: 'old-id', label: 'Unplugged' }, devices)).toBeNull();
  expect(resolveMic({ id: '', label: '' }, devices)).toBeNull();
});

it('offers a microphone choice only on desktop Chrome or Edge 133 and later', () => {
  const stub = (userAgentData: unknown) => vi.stubGlobal('navigator', {
    mediaDevices: { getUserMedia: vi.fn() }, userAgentData,
  });
  stub({ mobile: false, brands: [{ brand: 'Chromium', version: '156' }, { brand: 'Not:A-Brand', version: '8' }] });
  expect(deviceChoiceSupported()).toBe(true);
  stub({ mobile: false, brands: [{ brand: 'Microsoft Edge', version: '140' }] });
  expect(deviceChoiceSupported()).toBe(true);
  stub({ mobile: false, brands: [{ brand: 'Google Chrome', version: '132' }] });
  expect(deviceChoiceSupported()).toBe(false);
  stub({ mobile: true, brands: [{ brand: 'Google Chrome', version: '156' }] });
  expect(deviceChoiceSupported()).toBe(false);
  stub(undefined); // Safari, Firefox: không có userAgentData
  expect(deviceChoiceSupported()).toBe(false);
});
