import { describe, expect, it } from 'vitest';
import { isConversation } from '../src/shared/api/api';

// Thanh bên chỉ hiện một dòng cho mỗi nhóm phiên bản (22/11/2026): dòng đó vẫn là "đang mở" khi người dùng chuyển sang
// bản cũ bằng nút ‹ 1/2 › dưới câu trả lời, và xóa hay lưu trữ dòng đó thì đóng cả bản cũ đang mở.
describe('isConversation', () => {
  const row = { id: 'moi-nhat', version_ids: ['goc', 'lan-hai', 'moi-nhat'] };

  it('nhận mọi bản trong nhóm', () => {
    expect(isConversation(row, 'moi-nhat')).toBe(true);
    expect(isConversation(row, 'goc')).toBe(true);
    expect(isConversation(row, 'khac')).toBe(false);
  });

  it('không có danh sách bản (máy chủ cũ) thì so theo mã', () => {
    expect(isConversation({ id: 'a' }, 'a')).toBe(true);
    expect(isConversation({ id: 'a' }, 'b')).toBe(false);
  });

  it('chưa mở cuộc trò chuyện nào thì không dòng nào đang mở', () => {
    expect(isConversation(row, null)).toBe(false);
    expect(isConversation(row, undefined)).toBe(false);
  });
});
