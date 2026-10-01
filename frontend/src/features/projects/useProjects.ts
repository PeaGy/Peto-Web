import { useCallback, useEffect, useRef, useState } from 'react';
import { listConversations, UnauthorizedError, type Conversation } from '../../shared/api/api';
import { listProjects, type Project } from './projectApi';

export function useProjects(scope: string | null, onUnauthorized: () => void) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [chats, setChats] = useState<Record<string, {items:Conversation[]; more:boolean; loading:boolean; error?:string}>>({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const current = useRef(scope);
  current.current = scope;
  const version = useRef(0);
  const lifetime = useRef(0);
  const chatVersions = useRef<Record<string, number>>({});
  const chatsRef = useRef(chats);
  chatsRef.current = chats;
  const refresh = useCallback(async () => {
    if (!scope) return;
    const session = scope, request = ++version.current;
    setLoading(true);
    try {
      const items = await listProjects();
      if (current.current !== session || request !== version.current) return;
      setProjects(items); setError('');
    } catch (err) {
      if (current.current !== session || request !== version.current) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError('Chưa tải được dự án.');
    } finally { if (current.current === session && request === version.current) setLoading(false); }
  }, [scope, onUnauthorized]);
  const refreshChats = useCallback(async (id: string, more = false) => {
    if (!scope) return;
    const session = scope, epoch = lifetime.current;
    const request = chatVersions.current[id] = (chatVersions.current[id] ?? 0) + 1;
    const old = chatsRef.current[id]?.items ?? [];
    setChats(value => ({...value, [id]:{items:old, more:false, loading:true}}));
    try {
      const result = await listConversations(more ? old.length : 0, 20, '', {projectId:id});
      if (current.current !== session || epoch !== lifetime.current || request !== chatVersions.current[id]) return;
      setChats(value => ({...value, [id]:{items:more ? [...old,...result.conversations] : result.conversations, more:result.has_more, loading:false}}));
    } catch (err) {
      if (current.current !== session || epoch !== lifetime.current || request !== chatVersions.current[id]) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setChats(value => ({...value, [id]:{items:old, more:false, loading:false, error:'Chưa tải được hội thoại dự án.'}}));
    }
  }, [scope, onUnauthorized]);
  useEffect(() => {
    setProjects([]); setChats({}); setError(''); setLoading(false);
    chatVersions.current = {};
    void refresh();
    return () => { ++version.current; ++lifetime.current; chatVersions.current = {}; };
  }, [scope, refresh]);
  return {projects, chats, loading, error, refresh, refreshChats};
}
