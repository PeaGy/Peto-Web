import { test, expect, type Page } from '@playwright/test';
import { mockPeto, openSidebar, noPageOverflow, title } from './fixtures';

async function projectsFixture(page:Page) {
  await mockPeto(page);
  const state={projects:[{id:'P',name:'Báo cáo phần mềm',created_at:1,updated_at:2,instructions:'Trả lời bằng tiếng Việt',files:[{id:'F',name:'yeu-cau.md',mime:'text/markdown',size:25,url:'/api/projects/P/files/F',document:{version:1,status:'ready',notice:'Đã đọc tài liệu',characters:25}}]}],assigned:null as string|null,sent:null as Record<string,unknown>|null,creates:0,moveFailures:0};
  await page.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();
    const json=(value:unknown)=>route.fulfill({json:value});
    if(path==='/api/projects') {
      if(method==='POST') {state.creates++;const project={...state.projects[0],created_at:1,updated_at:2,id:'NEW',name:request.postDataJSON().name,files:[],instructions:''};state.projects.push(project);return json(project);}
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
      const conversations=[{id:'A',title,created_at:1,updated_at:2,message_count:2,title_state:'generated',project_id:state.assigned}];
      return json({has_more:false,conversations:conversations.filter(c=>project ? c.project_id===project : !url.searchParams.has('unassigned') || !c.project_id)});
    }
    if(path==='/api/conversations/A' && method==='PATCH') {if(state.moveFailures>0){state.moveFailures--;return route.fulfill({status:500,json:{detail:'Chưa chuyển được hội thoại. Thử lại nhé.'}});}state.assigned=request.postDataJSON().project_id;return json({updated:true});}
    if(path==='/api/conversations/A/messages') return json({messages:[],project_id:state.assigned,persona:'assistant'});
    if(path==='/api/chat') state.sent=request.postDataJSON();
    return route.fallback();
  });
  return state;
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
  await page.getByRole('button',{name:'Mở rộng dự án Dự án đầu tiên'}).click();
  await expect(page.locator('.project-chats').getByRole('button',{name:title,exact:true})).toBeVisible();
  await expect(page.getByRole('textbox',{name:'Nhắn cho Peto',exact:true})).toBeVisible();
});

test('dự án có trang riêng và chỉ gửi tài liệu được chọn',async({page},info)=>{
  const state=await projectsFixture(page);
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await page.getByRole('button',{name:'Báo cáo phần mềm',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Báo cáo phần mềm'})).toBeVisible();
  await expect(page.getByLabel('Peto nên trả lời và làm việc thế nào trong dự án này?')).toHaveValue('Trả lời bằng tiếng Việt');
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('project-overview.png');
  await page.getByRole('button',{name:'+ Chat mới trong dự án',exact:true}).click();
  await page.getByText('Tài liệu cho lượt này',{exact:true}).click();
  const selection=page.getByRole('checkbox',{name:/yeu-cau.md/});
  await expect(selection).not.toBeChecked();await selection.check();
  await page.getByText('Tài liệu cho lượt này · 1',{exact:true}).click();
  await page.getByLabel('Nhắn cho Peto',{exact:true}).fill('Tóm tắt yêu cầu');
  await page.getByRole('button',{name:'Gửi',exact:true}).click();
  await expect.poll(()=>state.sent?.project_id).toBe('P');
  expect(state.sent?.project_file_ids).toEqual(['F']);
  await openSidebar(page);
  const toggle=page.getByRole('button',{name:'Mở rộng dự án Báo cáo phần mềm'});
  await expect(toggle).toHaveAttribute('aria-expanded','false');
  if(info.project.name==='mobile') await expect(page.locator('.project-row .conv-hover-actions button')).toBeVisible();
});

test('tạo dự án, chuyển chat và xóa dự án vẫn giữ hội thoại',async({page})=>{
  const state=await projectsFixture(page);
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await page.getByRole('button',{name:'Tạo dự án',exact:true}).click();
  const create=page.getByRole('dialog',{name:'Tạo dự án'});
  await create.getByRole('textbox').fill('Bài tập mới');await create.getByRole('button',{name:'Lưu',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Bài tập mới'})).toBeVisible();
  await openSidebar(page);
  await page.locator('.conversation-list .conv').first().hover();
  await page.getByRole('button',{name:`Tùy chọn ${title}`,exact:true}).click();
  await page.getByRole('button',{name:'Chuyển vào dự án',exact:true}).click();
  const move=page.getByRole('dialog',{name:'Chuyển hội thoại vào dự án'});
  await move.getByLabel('Nơi lưu hội thoại').selectOption('NEW');await move.getByRole('button',{name:'Chuyển',exact:true}).click();
  await expect.poll(()=>state.assigned).toBe('NEW');
  await expect(page.locator('.conversation-list .conv')).toHaveCount(0);
  await page.getByRole('button',{name:'Mở rộng dự án Bài tập mới'}).click();
  await expect(page.locator('.project-chats').getByRole('button',{name:title,exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Bài tập mới',exact:true}).click();
  await page.locator('.project-title-row').getByRole('button',{name:'Tùy chọn dự án Bài tập mới'}).click();
  await page.getByRole('button',{name:'Xóa dự án',exact:true}).click();
  await page.getByRole('dialog',{name:'Xóa dự án này?'}).getByRole('button',{name:'Xóa',exact:true}).click();
  await expect.poll(()=>state.assigned).toBeNull();
  await openSidebar(page);
  await expect(page.locator('.conversation-list').getByRole('button',{name:title,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Bài tập mới',exact:true})).toHaveCount(0);
});
