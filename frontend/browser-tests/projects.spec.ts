import { test, expect, type Page } from '@playwright/test';
import { mockPeto, openSidebar, noPageOverflow, title } from './fixtures';

async function projectsFixture(page:Page) {
  const chat=await mockPeto(page);
  const state={projects:[{id:'P',name:'Báo cáo phần mềm',created_at:1,updated_at:2}],assigned:null as string|null,sent:null as Record<string,unknown>|null,creates:0,moveFailures:0,conversationTitle:title,deleted:false};
  await page.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();
    const json=(value:unknown)=>route.fulfill({json:value});
    if(path==='/api/projects') {
      if(method==='POST') {state.creates++;const project={created_at:1,updated_at:2,id:'NEW',name:request.postDataJSON().name};state.projects.push(project);return json(project);}
      return json({projects:state.projects});
    }
    const projectPath=path.match(/^\/api\/projects\/([^/]+)$/);
    if(projectPath) {
      const project=state.projects.find(p=>p.id===projectPath[1])!;
      if(method==='PATCH') {Object.assign(project,request.postDataJSON());return json({updated:true});}
      if(method==='DELETE') {state.projects=state.projects.filter(p=>p!==project);if(state.assigned===project.id)state.assigned=null;return json({deleted:true});}
      return json(project);
    }
    if(path==='/api/conversations') {
      const project=url.searchParams.get('project_id');
      const conversations=state.deleted ? [] : [{id:'A',title:state.conversationTitle,created_at:1,updated_at:2,message_count:chat.messages.length,title_state:'generated',project_id:state.assigned}];
      return json({has_more:false,conversations:conversations.filter(c=>project ? c.project_id===project : !url.searchParams.has('unassigned') || !c.project_id)});
    }
    if(path==='/api/conversations/A' && method==='PATCH') {
      const change=request.postDataJSON();
      if('project_id' in change) {
        if(state.moveFailures>0){state.moveFailures--;return route.fulfill({status:500,json:{detail:'Chưa chuyển được hội thoại. Thử lại nhé.'}});}
        state.assigned=change.project_id;
      }
      if('title' in change)state.conversationTitle=change.title;
      return json({updated:true});
    }
    if(path==='/api/conversations/A' && method==='DELETE') {state.deleted=true;return json({deleted:true});}
    if(path==='/api/conversations/A/messages') return json({messages:chat.messages,project_id:state.assigned,persona:'assistant'});
    if(path==='/api/chat') state.sent=request.postDataJSON();
    return route.fallback();
  });
  return state;
}

async function expandFolder(page:Page,name:string) {
  const folder=page.getByRole('button',{name,exact:true});
  if(await folder.getAttribute('aria-expanded')==='false') await folder.click();
  return folder;
}

test('chuyển chat khi chưa có dự án: tạo ngay và thử lại không tạo trùng',async({page})=>{
  const state=await projectsFixture(page);state.projects=[];state.moveFailures=1;
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await page.getByRole('button',{name:title,exact:true}).click();await openSidebar(page);
  await page.locator('.conversation-list .conv').first().hover();
  await page.getByRole('button',{name:`Tùy chọn ${title}`,exact:true}).click();
  await page.getByRole('button',{name:'Chuyển vào dự án',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Chuyển hội thoại vào dự án'});
  await expect(dialog.getByText('Chưa có dự án.',{exact:false})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Tạo và chuyển'})).toBeDisabled();
  await dialog.getByLabel('Tên dự án mới').fill('Dự án đầu tiên');
  await dialog.getByRole('button',{name:'Tạo và chuyển'}).click();
  await expect(dialog.getByRole('alert')).toHaveText('Chưa chuyển được hội thoại. Thử lại nhé.');
  await expect(dialog.getByLabel('Nơi lưu hội thoại')).toHaveValue('NEW');
  await dialog.getByRole('button',{name:'Chuyển',exact:true}).click();
  await expect(dialog).toHaveCount(0);await expect.poll(()=>state.assigned).toBe('NEW');
  expect(state.creates).toBe(1);
  await expect(page.locator('.conversation-list .conv')).toHaveCount(0);
  await expandFolder(page,'Dự án đầu tiên');
  await expect(page.locator('.project-chats').getByRole('button',{name:title,exact:true})).toBeVisible();
});

test('folder chỉ đóng mở chat, tên dự án ở góc trái và tệp gửi bằng đính kèm',async({page},info)=>{
  const state=await projectsFixture(page);state.assigned='P';
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  const folder=await expandFolder(page,'Báo cáo phần mềm');
  await expect(page.locator('.project-chat-name')).toHaveCount(0);
  await expect(page.getByText('Tài liệu cho lượt này')).toHaveCount(0);
  await expect(page.getByLabel('Peto nên trả lời và làm việc thế nào trong dự án này?')).toHaveCount(0);
  await page.locator('.project-chats').getByRole('button',{name:title,exact:true}).click();
  await expect(page.locator('.project-chat-name')).toHaveText('Báo cáo phần mềm');
  await expect(page.locator('.table-scroll')).toBeVisible();
  const bounds=await page.locator('.project-chat-name').boundingBox();
  const chatBounds=await page.locator('main.chat').boundingBox();
  expect(bounds!.y).toBeLessThan(70);
  expect(bounds!.x-chatBounds!.x).toBeLessThan(80);
  const panel=await page.getByRole('button',{name:'Mở bảng tài liệu',exact:true}).boundingBox();
  expect(panel!.x).toBeGreaterThan(bounds!.x+bounds!.width);
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('project-chat.png');
  await openSidebar(page);
  await page.locator('.project-row').hover();
  await expect(page.getByRole('button',{name:'Chat mới trong dự án Báo cáo phần mềm'})).toBeVisible();
  await expect(page).toHaveScreenshot('project-sidebar.png');
  await folder.click();
  await expect(folder).toHaveAttribute('aria-expanded','false');
  await expect(page.locator('.project-chats')).toHaveCount(0);
  // Gập thư mục không mở màn hình khác hoặc xóa hội thoại đang xem.
  await expect(page.locator('.project-chat-name')).toHaveText('Báo cáo phần mềm');
  await folder.click();
  await page.locator('.project-chats').getByRole('button',{name:title,exact:true}).click();
  await page.locator('.composer input[type=file]').setInputFiles('browser-tests/yeu-cau.txt');
  await expect(page.getByRole('button',{name:'Gỡ yeu-cau.txt'})).toBeVisible();
  await page.getByLabel('Nhắn cho Peto',{exact:true}).fill('Tóm tắt yêu cầu');
  await page.getByRole('button',{name:'Gửi',exact:true}).click();
  await expect.poll(()=>state.sent?.project_id).toBe('P');
  expect(state.sent?.project_file_ids).toBeUndefined();
  expect(state.sent?.attachments).toEqual([expect.objectContaining({name:'yeu-cau.txt'})]);
  await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.')).toBeVisible();
  await openSidebar(page);
  if(info.project.name==='mobile') await expect(page.locator('.project-row .conv-hover-actions button')).toHaveCount(2);
});

test('tải sẵn chat khi F5, mở lại folder không tải trùng hoặc thêm dòng đang tải',async({page})=>{
  const state=await projectsFixture(page);state.assigned='P';
  let loads=0,release!:()=>void;
  const ready=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/conversations?**',async route=>{
    if(new URL(route.request().url()).searchParams.get('project_id')!=='P') return route.fallback();
    loads++;await ready;return route.fallback();
  });
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await expect.poll(()=>loads).toBe(1);
  const folder=await expandFolder(page,'Báo cáo phần mềm');
  await expect(page.getByRole('status',{name:'Đang tải hội thoại dự án'})).toBeVisible();
  await folder.click();await folder.click();
  expect(loads).toBe(1);
  release();
  await expect(page.locator('.project-chats').getByRole('button',{name:title,exact:true})).toBeVisible();
  await expect(page.locator('.project-sidebar [role=status]')).toHaveCount(0);
  await folder.click();await folder.click();
  expect(loads).toBe(1);
  await page.reload();await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();
  await expect.poll(()=>loads).toBe(2);
  await openSidebar(page);await expandFolder(page,'Báo cáo phần mềm');
  await page.locator('.project-chats').getByRole('button',{name:title,exact:true}).click();
  await expect(page.locator('.table-scroll')).toBeVisible();
  await openSidebar(page);
  await expect(page.locator('.project-sidebar [role=status]')).toHaveCount(0);
  expect(loads).toBe(2);
});

test('đổi tên và xóa chat trong folder khác vẫn cập nhật danh sách đã tải sẵn',async({page})=>{
  const state=await projectsFixture(page);state.assigned='P';
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await expandFolder(page,'Báo cáo phần mềm');
  const chats=page.locator('.project-chats');
  await chats.getByRole('button',{name:title,exact:true}).hover();
  await chats.getByRole('button',{name:`Tùy chọn ${title}`,exact:true}).click();
  await page.getByRole('button',{name:'Đổi tên',exact:true}).click();
  const rename=page.getByRole('dialog',{name:'Đổi tên hội thoại'});
  await rename.getByRole('textbox').fill('Chat đã đổi tên');await rename.getByRole('button',{name:'Lưu',exact:true}).click();
  await expect(chats.getByRole('button',{name:'Chat đã đổi tên',exact:true})).toBeVisible();
  await expect(page.locator('.project-sidebar [role=status]')).toHaveCount(0);
  await chats.getByRole('button',{name:'Chat đã đổi tên',exact:true}).hover();
  await chats.getByRole('button',{name:'Tùy chọn Chat đã đổi tên',exact:true}).click();
  await page.getByRole('button',{name:'Xóa hội thoại',exact:true}).click();
  await page.getByRole('dialog',{name:'Xóa hội thoại này?'}).getByRole('button',{name:'Xóa hội thoại',exact:true}).click();
  await expect(chats.getByText('Chưa có hội thoại.',{exact:true})).toBeVisible();
  await expect(chats.getByRole('button',{name:'Chat đã đổi tên',exact:true})).toHaveCount(0);
  expect(state.deleted).toBe(true);
  await expect(page.locator('.project-chat-name')).toHaveCount(0);
});

test('tạo chat trong folder, đổi tên và xóa dự án vẫn giữ hội thoại đang xem',async({page})=>{
  const state=await projectsFixture(page);
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await page.getByRole('button',{name:'Tạo dự án',exact:true}).click();
  const create=page.getByRole('dialog',{name:'Tạo dự án'});
  await create.getByRole('textbox').fill('Bài tập mới');await create.getByRole('button',{name:'Lưu',exact:true}).click();
  await expect(page.locator('.project-chat-name')).toHaveText('Bài tập mới');
  await openSidebar(page);
  await page.locator('.conversation-list .conv').first().hover();
  await page.getByRole('button',{name:`Tùy chọn ${title}`,exact:true}).click();
  await page.getByRole('button',{name:'Chuyển vào dự án',exact:true}).click();
  const move=page.getByRole('dialog',{name:'Chuyển hội thoại vào dự án'});
  await move.getByLabel('Nơi lưu hội thoại').selectOption('NEW');await move.getByRole('button',{name:'Chuyển',exact:true}).click();
  await expect(move).toHaveCount(0);await expect.poll(()=>state.assigned).toBe('NEW');
  await expandFolder(page,'Bài tập mới');
  await page.locator('.project-chats').getByRole('button',{name:title,exact:true}).click();
  await expect(page.locator('.table-scroll')).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button',{name:'Bài tập mới',exact:true}).hover();
  await page.getByRole('button',{name:'Tùy chọn dự án Bài tập mới'}).click();
  await page.getByRole('button',{name:'Đổi tên dự án',exact:true}).click();
  const rename=page.getByRole('dialog',{name:'Đổi tên dự án'});
  await rename.getByRole('textbox').fill('Bài tập đã đổi');await rename.getByRole('button',{name:'Lưu',exact:true}).click();
  await expect(rename).toHaveCount(0);await expect(page.locator('.project-chat-name')).toHaveText('Bài tập đã đổi');
  await page.getByRole('button',{name:'Bài tập đã đổi',exact:true}).hover();
  await page.getByRole('button',{name:'Tùy chọn dự án Bài tập đã đổi'}).click();
  await page.getByRole('button',{name:'Xóa dự án',exact:true}).click();
  await page.getByRole('dialog',{name:'Xóa dự án này?'}).getByRole('button',{name:'Xóa',exact:true}).click();
  await expect.poll(()=>state.assigned).toBeNull();
  await expect(page.locator('.project-chat-name')).toHaveCount(0);
  await expect(page.locator('.table-scroll')).toBeAttached();
  await expect(page.locator('.conversation-list').getByRole('button',{name:title,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Bài tập đã đổi',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Báo cáo phần mềm',exact:true}).hover();
  await page.getByRole('button',{name:'Chat mới trong dự án Báo cáo phần mềm'}).click();
  await expect(page.locator('.project-chat-name')).toHaveText('Báo cáo phần mềm');
  await expect(page.locator('.table-scroll')).toHaveCount(0);
  await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();
});
