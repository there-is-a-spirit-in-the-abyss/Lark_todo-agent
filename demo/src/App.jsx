import React,{useState,useEffect,useMemo,useRef,useCallback} from 'react';
import {ReactFlow,Background,applyNodeChanges,useReactFlow} from '@xyflow/react';
import {GitBranch,Plus,Archive,ArrowUpRight,Check,Search,ChevronRight,Pencil,Trash2,X,Lock,ZoomIn,ZoomOut,Maximize,PanelLeft,RotateCcw,Layers,HardDrive as CloudCheck,AlertCircle} from 'lucide-react';
import {MEMBERS,STATES,apply,seed,subtree,projectTasks,projectOf,projectStatus,canRename} from './model.mjs';
import {load,save} from './storage.mjs';
import {makeGraph,WIDTH,HEIGHT} from './layout.mjs';
import {nodeTypes,IconButton,Status} from './Nodes.jsx';
import ActionDialog from './ActionDialog.jsx';

const newId=()=>globalThis.crypto?.randomUUID?.() || 'id-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
const pointer=e=>({x:e.clientX??e.changedTouches?.[0]?.clientX??0,y:e.clientY??e.changedTouches?.[0]?.clientY??0});

function Inspector({task,state,actor,onClose,onAction,onModal}) {
  const owner=MEMBERS.find(m=>m.id===task.owner),mine=task.owner===actor;
  const [title,setTitle]=useState(task.title),[description,setDescription]=useState(task.description);
  const children=subtree(state,task.id);
  const p=projectOf(state,task.id);
  return <aside className="inspector" aria-label="任务详情">
    <div className="inspector-head"><span>任务详情</span><IconButton icon={X} label="关闭详情" onClick={onClose}/></div>
    <div className="inspector-body">
      <Status value={task.status}/>
      <h2>{task.title}</h2>
      <div className="detail-owner"><span className="avatar" style={{background:owner.color}}>{owner.short}</span><div><strong>{owner.name}</strong><span>发布者 · 负责人</span></div>{!mine&&<Lock size={15}/>}</div>
      <div className="field"><span>状态</span><div className="state-switch" role="group" aria-label="任务状态">{Object.entries(STATES).map(([key,value])=><button key={key} type="button" aria-label={value.label} aria-pressed={key===task.status} disabled={!mine} className={key===task.status?'active '+key:''} onClick={()=>onAction({type:'status',id:task.id,status:key},'状态已更新')}><Status value={key}/></button>)}</div></div>
      <form onSubmit={e=>{e.preventDefault();onAction({type:'editTask',id:task.id,title,description},'任务已保存');}}>
        <label className="field">任务名称<input required maxLength={100} value={title} readOnly={!mine} onChange={e=>setTitle(e.target.value)}/></label>
        <label className="field">备注<textarea maxLength={2000} rows={3} placeholder={mine?'补充任务信息':'暂无备注'} value={description} readOnly={!mine} onChange={e=>setDescription(e.target.value)}/></label>
        {mine&&<button className="button secondary save-task" type="submit" disabled={title===task.title&&description===task.description}><Check size={15}/>保存修改</button>}
      </form>
      <dl className="task-facts"><div><dt>所在项目</dt><dd>{p?state.projects.find(pj=>pj.id===p)?.name:'暂存区'}</dd></div><div><dt>下游任务</dt><dd>{children.length-1} 个</dd></div></dl>
      <div className="detail-actions"><button className="button secondary" onClick={()=>onModal({type:'move',id:task.id})}><ArrowUpRight size={16}/>移动分支</button><button className="button secondary" disabled={task.parent===null} onClick={()=>onAction({type:'move',id:task.id,parent:null},'分支已移入暂存区')}><Archive size={16}/>移入暂存</button></div>
      <button className="button delete-action" disabled={!mine} title={mine?'删除此任务及全部后代':'只有发布者可以发起删除'} onClick={()=>onModal({type:'delete',id:task.id})}><Trash2 size={16}/>删除分支</button>
    </div>
  </aside>;
}

export default function App() {
  const [initial]=useState(()=>{try{return load(window.localStorage);}catch{return {state:seed(),error:'本机存储不可用'};}});
  const [state,setState]=useState(initial.state),[actor,setActor]=useState('jia');
  const [active,setActive]=useState(initial.state.projects[0]?.id||null),[selected,setSelected]=useState(null);
  const [modal,setModal]=useState(null),[toast,setToast]=useState(''),[saveError,setSaveError]=useState(initial.error);
  const [sidebar,setSidebar]=useState(false),[query,setQuery]=useState(''),[mineOnly,setMineOnly]=useState(false);
  const [nodes,setNodes]=useState([]),[edges,setEdges]=useState([]),[dropTarget,setDropTarget]=useState(null);
  const [zoom,setZoom]=useState(100);
  const flow=useReactFlow(),drag=useRef(null),autoFit=useRef(true),board=useRef(null);
  const member=MEMBERS.find(m=>m.id===actor);
  const onAdd=useCallback(parent=>setModal({type:'createTask',parent}),[]);
  const onRename=useCallback(id=>setModal({type:'rename',id}),[]);
  const graph=useMemo(()=>makeGraph(state,active,selected,actor,onAdd,onRename),[state,active,selected,actor,onAdd,onRename]);
  const current=state.projects.find(p=>p.id===active);
  const attached=current?projectTasks(state,active):[];
  const staged=state.tasks.filter(t=>projectOf(state,t.id)===null);
  const selectedTask=state.tasks.find(t=>t.id===selected);
  const done=attached.filter(t=>t.status!=='pending').length;
  const matched=t=>(!mineOnly||t.owner===actor)&&(!query||t.title.toLowerCase().includes(query.toLowerCase())||MEMBERS.find(m=>m.id===t.owner)?.name.includes(query));
  const fit=useCallback((zone='all',duration=280)=>{
    const all=flow.getNodes();
    const relevant=all.filter(n=>n.type!=='staging'&&(zone==='all'||(zone==='staging'?n.data.staged:!n.data.staged)));
    if(duration===0&&window.innerWidth<640&&relevant.length){
      const anchor=relevant.find(n=>n.type==='project')||relevant[0];
      const top=Math.min(...relevant.map(n=>n.position.y));
      flow.setViewport({x:18-anchor.position.x*0.85,y:65-top*0.85,zoom:0.85});
      return;
    }
    if(relevant.length) flow.fitView({nodes:relevant,padding:0.16,maxZoom:1,minZoom:0.25,duration});
    else if(zone==='staging')flow.setCenter(graph.stageRect.x+400,graph.stageRect.y+100,{zoom:0.8,duration:280});
  },[flow,graph.stageRect.x,graph.stageRect.y]);
  useEffect(()=>{
    setNodes(graph.nodes);setEdges(graph.edges);
  },[graph]);
  useEffect(()=>{
    if(!autoFit.current)return;
    const timer=setTimeout(()=>{autoFit.current=false;fit('all',0);},60);
    return()=>clearTimeout(timer);
  },[state,active]);
  useEffect(()=>{
    let timer;
    const observer=new ResizeObserver(()=>{
      clearTimeout(timer);
      timer=setTimeout(()=>{if(!drag.current)fit('all',0);},120);
    });
    if(board.current)observer.observe(board.current);
    return()=>{observer.disconnect();clearTimeout(timer);};
  },[flow]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(''),4200);return()=>clearTimeout(timer);},[toast]);
  const commit=(action,message)=>{
    try {
      const next=apply(state,action,actor);
      save(window.localStorage,next);
      setState(next);setSaveError('');
      const gone=state.projects.filter(p=>!next.projects.some(q=>q.id===p.id));
      if(!next.projects.some(p=>p.id===active))setActive(next.projects[0]?.id||null);
      if(selected&&!next.tasks.some(t=>t.id===selected)&&!next.projects.some(p=>p.id===selected))setSelected(null);
      autoFit.current=true;
      setToast((message||'已保存')+(gone.length?' · 空项目已自动删除':''));
      return '';
    }catch(e){setToast(e.message);return e.message;}
  };
  const changeProject=id=>{setActive(id);setSelected(null);setSidebar(false);autoFit.current=true;};
  const submitModal=payload=>{
    let action={type:modal.type,id:modal.id};
    if(modal.type==='createProject')action={type:modal.type,id:newId(),name:payload.name};
    if(modal.type==='createTask')action={type:modal.type,id:newId(),title:payload.name,parent:modal.parent};
    if(modal.type==='rename')action.name=payload.name;
    if(modal.type==='move')action.parent=payload.parent;
    if(modal.type==='reset'){
      try{const next=seed();save(window.localStorage,next);setState(next);setActive(next.projects[0].id);setSelected(null);setSaveError('');autoFit.current=true;setModal(null);setToast('示例已重置');return '';}catch(e){return e.message;}
    }
    const error=commit(action,modal.type==='delete'?'分支已删除':modal.type==='move'?'分支已移动':'已保存');
    if(!error){setModal(null);if(modal.type==='createProject')setActive(action.id);if(modal.type==='createTask')setSelected(action.id);}
    return error;
  };
  const targetAt=(event)=>{
    const pos=flow.screenToFlowPosition(pointer(event)),ids=drag.current?.ids||new Set();
    const target=flow.getNodes().filter(n=>n.type!=='staging'&&!ids.has(n.id)).find(n=>pos.x>=n.position.x-14&&pos.x<=n.position.x+WIDTH+14&&pos.y>=n.position.y-14&&pos.y<=n.position.y+HEIGHT+14);
    if(target)return {kind:target.type==='project'?'project':'task',id:target.id};
    const r=graph.stageRect;
    if(pos.x>=r.x&&pos.x<=r.x+r.width&&pos.y>=r.y&&pos.y<=r.y+r.height)return {kind:'staging',id:'_staging'};
    return null;
  };
  const onDragStart=(e,node)=>{
    if(node.type!=='task')return;
    const ids=new Set(subtree(state,node.id).map(t=>t.id));
    drag.current={id:node.id,ids,start:{...node.position},positions:new Map(flow.getNodes().map(n=>[n.id,{...n.position}]))};
  };
  const onDrag=(e,node)=>{
    const d=drag.current;if(!d)return;
    const delta={x:node.position.x-d.start.x,y:node.position.y-d.start.y};
    setNodes(previous=>previous.map(n=>d.ids.has(n.id)?{...n,position:{x:d.positions.get(n.id).x+delta.x,y:d.positions.get(n.id).y+delta.y},zIndex:100}:n));
    setDropTarget(targetAt(e));
  };
  const onDragStop=(e,node)=>{
    if(!drag.current)return;
    const target=targetAt(e);
    drag.current=null;setDropTarget(null);
    setNodes(graph.nodes);
    if(target){
      const parent=target.kind==='staging'?null:target;
      const original=state.tasks.find(t=>t.id===node.id)?.parent;
      if(JSON.stringify(original)!==JSON.stringify(parent))commit({type:'move',id:node.id,parent},parent?'分支已重新接入':'分支已移入暂存区');
    }else setToast('未接入新位置，分支已回到原处');
  };
  const displayNodes=nodes.map(n=>({...n,className:[n.id===dropTarget?.id?'drop-target':'',n.type==='task'&&!matched(n.data)?'dimmed':''].join(' ')}));
  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><GitBranch size={23}/></span><strong>汇漾</strong><span className="brand-divider"/><span className="product-name">项目树</span><span className="demo-badge">DEMO</span></div>
      <div className="topbar-right"><span className="save-state"><CloudCheck size={15}/>本机存档</span><label className="member-select"><span className="avatar small" style={{background:member.color}}>{member.short}</span><select aria-label="当前成员" value={actor} onChange={e=>{setActor(e.target.value);setMineOnly(false);}}>{MEMBERS.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label></div>
    </header>
    <div className="workspace">
      {sidebar&&<div className="sidebar-backdrop" onClick={()=>setSidebar(false)}/>}
      <aside className={'sidebar'+(sidebar?' open':'')}>
        <div className="workspace-label"><span className="workspace-symbol"><Layers size={18}/></span><div><strong>团队工作空间</strong><span>3 位成员</span></div><IconButton className="mobile-only" icon={X} label="关闭项目列表" onClick={()=>setSidebar(false)}/></div>
        <div className="section-label"><span>全部项目 <b>{state.projects.length}</b></span><IconButton icon={Plus} label="新建项目" onClick={()=>{setModal({type:'createProject'});setSidebar(false);}}/></div>
        <nav aria-label="项目列表">{state.projects.map(p=>{const tasks=projectTasks(state,p.id);return <button key={p.id} className={'project-nav'+(active===p.id?' active':'')} onClick={()=>changeProject(p.id)}><GitBranch size={17}/><span>{p.name}</span>{projectStatus(state,p.id)==='completed'?<Check size={15}/>:<small>{tasks.length}</small>}</button>;})}</nav>
        {!state.projects.length&&<div className="sidebar-empty">暂无项目</div>}
        <button className="staging-nav" onClick={()=>{setSidebar(false);fit('staging');}}><Archive size={17}/><span>暂存区</span><small>{staged.length}</small></button>
        <div className="sidebar-members"><div className="section-label">项目成员</div>{MEMBERS.map(m=><div className="member-row" key={m.id}><span className="avatar small" style={{background:m.color}}>{m.short}</span><span>{m.name}<small>{m.role}</small></span>{m.id===actor&&<span className="you-label">我</span>}</div>)}</div>
        <div className="sidebar-footer"><span className="version">HUIYANG / 01</span><IconButton icon={RotateCcw} label="重置示例数据" onClick={()=>setModal({type:'reset'})}/></div>
      </aside>
      <main className="main">
        <section className="project-header">
          <div className="breadcrumb"><IconButton className="mobile-only" icon={PanelLeft} label="打开项目列表" onClick={()=>setSidebar(true)}/><span>工作空间</span><ChevronRight size={13}/><span>{current?'项目':'暂存'}</span></div>
          <div className="title-row"><div className="project-title"><h1>{current?.name||'暂存工作区'}</h1>{current&&<><IconButton icon={Pencil} label="重命名当前项目" disabled={!canRename(state,active,actor)} onClick={()=>onRename(active)}/><span className={'project-status '+projectStatus(state,active)}>{projectStatus(state,active)==='completed'?'已完成':'待完成'}</span></>}</div><button className="button primary" onClick={()=>current?onAdd({kind:'project',id:active}):setModal({type:'createProject'})}><Plus size={17}/>{current?'发布任务':'新建项目'}</button></div>
          <div className="project-meta"><span>{attached.length} 个任务</span><span>{attached.filter(t=>t.owner===actor).length} 个由我负责</span><div className="progress-track"><i style={{width:(attached.length?done/attached.length*100:0)+'%'}}/></div><span>{done}/{attached.length} 已结束</span></div>
        </section>
        <div className="canvas-toolbar"><div className="view-label"><GitBranch size={16}/>任务树</div><label className="search"><Search size={15}/><input aria-label="查找任务" placeholder="查找任务或负责人" value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="mine-toggle"><input type="checkbox" checked={mineOnly} onChange={e=>setMineOnly(e.target.checked)}/>突出我的任务</label><div className="legend">{Object.keys(STATES).map(s=><Status key={s} value={s}/>)}</div></div>
        {saveError&&<div role="alert" className="storage-error"><AlertCircle size={16}/>{saveError}</div>}
        <div className="canvas-body" ref={board}>
          <ReactFlow nodes={displayNodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={changes=>setNodes(ns=>applyNodeChanges(changes.filter(c=>c.type==='dimensions'||c.type==='position'),ns))}
            onNodeClick={(e,n)=>{if(n.type==='task')setSelected(n.id);}} onPaneClick={()=>setSelected(null)}
            onNodeDragStart={onDragStart} onNodeDrag={onDrag} onNodeDragStop={onDragStop}
            nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} selectionKeyCode={null} multiSelectionKeyCode={null} selectionOnDrag={false} nodeDragThreshold={6}
            minZoom={0.2} maxZoom={1.6} onMove={(e,v)=>setZoom(Math.round(v.zoom*100))} fitView fitViewOptions={{maxZoom:1,padding:0.16}}
            onInit={()=>{setTimeout(()=>fit('all',0),100);}} onlyRenderVisibleElements={false}>
            <Background color="#dce1df" gap={22} size={1}/>
          </ReactFlow>
          {!current&&<div className="empty-project"><GitBranch size={22}/><strong>暂无项目</strong><button className="button secondary" onClick={()=>setModal({type:'createProject'})}><Plus size={15}/>新建项目</button></div>}
          <div className="canvas-tools"><IconButton icon={ZoomOut} label="缩小" onClick={()=>flow.zoomOut({duration:180})}/><span>{zoom}%</span><IconButton icon={ZoomIn} label="放大" onClick={()=>flow.zoomIn({duration:180})}/><i/><IconButton icon={Maximize} label="适应全部任务" onClick={()=>fit()}/><IconButton icon={GitBranch} label="聚焦项目" onClick={()=>fit('project')}/><IconButton icon={Archive} label="聚焦暂存区" onClick={()=>fit('staging')}/></div>
          <div className="canvas-caption"><span className="live-dot"/>{current?'项目视图':'暂存视图'}<span>·</span>{staged.length} 个暂存任务</div>
          {dropTarget&&<div className="drop-hint">{dropTarget.kind==='staging'?'移入暂存区':'接到「'+(state.tasks.find(t=>t.id===dropTarget.id)?.title||state.projects.find(p=>p.id===dropTarget.id)?.name)+'」后'}</div>}
        </div>
      </main>
      {selectedTask&&<Inspector key={selectedTask.id+'-'+actor} task={selectedTask} state={state} actor={actor} onClose={()=>setSelected(null)} onAction={commit} onModal={setModal}/>}
    </div>
    {toast&&<div className="toast" role="status">{toast}</div>}
    {modal&&<ActionDialog key={modal.type+'-'+(modal.id||'new')} modal={modal} state={state} onClose={()=>setModal(null)} onSubmit={submitModal}/>}
  </div>;
}
