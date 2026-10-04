/**
 * Nạp sẵn những phần App tải riêng (React.lazy, markdownExtras) trước khi test chạy. Trong trình duyệt chúng tải lúc mở
 * lần đầu; trong test, lần nạp đầu còn phải dịch tệp, và nếu rơi vào giữa một test thì dễ vượt hạn giờ của test đó khi
 * cả bộ test chạy song song. Nạp ở beforeAll thì việc dịch nằm ngoài giờ của từng test, như trước khi tách tệp.
 */
export async function preloadLazyParts(): Promise<void> {
  await Promise.all([
    import('../src/features/imagine/Imagine'),
    import('../src/features/companion/Companion'),
    import('../src/features/settings/ProfileSettings'),
    import('../src/features/companion/speech/VoiceSettings'),
    import('../src/features/settings/MemorySettings'),
    import('../src/features/settings/SearchSettings'),
    import('../src/features/settings/AgentSettings'),
    import('../src/features/settings/ArchivedConversations'),
    import('../src/features/companion/characters/CharacterSettings'),
    import('../src/features/connectors/ConnectorSettings'),
    import('../src/shared/markdown/markdownMath'),
    import('../src/shared/markdown/markdownCode'),
    import('../src/features/diagrams/DiagramPanel'),
    import('../src/features/documents/SheetView'),
  ]);
}
