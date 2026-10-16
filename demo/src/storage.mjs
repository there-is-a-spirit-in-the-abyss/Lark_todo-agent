import { seed, validate } from './model.mjs';
export const STORAGE_KEY = 'huiyang-tree-demo-v1';
export function load(storage) {
  try {
    const value = storage.getItem(STORAGE_KEY);
    if (!value) return {state: seed(), error: ''};
    return {state: validate(JSON.parse(value)), error: ''};
  } catch { return {state: seed(), error: '本机存档无法读取，已载入示例；原存档未覆盖。'}; }
}
export function save(storage, state) {
  validate(state); storage.setItem(STORAGE_KEY, JSON.stringify(state));
}
