type Glyph = 'heart' | 'queue' | 'next' | 'search' | 'plus' | 'close' | 'play' | 'grip' | 'more' | 'up' | 'down' | 'shuffle' | 'repeat' | 'repeat-one';

export function LibraryIcon({ name, filled = false, size = 21 }: { name: Glyph; filled?: boolean; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'heart' && <path fill={filled ? 'currentColor' : 'none'} d="M20.5 4.8a5.1 5.1 0 0 0-7.2 0L12 6.1l-1.3-1.3a5.1 5.1 0 0 0-7.2 7.2L12 20.5l8.5-8.5a5.1 5.1 0 0 0 0-7.2Z" />}
    {name === 'queue' && <><path d="M4 5h16M4 11h16M4 17h9" /><path fill="currentColor" stroke="none" d="m17 14 5 3-5 3z" /></>}
    {name === 'next' && <><path fill="currentColor" stroke="none" d="m5 5 12 7-12 7z" /><path d="M19 5v14" /></>}
    {name === 'search' && <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></>}
    {name === 'plus' && <path d="M12 5v14M5 12h14" />}
    {name === 'close' && <path d="m6 6 12 12M18 6 6 18" />}
    {name === 'play' && <path fill="currentColor" stroke="none" d="m7 4 13 8-13 8z" />}
    {name === 'grip' && <>{[7, 12, 17].map(y => <g key={y}><circle cx="9" cy={y} r=".8" fill="currentColor" /><circle cx="15" cy={y} r=".8" fill="currentColor" /></g>)}</>}
    {name === 'more' && <>{[5, 12, 19].map(y => <circle key={y} cx="12" cy={y} r="1" fill="currentColor" />)}</>}
    {name === 'up' && <path d="m6 14 6-6 6 6" />}
    {name === 'down' && <path d="m6 10 6 6 6-6" />}
    {name === 'shuffle' && <><path d="M3 6h2c5 0 9 12 14 12h2m-4-4 4 4-4 4M3 18h2c2 0 3.7-2 5.4-4.5M14 8c1.6-1.3 3.1-2 5-2h2m-4-4 4 4-4 4" /></>}
    {(name === 'repeat' || name === 'repeat-one') && <><path d="m17 2 4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4m14-1v2a3 3 0 0 1-3 3H3" />{name === 'repeat-one' && <path d="m10 10 2-1v6m-2 0h4" />}</>}
  </svg>;
}
