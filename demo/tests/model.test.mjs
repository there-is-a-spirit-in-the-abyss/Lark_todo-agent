import test from 'node:test';
import assert from 'node:assert/strict';
import { apply, validate, projectTasks, projectStatus, subtree, canRename } from '../src/model.mjs';

const base = () => ({version:1, projects:[{id:'p',name:'Project',everUsed:true},{id:'q',name:'Empty',everUsed:false}], tasks:[
 {id:'a',title:'A',description:'',owner:'jia',status:'pending',parent:{kind:'project',id:'p'}},
 {id:'b',title:'B',description:'',owner:'yi',status:'completed',parent:{kind:'task',id:'a'}},
 {id:'c',title:'C',description:'',owner:'bing',status:'discarded',parent:{kind:'task',id:'b'}}]});
const act=(s,actor,type,args={})=>apply(s,{type,...args},actor);
test('only author updates state, with no administrator exception',()=>{ const s=base();assert.throws(()=>act(s,'yi','status',{id:'a',status:'completed'})); assert.equal(act(s,'jia','status',{id:'a',status:'completed'}).tasks[0].status,'completed');assert.equal(s.tasks[0].status,'pending'); });
test('own deletion cascades across all owners and deletes an empty used project',()=>{const s=act(base(),'jia','delete',{id:'a'});assert.equal(s.tasks.length,0);assert.deepEqual(s.projects.map(p=>p.id),['q']);});
test('cannot initiate deletion at someone else task',()=>assert.throws(()=>act(base(),'yi','delete',{id:'a'})));
test('any member may stage another owner subtree and preserve all descendant links',()=>{const s=act(base(),'bing','move',{id:'a',parent:null});assert.equal(s.projects.length,1);assert.equal(s.tasks.length,3);assert.equal(s.tasks[0].parent,null);assert.deepEqual(s.tasks[2].parent,{kind:'task',id:'b'});assert.equal(s.tasks[0].owner,'jia');});
test('saving a branch before deletion preserves other owners and allows reattachment',()=>{let s=act(base(),'jia','move',{id:'b',parent:null});s=act(s,'jia','delete',{id:'a'});assert.deepEqual(s.tasks.map(t=>t.id),['b','c']);s=act(s,'jia','move',{id:'b',parent:{kind:'project',id:'q'}});assert.equal(projectTasks(s,'q').length,2);assert.equal(s.projects[0].everUsed,true);});
test('cross-project move deletes source, preserves order, and grants rename to attached owners',()=>{const s=act(base(),'yi','move',{id:'a',parent:{kind:'project',id:'q'}});assert.equal(s.projects.length,1);assert.deepEqual(subtree(s,'a').map(t=>t.id),['a','b','c']);assert.equal(canRename(s,'q','yi'),true);assert.equal(canRename(s,'q','unknown'),false);assert.equal(act(s,'yi','rename',{id:'q',name:'New'}).projects[0].name,'New');});
test('self and descendant attachment fail without changing original state',()=>{const s=base();for(const id of ['a','b','c'])assert.throws(()=>act(s,'yi','move',{id:'a',parent:{kind:'task',id}}));assert.deepEqual(s,base());});
test('completion counts discarded and completed; reopening a task reopens project',()=>{let s=act(base(),'jia','status',{id:'a',status:'completed'});assert.equal(projectStatus(s,'p'),'completed');s=act(s,'bing','status',{id:'c',status:'pending'});assert.equal(projectStatus(s,'p'),'pending');assert.equal(projectStatus(s,'q'),'pending');});
test('never-used empty projects persist and grant nobody rename privilege',()=>{const s=act(base(),'yi','createProject',{id:'r',name:'Fresh'});assert.equal(s.projects.length,3);assert.equal(canRename(s,'r','yi'),false);assert.throws(()=>act(s,'yi','rename',{id:'r',name:'No'}));assert.throws(()=>act(s,'yi','delete',{id:'r'}));});
test('new task ownership is always the actor and first task marks project used',()=>{const s=act(base(),'bing','createTask',{id:'d',title:'D',owner:'jia',parent:{kind:'project',id:'q'}});assert.equal(s.tasks.at(-1).owner,'bing');assert.equal(s.projects.find(p=>p.id==='q').everUsed,true);});
test('last branch staged deletes root despite surviving staged descendants',()=>{const s=act(base(),'yi','move',{id:'a',parent:null});assert.equal(s.projects.some(p=>p.id==='p'),false);assert.equal(s.tasks.length,3);assert.equal(projectTasks(s,'q').length,0);});
test('moving within same project does not delete its root',()=>{const s=act(base(),'yi','move',{id:'b',parent:{kind:'project',id:'p'}});assert.equal(projectTasks(s,'p').length,3);assert.equal(s.projects.length,2);});
test('invalid targets, names, statuses and actors fail',()=>{for(const action of [{type:'move',id:'a',parent:{kind:'task',id:'missing'}},{type:'status',id:'a',status:'invalid'},{type:'createProject',id:'r',name:' '},{type:'rename',id:'p',name:' '},{type:'createTask',id:'a',title:'Duplicate',parent:null}])assert.throws(()=>apply(base(),action,'jia'));assert.throws(()=>apply(base(),{type:'delete',id:'a'},'admin'));});
test('persisted state validation rejects cycles, unknown owners and dangling parents',()=>{assert.equal(validate(JSON.parse(JSON.stringify(base()))).version,1);for(const mutate of [s=>s.tasks[0].parent={kind:'task',id:'c'},s=>s.tasks[0].owner='root',s=>s.tasks[0].parent={kind:'project',id:'missing'},s=>s.tasks[0].status='unknown']){const s=base();mutate(s);assert.throws(()=>validate(s));}});
test('ordinary members cannot edit other owner task text',()=>{assert.throws(()=>act(base(),'yi','editTask',{id:'a',title:'Wrong',description:''}));assert.equal(act(base(),'jia','editTask',{id:'a',title:'New A',description:'Note'}).tasks[0].description,'Note');});
import {load,save,STORAGE_KEY} from '../src/storage.mjs';
import {seed} from '../src/model.mjs';
test('corrupt browser save is preserved while showing sample fallback',()=>{
  const raw='{invalid';
  const storage={getItem:()=>raw,setItem:()=>assert.fail('must not overwrite corrupt data')};
  const result=load(storage);assert.match(result.error,/存档/);assert.deepEqual(result.state,seed());
});
test('browser storage roundtrip retains staged descendants after source removal',()=>{
  const memory=new Map(),storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v)};
  const staged=act(base(),'yi','move',{id:'a',parent:null});
  save(storage,staged);assert.deepEqual(load(storage).state,staged);assert.ok(memory.has(STORAGE_KEY));
});
test('storage quota failures propagate without pretending changes were saved',()=>{
  assert.throws(()=>save({setItem:()=>{throw new Error('QuotaExceededError');}},base()),/Quota/);
});
