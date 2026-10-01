import { test, expect, type Page } from '@playwright/test';
import { mockPeto, openSidebar, noPageOverflow, title } from './fixtures';

async function fixture(page: Page) {
  const chat=await mockPeto(page);
  const state={items:[
    {id:'A',title,project_id:'P' as string|null,archived:false,created_at:1,updated_at:2,message_count:2,title_state:'generated'},
    {id:'B',title:'Hội thoại đã hoàn thành',project_id:null as string|null,archived:false,created_at:1,updated_at:1,message_count:2,title_state:'generated'},
  ], failRestore:false};
  await page.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname;
    const json=(value:unknown)=>route.fulfill({json:value});
    if(path==='/api/projects') return json({projects:[{id:'P',name:'Dự án công việc',created_at:1,updated_at:2}]});
    if(path==='/api/conversations') {
      const archived=url.searchParams.get('archived')==='true',project=url.searchParams.get('project_id'),q=url.searchParams.get('q')?.toLowerCase() ?? '';
      return json({has_more:false,conversations:state.items.filter(c=>c.archived===archived && (!project || c.project_id===project) && (!url.searchParams.has('unassigned') || !c.project_id) && c.title.toLowerCase().includes(q))});
    }
    const match=path.match(/^\/api\/conversations\/([AB])(\/messages)?$/);
    if(match) {
      const item=state.items.find(c=>c.id===match[1]);
      if(!item)return route.fulfill({status:404,json:{detail:'Không tìm thấy hội thoại'}});
      if(match[2])return json({messages:chat.messages,project_id:item.project_id,archived:item.archived});
      if(request.method()==='PATCH') {
        const change=request.postDataJSON();
        if(change.archived===false && state.failRestore)return route.fulfill({status:500,json:{detail:'Chưa khôi phục được hội thoại.'}});
        Object.assign(item,change);return json({updated:true});
      }
      if(request.method()==='DELETE'){state.items=state.items.filter(c=>c!==item);return json({deleted:true});}
    }
    return route.fallback();
  });
  return state;
}

async function archive(page:Page, name:string) {
  await openSidebar(page);
  const row=page.locator('.conv').filter({has:page.getByRole('button',{name,exact:true})});
  await row.hover();
  await page.getByRole('button',{name:`Tùy chọn ${name}`,exact:true}).click();
  await page.getByRole('button',{name:'Lưu trữ',exact:true}).click();
  await expect(row).toHaveCount(0);
}

async function settings(page:Page) {
  await openSidebar(page);
  await page.getByRole('button',{name:'Tài khoản · Người kiểm thử'}).click();
  await page.getByRole('menuitem',{name:'Cài đặt',exact:true}).click();
  await page.getByRole('button',{name:'Hội thoại đã lưu trữ',exact:true}).click();
  return page.getByRole('dialog',{name:'Cài đặt',exact:true});
}

test('lưu trữ chat gần đây và dự án, đọc lại và khôi phục đúng folder',async({page})=>{
  const state=await fixture(page);
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();await openSidebar(page);
  await page.getByRole('button',{name:'Dự án công việc',exact:true}).click();
  await page.getByRole('button',{name:title,exact:true}).click();
  await expect(page.locator('.bubble')).toHaveCount(2);
  await archive(page,title);
  await expect(page.locator('.bubble')).toHaveCount(0);
  await archive(page,'Hội thoại đã hoàn thành');
  const dialog=await settings(page);
  await expect(dialog.getByRole('button',{name:title,exact:true})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Hội thoại đã hoàn thành',exact:true})).toBeVisible();
  await noPageOverflow(page);
  await expect(dialog).toHaveScreenshot('archived-settings.png',{maxDiffPixelRatio:0});
  await dialog.getByRole('button',{name:title,exact:true}).click();
  await expect(page.locator('.bubble')).toHaveCount(2);
  await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Khôi phục để tiếp tục'})).toBeVisible();
  await noPageOverflow(page);
  const banner=await page.locator('.archived-chat-notice').boundingBox();
  const main=await page.locator('main.chat').boundingBox();
  expect(banner!.x).toBeGreaterThan(main!.x);
  expect(banner!.y+banner!.height).toBeLessThan(main!.y+main!.height);
  await expect(page.locator('main.chat')).toHaveScreenshot('archived-chat.png',{maxDiffPixelRatio:0});
  await page.getByRole('button',{name:'Khôi phục để tiếp tục'}).click();
  await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();
  await expect.poll(()=>state.items[0].archived).toBe(false);
  await openSidebar(page);
  await expect(page.locator('.project-chats').getByRole('button',{name:title,exact:true})).toBeVisible();
  await expect(page.locator('.conversation-list').getByRole('button',{name:title,exact:true})).toHaveCount(0);
});

test('lưu trữ vẫn còn sau F5, tìm kiếm, lỗi khôi phục và xác nhận xóa',async({page})=>{
  const state=await fixture(page);state.items.forEach(c=>c.archived=true);
  await page.goto('/');await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();
  let dialog=await settings(page);
  await expect(dialog.getByRole('button',{name:title,exact:true})).toBeVisible();
  await page.reload();await expect(page.getByLabel('Nhắn cho Peto',{exact:true})).toBeVisible();
  dialog=await settings(page);
  await dialog.getByRole('searchbox').fill('hoàn thành');
  await expect(dialog.getByRole('button',{name:title,exact:true})).toHaveCount(0);
  await expect(dialog.getByRole('button',{name:'Hội thoại đã hoàn thành',exact:true})).toBeVisible();
  state.failRestore=true;
  await dialog.getByRole('button',{name:'Khôi phục: Hội thoại đã hoàn thành'}).click();
  await expect(dialog.getByRole('alert')).toContainText('Chưa khôi phục được hội thoại.');
  await dialog.getByRole('button',{name:'Xóa: Hội thoại đã hoàn thành'}).click();
  await dialog.getByRole('button',{name:'Hủy',exact:true}).click();
  expect(state.items.length).toBe(2);
  await dialog.getByRole('button',{name:'Xóa: Hội thoại đã hoàn thành'}).click();
  await dialog.getByRole('button',{name:'Xóa vĩnh viễn',exact:true}).click();
  await expect(dialog.getByText('Không tìm thấy hội thoại phù hợp.')).toBeVisible();
  expect(state.items.length).toBe(1);
});
