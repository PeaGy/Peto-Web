import { useEffect, useMemo, useState } from 'react';
import '../../shared/styles/styles.css';
import '../documents/documentPanel.css';
import './desktopComposer.css';
import './sharedChat.css';
import { getSharedChat, type ChatAttachment, type Message, type SharedChat as Shared } from '../../shared/api/api';
import { LoadingIndicator } from '../../shared/ui/LoadingIndicator';
import { ChatMessage } from './ChatMessage';
import SourcesPanel from './SourcesPanel';

const shareId = () => location.pathname.replace(/^\/s\//, '').replace(/\/$/, '');

const day = (seconds: number) => {
  const date = new Date(seconds * 1000);
  return `${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
};

/**
 * Trang công khai của link chia sẻ ``/s/{id}`` (28/11/2026): đọc bản chụp, không cần đăng nhập, không có ô nhắn. Tin
 * nhắn vẽ bằng chính ``ChatMessage`` của Chat nên công thức, bảng, code và nguồn giống hệt trong app. Ảnh người dùng
 * gửi chỉ có khi link được tạo với "Kèm ảnh"; tệp khác và tài liệu Peto tạo chỉ hiện tên.
 */
export default function SharedChat() {
  const id = shareId();
  const [chat, setChat] = useState<Shared | null>(null);
  const [error, setError] = useState('');
  const [sourcesIndex, setSourcesIndex] = useState<number | null>(null);

  useEffect(() => {
    const theme = localStorage.getItem('peto-theme');
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
    const controller = new AbortController();
    void getSharedChat(id, controller.signal).then(data => {
      setChat(data);
      document.title = `${data.title} · Peto`;
    }).catch(err => {
      if (!controller.signal.aborted) setError(err instanceof Error && !(err instanceof TypeError)
        ? err.message : 'Chưa tải được cuộc trò chuyện. Bạn thử tải lại trang nhé.');
    });
    return () => controller.abort();
  }, [id]);

  const messages = useMemo<Message[]>(() => (chat?.messages ?? []).map((item) => {
    const images: ChatAttachment[] = (item.attachments ?? []).filter(file => file.kind === 'image' && file.id).map(file => ({
      id: file.id!, name: file.name, mime: 'image/*', kind: 'image', size: 0,
      url: `/api/shared/${encodeURIComponent(id)}/images/${encodeURIComponent(file.id!)}`,
    }));
    return { role: item.role, content: item.content, created_at: item.created_at, sources: item.sources,
      attachments: images.length ? images : undefined, status: 'complete' };
  }), [chat, id]);

  if (error) return <div className="shared-page"><SharedHeader />
    <main className="shared-empty" role="alert"><h1>Không mở được link</h1><p>{error}</p>
      <a className="shared-cta" href="/">Trò chuyện với Peto</a></main></div>;
  if (!chat) return <LoadingIndicator variant="screen" label="Đang tải" />;

  return <div className="shared-page">
    <SharedHeader />
    <div className={`chat-layout shared-body${sourcesIndex !== null ? ' sources-open' : ''}`}>
    <main className="chat shared-chat" aria-label="Cuộc trò chuyện được chia sẻ">
      <div className="messages shared-messages" role="region" aria-label="Nội dung hội thoại">
        <header className="shared-heading">
          <h1>{chat.title}</h1>
          <p>Bản chụp ngày {day(chat.updated_at)} · chỉ đọc</p>
        </header>
        {messages.map((message, index) => {
          const source = chat.messages[index];
          const files = (source.attachments ?? []).filter(file => file.kind !== 'image' || !file.id).map(file => file.name);
          const documents = (source.documents ?? []).map(item => item.filename || item.title).filter(Boolean);
          return <div key={index} className={`shared-turn ${message.role}`}>
            <ChatMessage message={message} live={false} writing={false} onPreview={() => {}} onEdit={() => {}}
              onOpenSources={setSourcesIndex} sourceIndex={index} sourcesExpanded={sourcesIndex === index} />
            {files.length > 0 && <p className="shared-files">Tệp đính kèm: {files.join(', ')}</p>}
            {documents.length > 0 && <p className="shared-files">Tài liệu Peto tạo: {documents.join(', ')}</p>}
          </div>;
        })}
        <footer className="shared-footer">
          <p>Đây là bản chụp một cuộc trò chuyện với Peto, trợ lý AI. Nội dung do AI tạo, có thể chưa chính xác.</p>
          <a className="shared-cta" href="/">Trò chuyện với Peto</a>
        </footer>
      </div>
    </main>
    {sourcesIndex !== null && messages[sourcesIndex] &&
      <SourcesPanel key={sourcesIndex} sources={messages[sourcesIndex].sources} onClose={() => setSourcesIndex(null)} />}
    </div>
  </div>;
}

function SharedHeader() {
  return <header className="shared-bar">
    <a href="/" className="shared-brand" aria-label="Peto, về trang chủ">
      <img src="/docs-assets/logo.webp" alt="" width="28" height="28" />Peto</a>
    <span>Cuộc trò chuyện được chia sẻ</span>
  </header>;
}
