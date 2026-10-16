import {test,expect} from '@playwright/test';
import {seed,apply,MEMBERS} from '../../demo/src/model.mjs';

async function setup(page,{empty=false,departed=false}={}) {
  let data={board:empty?{version:1,projects:[],tasks:[]}:seed(),revision:0,actor:'jia',csrf:'csrf',
    space:{id:'oc_test',name:'产品协作团队'},members:MEMBERS.map(m=>({...m,active:!(departed&&m.id==='yi')}))};
  let deny=false,conflict=false;
  await page.route('**/api/team/spaces/**',async route=>{
    if(deny)return route.fulfill({status:403,json:{detail:'你不在此飞书群中'}});
    if(route.request().method()==='POST'){
      if(conflict){conflict=false;data.revision++;return route.fulfill({status:409,json:{detail:'其他成员已更新，请刷新后重试'}});}
      const body=route.request().postDataJSON();
      expect(body.revision).toBe(data.revision);
      data={...data,board:apply(data.board,body.action,data.actor),revision:data.revision+1};
    }
    await route.fulfill({json:data});
  });
  await page.goto('/team/oc_test');
  return {deny:()=>{deny=true;},conflict:()=>{conflict=true;},
    update:()=>{data={...data,revision:data.revision+1,board:{...data.board,tasks:data.board.tasks.map(t=>t.id==='api'?{...t,description:'其他成员的新备注'}:t)}};},
    data:()=>data};
}

test('shared server state, ownership and async dialogs',async({page})=>{
  const server=await setup(page);
  await expect(page.getByRole('heading',{name:'产品协作平台',exact:true})).toBeVisible();
  await expect(page.getByLabel('当前成员')).toHaveCount(0);
  await page.locator('[data-task-id="page"]').click();
  await expect(page.getByLabel('任务名称',{exact:true})).toHaveAttribute('readonly','');
  await expect(page.getByRole('button',{name:'完成',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'关闭详情'}).click();
  await page.getByRole('button',{name:'发布任务',exact:true}).click();
  await page.getByRole('dialog').getByLabel('任务名称').fill('新团队任务');
  await page.getByRole('dialog').getByRole('button',{name:'保存',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(server.data().board.tasks.some(t=>t.title==='新团队任务')).toBeTruthy();
  await page.reload();
  await expect(page.getByText('新团队任务',{exact:true})).toBeVisible();
  await page.screenshot({path:'.runtime/desktop.png',fullPage:true});
});

test('empty workspace creates its first project without sample data',async({page})=>{
  await setup(page,{empty:true});
  await expect(page.locator('[data-task-id]')).toHaveCount(0);
  await page.getByRole('button',{name:'新建项目',exact:true}).first().click();
  await page.getByRole('dialog').getByLabel('项目名称').fill('空白团队新项目');
  await page.getByRole('dialog').getByRole('button',{name:'保存',exact:true}).click();
  await expect(page.getByRole('heading',{name:'空白团队新项目'})).toBeVisible();
});

test('departed author is editable and revocation clears the page',async({page})=>{
  const server=await setup(page,{departed:true});
  await page.locator('[data-task-id="page"]').click();
  await expect(page.getByLabel('任务名称',{exact:true})).not.toHaveAttribute('readonly','');
  await expect(page.getByRole('button',{name:'完成',exact:true})).toBeEnabled();
  server.deny();
  await expect(page.getByRole('alert')).toContainText('你不在此飞书群中',{timeout:10000});
  await expect(page.locator('[data-task-id]')).toHaveCount(0);
});

test('stale write reports conflict without retrying mutation',async({page})=>{
  const server=await setup(page);
  server.conflict();
  await page.getByRole('button',{name:'发布任务',exact:true}).click();
  await page.getByRole('dialog').getByLabel('任务名称').fill('不应覆盖');
  await page.getByRole('dialog').getByRole('button',{name:'保存',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('其他成员已更新');
  expect(server.data().board.tasks.some(t=>t.title==='不应覆盖')).toBeFalsy();
});

test('mobile tree renders without document overflow',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await setup(page);
  await expect(page.getByRole('heading',{name:'产品协作平台',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:'.runtime/mobile.png',fullPage:true});
  await page.getByRole('button',{name:'打开项目列表'}).click();
  await expect(page.getByRole('navigation',{name:'项目列表'})).toBeVisible();
});

test('conflict refresh replaces stale inspector draft before a retry',async({page})=>{
  const server=await setup(page);
  await page.locator('[data-task-id="api"]').click();
  await page.getByLabel('任务名称',{exact:true}).fill('我改的标题');
  server.update();server.conflict();
  await page.getByRole('button',{name:'保存修改'}).click();
  await expect(page.getByLabel('备注',{exact:true})).toHaveValue('其他成员的新备注');
});

test('late background reads cannot roll back a successful mutation',async({page})=>{
  let data={board:seed(),revision:0,actor:'jia',csrf:'csrf',
    space:{id:'oc_test',name:'测试群'},members:MEMBERS.map(m=>({...m,active:true}))};
  let reads=0,release,started;
  const pending=new Promise(resolve=>{started=resolve;});
  const gate=new Promise(resolve=>{release=resolve;});
  await page.route('**/api/team/spaces/**',async route=>{
    if(route.request().method()==='GET'){
      reads++;const snapshot=structuredClone(data);
      if(reads===2){started();await gate;}
      return route.fulfill({json:snapshot});
    }
    const body=route.request().postDataJSON();
    data={...data,revision:data.revision+1,board:apply(data.board,body.action,'jia')};
    await route.fulfill({json:data});
  });
  await page.goto('/team/oc_test');
  await pending;
  await page.getByRole('button',{name:'发布任务',exact:true}).click();
  await page.getByRole('dialog').getByLabel('任务名称').fill('最新保存');
  await page.getByRole('dialog').getByRole('button',{name:'保存',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  release();
  await page.getByRole('button',{name:'关闭详情'}).click();
  await expect(page.locator('.task-title').filter({hasText:'最新保存'})).toBeVisible();
});

test('changing status preserves an unsaved detail draft',async({page})=>{
  await setup(page);
  await page.locator('[data-task-id="api"]').click();
  await page.getByLabel('备注',{exact:true}).fill('尚未保存的备注');
  await page.getByRole('button',{name:'待完成',exact:true}).click();
  await expect(page.getByRole('button',{name:'待完成',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByLabel('备注',{exact:true})).toHaveValue('尚未保存的备注');
});


test('language defaults to Chinese, English edits persist and task content stays unchanged',async({page})=>{
  const server=await setup(page);
  await expect(page.getByLabel('Language / 语言')).toHaveValue('zh-CN');
  await page.getByLabel('Language / 语言').selectOption('en-US');
  await expect(page.getByRole('button',{name:'Publish task',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Publish task',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Task name').fill('保留中文任务');
  await page.getByRole('dialog').getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(server.data().board.tasks.some(t=>t.title==='保留中文任务')).toBeTruthy();
  await page.reload();
  await expect(page.getByLabel('Language / 语言')).toHaveValue('en-US');
  await expect(page.getByText('保留中文任务',{exact:true})).toBeVisible();
  await page.getByLabel('Language / 语言').selectOption('zh-CN');
  await expect(page.getByRole('button',{name:'发布任务',exact:true})).toBeVisible();
});

test('English access error keeps a usable language switch and Feishu login',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('huiyang.language','en-US'));
  await page.route('**/api/team/spaces/**',route=>route.fulfill({status:401,json:{detail:'请通过飞书登录'}}));
  await page.goto('/team/oc_test');
  await expect(page.getByRole('link',{name:'Feishu login'})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Please sign in with Feishu');
  await page.getByLabel('Language / 语言').selectOption('zh-CN');
  await expect(page.getByRole('link',{name:'飞书登录'})).toBeVisible();
});


test('English mobile layout retains ownership and move permissions',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await setup(page);
  await page.getByLabel('Language / 语言').selectOption('en-US');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.locator('[data-task-id="page"]').click();
  await expect(page.getByLabel('Task name',{exact:true})).toHaveAttribute('readonly','');
  await expect(page.getByRole('button',{name:'Completed',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Move branch',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Delete branch',exact:true})).toBeDisabled();
});
