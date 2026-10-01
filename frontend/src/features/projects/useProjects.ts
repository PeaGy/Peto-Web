import { useCallback, useEffect, useRef, useState } from 'react';
import { listConversations, UnauthorizedError, type Conversation } from '../../shared/api/api';
import { listProjects, type Project } from './projectApi';

type ChatPage = {items:Conversation[]; more:boolean; loading:boolean; loaded?:boolean; error?:string};

export function useProjects(scope: string | null, onUnauthorized: () => void) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [chats, setChats] = useState<Record<string, ChatPage>>({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(scope));
  const current = useRef(scope);
  current.current = scope;
  const version = useRef(0);
  const lifetime = useRef(0);
  const loaded = useRef(false);
  const chatVersions = useRef<Record<string, number>>({});
  const chatsRef = useRef<Record<string, ChatPage>>({});
  const pending = useRef<Partial<Record<string, Promise<void>>>>({});

  const refreshChats = useCallback((id: string, more = false): Promise<void> => {
    if (!scope) return Promise.resolve();
    const session = scope, epoch = lifetime.current;
    const request = chatVersions.current[id] = (chatVersions.current[id] ?? 0) + 1;
    const old = chatsRef.current[id];
    const items = old?.items ?? [];
    const valid = () => current.current === session && epoch === lifetime.current && request === chatVersions.current[id];
    const publish = (page: ChatPage) => {
      chatsRef.current = {...chatsRef.current, [id]:page};
      setChats(chatsRef.current);
    };
    // Giữ các hàng đã có; cập nhật nền không chèn thêm dòng tải vào danh sách.
    publish({items, more:old?.more ?? false, loading:true, loaded:old?.loaded ?? false});
    const task = (async () => {
      try {
        const result = await listConversations(more ? items.length : 0, 20, '', {projectId:id});
        if (!valid()) return;
        publish({items:more ? [...items,...result.conversations] : result.conversations, more:result.has_more, loading:false, loaded:true});
      } catch (err) {
        if (!valid()) return;
        if (err instanceof UnauthorizedError) onUnauthorized();
        else publish({items, more:old?.more ?? false, loading:false, loaded:old?.loaded ?? false, error:'Chưa tải được hội thoại dự án.'});
      } finally {
        if (valid()) delete pending.current[id];
      }
    })();
    pending.current[id] = task;
    return task;
  }, [scope, onUnauthorized]);

  const ensureChats = useCallback((id:string): Promise<void> => {
    const task = pending.current[id];
    if (task) return task;
    if (chatsRef.current[id] && !chatsRef.current[id].error) return Promise.resolve();
    return refreshChats(id);
  }, [refreshChats]);

  const refresh = useCallback(async () => {
    if (!scope) return;
    const session = scope, epoch = lifetime.current, request = ++version.current;
    setLoading(!loaded.current);
    try {
      const items = await listProjects();
      if (current.current !== session || request !== version.current || epoch !== lifetime.current) return;
      loaded.current = true;
      setProjects(items); setError('');
      // Tải trang đầu của mọi folder, tối đa ba yêu cầu cùng lúc. Bấm folder dùng lại kết quả hoặc yêu cầu đang chạy.
      let index = 0;
      const preload = async () => {
        while (index < items.length) {
          if (current.current !== session || epoch !== lifetime.current || request !== version.current) return;
          await ensureChats(items[index++].id);
        }
      };
      void Promise.all(Array.from({length:Math.min(3,items.length)},preload));
    } catch (err) {
      if (current.current !== session || request !== version.current || epoch !== lifetime.current) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError('Chưa tải được dự án.');
    } finally {
      if (current.current === session && request === version.current && epoch === lifetime.current) setLoading(false);
    }
  }, [scope, onUnauthorized, ensureChats]);

  useEffect(() => {
    setProjects([]); setChats({}); setError(''); setLoading(Boolean(scope));
    loaded.current = false;
    chatsRef.current = {}; pending.current = {}; chatVersions.current = {};
    void refresh();
    return () => { ++version.current; ++lifetime.current; pending.current = {}; chatVersions.current = {}; };
  }, [scope, refresh]);
  return {projects, chats, loading, error, refresh, refreshChats, ensureChats};
}
