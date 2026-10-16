import {test} from 'node:test';
import assert from 'node:assert/strict';
import {tr,setLanguage,getLanguage,english} from '../src/i18n.mjs';

test('Chinese default and invalid saved choices resolve to Chinese',()=>{
  assert.equal(getLanguage(),'zh-CN');
  setLanguage('unsupported');
  assert.equal(tr('任务详情'),'任务详情');
});
test('English labels render while arbitrary task content is retained',()=>{
  setLanguage('en-US');
  assert.equal(tr('任务详情'),'Task details');
  assert.equal(tr('某个用户的中文任务'),'某个用户的中文任务');
  setLanguage('zh-CN');
});
test('existing API errors can be switched back to Chinese',()=>{
  setLanguage('zh-CN');
  assert.equal(tr('Please sign in with Feishu'),'请通过飞书登录');
});
test('catalog templates render counts and retain their interpolation fields',()=>{
  setLanguage('en-US');
  assert.equal(tr('请输入 1 至 {maximum} 个字符',{maximum:60}),'Enter 1 to 60 characters');
  for(const [source,translation] of Object.entries(english)) {
    assert.ok(translation.trim(),source);
    assert.doesNotMatch(translation,/[\u4e00-\u9fff]/,source);
    assert.deepEqual([...source.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort(),
                     [...translation.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort(),source);
  }
  setLanguage('zh-CN');
});

test('every static UI translation key has a catalog entry',async()=>{
  const {readFile}=await import('node:fs/promises');
  for(const file of ['App.jsx','Nodes.jsx','ActionDialog.jsx','api.mjs']) {
    const source=await readFile(new URL('../src/'+file,import.meta.url),'utf8');
    for(const match of source.matchAll(/tr\((['"])(.*?)\1/g))
      assert.ok(Object.hasOwn(english,match[2]),file+': '+match[2]);
  }
});
