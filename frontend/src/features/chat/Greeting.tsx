import { useEffect, useState } from 'react';
import { fillName, greetingKey, pickGreeting } from './timeGreeting';

/**
 * Lời chào đổi theo giờ trên máy, như Claude. Chọn một câu mỗi lần màn hình
 * trống hiện ra để chữ không nhảy trong lúc đang đọc. Quay lại tab khi đã sang
 * buổi khác hoặc ngày khác thì chọn lại, kẻo sáng ra vẫn còn "Khuya rồi".
 */
export function Greeting({ name }: { name: string }) {
  const [greeting, setGreeting] = useState(() => {
    const now = new Date();
    return { key: greetingKey(now), text: pickGreeting(now) };
  });

  useEffect(() => {
    function refresh() {
      if (document.visibilityState !== "visible") return;
      const now = new Date();
      const key = greetingKey(now);
      setGreeting((prev) => (prev.key === key ? prev : { key, text: pickGreeting(now) }));
    }
    document.addEventListener("visibilitychange", refresh);
    return () => document.removeEventListener("visibilitychange", refresh);
  }, []);

  return <h1>{fillName(greeting.text, name)}</h1>;
}

