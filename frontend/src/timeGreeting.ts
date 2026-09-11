/**
 * Lời chào ở màn hình trống, đổi theo giờ như Claude.
 *
 * Giờ lấy từ máy người dùng chứ không phải máy chủ: "chào buổi sáng" phải khớp
 * với trời ngoài cửa sổ của họ. Mỗi buổi có vài câu để chọn ngẫu nhiên, ban
 * ngày thêm một câu theo thứ trong tuần. `{name}` là chỗ điền tên.
 */

export type DaySlot = "khuya" | "sang" | "trua" | "chieu" | "toi" | "dem";

const SLOT_GREETINGS: Record<DaySlot, readonly string[]> = {
  khuya: ["Khuya rồi, {name} còn thức à?", "Cú đêm {name} đây rồi", "Giờ này {name} vẫn chưa ngủ sao?"],
  sang: ["Chào buổi sáng, {name}", "Sáng nay thế nào, {name}?", "Cà phê sáng chưa, {name}?"],
  trua: ["Chào buổi trưa, {name}", "Trưa rồi, {name} ăn gì chưa?", "Nghỉ trưa chút không, {name}?"],
  chieu: ["Chào buổi chiều, {name}", "Chiều nay có gì vui không, {name}?", "Làm ly trà chiều không, {name}?"],
  toi: ["Chào buổi tối, {name}", "Hôm nay của {name} thế nào?", "Tối nay rảnh không, {name}?"],
  dem: ["Tối muộn rồi đó, {name}", "Sắp đi ngủ chưa, {name}?", "Đêm nay tâm sự chút không, {name}?"],
};

/** Khóa theo Date.getDay(): 0 là Chủ nhật. Chỉ thêm vào các buổi ban ngày. */
const WEEKDAY_GREETINGS: Readonly<Partial<Record<number, string>>> = {
  0: "Chủ nhật thảnh thơi chứ, {name}?",
  1: "Đầu tuần rồi, cố lên nhé {name}",
  5: "Thứ Sáu rồi, {name} ơi!",
  6: "Cuối tuần vui chứ, {name}?",
};

const DAYTIME: readonly DaySlot[] = ["sang", "trua", "chieu", "toi"];

export function daySlot(date: Date): DaySlot {
  const hour = date.getHours();
  if (hour < 5) return "khuya";
  if (hour < 11) return "sang";
  if (hour < 14) return "trua";
  if (hour < 18) return "chieu";
  if (hour < 22) return "toi";
  return "dem";
}

/** Mọi câu có thể hiện vào lúc `date`, chưa điền tên. */
export function greetingOptions(date: Date): string[] {
  const slot = daySlot(date);
  const extra = DAYTIME.includes(slot) ? WEEKDAY_GREETINGS[date.getDay()] : undefined;
  return extra ? [...SLOT_GREETINGS[slot], extra] : [...SLOT_GREETINGS[slot]];
}

/** Chỉ đổi khi sang buổi khác hoặc sang ngày khác — lúc đó mới cần chọn câu mới. */
export function greetingKey(date: Date): string {
  return `${date.toDateString()} ${daySlot(date)}`;
}

export function pickGreeting(date: Date, random: () => number = Math.random): string {
  const options = greetingOptions(date);
  // Math.random không bao giờ ra 1, nhưng hàm thay thế trong test thì có thể.
  return options[Math.min(options.length - 1, Math.floor(random() * options.length))];
}

export function fillName(template: string, name: string): string {
  return template.replace("{name}", name);
}
