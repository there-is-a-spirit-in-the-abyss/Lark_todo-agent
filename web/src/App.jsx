import {tr, useLocale, LanguageSelect} from './locale.jsx';
import React,{useState,useEffect,useMemo,useRef,useCallback} from 'react';
import {ReactFlow,Background,applyNodeChanges,useReactFlow} from '@xyflow/react';
import {GitBranch,Plus,Archive,ArrowUpRight,Check,Search,ChevronRight,Pencil,Trash2,X,Lock,ZoomIn,ZoomOut,Maximize,PanelLeft,RotateCcw,Layers,HardDrive as CloudCheck,AlertCircle} from 'lucide-react';
import {MEMBERS,STATES,setMembers,canManage,subtree,projectTasks,projectOf,projectStatus,canRename} from './model.mjs';
import {request,loginUrl} from './api.mjs';
import {makeGraph,WIDTH,HEIGHT} from './layout.mjs';
import {nodeTypes,IconButton,Status} from './Nodes.jsx';
import ActionDialog from './ActionDialog.jsx';

const newId=()=>globalThis.crypto?.randomUUID?.() || 'id-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
const pointer=e=>({x:e.clientX??e.changedTouches?.[0]?.clientX??0,y:e.clientY??e.changedTouches?.[0]?.clientY??0});

function Inspector({task,state,actor,onClose,onAction,onModal}) {
  useLocale();
  const owner=MEMBERS.find(m=>m.id===task.owner),mine=canManage(task,actor);
  const [title,setTitle]=useState(task.title),[description,setDescription]=useState(task.description);
  const children=subtree(state,task.id);
  const p=projectOf(state,task.id);
  return <aside className="inspector" aria-label={tr("任务详情")}>
    <div className="inspector-head"><span>{tr("任务详情")}</span><IconButton icon={X} label={tr("关闭详情")} onClick={onClose}/></div>
    <div className="inspector-body">
      <Status value={task.status}/>
      <h2>{task.title}</h2>
      <div className="detail-owner"><span className="avatar" style={{background:owner.color}}>{owner.short}</span><div><strong>{owner.name}</strong><span>{owner.active?tr('发布者 · 负责人'):tr('已退群 · 群成员可维护')}</span></div>{!mine&&<Lock size={15}/>}</div>
      <div className="field"><span>{tr("状态")}</span><div className="state-switch" role="group" aria-label={tr("任务状态")}>{Object.entries(STATES).map(([key,value])=><button key={key} type="button" aria-label={tr(value.label)} aria-pressed={key===task.status} disabled={!mine} className={key===task.status?'active '+key:''} onClick={()=>onAction({type:'status',id:task.id,status:key},tr('状态已更新'))}><Status value={key}/></button>)}</div></div>
      <form onSubmit={e=>{e.preventDefault();onAction({type:'editTask',id:task.id,title,description},tr('任务已保存'));}}>
        <label className="field">{tr("任务名称")}<input required maxLength={100} value={title} readOnly={!mine} onChange={e=>setTitle(e.target.value)}/></label>
        <label className="field">{tr("备注")}<textarea aria-label={tr("备注")} maxLength={2000} rows={3} placeholder={mine?tr('补充任务信息'):tr('暂无备注')} value={description} readOnly={!mine} onChange={e=>setDescription(e.target.value)}/></label>
        {mine&&<button className="button secondary save-task" type="submit" disabled={title===task.title&&description===task.description}><Check size={15}/>{tr("保存修改")}</button>}
      </form>
      <dl className="task-facts"><div><dt>{tr("所在项目")}</dt><dd>{p?state.projects.find(pj=>pj.id===p)?.name:tr('暂存区')}</dd></div><div><dt>{tr("下游任务")}</dt><dd>{children.length-1}{tr(" 个")}</dd></div></dl>
      <div className="detail-actions"><button className="button secondary" onClick={()=>onModal({type:'move',id:task.id})}><ArrowUpRight size={16}/>{tr("移动分支")}</button><button className="button secondary" disabled={task.parent===null} onClick={()=>onAction({type:'move',id:task.id,parent:null},tr('分支已移入暂存区'))}><Archive size={16}/>{tr("移入暂存")}</button></div>
      <button className="button delete-action" disabled={!mine} title={mine?tr('删除此任务及全部后代'):tr('只有发布者可以发起删除')} onClick={()=>onModal({type:'delete',id:task.id})}><Trash2 size={16}/>{tr("删除分支")}</button>
    </div>
  </aside>;
}

export default function App() {
  useLocale();
  const [initial,setInitial]=useState(null),[error,setError]=useState(null);
  useEffect(()=>{let alive=true;request().then(data=>{if(alive){setMembers(data.members);setInitial(data);}}).catch(e=>{if(alive)setError(e);});return()=>{alive=false;};},[]);
  if(error)return <div className="access-state" role="alert"><LanguageSelect/><h1>{tr("汇漾 · 团队任务")}</h1><p>{tr(error.message)}</p>{error.status===401?<a className="button primary" href={loginUrl}>{tr("飞书登录")}</a>:<button className="button secondary" onClick={()=>location.reload()}>{tr("重新加载")}</button>}</div>;
  if(!initial)return <div className="access-state" role="status"><LanguageSelect/>{tr("正在载入团队任务...")}</div>;
  return <Workspace initial={initial} onDenied={setError}/>;
}

function Workspace({initial,onDenied}) {
  useLocale();
  const [state,setState]=useState(initial.board),actor=initial.actor;
  const snapshot=useRef(initial),busy=useRef(false);
  const [saving,setSaving]=useState(false);
  const [editorEpoch,setEditorEpoch]=useState(0);
  const [active,setActive]=useState(initial.board.projects[0]?.id||null),[selected,setSelected]=useState(null);
  const [modal,setModal]=useState(null),[toast,setToast]=useState(''),[saveError,setSaveError]=useState('');
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
  const accept=data=>{
    if(data.revision<snapshot.current.revision)return;
    setMembers(data.members);snapshot.current=data;setState(data.board);
    setActive(id=>data.board.projects.some(p=>p.id===id)?id:data.board.projects[0]?.id||null);
    setSelected(id=>data.board.tasks.some(t=>t.id===id)?id:null);
  };
  useEffect(()=>{
    const timer=setInterval(async()=>{
      if(busy.current||document.hidden)return;
      try{
        const data=await request();
        if(busy.current)return;
        if(!modal&&!selected)accept(data);
        setSaveError('');
      }catch(e){if(e.status===401||e.status===403)onDenied(e);else setSaveError(e.message);}
    },5000);
    return()=>clearInterval(timer);
  },[modal,selected]);
  const commit=async(action,message)=>{
    if(busy.current)return tr('正在保存，请稍候');
    busy.current=true;setSaving(true);
    try {
      const data=await request(action,snapshot.current.revision,snapshot.current.csrf);
      const next=data.board;
      accept(data);setSaveError('');
      const gone=state.projects.filter(p=>!next.projects.some(q=>q.id===p.id));
      if(!next.projects.some(p=>p.id===active))setActive(next.projects[0]?.id||null);
      if(selected&&!next.tasks.some(t=>t.id===selected)&&!next.projects.some(p=>p.id===selected))setSelected(null);
      autoFit.current=true;
      setToast((message||tr('已保存'))+(gone.length?tr(' · 空项目已自动删除'):''));
      return '';
    }catch(e){
      if(e.status===401||e.status===403) {
        try{await request();}catch(check){if(check.status===401||check.status===403)onDenied(check);}
      }
      if(e.status===409){try{accept(await request());setEditorEpoch(n=>n+1);setModal(null);}catch{}}
      setToast(e.message);return e.message;
    }finally{busy.current=false;setSaving(false);}
  };
  const changeProject=id=>{setActive(id);setSelected(null);setSidebar(false);autoFit.current=true;};
  const submitModal=async payload=>{
    let action={type:modal.type,id:modal.id};
    if(modal.type==='createProject')action={type:modal.type,id:newId(),name:payload.name};
    if(modal.type==='createTask')action={type:modal.type,id:newId(),title:payload.name,parent:modal.parent};
    if(modal.type==='rename')action.name=payload.name;
    if(modal.type==='move')action.parent=payload.parent;
    const error=await commit(action,modal.type==='delete'?tr('分支已删除'):modal.type==='move'?tr('分支已移动'):tr('已保存'));
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
      if(JSON.stringify(original)!==JSON.stringify(parent))commit({type:'move',id:node.id,parent},parent?tr('分支已重新接入'):tr('分支已移入暂存区'));
    }else setToast(tr('未接入新位置，分支已回到原处'));
  };
  const displayNodes=nodes.map(n=>({...n,className:[n.id===dropTarget?.id?'drop-target':'',n.type==='task'&&!matched(n.data)?'dimmed':''].join(' ')}));
  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><GitBranch size={23}/></span><strong>{tr("汇漾")}</strong><span className="brand-divider"/><span className="product-name">{tr("项目树")}</span></div>
      <div className="topbar-right"><LanguageSelect/><span className="save-state"><CloudCheck size={15}/>{saving?tr('保存中'):tr('已连接')}</span><div className="member-select"><span className="avatar small" style={{background:member.color}}>{member.short}</span><span>{member.name}</span></div></div>
    </header>
    <div className="workspace">
      {sidebar&&<div className="sidebar-backdrop" onClick={()=>setSidebar(false)}/>}
      <aside className={'sidebar'+(sidebar?' open':'')}>
        <div className="workspace-label"><span className="workspace-symbol"><Layers size={18}/></span><div><strong>{initial.space.name}</strong><span>{MEMBERS.filter(m=>m.active).length}{tr(" 位成员")}</span></div><IconButton className="mobile-only" icon={X} label={tr("关闭项目列表")} onClick={()=>setSidebar(false)}/></div>
        <div className="section-label"><span>{tr("全部项目 ")}<b>{state.projects.length}</b></span><IconButton icon={Plus} label={tr("新建项目")} onClick={()=>{setModal({type:'createProject'});setSidebar(false);}}/></div>
        <nav aria-label={tr("项目列表")}>{state.projects.map(p=>{const tasks=projectTasks(state,p.id);return <button key={p.id} className={'project-nav'+(active===p.id?' active':'')} onClick={()=>changeProject(p.id)}><GitBranch size={17}/><span>{p.name}</span>{projectStatus(state,p.id)==='completed'?<Check size={15}/>:<small>{tasks.length}</small>}</button>;})}</nav>
        {!state.projects.length&&<div className="sidebar-empty">{tr("暂无项目")}</div>}
        <button className="staging-nav" onClick={()=>{setSidebar(false);fit('staging');}}><Archive size={17}/><span>{tr("暂存区")}</span><small>{staged.length}</small></button>
        <div className="sidebar-members"><div className="section-label">{tr("项目成员")}</div>{MEMBERS.map(m=><div className="member-row" key={m.id}><span className="avatar small" style={{background:m.color}}>{m.short}</span><span>{m.name}<small>{tr(m.role)}</small></span>{m.id===actor&&<span className="you-label">{tr("我")}</span>}</div>)}</div>
        <div className="sidebar-footer"><span className="version">HUIYANG</span></div>
      </aside>
      <main className="main">
        <section className="project-header">
          <div className="breadcrumb"><IconButton className="mobile-only" icon={PanelLeft} label={tr("打开项目列表")} onClick={()=>setSidebar(true)}/><span>{tr("工作空间")}</span><ChevronRight size={13}/><span>{current?tr('项目'):tr('暂存')}</span></div>
          <div className="title-row"><div className="project-title"><h1>{current?.name||tr('暂存工作区')}</h1>{current&&<><IconButton icon={Pencil} label={tr("重命名当前项目")} disabled={!canRename(state,active,actor)} onClick={()=>onRename(active)}/><span className={'project-status '+projectStatus(state,active)}>{projectStatus(state,active)==='completed'?tr('已完成'):tr('待完成')}</span></>}</div><button className="button primary" onClick={()=>current?onAdd({kind:'project',id:active}):setModal({type:'createProject'})}><Plus size={17}/>{current?tr('发布任务'):tr('新建项目')}</button></div>
          <div className="project-meta"><span>{attached.length}{tr(" 个任务")}</span><span>{attached.filter(t=>t.owner===actor).length}{tr(" 个由我负责")}</span><div className="progress-track"><i style={{width:(attached.length?done/attached.length*100:0)+'%'}}/></div><span>{done}/{attached.length}{tr(" 已结束")}</span></div>
        </section>
        <div className="canvas-toolbar"><div className="view-label"><GitBranch size={16}/>{tr("任务树")}</div><label className="search"><Search size={15}/><input aria-label={tr("查找任务")} placeholder={tr("查找任务或负责人")} value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="mine-toggle"><input type="checkbox" checked={mineOnly} onChange={e=>setMineOnly(e.target.checked)}/>{tr("突出我的任务")}</label><div className="legend">{Object.keys(STATES).map(s=><Status key={s} value={s}/>)}</div></div>
        {saveError&&<div role="alert" className="storage-error"><AlertCircle size={16}/>{tr(saveError)}</div>}
        <div className="canvas-body" ref={board}>
          <ReactFlow nodes={displayNodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={changes=>setNodes(ns=>applyNodeChanges(changes.filter(c=>c.type==='dimensions'||c.type==='position'),ns))}
            onNodeClick={(e,n)=>{if(n.type==='task')setSelected(n.id);}} onPaneClick={()=>setSelected(null)}
            onNodeDragStart={onDragStart} onNodeDrag={onDrag} onNodeDragStop={onDragStop}
            nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} selectionKeyCode={null} multiSelectionKeyCode={null} selectionOnDrag={false} nodeDragThreshold={6}
            minZoom={0.2} maxZoom={1.6} onMove={(e,v)=>setZoom(Math.round(v.zoom*100))} fitView fitViewOptions={{maxZoom:1,padding:0.16}}
            onInit={()=>{setTimeout(()=>fit('all',0),100);}} onlyRenderVisibleElements={false}>
            <Background color="#dce1df" gap={22} size={1}/>
          </ReactFlow>
          {!current&&<div className="empty-project"><GitBranch size={22}/><strong>{tr("暂无项目")}</strong><button className="button secondary" onClick={()=>setModal({type:'createProject'})}><Plus size={15}/>{tr("新建项目")}</button></div>}
          <div className="canvas-tools"><IconButton icon={ZoomOut} label={tr("缩小")} onClick={()=>flow.zoomOut({duration:180})}/><span>{zoom}%</span><IconButton icon={ZoomIn} label={tr("放大")} onClick={()=>flow.zoomIn({duration:180})}/><i/><IconButton icon={Maximize} label={tr("适应全部任务")} onClick={()=>fit()}/><IconButton icon={GitBranch} label={tr("聚焦项目")} onClick={()=>fit('project')}/><IconButton icon={Archive} label={tr("聚焦暂存区")} onClick={()=>fit('staging')}/></div>
          <div className="canvas-caption"><span className="live-dot"/>{current?tr('项目视图'):tr('暂存视图')}<span>·</span>{staged.length}{tr(" 个暂存任务")}</div>
          {dropTarget&&<div className="drop-hint">{dropTarget.kind==='staging'?tr('移入暂存区'):tr('接到「')+(state.tasks.find(t=>t.id===dropTarget.id)?.title||state.projects.find(p=>p.id===dropTarget.id)?.name)+tr('」后')}</div>}
        </div>
      </main>
      {selectedTask&&<Inspector key={selectedTask.id+'-'+actor+'-'+editorEpoch} task={selectedTask} state={state} actor={actor} onClose={()=>setSelected(null)} onAction={commit} onModal={setModal}/>}
    </div>
    {toast&&<div className="toast" role="status">{toast}</div>}
    {modal&&<ActionDialog key={modal.type+'-'+(modal.id||'new')} modal={modal} state={state} onClose={()=>setModal(null)} onSubmit={submitModal}/>}
  </div>;
}
