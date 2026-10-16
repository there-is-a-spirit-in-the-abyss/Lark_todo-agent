import {tr, useLocale} from './locale.jsx';
import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { Plus, GitBranch, Check, Circle, Minus, GripVertical, Pencil, Archive } from 'lucide-react';
import { STATES, canRename } from './model.mjs';

export function IconButton({icon:Icon,label,onClick,disabled=false,className='',...rest}) {
  return <button type="button" className={'icon-button '+className} title={label} aria-label={label} onClick={onClick} disabled={disabled} {...rest}><Icon size={17}/></button>;
}
export function Status({value}) {
  useLocale();
  const Icon = value==='completed' ? Check : value==='discarded' ? Minus : Circle;
  return <span className={'status '+value}><Icon size={12}/>{tr(STATES[value].label)}</span>;
}
export function TaskNode({id,data,selected}) {
  useLocale();
  return <div className={'task-node '+data.status+(selected?' selected':'')} data-task-id={id}>
    <Handle type="target" position={Position.Left} isConnectable={false}/>
    <div className="task-drag">
      <div className="node-top"><Status value={data.status}/><GripVertical size={15} className="grip"/></div>
      <div className="task-title" title={data.title}>{data.title}</div>
      <div className="node-bottom"><span className="owner"><span className="avatar small" style={{background:data.member.color}}>{data.member.short}</span>{data.member.name}</span>
        {data.descendants>0 && <span className="descendant-count"><GitBranch size={12}/>{data.descendants}</span>}
      </div>
    </div>
    <IconButton icon={Plus} label={tr('在「')+data.title+tr('」后发布任务')} className="node-add nodrag" onClick={e=>{e.stopPropagation();data.onAdd({kind:'task',id});}}/>
    <Handle type="source" position={Position.Right} isConnectable={false}/>
  </div>;
}
export function ProjectNode({id,data,selected}) {
  useLocale();
  return <div className={'project-node'+(selected?' selected':'')} data-project-id={id}>
    <div className="node-top"><span className="project-label"><GitBranch size={13}/>{tr("项目")}</span><Status value={data.status}/></div>
    <div className="root-name" title={data.name}>{data.name}</div>
    <div className="root-bottom"><span>{data.done} / {data.count}{tr(" 已结束")}</span>
      <IconButton icon={Pencil} label={tr("修改项目名称")} disabled={!canRename(data.state,id,data.actor)} className="nodrag" onClick={e=>{e.stopPropagation();data.onRename(id);}}/>
    </div>
    <IconButton icon={Plus} label={tr('在「')+data.name+tr('」下发布任务')} className="node-add nodrag" onClick={e=>{e.stopPropagation();data.onAdd({kind:'project',id});}}/>
    <Handle type="source" position={Position.Right} isConnectable={false}/>
  </div>;
}
export function StagingNode({data}) {
  useLocale();
  return <div className="staging-zone" data-testid="staging-zone"><div className="staging-label"><Archive size={18}/><strong>{tr("暂存区")}</strong><span>{data.count}{tr(" 个任务")}</span></div></div>;
}
export const nodeTypes = {task:TaskNode,project:ProjectNode,staging:StagingNode};
