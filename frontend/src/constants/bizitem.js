// 业务项是多选组合，存储时用「+」拼成一段文本（如 解非+工商注销），
// 展示沿用文本，编辑时再拆回数组，历史数据不用迁移。
export const ITEM_SEPARATOR = '+'

const SPLIT_RE = /[+＋、,，/／|]+/

export function splitItems(text) {
  return String(text || '')
    .split(SPLIT_RE)
    .map(item => item.trim())
    .filter((item, index, arr) => item && arr.indexOf(item) === index)
}

export function joinItems(list) {
  const names = (list || [])
    .map(item => String(item || '').trim())
    .filter((item, index, arr) => item && arr.indexOf(item) === index)
  return names.join(ITEM_SEPARATOR)
}

export function formatMoney(value) {
  const num = Number(value || 0)
  return num.toFixed(2).replace(/\.00$/, '')
}
