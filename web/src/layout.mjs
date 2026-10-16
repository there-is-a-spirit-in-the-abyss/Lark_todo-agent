import dagre from '@dagrejs/dagre';
import { projectTasks, projectStatus, MEMBERS, subtree, projectOf } from './model.mjs';
export const WIDTH = 220, HEIGHT = 108;
function arrange(items, root, originY) {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: 'LR', nodesep: 36, ranksep: 60, marginx: 40, marginy: 32 });
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setNode(root, { width: WIDTH, height: HEIGHT });
  items.forEach(t => graph.setNode(t.id, {width:WIDTH,height:HEIGHT}));
  items.forEach(t => graph.setEdge(t.parent?.kind === 'task' ? t.parent.id : root, t.id));
  dagre.layout(graph);
  const positions = new Map();
  for (const id of graph.nodes()) {
    const n = graph.node(id);
    positions.set(id,{x:n.x-WIDTH/2,y:n.y-HEIGHT/2+originY});
  }
  return {positions,height:graph.graph().height || 172,width:graph.graph().width || 300};
}
export function makeGraph(state, projectId, selected, actor, onAdd, onRename) {
  const p = state.projects.find(p=>p.id===projectId);
  const attached = p ? projectTasks(state,p.id) : [];
  const staged = state.tasks.filter(t=>projectOf(state,t.id)===null);
  const upper = arrange(attached,p?.id || '_empty',30);
  const stageY = Math.max(upper.height+90,350);
  const lower = arrange(staged,'_staging',stageY+50);
  const stageRect = {x:10,y:stageY,width:Math.max(upper.width,lower.width,960)+30,height:Math.max(lower.height+80,210)};
  const nodes = [], edges = [];
  if (p) nodes.push({id:p.id,type:'project',position:upper.positions.get(p.id),draggable:false,selectable:true,
    data:{...p,status:projectStatus(state,p.id),count:attached.length,done:attached.filter(t=>t.status!=='pending').length,onAdd,onRename,actor,state},selected:p.id===selected});
  nodes.push({id:'_staging',type:'staging',position:{x:stageRect.x,y:stageRect.y},draggable:false,selectable:false,zIndex:-1,
    style:{width:stageRect.width,height:stageRect.height},data:{count:staged.length}});
  for (const t of [...attached,...staged]) {
    const isStaged = projectOf(state,t.id)===null;
    const position = (isStaged?lower:upper).positions.get(t.id);
    nodes.push({id:t.id,type:'task',position,selected:t.id===selected,dragHandle:'.task-drag',data:{...t,onAdd,member:MEMBERS.find(m=>m.id===t.owner),descendants:subtree(state,t.id).length-1,staged:isStaged}});
    if (t.parent) edges.push({id:'edge-'+t.id,source:t.parent.id,target:t.id,type:'smoothstep',selectable:false,
      style:{stroke:t.status==='completed'?'#79af9f':t.status==='discarded'?'#c4c8ce':'#a3acb4',strokeWidth:1.6,strokeDasharray:t.status==='discarded'?'5 4':undefined}});
  }
  return {nodes,edges,stageRect};
}
