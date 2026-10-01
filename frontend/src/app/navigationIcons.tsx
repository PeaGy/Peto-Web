

export function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** Bút trên tờ giấy: như Grok, mục Trò chuyện cũng là nơi mở cuộc mới. */
export function ComposeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="m17.5 3.5 3 3L12 15l-3.5.5.5-3.5 8.5-8.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

export function ImageIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="4" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="9" cy="9" r="1.6" fill="currentColor" />
      <path d="m4 17 4.5-4.5 3.5 3.5 3-3.5 5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function CompanionIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3z" stroke="currentColor" strokeWidth="2" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function SidebarIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M9.5 4.5v15" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function PinIcon() { return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path className="pin-head" d="m14 3 7 7-4 1-4 5-5-5 5-4z"/><path d="m10.5 13.5-7 7"/></svg>; }
export function SearchIcon() { return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>; }

