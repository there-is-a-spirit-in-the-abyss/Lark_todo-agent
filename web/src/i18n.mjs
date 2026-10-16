import english from './messages.en.json' with {type:'json'};

export const languages=['zh-CN','en-US'];
const chinese=Object.fromEntries(Object.entries(english).map(([key,value])=>[value,key]));
let language='zh-CN';
try { const saved=globalThis.localStorage?.getItem('huiyang.language'); if(languages.includes(saved))language=saved; } catch {}
export const getLanguage=()=>language;
export function setLanguage(value) {
  language=languages.includes(value)?value:'zh-CN';
  try { globalThis.localStorage?.setItem('huiyang.language',language); } catch {}
  if(globalThis.document)document.documentElement.lang=language;
}
export function tr(text,values={}) {
  const template=language==='en-US'?(english[text]||text):(chinese[text]||text);
  return String(template).replace(/\{(\w+)\}/g,(_,key)=>values[key]??`{${key}}`);
}
export {english};
