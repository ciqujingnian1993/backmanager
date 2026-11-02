// 订单进度的阶段口径：通用流转 + 工商/税务两条办理线。
// 工商、税务阶段带「工商 · / 税务 ·」前缀，写进 step 字段后能直接从文案判断归属。
// 后端 app.py 的 PROGRESS_STAGE_GROUPS 与此保持一致，接口会回传，网络异常时用本地兜底。

export const STAGE_GROUPS = [
  {
    key: 'common',
    label: '通用流程',
    hint: '从接单到收款',
    stages: ['已录入', '已联系', '已报价', '已付款', '办理中', '已交付', '已完成']
  },
  {
    key: 'biz',
    label: '工商办理',
    hint: '执照 / 年报 / 变更 / 注销',
    stages: [
      '工商 · 资料收集',
      '工商 · 名称核准',
      '工商 · 网上申报',
      '工商 · 材料签署',
      '工商 · 受理审核',
      '工商 · 补正材料',
      '工商 · 公示公告',
      '工商 · 领取执照',
      '工商 · 刻章/银行',
      '工商 · 办结'
    ]
  },
  {
    key: 'tax',
    label: '税务办理',
    hint: '报到 / 补报 / 解非 / 清税',
    stages: [
      '税务 · 资料收集',
      '税务 · 税务报到',
      '税务 · 票种核定',
      '税务 · 补申报',
      '税务 · 欠税罚款处理',
      '税务 · 解除非正常',
      '税务 · 清税申报',
      '税务 · 清税证明',
      '税务 · 办结'
    ]
  }
]

export const GROUP_META = {
  common: { label: '通用', color: '#909399', tagType: 'info' },
  biz: { label: '工商', color: '#409eff', tagType: '' },
  tax: { label: '税务', color: '#e6a23c', tagType: 'warning' }
}

const SEPARATOR = '·'

// 「工商 · 受理审核」→ biz；老数据（已录入/已联系…）→ common
export function groupKeyOfStep(step) {
  const text = String(step || '')
  const head = text.split(SEPARATOR)[0].trim()
  if (head === '工商') return 'biz'
  if (head === '税务') return 'tax'
  return 'common'
}

// 去掉前缀，只留节点名，用于步骤条等窄空间
export function shortStage(step) {
  const text = String(step || '')
  if (text.indexOf(SEPARATOR) < 0) return text
  const parts = text.split(SEPARATOR)
  parts.shift()
  return parts.join(SEPARATOR).trim() || text
}

export function stepTagType(step) {
  return GROUP_META[groupKeyOfStep(step)].tagType
}

export function stepColor(step) {
  return GROUP_META[groupKeyOfStep(step)].color
}

// 按业务项判断这一单涉及哪几条办理线：解非+工商注销 → 工商、税务都适用
export function pickGroupKeys(items) {
  const text = String(items || '')
  if (!text.trim()) return []
  const keys = []
  // 「工商注销」由「工商」命中；单独的「税务注销」不会误判成工商线
  const bizHit = /工商|执照|变更|年报|地址异常|另册|虚假|挂靠/.test(text)
  const taxHit = /税务|解非|清税|有税|无税|报税/.test(text)
  if (bizHit) keys.push('biz')
  if (taxHit) keys.push('tax')
  return keys
}

// 下拉与步骤条用的分组顺序：本单适用的组排前面，通用始终垫底留给「已联系/已收款」这类动作
export function orderGroups(groups, items) {
  const matched = pickGroupKeys(items)
  const list = groups && groups.length ? groups : STAGE_GROUPS
  const rank = group => {
    const index = matched.indexOf(group.key)
    return index < 0 ? 99 + list.indexOf(group) : index
  }
  return list
    .map(group => Object.assign({}, group, { matched: matched.indexOf(group.key) >= 0 }))
    .sort((a, b) => rank(a) - rank(b))
}

// 某条办理线自己的下一个节点：该组里第一个还没完成的阶段
export function nextStageOf(group, doneSteps) {
  const done = doneSteps instanceof Set ? doneSteps : new Set(doneSteps || [])
  for (const stage of (group && group.stages) || []) {
    if (!done.has(stage)) return stage
  }
  return ''
}

// 下一个该做的节点：本单适用线里第一个还没完成的阶段；都完成了就返回空
// 同时涉及工商与税务时（如解非+工商注销），税务动作通常在工商提交前完成，优先推荐税务
export function suggestStage(groups, items, doneSteps) {
  const done = doneSteps instanceof Set ? doneSteps : new Set(doneSteps || [])
  const matched = pickGroupKeys(items)
  const list = groups && groups.length ? groups : STAGE_GROUPS
  const priority = ['tax', 'biz', 'common']
  const candidates = (matched.length
    ? list.filter(group => matched.indexOf(group.key) >= 0)
    : list
  ).slice().sort((a, b) => priority.indexOf(a.key) - priority.indexOf(b.key))
  for (const group of candidates) {
    for (const stage of group.stages || []) {
      if (!done.has(stage)) return stage
    }
  }
  return ''
}
