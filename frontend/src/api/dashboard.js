import request from '@/utils/request'

// 首页经营分析：KPI、趋势、收入/成本结构、订单进度分布、待办清单
export function fetchDashboardOverview() {
  return request({
    url: '/vue-element-admin/dashboard/overview',
    method: 'get'
  })
}
