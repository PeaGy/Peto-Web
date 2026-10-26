import { useEffect, useId, useState, type ReactNode } from 'react';
import { CheckIcon, CollapseIcon, CopyIcon, WrapIcon } from './messageUtilityIcons';
import { useMessageCopy } from './useMessageCopy';
import './messageUtilities.css';

// Keep aliases aligned with the optional highlighter in markdownCode.ts.
const CODE_LABELS: Record<string, string> = {
  bash: 'Bash', c: 'C', 'c#': 'C#', 'c++': 'C++', cc: 'C++', console: 'Bash', cpp: 'C++',
  cs: 'C#', csharp: 'C#', css: 'CSS', dart: 'Dart', diff: 'Diff', docker: 'Dockerfile',
  dockerfile: 'Dockerfile', go: 'Go', golang: 'Go', h: 'C', html: 'HTML', ini: 'INI',
  java: 'Java', javascript: 'JavaScript', js: 'JavaScript', json: 'JSON', jsx: 'JSX',
  kotlin: 'Kotlin', kt: 'Kotlin', lua: 'Lua', markdown: 'Markdown', md: 'Markdown',
  php: 'PHP', plaintext: 'Văn bản', powershell: 'PowerShell', ps1: 'PowerShell',
  pwsh: 'PowerShell', python: 'Python', rb: 'Ruby', rs: 'Rust', ruby: 'Ruby',
  rust: 'Rust', sh: 'Bash', shell: 'Bash', sql: 'SQL', text: 'Văn bản', toml: 'TOML',
  ts: 'TypeScript', tsx: 'TSX', txt: 'Văn bản', typescript: 'TypeScript', xml: 'HTML',
  yaml: 'YAML', yml: 'YAML', zsh: 'Bash',
};

export default function CodeBlock({ language, source, children }: { language: string; source: string; children: ReactNode }) {
  const { state, label: copyText, copy } = useMessageCopy();
  const [collapsed, setCollapsed] = useState(false);
  const [wrapped, setWrapped] = useState(false);
  const [narrow, setNarrow] = useState(() => window.matchMedia?.('(max-width: 720px)').matches ?? false);
  const preId = useId();
  const label = CODE_LABELS[language] ?? (language ? language.toUpperCase() : 'Mã');
  const lines = source.replace(/\n$/, '').split('\n');
  const canCollapse = lines.length > 5;
  const canWrap = lines.some(line => line.length > (narrow ? 50 : 90));
  const isCollapsed = canCollapse && collapsed;

  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 720px)');
    if (!media) return;
    const change = () => setNarrow(media.matches);
    change();
    media.addEventListener?.('change', change);
    return () => media.removeEventListener?.('change', change);
  }, []);

  return <div className={`code-block message-code${isCollapsed ? ' collapsed' : ''}${wrapped ? ' wrapped' : ''}`}>
    <div className="code-head">
      <span className="code-lang">{label}</span>
      <div className="code-actions" data-export-exclude>
        {canWrap && <button type="button" className="message-utility-button" aria-label={wrapped ? 'Tắt ngắt dòng' : 'Ngắt dòng'}
          aria-pressed={wrapped} data-tip onClick={() => setWrapped(value => !value)}><WrapIcon wrapped={wrapped} /></button>}
        {canCollapse && <button type="button" className="message-utility-button" aria-label={isCollapsed ? 'Mở rộng mã' : 'Thu gọn mã'}
          aria-expanded={!isCollapsed} aria-controls={preId} data-tip onClick={() => setCollapsed(value => !value)}>
          <CollapseIcon collapsed={isCollapsed} />
        </button>}
        {/* Copy the unmodified code, even when the pre is hidden or visually wrapped. */}
        <button type="button" className={`message-utility-button code-copy${state === 'done' ? ' done' : ''}`}
          aria-label={copyText} data-tip onClick={() => void copy(source)}>{state === 'done' ? <CheckIcon /> : <CopyIcon />}</button>
      </div>
    </div>
    {isCollapsed && <button type="button" className="code-collapsed-summary" data-export-exclude
      onClick={() => setCollapsed(false)} aria-label={`Mở rộng ${lines.length} dòng mã`}>{lines.length} dòng đã ẩn</button>}
    <pre id={preId} hidden={isCollapsed} tabIndex={0} role="region" aria-label={`Mã ${label}`}>{children}</pre>
  </div>;
}
