import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import type { ChatAttachment, Message } from '../src/shared/api/api';

const document: ChatAttachment = { id: 'readme', name: 'README.md', mime: 'text/markdown', kind: 'file', size: 2048, url: '/api/attachments/readme' };
const image: ChatAttachment = { id: 'photo', name: 'ảnh.png', mime: 'image/png', kind: 'image', size: 4096, url: '/api/attachments/photo' };

function draw(message: Partial<Message> = {}, editor?: ReactNode) {
  return render(<ChatMessage message={{ id: 1, role: 'user', content: 'Bạn xem giúp những tệp này nhé.', ...message }}
    live={false} writing={false} onEdit={() => {}} onPreview={() => {}} editor={editor} />);
}

describe('đính kèm của tin nhắn Chat', () => {
  it('đặt hai tệp phía trên lời nhắn, giữ tên, loại và liên kết tải', () => {
    const { container } = draw({ attachments: [document, { ...document, id: 'report', name: 'report.md', url: '/api/attachments/report' }] });
    const text = container.querySelector('.user-message-text')!;
    const attachments = screen.getByRole('group', { name: 'Đính kèm trong tin nhắn' });
    expect(text.contains(attachments)).toBe(false);
    expect(attachments.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const links = screen.getAllByRole('link');
    expect(links.map(link => link.getAttribute('download'))).toEqual(['README.md', 'report.md']);
    expect(links.map(link => link.getAttribute('href'))).toEqual(['/api/attachments/readme', '/api/attachments/report']);
    expect(screen.getAllByText('Tài liệu · 2 KB')).toHaveLength(2);
  });

  it('chỉ gửi ảnh thì không dựng bong bóng chữ rỗng, ảnh vẫn mở được', () => {
    const { container } = draw({ content: '', attachments: [image] });
    expect(container.querySelector('.user-message-text')).toBeNull();
    const photo = screen.getByRole('img', { name: 'ảnh.png' });
    expect(photo.getAttribute('width')).toBe('112');
    expect(photo.getAttribute('height')).toBe('112');
    expect(photo.closest('a')?.getAttribute('href')).toBe(image.url);
    expect(photo.closest('a')?.getAttribute('target')).toBe('_blank');
    expect(screen.getByRole('button', { name: 'Sửa tin nhắn' })).toBeTruthy();
  });

  it('giữ đủ bốn ảnh và nhiều tệp trong tin hỗn hợp', () => {
    const images = Array.from({ length: 4 }, (_, i) => ({ ...image, id: `image-${i}`, name: `ảnh-${i}.png` }));
    const files = Array.from({ length: 12 }, (_, i) => ({ ...document, id: `file-${i}`, name: `báo-cáo-${i}.md` }));
    draw({ attachments: [...images, ...files] });
    expect(screen.getAllByRole('img')).toHaveLength(4);
    expect(screen.getAllByRole('link')).toHaveLength(16);
    files.forEach(file => expect(screen.getByRole('link', { name: `${file.name}, Tài liệu · 2 KB` })).toBeTruthy());
  });

  it('tên rất dài vẫn có tên đầy đủ trong liên kết và gợi ý', () => {
    const name = `Báo cáo ${'phân tích rất dài '.repeat(20)}2026.xlsx`;
    draw({ attachments: [{ ...document, name, mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }] });
    const link = screen.getByRole('link', { name: `${name}, Bảng tính · 2 KB` });
    expect(link.getAttribute('title')).toBe(`${name} · Bảng tính · 2 KB`);
    expect(link.getAttribute('download')).toBe(name);
  });

  it('tệp chưa có URL không tạo liên kết tải giả nhưng vẫn hiện thông tin', () => {
    draw({ attachments: [{ ...document, url: '' }, { ...image, url: '' }] });
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('README.md')).toBeTruthy();
    expect(screen.getByText('Ảnh · 4 KB')).toBeTruthy();
  });

  it('sửa lời nhắn giữ đính kèm và không hiển thị lời cũ cùng ô sửa', () => {
    const { container } = draw({ attachments: [image, document] }, <textarea aria-label="Sửa tin nhắn" defaultValue="Lời mới" />);
    expect(screen.getByRole('img')).toBeTruthy();
    expect(screen.getByRole('link', { name: /README.md/ })).toBeTruthy();
    expect(screen.getByRole('textbox', { name: 'Sửa tin nhắn' })).toBeTruthy();
    expect(screen.queryByText('Bạn xem giúp những tệp này nhé.')).toBeNull();
    expect(container.querySelector('.user-message-text')).toBeNull();
  });

  it('tin văn bản và câu trả lời Peto giữ nội dung Markdown, không có nhóm đính kèm rỗng', () => {
    const { container, rerender } = draw({ content: '**Lời nhắn**' });
    expect(container.querySelector('.bubble.user strong')?.textContent).toBe('Lời nhắn');
    expect(container.querySelector('.user-message-text')).toBeNull();
    expect(screen.queryByRole('group')).toBeNull();
    rerender(<ChatMessage message={{ role: 'assistant', content: '**Câu trả lời**' }} live={false} writing={false} onEdit={() => {}} onPreview={() => {}} />);
    expect(container.querySelector('.bubble.assistant strong')?.textContent).toBe('Câu trả lời');
    expect(container.querySelector('.user-message-text')).toBeNull();
  });
});
