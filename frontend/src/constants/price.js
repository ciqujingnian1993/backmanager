// 价目表展示口径：类别配色、金额格式、价差文案，设置页与查看页共用
export const PRICE_CATEGORY_COLORS = {
  税务注销: '#409eff',
  解除非正常: '#e6a23c',
  工商注销: '#67c23a',
  综合套餐: '#9254de',
  附加服务: '#909399'
}

export function categoryColor(name) {
  return PRICE_CATEGORY_COLORS[name] || '#409eff'
}

export function formatMoney(value) {
  const num = Number(value || 0)
  return num.toFixed(2).replace(/\.00$/, '')
}

export function formatPrice(value) {
  return '¥' + formatMoney(value)
}

/**
 * 标准价 - 同行价：负数=比同行便宜，正数=比同行贵
 * 返回 { text, type }，type 用于配色（down 绿 / up 红 / same 灰）
 */
export function diffInfo(item) {
  const peer = Number((item && item.peer_price) || 0)
  if (!peer) return { text: '—', type: 'none' }
  const diff = Number(item.price || 0) - peer
  if (!diff) return { text: '持平', type: 'same' }
  const abs = formatMoney(Math.abs(diff))
  return diff < 0 ? { text: '低 ¥' + abs, type: 'down' } : { text: '高 ¥' + abs, type: 'up' }
}
