/**
 * Chữ trong bóng chat Companion, như MarkdownRenderer trong user-item.vue và assistant-item.vue của AIRI: in đậm, nghiêng
 * (lời *hành động* của thẻ tự viết), danh sách, link và code đều hiện đúng thay vì ký tự thô. Dùng chung bộ plugin của tab
 * Trò chuyện (toán và tô màu code chỉ tải khi tin cần). Không cho HTML thô.
 */
import { memo, useMemo } from 'react';
import Markdown, { type Components } from 'react-markdown';
import { normalizeMath } from '../../../shared/markdown/mathMarkdown';
import { useMarkdownPlugins } from '../../../shared/markdown/markdownExtras';

const components: Components = {
  a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
  table: ({ children }) => <div className="table-scroll" tabIndex={0} role="region" aria-label="Bảng nội dung"><table>{children}</table></div>,
};

export const CompanionMarkdown = memo(function CompanionMarkdown({ text }: { text: string }) {
  const source = useMemo(() => normalizeMath(text), [text]);
  const { remarkPlugins, rehypePlugins } = useMarkdownPlugins(source);
  return (
    <div className="cchat-text">
      <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>{source}</Markdown>
    </div>
  );
});
