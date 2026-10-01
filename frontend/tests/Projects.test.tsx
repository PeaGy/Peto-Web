import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ProjectSidebar from '../src/features/projects/ProjectSidebar';
import MoveConversationDialog from '../src/features/projects/MoveConversationDialog';
import { useProjects } from '../src/features/projects/useProjects';
import * as projects from '../src/features/projects/projectApi';
import * as api from '../src/shared/api/api';

vi.mock('../src/features/projects/projectApi', async original => ({
  ...await original<typeof import('../src/features/projects/projectApi')>(),
  listProjects:vi.fn(),
}));
vi.mock('../src/shared/api/api', async original => ({...await original<typeof import('../src/shared/api/api')>(), listConversations:vi.fn()}));

const detail = (): projects.Project => ({id:'P',name:'Báo cáo',created_at:1,updated_at:1});
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(projects.listProjects).mockResolvedValue([detail()]);
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[],has_more:false});
});

it('chưa có dự án thì tạo và chuyển ngay, lỗi chuyển không tạo trùng khi thử lại', async () => {
  const onCreate=vi.fn().mockResolvedValue(detail()),onSave=vi.fn();
  const props={item:{id:'A',title:'Chat cần chuyển',created_at:1,updated_at:1,message_count:2},projects:[],busy:false,loading:false,onRetry:vi.fn(),onCreate,onSave,onClose:vi.fn()};
  const view=render(<MoveConversationDialog {...props}/>);
  expect((screen.getByRole('button',{name:'Tạo và chuyển'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Tên dự án mới'),{target:{value:' Báo cáo '}});
  fireEvent.click(screen.getByRole('button',{name:'Tạo và chuyển'}));
  await waitFor(()=>expect(onSave).toHaveBeenCalledWith('P'));
  expect(onCreate).toHaveBeenCalledWith('Báo cáo');
  view.rerender(<MoveConversationDialog {...props} error="Chưa chuyển được hội thoại"/>);
  expect((screen.getByLabelText('Nơi lưu hội thoại') as HTMLSelectElement).value).toBe('P');
  fireEvent.click(screen.getByRole('button',{name:'Chuyển',exact:true}));
  expect(onSave).toHaveBeenCalledTimes(2);
  expect(onCreate).toHaveBeenCalledTimes(1);
});

it('không cho chuyển về đích cũ, báo tải lỗi và cho thử tải lại danh sách', () => {
  const props={item:{id:'A',title:'Chat',project_id:'P',created_at:1,updated_at:1,message_count:2},projects:[detail()],busy:false,loading:false,onRetry:vi.fn(),onCreate:vi.fn(),onSave:vi.fn(),onClose:vi.fn()};
  const view=render(<MoveConversationDialog {...props}/>);
  const button=screen.getByRole('button',{name:'Chuyển',exact:true}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Nơi lưu hội thoại'),{target:{value:''}});
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  expect(props.onSave).toHaveBeenCalledWith(null);
  view.rerender(<MoveConversationDialog {...props} projects={[]} loadError="Chưa tải được dự án."/>);
  expect(screen.getByRole('alert').textContent).toContain('Chưa tải được dự án');
  fireEvent.click(screen.getByRole('button',{name:'Thử tải lại'}));
  expect(props.onRetry).toHaveBeenCalledOnce();
});

it('bấm folder chỉ đóng mở chat, nút chat mới và hội thoại có thao tác riêng', () => {
  const chat={id:'A',title:'Hội thoại báo cáo',created_at:1,updated_at:1,message_count:2};
  const state={projects:[detail()],chats:{P:{items:[chat],more:false,loading:false}},loading:false,error:'',refresh:vi.fn(),refreshChats:vi.fn(),ensureChats:vi.fn()};
  const props={state,activeId:null,conversationId:'A',disabled:false,onCreate:vi.fn(),onNewChat:vi.fn(),onChat:vi.fn(),onMenu:vi.fn(),onConversationMenu:vi.fn()};
  const view=render(<ProjectSidebar {...props}/>);
  const folder=screen.getByRole('button',{name:'Báo cáo',exact:true});
  expect(folder.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(folder);
  expect(folder.getAttribute('aria-expanded')).toBe('true');
  expect(state.ensureChats).toHaveBeenCalledWith('P');
  expect(state.refreshChats).not.toHaveBeenCalled();
  expect(props.onChat).not.toHaveBeenCalled();
  expect(props.onNewChat).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Hội thoại báo cáo',exact:true}));
  expect(props.onChat).toHaveBeenCalledWith('A');
  view.rerender(<ProjectSidebar {...props} activeId="P"/>);
  fireEvent.click(folder);
  expect(screen.queryByRole('button',{name:'Hội thoại báo cáo',exact:true})).toBeNull();
  view.rerender(<ProjectSidebar {...props} activeId="P"/>);
  expect(folder.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(screen.getByRole('button',{name:'Chat mới trong dự án Báo cáo'}));
  expect(props.onNewChat).toHaveBeenCalledWith('P');
  expect(folder.getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByRole('button',{name:'Hội thoại báo cáo',exact:true})).toBeTruthy();
  view.rerender(<ProjectSidebar {...props} activeId="P" state={{...state,loading:true,chats:{P:{items:[chat],more:false,loading:true}}}}/>);
  expect(screen.queryByRole('status')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Dự án',exact:true}));
  expect(screen.queryByRole('button',{name:'Báo cáo',exact:true})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Dự án',exact:true}));
  expect(screen.getByRole('button',{name:'Hội thoại báo cáo',exact:true})).toBeTruthy();
});

it('thu gọn mục dự án trống, nhớ lựa chọn khi mở lại và vẫn tạo được dự án', () => {
  const state={projects:[],chats:{},loading:false,error:'',refresh:vi.fn(),refreshChats:vi.fn(),ensureChats:vi.fn()};
  const props={state,activeId:null,conversationId:null,disabled:false,onCreate:vi.fn(),onNewChat:vi.fn(),onChat:vi.fn(),onMenu:vi.fn(),onConversationMenu:vi.fn()};
  const view=render(<ProjectSidebar {...props}/>);
  const heading=screen.getByRole('button',{name:'Dự án',exact:true});
  expect(heading.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(heading);
  expect(heading.getAttribute('aria-expanded')).toBe('false');
  expect(screen.getByText('Chưa có dự án.').closest('[hidden]')).toBeTruthy();
  view.unmount();
  render(<ProjectSidebar {...props}/>);
  expect(screen.getByRole('button',{name:'Dự án',exact:true}).getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(screen.getByRole('button',{name:'Tạo dự án'}));
  expect(props.onCreate).toHaveBeenCalledOnce();
  expect(screen.getByRole('button',{name:'Dự án',exact:true}).getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByText('Chưa có dự án.').closest('[hidden]')).toBeNull();
});

it('tải sẵn chat của mọi folder với tối đa ba yêu cầu, mở folder dùng lại dữ liệu đã tải', async () => {
  const items=Array.from({length:5},(_,i)=>({...detail(),id:`P${i}`}));
  vi.mocked(projects.listProjects).mockResolvedValue(items);
  const replies:Record<string,()=>void>={};
  vi.mocked(api.listConversations).mockImplementation((_offset,_limit,_query,filter)=>new Promise(resolve=>{
    const id=filter!.projectId!;
    replies[id]=()=>resolve({conversations:[],has_more:false});
  }));
  const unauthorized=vi.fn();
  const {result}=renderHook(()=>useProjects('account',unauthorized));
  await waitFor(()=>expect(api.listConversations).toHaveBeenCalledTimes(3));
  act(()=>{void result.current.ensureChats('P0');});
  expect(api.listConversations).toHaveBeenCalledTimes(3);
  await act(async()=>{replies.P0();replies.P1();});
  await waitFor(()=>expect(api.listConversations).toHaveBeenCalledTimes(5));
  await act(async()=>{replies.P2();replies.P3();replies.P4();});
  expect(Object.values(result.current.chats).every(page=>page.loaded && !page.loading)).toBe(true);
  await act(async()=>{await result.current.ensureChats('P0');await result.current.ensureChats('P4');});
  expect(api.listConversations).toHaveBeenCalledTimes(5);
});

it('cập nhật nền giữ chat và không bật lại trạng thái tải danh sách dự án', async () => {
  const chat={id:'A',title:'Chat đã tải',created_at:1,updated_at:1,message_count:1};
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[chat],has_more:true});
  const unauthorized=vi.fn();
  const {result}=renderHook(()=>useProjects('account',unauthorized));
  await waitFor(()=>expect(result.current.chats.P?.loaded).toBe(true));
  let projectReply!:(items:projects.Project[])=>void;
  let chatReply!:(page:Awaited<ReturnType<typeof api.listConversations>>)=>void;
  vi.mocked(projects.listProjects).mockImplementationOnce(()=>new Promise(resolve=>{projectReply=resolve;}));
  vi.mocked(api.listConversations).mockImplementationOnce(()=>new Promise(resolve=>{chatReply=resolve;}));
  act(()=>{void result.current.refresh();void result.current.refreshChats('P');});
  expect(result.current.loading).toBe(false);
  expect(result.current.projects).toEqual([detail()]);
  expect(result.current.chats.P).toMatchObject({items:[chat],more:true,loading:true,loaded:true});
  await act(async()=>{projectReply([detail()]);chatReply({conversations:[{...chat,title:'Chat mới cập nhật'}],has_more:false});});
  expect(result.current.chats.P.items[0].title).toBe('Chat mới cập nhật');
  expect(result.current.chats.P.loading).toBe(false);
});

it('hội thoại trả về muộn từ phiên cũ không đi vào tài khoản mới', async () => {
  let resolve!:(value:Awaited<ReturnType<typeof api.listConversations>>)=>void;
  vi.mocked(api.listConversations).mockImplementationOnce(()=>new Promise(yes=>{resolve=yes;}));
  const unauthorized=vi.fn();
  function Harness({scope}:{scope:string|null}) {
    const state=useProjects(scope,unauthorized);
    return <><button onClick={()=>void state.refreshChats('P')}>Tải</button><span>{state.chats.P?.items.map(c=>c.title).join(',')}</span></>;
  }
  const view=render(<Harness scope="account"/>);
  fireEvent.click(screen.getByText('Tải'));
  view.rerender(<Harness scope={null}/>);
  view.rerender(<Harness scope="account"/>);
  fireEvent.click(screen.getByText('Tải'));
  await act(async()=>{resolve({conversations:[{id:'old',title:'Chat phiên cũ',created_at:1,updated_at:1,message_count:1}],has_more:false});});
  expect(screen.queryByText('Chat phiên cũ')).toBeNull();
});
