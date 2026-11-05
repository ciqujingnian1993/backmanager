// 营业执照的工商状态与税务状态：新建/编辑下拉、列表标签共用一套口径
// 工商状态支持多选，库里存的是按本数组顺序拼接的字符串，如「正常,另册管理」
export const BIZ_STATUS_OPTIONS = ['正常', '年报异常', '地址异常', '另册管理', '吊销']

export const TAX_STATUS_OPTIONS = ['税务正常', '无税务', '税务非正常', '清算']

const BIZ_TAG_TYPE = {
  正常: 'success',
  年报异常: 'warning',
  地址异常: 'warning',
  另册管理: 'info',
  吊销: 'danger'
}

// 多选时的标签配色：按「严重程度」取最重的一个，避免一列里颜色花掉
const BIZ_TAG_PRIORITY = ['吊销', '年报异常', '地址异常', '另册管理', '正常']

const TAX_TAG_TYPE = {
  税务正常: 'success',
  有税务: 'success', // 历史文案，兼容未刷新的旧数据
  无税务: 'info',
  税务非正常: 'danger',
  清算: 'warning'
}

/** 把「正常,另册管理」拆成数组；也兼容数组、中文逗号、顿号等历史写法 */
export function splitBizStatus(value) {
  if (!value) return []
  const list = Array.isArray(value) ? value : String(value).split(/[,，、/|]/)
  const result = []
  list.forEach(item => {
    const text = String(item == null ? '' : item).trim()
    if (text && result.indexOf(text) === -1) result.push(text)
  })
  return result
}

/** 数组 → 存储字符串；按选项固定顺序排列，未知值保持原顺序跟在后面 */
export function joinBizStatus(value) {
  const parts = splitBizStatus(value)
  if (!parts.length) return ''
  const ordered = BIZ_STATUS_OPTIONS.filter(item => parts.indexOf(item) !== -1)
  parts.forEach(item => {
    if (BIZ_STATUS_OPTIONS.indexOf(item) === -1) ordered.push(item)
  })
  return ordered.join(',')
}

/** 展示用文案：用顿号连接 */
export function bizStatusText(value) {
  return splitBizStatus(value).join('、')
}

export function bizStatusType(value) {
  const parts = splitBizStatus(value)
  if (!parts.length) return 'info'
  for (let i = 0; i < BIZ_TAG_PRIORITY.length; i += 1) {
    if (parts.indexOf(BIZ_TAG_PRIORITY[i]) !== -1) return BIZ_TAG_TYPE[BIZ_TAG_PRIORITY[i]]
  }
  return 'info'
}

export function taxStatusType(value) {
  return TAX_TAG_TYPE[value] || 'info'
}
