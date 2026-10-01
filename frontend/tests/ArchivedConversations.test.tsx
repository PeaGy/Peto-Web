import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ArchivedConversations from '../src/features/settings/ArchivedConversations';
import * as api from '../src/shared/api/api';

vi.mock('../src/shared/api/api', async original => ({...await original<typeof import('../src/shared/api/api')>(), listConversations:vi.fn(), updateConversation:vi.fn(), deleteConversation:vi.fn()}));
const item = (id: string): api.Conversation => ({id, title: `Chat ${id}`, created_at:1, updated_at:2, message_count:2, archived:true});
const props = () => ({open:true, disabled:false, onOpen:vi.fn(), onChanged:vi.fn(), onUnauthorized:vi.fn()});
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[item('A')], has_more:false});
  vi.mocked(api.updateConversation).mockResolvedValue();
  vi.mocked(api.deleteConversation).mockResolvedValue();
});

it('chỉ tải khi mở mục, phân trang và tìm trong danh sách lưu trữ', async () => {
  const p = props();
  const view = render(<ArchivedConversations {...p} open={false}/>);
  expect(api.listConversations).not.toHaveBeenCalled();
  vi.mocked(api.listConversations).mockResolvedValueOnce({conversations:[item('A')],has_more:true}).mockResolvedValueOnce({conversations:[item('B')],has_more:false});
  view.rerender(<ArchivedConversations {...p}/>);
  await screen.findByRole('button',{name:'Chat A'});
  fireEvent.click(screen.getByRole('button',{name:'Xem thêm'}));
  await screen.findByRole('button',{name:'Chat B'});
  expect(api.listConversations).toHaveBeenLastCalledWith(1,50,'',{archived:true},expect.any(AbortSignal));
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'Tài liệu'}});
  await waitFor(() => expect(api.listConversations).toHaveBeenLastCalledWith(0,50,'Tài liệu',{archived:true},expect.any(AbortSignal)));
  await screen.findByRole('button',{name:'Chat A'});
  expect(screen.queryByRole('button',{name:'Chat B'})).toBeNull();
});

it('mở để đọc, khôi phục thành công rồi thông báo cho app', async () => {
  const p = props(); render(<ArchivedConversations {...p}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Chat A'}));
  expect(p.onOpen).toHaveBeenCalledWith('A');
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[],has_more:false});
  fireEvent.click(screen.getByRole('button',{name:'Khôi phục: Chat A'}));
  await waitFor(() => expect(p.onChanged).toHaveBeenCalledWith(item('A'),false));
  expect(api.updateConversation).toHaveBeenCalledWith('A',{archived:false});
  await screen.findByText('Chưa có hội thoại đã lưu trữ.');
});

it('xóa cần xác nhận và lỗi khôi phục giữ lại chat để thử lại', async () => {
  const p = props(); render(<ArchivedConversations {...p}/>);
  await screen.findByRole('button',{name:'Chat A'});
  vi.mocked(api.updateConversation).mockRejectedValueOnce(new TypeError('Mất mạng'));
  fireEvent.click(screen.getByRole('button',{name:'Khôi phục: Chat A'}));
  await screen.findByRole('alert');
  expect(p.onChanged).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Chat A'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Xóa: Chat A'}));
  expect(api.deleteConversation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Hủy'}));
  fireEvent.click(screen.getByRole('button',{name:'Xóa: Chat A'}));
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[],has_more:false});
  fireEvent.click(screen.getByRole('button',{name:'Xóa vĩnh viễn'}));
  await waitFor(() => expect(p.onChanged).toHaveBeenCalledWith(item('A'),true));
  expect(api.deleteConversation).toHaveBeenCalledWith('A');
});

it('bỏ qua phản hồi tìm kiếm cũ và báo hết phiên', async () => {
  let finish!: (value:{conversations:api.Conversation[];has_more:boolean}) => void;
  vi.mocked(api.listConversations).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  const p=props();render(<ArchivedConversations {...p}/>);
  await waitFor(() => expect(api.listConversations).toHaveBeenCalledOnce());
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[item('B')],has_more:false});
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'B'}});
  await screen.findByRole('button',{name:'Chat B'});
  await act(async () => finish({conversations:[item('A')],has_more:false}));
  expect(screen.queryByRole('button',{name:'Chat A'})).toBeNull();
  vi.mocked(api.updateConversation).mockRejectedValueOnce(new api.UnauthorizedError());
  fireEvent.click(screen.getByRole('button',{name:'Khôi phục: Chat B'}));
  await waitFor(() => expect(p.onUnauthorized).toHaveBeenCalledOnce());
});

it('rời tài khoản khi đang khôi phục không cập nhật app cũ', async () => {
  let finish!: () => void;
  vi.mocked(api.updateConversation).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  const p=props();const view=render(<ArchivedConversations {...p}/>);
  await screen.findByRole('button',{name:'Chat A'});
  fireEvent.click(screen.getByRole('button',{name:'Khôi phục: Chat A'}));
  view.unmount();
  await act(async () => finish());
  expect(p.onChanged).not.toHaveBeenCalled();
});
