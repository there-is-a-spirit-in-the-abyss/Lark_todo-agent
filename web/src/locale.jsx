import React,{createContext,useContext,useState} from 'react';
import {getLanguage,setLanguage,tr} from './i18n.mjs';

const LocaleContext=createContext(null);
export function LocaleProvider({children}) {
  const [language,update]=useState(getLanguage);
  const change=value=>{setLanguage(value);update(getLanguage());};
  document.documentElement.lang=language;
  document.title=tr('汇漾 · 团队任务');
  return <LocaleContext.Provider value={{language,change}}>{children}</LocaleContext.Provider>;
}
export const useLocale=()=>useContext(LocaleContext);
export function LanguageSelect() {
  const {language,change}=useLocale();
  return <select className="language-select" aria-label="Language / 语言" value={language} onChange={e=>change(e.target.value)}>
    <option value="zh-CN">简体中文</option><option value="en-US">English</option>
  </select>;
}
export {tr};
