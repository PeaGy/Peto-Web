// Lựa chọn của menu cạnh nút micro (ngôn ngữ nghe, micro), nhớ trong trình duyệt này. Web Speech cần biết trước một
// ngôn ngữ cho mỗi lần nghe nên không có "Tự động"; mặc định là tiếng Việt.

export interface DictationLanguage { code: string; label: string }

/** Ba ngôn ngữ đầu là hay dùng nhất ở Peto; phần sau theo bảng chữ cái tiếng Việt. Chrome nhận hầu hết các mã này;
 * Safari tùy máy, không nghe được thì trình duyệt báo `language-not-supported`. */
export const DICTATION_LANGUAGES: DictationLanguage[] = [
  { code: 'vi-VN', label: 'Tiếng Việt' },
  { code: 'en-US', label: 'Tiếng Anh (Mỹ)' },
  { code: 'en-GB', label: 'Tiếng Anh (Anh)' },
  { code: 'pt-BR', label: 'Tiếng Bồ Đào Nha (Brazil)' },
  { code: 'de-DE', label: 'Tiếng Đức' },
  { code: 'nl-NL', label: 'Tiếng Hà Lan' },
  { code: 'ko-KR', label: 'Tiếng Hàn' },
  { code: 'hi-IN', label: 'Tiếng Hindi' },
  { code: 'id-ID', label: 'Tiếng Indonesia' },
  { code: 'km-KH', label: 'Tiếng Khmer' },
  { code: 'lo-LA', label: 'Tiếng Lào' },
  { code: 'ms-MY', label: 'Tiếng Mã Lai' },
  { code: 'ru-RU', label: 'Tiếng Nga' },
  { code: 'ja-JP', label: 'Tiếng Nhật' },
  { code: 'fr-FR', label: 'Tiếng Pháp' },
  { code: 'fil-PH', label: 'Tiếng Philippines' },
  { code: 'yue-Hant-HK', label: 'Tiếng Quảng Đông' },
  { code: 'es-ES', label: 'Tiếng Tây Ban Nha' },
  { code: 'th-TH', label: 'Tiếng Thái' },
  { code: 'cmn-Hans-CN', label: 'Tiếng Trung (Phổ thông)' },
  { code: 'cmn-Hant-TW', label: 'Tiếng Trung (Đài Loan)' },
  { code: 'it-IT', label: 'Tiếng Ý' },
];

const LANGUAGE_KEY = 'peto-dictation-language';
const MIC_KEY = 'peto-dictation-mic';

export function languageOf(code: string): DictationLanguage {
  return DICTATION_LANGUAGES.find((item) => item.code === code) ?? DICTATION_LANGUAGES[0];
}

export function loadLanguage(): string {
  try { return languageOf(localStorage.getItem(LANGUAGE_KEY) ?? '').code; } catch { return DICTATION_LANGUAGES[0].code; }
}

export function saveLanguage(code: string) {
  try { localStorage.setItem(LANGUAGE_KEY, languageOf(code).code); } catch { /* Vẫn dùng được trong phiên này. */ }
}

/** Micro đã chọn: mã thiết bị và tên. Mã rỗng là micro mặc định của máy. Nhớ cả tên vì mã thiết bị có thể đổi (xóa
 * cookie, cửa sổ ẩn danh; Chromium của Playwright cấp mã mới mỗi lần tải trang), khi đó tìm lại theo tên. */
export interface MicChoice { id: string; label: string }
export const DEFAULT_MIC: MicChoice = { id: '', label: '' };

export function loadMic(): MicChoice {
  try {
    const saved = JSON.parse(localStorage.getItem(MIC_KEY) ?? 'null') as Partial<MicChoice> | null;
    return saved && typeof saved.id === 'string' && saved.id
      ? { id: saved.id, label: typeof saved.label === 'string' ? saved.label : '' } : DEFAULT_MIC;
  } catch { return DEFAULT_MIC; }
}

export function saveMic(choice: MicChoice) {
  try {
    if (choice.id && choice.id !== 'default') localStorage.setItem(MIC_KEY, JSON.stringify(choice));
    else localStorage.removeItem(MIC_KEY);
  } catch { /* Vẫn dùng được trong phiên này. */ }
}

/** Mã thiết bị để mở micro đã chọn lúc này: theo mã, không có thì theo tên; không thấy nữa thì null (dùng mặc định). */
export function resolveMic(choice: MicChoice, devices: { deviceId: string; label: string }[]): string | null {
  if (!choice.id) return null;
  if (devices.some((item) => item.deviceId === choice.id)) return choice.id;
  return devices.find((item) => choice.label && item.label === choice.label)?.deviceId ?? null;
}

/** Bỏ dấu, viết thường: ô tìm ngôn ngữ khớp "tieng anh" với "Tiếng Anh", và cả mã như "en". */
export function matchesLanguage(item: DictationLanguage, query: string): boolean {
  const fold = (value: string) => value.normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/gi, 'd').toLowerCase();
  const wanted = fold(query.trim());
  return !wanted || fold(item.label).includes(wanted) || item.code.toLowerCase().startsWith(wanted);
}

interface Brand { brand: string; version: string }

/**
 * Trình duyệt có nghe được từ micro người dùng chọn không: `SpeechRecognition.start(track)` có từ Chrome 133 trên máy
 * tính (Edge cùng nhân). Trình duyệt chưa có thì lặng lẽ bỏ qua track và nghe micro mặc định, không báo lỗi, nên không
 * thể thử bằng cách gọi; dò theo nhãn trình duyệt. Thử thật ngày 20/11/2026: Chromium 156 trong app Claude nhận track
 * âm thanh và từ chối track hình bằng InvalidStateError. Safari, Firefox, điện thoại: chỉ micro mặc định.
 */
export function deviceChoiceSupported(): boolean {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) return false;
  const data = (navigator as Navigator & { userAgentData?: { brands?: Brand[]; mobile?: boolean } }).userAgentData;
  if (!data?.brands || data.mobile) return false;
  return data.brands.some((item) => /^(Chromium|Google Chrome|Microsoft Edge)$/.test(item.brand) && Number(item.version) >= 133);
}
