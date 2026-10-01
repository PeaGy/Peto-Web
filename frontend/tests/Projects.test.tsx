import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import ProjectWorkspace from '../src/features/projects/ProjectWorkspace';
import MoveConversationDialog from '../src/features/projects/MoveConversationDialog';
import { ProjectContext } from '../src/features/projects/ProjectControls';
import { useProjects } from '../src/features/projects/useProjects';
import * as projects from '../src/features/projects/projectApi';
import * as api from '../src/shared/api/api';

vi.mock('../src/features/projects/projectApi', async original => ({
  ...await original<typeof import('../src/features/projects/projectApi')>(),
  listProjects:vi.fn(), getProject:vi.fn(), updateProject:vi.fn(), uploadProjectFile:vi.fn(), deleteProjectFile:vi.fn(),
}));
vi.mock('../src/shared/api/api', async original => ({...await original<typeof import('../src/shared/api/api')>(), listConversations:vi.fn()}));

const file = (id:string): projects.ProjectFile => ({id,name:`${id}.txt`,mime:'text/plain',size:10,url:`/api/projects/P/files/${id}`,document:{version:1,status:'ready',notice:'Đã đọc',characters:10}});
const detail = (): projects.ProjectDetail => ({id:'P',name:'Báo cáo',instructions:'Hướng dẫn đã lưu',created_at:1,updated_at:1,files:[file('A')]});
const callbacks = () => ({onMore:vi.fn(),onChat:vi.fn(),onNewChat:vi.fn(),onUpdated:vi.fn(),onUnauthorized:vi.fn(),onSidebar:vi.fn(),onOptions:vi.fn()});
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(projects.getProject).mockResolvedValue(detail());
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

it('thêm tài liệu và đổi tên không làm mất hướng dẫn đang soạn', async () => {
  const props={id:'P',name:'Báo cáo',chats:[],chatsLoading:false,more:false,disabled:false,...callbacks()};
  const view=render(<ProjectWorkspace {...props}/>);
  const instructions=await screen.findByLabelText('Peto nên trả lời và làm việc thế nào trong dự án này?');
  await waitFor(()=>expect((instructions as HTMLTextAreaElement).value).toBe('Hướng dẫn đã lưu'));
  fireEvent.change(instructions,{target:{value:'Bản nháp cần giữ'}});
  vi.mocked(projects.getProject).mockResolvedValue({...detail(),files:[file('A'),file('B')]});
  fireEvent.change(screen.getByLabelText('Thêm tài liệu dự án'),{target:{files:[new File(['tài liệu'],'B.txt',{type:'text/plain'})]}});
  await screen.findByText('B.txt');
  expect((instructions as HTMLTextAreaElement).value).toBe('Bản nháp cần giữ');
  view.rerender(<ProjectWorkspace {...props} name="Tên mới"/>);
  expect(screen.getByRole('heading',{name:'Tên mới'})).toBeTruthy();
  expect((instructions as HTMLTextAreaElement).value).toBe('Bản nháp cần giữ');
  fireEvent.click(screen.getByRole('button',{name:'Lưu hướng dẫn'}));
  await waitFor(()=>expect(projects.updateProject).toHaveBeenCalledWith('P',{instructions:'Bản nháp cần giữ'}));
});

it('tài liệu chưa chọn không tự vào lượt gửi và giới hạn lựa chọn là bốn', async () => {
  vi.mocked(projects.getProject).mockResolvedValue({...detail(),files:['A','B','C','D','E'].map(file)});
  function Context() {const [selected,setSelected]=useState<string[]>([]);return <ProjectContext id="P" selected={selected} onSelect={setSelected} onOpen={()=>{}} onUnauthorized={()=>{}} disabled={false}/>;}
  render(<Context/>);
  fireEvent.click(screen.getByText('Tài liệu cho lượt này'));
  const boxes=await screen.findAllByRole('checkbox');
  expect(boxes.every(box=>!(box as HTMLInputElement).checked)).toBe(true);
  boxes.slice(0,4).forEach(box=>fireEvent.click(box));
  expect((boxes[4] as HTMLInputElement).disabled).toBe(true);
  expect(screen.getByText('Tài liệu cho lượt này · 4')).toBeTruthy();
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
