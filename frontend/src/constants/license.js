// 营业执照的工商状态与税务状态：新建/编辑下拉、列表标签共用一套口径
export const BIZ_STATUS_OPTIONS = ['正常', '年报异常', '地址异常', '另册管理', '吊销']

export const TAX_STATUS_OPTIONS = ['税务正常', '无税务', '税务非正常']

const BIZ_TAG_TYPE = {
  正常: 'success',
  年报异常: 'warning',
  地址异常: 'warning',
  另册管理: 'info',
  吊销: 'danger'
}

const TAX_TAG_TYPE = {
  税务正常: 'success',
  有税务: 'success', // 历史文案，兼容未刷新的旧数据
  无税务: 'info',
  税务非正常: 'danger'
}

export function bizStatusType(value) {
  return BIZ_TAG_TYPE[value] || 'info'
}

export function taxStatusType(value) {
  return TAX_TAG_TYPE[value] || 'info'
}
