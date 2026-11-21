// 订单 / 任务状态口径：任务（执照明细）先有状态，订单状态由后端按任务回算。
// 新增「取消订单」「已退款」后，前端筛选、标签、详情统一走这里，避免各页面各写一份。
export const ORDER_STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成',
  cancelled: '取消订单',
  refunded: '已退款'
}

export const ORDER_STATUS_OPTIONS = [
  { label: '待定', value: 'pending' },
  { label: '进行中', value: 'doing' },
  { label: '已完成', value: 'done' },
  { label: '取消订单', value: 'cancelled' },
  { label: '已退款', value: 'refunded' }
]

// 主任务（执照）只有三种取值，且由子任务决定：子任务没全办结 → 进行中；全办结 → 已完成；
// 订单取消时整条任务跟着取消。「待定 / 已退款」只在订单层出现。
export const ITEM_STATUS_OPTIONS = [
  { label: '进行中', value: 'doing' },
  { label: '已完成', value: 'done' },
  { label: '取消订单', value: 'cancelled' }
]

export function orderStatusText(status) {
  return ORDER_STATUS_MAP[status] || '待定'
}

export function orderStatusType(status) {
  if (status === 'done') return 'success'
  if (status === 'doing') return 'warning'
  if (status === 'refunded') return 'danger'
  if (status === 'cancelled') return 'info'
  return 'info'
}

// 不能再退款的状态：已取消（没有收款）与已全额退款
export const REFUND_BLOCKED_STATUSES = ['cancelled', 'refunded']

// 取消订单的常见原因：下拉默认给这几个，也可以自己输入
export const CANCEL_REASON_OPTIONS = [
  '客户主动取消',
  '客户联系不上',
  '价格未谈拢',
  '材料无法提供',
  '重复下单',
  '转其他渠道办理',
  '其他'
]

// 不能取消的状态：已取消（重复操作）与已全额退款（钱已经退了）
export const CANCEL_BLOCKED_STATUSES = ['cancelled', 'refunded']
