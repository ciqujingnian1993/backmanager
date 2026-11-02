import request from '@/utils/request'

// 月度财务报表：汇总一个自然月的订单收入、直接成本与支出
export function fetchFinanceReport(params) {
  return request({
    url: '/vue-element-admin/finance/report',
    method: 'get',
    params
  })
}
