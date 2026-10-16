export const MEMBERS = [
  { id: 'jia', name: '甲 · 林舟', short: '甲', color: '#217b67', role: '接口与服务' },
  { id: 'yi', name: '乙 · 许宁', short: '乙', color: '#466aba', role: '产品与页面' },
  { id: 'bing', name: '丙 · 陈禾', short: '丙', color: '#ad6b28', role: '测试与交付' },
];
export const STATES = {
  pending: { label: '待完成', color: '#ae791b' },
  completed: { label: '完成', color: '#23836d' },
  discarded: { label: '废弃', color: '#858b97' },
};
const fail = message => { throw new Error(message); };
const member = actor => MEMBERS.some(m => m.id === actor) || fail('请选择有效成员');
const task = (s, id) => s.tasks.find(t => t.id === id) || fail('任务已不存在');
const project = (s, id) => s.projects.find(p => p.id === id) || fail('项目已不存在');
const own = (t, actor) => t.owner === actor || fail('只有发布者可以执行此操作');
const text = (value, max = 100) => {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > max) fail('请输入 1 至 ' + max + ' 个字符');
  return value.trim();
};
export function subtree(s, id) {
  const found = [], queue = [task(s, id)], visited = new Set();
  while (queue.length) {
    const t = queue.shift();
    if (visited.has(t.id)) fail('连接不能形成循环');
    visited.add(t.id); found.push(t);
    queue.push(...s.tasks.filter(c => c.parent?.kind === 'task' && c.parent.id === t.id));
  }
  return found;
}
export function projectOf(s, id) {
  let p = task(s, id).parent;
  const visited = new Set([id]);
  while (p?.kind === 'task') {
    if (visited.has(p.id)) fail('连接不能形成循环');
    visited.add(p.id); p = task(s, p.id).parent;
  }
  return p?.kind === 'project' ? p.id : null;
}
export const projectTasks = (s, id) => s.tasks.filter(t => projectOf(s, t.id) === id);
export const projectStatus = (s, id) => {
  const tasks = projectTasks(s, id);
  return tasks.length && tasks.every(t => t.status !== 'pending') ? 'completed' : 'pending';
};
export const canRename = (s, id, actor) => projectTasks(s, id).some(t => t.owner === actor);
function validParent(s, parent) {
  if (parent === null) return;
  if (!parent || !['task', 'project'].includes(parent.kind)) fail('无效的连接位置');
  if (parent.kind === 'task') task(s, parent.id); else project(s, parent.id);
}
export function validate(s) {
  if (!s || s.version !== 1 || !Array.isArray(s.tasks) || !Array.isArray(s.projects)) fail('无法读取此版本的数据');
  if (s.tasks.length > 3000 || s.projects.length > 200) fail('Demo 数据超过容量');
  const ids = new Set();
  for (const row of [...s.projects, ...s.tasks]) {
    if (typeof row.id !== 'string' || !row.id || row.id.length > 100 || ids.has(row.id)) fail('数据标识无效或重复');
    ids.add(row.id);
  }
  for (const p of s.projects) { text(p.name, 60); if (typeof p.everUsed !== 'boolean') fail('项目数据无效'); }
  for (const t of s.tasks) {
    text(t.title); member(t.owner);
    if (!Object.hasOwn(STATES, t.status) || typeof t.description !== 'string' || t.description.length > 2000) fail('任务数据无效');
    validParent(s, t.parent); projectOf(s, t.id);
  }
  return s;
}
export function apply(previous, action, actor) {
  member(actor);
  const s = structuredClone(previous), a = action;
  const unique = id => {
    if (typeof id !== 'string' || !id || s.tasks.some(t => t.id === id) || s.projects.some(p => p.id === id)) fail('标识重复或无效');
  };
  switch (a.type) {
    case 'createProject':
      unique(a.id); s.projects.push({ id: a.id, name: text(a.name, 60), everUsed: false }); break;
    case 'createTask':
      unique(a.id); validParent(s, a.parent);
      s.tasks.push({ id: a.id, title: text(a.title), description: '', owner: actor, status: 'pending', parent: a.parent }); break;
    case 'rename':
      project(s, a.id);
      if (!canRename(s, a.id, actor)) fail('只有项目当前任务负责人可以修改项目名称');
      project(s, a.id).name = text(a.name, 60); break;
    case 'status': {
      const t = task(s, a.id); own(t, actor);
      if (!Object.hasOwn(STATES, a.status)) fail('无效的任务状态');
      t.status = a.status; break;
    }
    case 'editTask': {
      const t = task(s, a.id); own(t, actor); t.title = text(a.title);
      if (typeof a.description !== 'string' || a.description.length > 2000) fail('任务备注最多 2000 个字符');
      t.description = a.description.trim(); break;
    }
    case 'move': {
      const t = task(s, a.id); validParent(s, a.parent);
      if (a.parent?.kind === 'task' && subtree(s, a.id).some(c => c.id === a.parent.id)) fail('不能接到自身或自己的后代');
      t.parent = a.parent; break;
    }
    case 'delete': {
      own(task(s, a.id), actor);
      const ids = new Set(subtree(s, a.id).map(t => t.id)); s.tasks = s.tasks.filter(t => !ids.has(t.id)); break;
    }
    default: fail('未知操作');
  }
  // Cleanup follows reattachment so an in-project move cannot erase its root.
  for (const p of s.projects) if (projectTasks(s, p.id).length) p.everUsed = true;
  s.projects = s.projects.filter(p => !p.everUsed || s.tasks.some(t => t.parent?.kind === 'project' && t.parent.id === p.id));
  return validate(s);
}
export function seed() {
  const t = (id, title, owner, status, kind, parent) => ({id,title,owner,status,description:'',parent:parent ? {kind,id:parent} : null});
  return {version:1,projects:[
    {id:'p-launch',name:'产品协作平台',everUsed:true},
    {id:'p-brand',name:'品牌官网更新',everUsed:true},
    {id:'p-new',name:'下一步计划',everUsed:false},
  ],tasks:[
    t('api','接口设计与契约','jia','completed','project','p-launch'),
    t('auth','登录与权限接口','jia','pending','task','api'),
    t('integration','页面联调','yi','pending','task','auth'),
    t('page','工作台页面','yi','pending','project','p-launch'),
    t('qa','验收清单','bing','discarded','task','page'),
    t('brand','视觉规范整理','yi','completed','project','p-brand'),
    t('review','旧版素材归档','bing','discarded','task','brand'),
    t('idea','消息通知方案','bing','pending',null,null),
    t('copy','通知文案','yi','pending','task','idea'),
  ]};
}
