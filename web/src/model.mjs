export let MEMBERS = [];
export function setMembers(members) { MEMBERS = members; }
export const STATES = {
  pending: {label:'待完成',color:'#ae791b'},
  completed: {label:'完成',color:'#23836d'},
  discarded: {label:'废弃',color:'#858b97'},
};
export function subtree(state,id) {
  const result=[], queue=[state.tasks.find(t=>t.id===id)], seen=new Set();
  while(queue.length) {
    const task=queue.shift();
    if(!task||seen.has(task.id))continue;
    seen.add(task.id);result.push(task);
    queue.push(...state.tasks.filter(t=>t.parent?.kind==='task'&&t.parent.id===task.id));
  }
  return result;
}
export function projectOf(state,id) {
  const seen=new Set();
  let task=state.tasks.find(t=>t.id===id);
  while(task) {
    if(seen.has(task.id))return null;
    seen.add(task.id);
    if(!task.parent)return null;
    if(task.parent.kind==='project')return task.parent.id;
    task=state.tasks.find(t=>t.id===task.parent.id);
  }
  return null;
}
export const projectTasks=(state,id)=>state.tasks.filter(t=>projectOf(state,t.id)===id);
export const projectStatus=(state,id)=>{
  const tasks=projectTasks(state,id);
  return tasks.length&&tasks.every(t=>t.status!=='pending')?'completed':'pending';
};
export const canManage=(task,actor)=>task.owner===actor||MEMBERS.find(m=>m.id===task.owner)?.active===false;
export const canRename=(state,id,actor)=>projectTasks(state,id).some(t=>canManage(t,actor));
