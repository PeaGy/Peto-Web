import { EditIcon } from '../../shared/ui/EditIcon';
import { createContext, memo, useContext, useMemo, useRef, type ReactNode } from 'react';
import Markdown, { type Components } from 'react-markdown';
import { normalizeMath } from '../../shared/markdown/mathMarkdown';
import { useMarkdownPlugins } from '../../shared/markdown/markdownExtras';
import { DiagramCard } from '../diagrams/DiagramCard';
import { hastText } from '../diagrams/diagrams';
import DocumentArtifactCard from '../documents/DocumentArtifactCard';
import MessageAttachments from './MessageAttachments';
import { MessageLink } from './LinkChip';
import WebSources, { safeSources } from './WebSources';
import { CitationGroup, remarkCitations } from './Citations';
import WorkTimeline from './WorkTimeline';
import type { Message, WebSource } from '../../shared/api/api';
import CodeBlock from './CodeBlock';
import MarkdownTable from './MarkdownTable';
import ResponseActions, { type ResponseVariants } from './ResponseActions';
import { CheckIcon, CopyIcon } from './messageUtilityIcons';
import { useMessageCopy } from './useMessageCopy';
import { mergeDisplaySources } from './sourceActivity';
import { QuoteExcerpt } from './QuotedFollowup';

const MarkdownRuntime = createContext<{ sources: WebSource[]; writing: boolean; user: boolean }>({ sources: [], writing: false, user: false });

// Stable component identities preserve code collapse/wrap/copy state when a stream ends or sources arrive.
const MARKDOWN_COMPONENTS: Components = {
  table: function Table({ children }) {
    const { writing } = useContext(MarkdownRuntime);
    return <MarkdownTable pending={writing}>{children}</MarkdownTable>;
  },
  td: ({ node, children }) => <td className={hastText(node).length > 30 ? 'wide' : undefined}>{children}</td>,
  cite: function Cite({ node, children }) {
    const { sources, writing } = useContext(MarkdownRuntime);
    const refs = node?.properties?.['dataCitationRefs'] ?? node?.properties?.['data-citation-refs'];
    if (typeof refs !== 'string') return <cite>{children}</cite>;
    try { return <CitationGroup refs={JSON.parse(refs)} sources={sources} writing={writing} />; }
    catch { return <cite>{children}</cite>; }
  },
  a: function Link({ node, children, href }) {
    const { user } = useContext(MarkdownRuntime);
    return user && href && hastText(node) === href && /^https?:\/\//i.test(href)
      ? <MessageLink href={href} />
      : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  },
  pre: function Pre({ node, children }) {
    const { writing } = useContext(MarkdownRuntime);
    const code = node?.children?.[0];
    const names = code?.type === 'element' && Array.isArray(code.properties?.className)
      ? code.properties.className.map(String) : [];
    const tag = names.find(name => name.startsWith('language-'));
    if (tag === 'language-mermaid') return <DiagramCard source={hastText(code)} pending={writing} />;
    return <CodeBlock language={tag ? tag.slice('language-'.length) : ''} source={hastText(code)}>{children}</CodeBlock>;
  },
};

function UserMessageCopy({ text }: { text: string }) {
  const { state, label, copy } = useMessageCopy();
  return <button type="button" className={`user-message-copy${state === 'done' ? ' done' : ''}`}
    aria-label={`${label} tin nhắn`} onClick={() => void copy(text)}>
    {state === 'done' ? <CheckIcon /> : <CopyIcon />}
  </button>;
}


export const ChatMessage = memo(function ChatMessage({ message, live, writing, onPreview, onEdit, onRetry, onRegenerate, variants, onJumpQuote, onOpenSources, sourceIndex = 0, sourcesExpanded, actionsDisabled, editor }: {
  message: Message; live: boolean; writing: boolean;
  actionsDisabled?: boolean; editor?: ReactNode; onRetry?: () => void;
  onRegenerate?: (messageId: number) => void; variants?: ResponseVariants;
  onJumpQuote?: (messageId: number) => void;
  onOpenSources?: (index: number) => void; sourceIndex?: number; sourcesExpanded?: boolean;
  onPreview: (item: { id: string; version: number }) => void;
  onEdit: (item: { id: string; version: number }) => void;
}) {
  const hasUserAttachments = message.role === 'user' && Boolean(message.attachments?.length);
  const user = message.role === 'user';
  const contentRef = useRef<HTMLDivElement>(null);
  const sources = useMemo(() => safeSources(message.sources), [message.sources]);
  const exportSources = useMemo(() => mergeDisplaySources(message.sources, message.work?.web), [message.sources, message.work?.web]);
  const complete = message.id !== undefined && !message.local && !message.stopped && message.status !== 'incomplete'
    && (!message.turn_state || message.turn_state === 'complete');
  const text = message.content ? normalizeMath(message.content) : "";
  const { remarkPlugins, rehypePlugins } = useMarkdownPlugins(text);
  const citationPlugins = useMemo<NonNullable<import('react-markdown').Options['remarkPlugins']>>(
    () => user ? remarkPlugins : [...remarkPlugins, [remarkCitations, { sources, writing }]],
    [remarkPlugins, sources, writing, user]);
  const runtime = useMemo(() => ({ sources, writing, user }), [sources, writing, user]);
  return (<article aria-label={message.role === 'user' ? 'Bạn' : 'Peto'} data-message-id={message.id} data-role={message.role} data-streaming={writing || live || undefined} data-quoteable={user ? undefined : complete} className={`bubble ${message.role}${hasUserAttachments ? ' chat-user-message' : ''}${editor ? ' editing' : ''}`}>
              {message.attachments && message.attachments.length > 0 && (
                <MessageAttachments attachments={message.attachments} sent={message.role === 'user'} />
              )}
              {message.role === "assistant" && message.work ? (
                <WorkTimeline work={message.work} live={live} startedAt={message.workStartedAt} answering={Boolean(message.content)} />
              ) : null}
              {user && message.quoted_source && <QuoteExcerpt quote={message.quoted_source} onJump={onJumpQuote} />}
              {editor || (message.content ? <div ref={contentRef} className={`message-markdown${hasUserAttachments ? ' user-message-text' : ''}`} data-message-content>
                <MarkdownRuntime.Provider value={runtime}><Markdown remarkPlugins={citationPlugins} rehypePlugins={rehypePlugins} components={MARKDOWN_COMPONENTS}>{text}</Markdown></MarkdownRuntime.Provider>
              </div> : null)}
              {message.role === "assistant" && <WebSources sources={message.sources} web={message.work?.web}
                onOpen={() => onOpenSources?.(sourceIndex)} expanded={sourcesExpanded} />}
              {message.artifacts?.map(artifact => <DocumentArtifactCard key={`${artifact.id}-${artifact.version}`} artifact={artifact} onOpen={onPreview} onEdit={onEdit} />)}
              {message.stopped ? <p className="message-stopped">Đã dừng theo yêu cầu của bạn.</p>
                : message.status === "incomplete" && <p className="message-status">{message.turn_outcome === 'process_restarted'
                  ? 'Lượt bị ngắt khi máy chủ khởi động lại.'
                  : message.turn_state === 'timeout' ? 'Lượt đã hết thời gian chờ. Câu trả lời chưa hoàn tất.'
                  : message.turn_state === 'running' ? 'Lượt này vẫn đang được xử lý.'
                  : 'Câu trả lời chưa hoàn tất'}</p>}
              {message.role === "assistant" && (message.content || message.stopped || onRetry || variants) && (
                <ResponseActions text={message.content} sources={exportSources} messageId={message.id} contentRef={contentRef}
                  stopped={message.stopped} onRetry={onRetry} onRegenerate={complete ? onRegenerate : undefined} variants={variants}
                  disabled={actionsDisabled || live || writing} />
              )}
              {!writing && !editor && message.role === 'user' && <span className="user-message-actions">
                {message.id && <button type="button" aria-label="Sửa tin nhắn" data-tip disabled={actionsDisabled} data-revise={message.id}><EditIcon /></button>}
                {message.content.trim() && <UserMessageCopy text={message.content} />}
              </span>}
            </article>);
});

