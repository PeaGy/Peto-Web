import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import type { Message } from '../src/shared/api/api';

const props = { live: false, writing: false, onPreview: () => {}, onEdit: () => {} };
const NOTE = 'Peto không viết gì cho lượt này.';

describe('Peto im lặng có chủ đích', () => {
  it('lượt hoàn tất mà rỗng hiện dòng mờ, không báo chưa hoàn tất, vẫn tạo lại được', () => {
    const message: Message = { id: 7, role: 'assistant', content: '', turn_state: 'complete' };
    render(<ChatMessage {...props} message={message} onRegenerate={() => {}} />);
    expect(screen.getByText(NOTE).classList.contains('message-silent')).toBe(true);
    expect(screen.queryByText(/chưa hoàn tất/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Sao chép/ })).toBeNull();
  });

  it('không hiện khi đang viết, khi lượt lỗi hay khi có chữ', () => {
    const cases: [Message, Partial<typeof props>][] = [
      [{ id: 8, role: 'assistant', content: '' }, { live: true, writing: true }],
      [{ id: 9, role: 'assistant', content: '', status: 'incomplete', turn_state: 'error' }, {}],
      [{ id: 10, role: 'assistant', content: 'Chào bạn.', turn_state: 'complete' }, {}],
      [{ role: 'assistant', content: '', local: true }, {}],
    ];
    for (const [message, extra] of cases) {
      const { unmount } = render(<ChatMessage {...props} {...extra} message={message} />);
      expect(screen.queryByText(NOTE)).toBeNull();
      unmount();
    }
  });
});
