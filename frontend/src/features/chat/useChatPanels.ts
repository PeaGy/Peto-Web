import { useCallback, useEffect, useMemo, useState } from 'react';
import type { DocumentPanelSelection } from '../documents/DocumentPanel';
import type { DocumentDraftRequest } from '../documents/documentApi';

/** Bảng bên phải của tab Trò chuyện: nguồn của một câu trả lời, bảng tài liệu và bảng sơ đồ. Ba bảng dùng chung một chỗ,
 * nên mở bảng này thì đóng bảng kia. Tách khỏi App.tsx (G3.3, 13/11/2026). */
export function useChatPanels(view: string, conversationId: string | null) {
  const [sourcesIndex, setSourcesIndex] = useState<number | null>(null);
  const closeSources = useCallback(() => setSourcesIndex(null), []);
  const [documentRequest, setDocumentRequest] = useState<DocumentDraftRequest | null>(null);
  const [documentSelection, setDocumentSelection] = useState<{ id: string; version: number; key: number } | null>(null);
  const [documentRefresh, setDocumentRefresh] = useState(0);
  const [documentPanelOpen, setDocumentPanelOpen] = useState(false);
  const [documentPanelExpanded, setDocumentPanelExpanded] = useState(false);
  const [documentPreview, setDocumentPreview] = useState<DocumentPanelSelection | null>(null);
  const closeDocumentPanel = useCallback(() => { setDocumentPanelOpen(false); setDocumentPanelExpanded(false); }, []);
  // Sơ đồ đang mở ở bảng bên phải (mã Mermaid đã chuẩn hóa).
  const [diagram, setDiagram] = useState<string | null>(null);
  const closeDiagram = useCallback(() => setDiagram(null), []);
  const openSources = useCallback((index: number) => {
    setDocumentPanelOpen(false); setDocumentPanelExpanded(false); setDiagram(null);
    setSourcesIndex(current => current === index ? null : index);
  }, []);
  const diagramApi = useMemo(() => ({
    current: diagram,
    open: (code: string) => { setSourcesIndex(null); setDocumentPanelOpen(false); setDocumentPanelExpanded(false); setDiagram(code); },
  }), [diagram]);
  const previewDocument = useCallback((item: { id: string; version: number }) => {
    setSourcesIndex(null);
    setDocumentPreview({ id: item.id, version: item.version, key: Date.now() });
    setDiagram(null);
    setDocumentPanelOpen(true);
  }, []);
  const editDocument = useCallback((item: { id: string; version: number }) => {
    setDocumentSelection({ id: item.id, version: item.version, key: Date.now() });
  }, []);
  // Nút Tài liệu ở góc trên và phím Ctrl+Alt+B.
  const toggleDocumentPanel = useCallback(() => {
    setSourcesIndex(null); setDocumentPanelOpen(value => !value); setDocumentPanelExpanded(false); setDiagram(null);
  }, []);
  // Phiên đăng nhập hết hạn: đóng hết, quên tài liệu đang xem.
  const resetPanels = useCallback(() => {
    setDocumentRequest(null);
    setDocumentSelection(null);
    closeDocumentPanel(); setDocumentPreview(null); setDiagram(null);
    setSourcesIndex(null);
  }, [closeDocumentPanel]);
  useEffect(() => setSourcesIndex(null), [view]);
  useEffect(() => {
    setDocumentPanelOpen(false); setDocumentPanelExpanded(false); setDocumentPreview(null); setDocumentSelection(null);
    setDiagram(null);
    setSourcesIndex(null);
  }, [conversationId]);
  useEffect(() => {
    if (view !== 'chat') return;
    const shortcut = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && event.code === 'KeyB' && !document.querySelector('.document-workspace[open], .settings-dialog[open]')) {
        event.preventDefault(); toggleDocumentPanel();
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [view, toggleDocumentPanel]);
  return {
    sourcesIndex, setSourcesIndex, closeSources, openSources, documentRequest, documentSelection, setDocumentSelection,
    documentRefresh, setDocumentRefresh, documentPanelOpen, documentPanelExpanded, setDocumentPanelExpanded, documentPreview,
    setDocumentPreview, closeDocumentPanel, toggleDocumentPanel, diagram, setDiagram, closeDiagram, diagramApi, previewDocument,
    editDocument, resetPanels,
  };
}
