import {tr,getLanguage} from './i18n.mjs';
const path=window.location.pathname.split('/').filter(Boolean);
export const group=path[0]==='team'?path[1]:'';
export const loginUrl='/api/team/login?chat_id='+encodeURIComponent(group||'');
export async function request(action,revision,csrf) {
  if(!group||!/^oc_[A-Za-z0-9_-]+$/.test(group))throw Object.assign(new Error(tr('请从飞书群内的团队链接进入')),{status:400});
  const response=await fetch('/api/team/spaces/'+encodeURIComponent(group)+(action?'/actions':''),{
    method:action?'POST':'GET',credentials:'same-origin',cache:'no-store',
    headers:{'Accept-Language':getLanguage(),...(action?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{})},
    body:action?JSON.stringify({revision,action}):undefined,
  });
  const data=await response.json().catch(()=>({detail:tr('服务暂时不可用')}));
  if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:tr('请求未完成，请重试')),{status:response.status});
  return data;
}
