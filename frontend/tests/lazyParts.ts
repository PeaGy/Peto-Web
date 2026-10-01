/**
 * Nạp sẵn những phần App tải riêng (React.lazy, markdownExtras) trước khi test chạy. Trong trình duyệt chúng tải lúc mở
 * lần đầu; trong test, lần nạp đầu còn phải dịch tệp, và nếu rơi vào giữa một test thì dễ vượt hạn giờ của test đó khi
 * cả bộ test chạy song song. Nạp ở beforeAll thì việc dịch nằm ngoài giờ của từng test, như trước khi tách tệp.
 */
export async function preloadLazyParts(): Promise<void> {
  await Promise.all([
    import('../src/Imagine'),
    import('../src/Companion'),
    import('../src/ProfileSettings'),
    import('../src/VoiceSettings'),
    import('../src/MemorySettings'),
    import('../src/SearchSettings'),
    import('../src/AgentSettings'),
    import('../src/CharacterSettings'),
    import('../src/markdownMath'),
    import('../src/markdownCode'),
    import('../src/DiagramPanel'),
  ]);
}
