import request from '@/utils/request'

// 订单进度总览：每个订单 + 最新一条进度
export function fetchProgressOverview(params) {
  return request({
    url: '/vue-element-admin/account/progress/overview',
    method: 'get',
    params
  })
}

// 单个订单的完整跟进记录
export function fetchProgressList(accountId) {
  return request({
    url: '/vue-element-admin/account/progress/list',
    method: 'get',
    params: { account_id: accountId }
  })
}

export function fetchProgressSummary() {
  return request({
    url: '/vue-element-admin/account/progress/summary',
    method: 'get'
  })
}

export function createProgress(data) {
  return request({
    url: '/vue-element-admin/account/progress/create',
    method: 'post',
    data
  })
}

export function deleteProgress(data) {
  return request({
    url: '/vue-element-admin/account/progress/delete',
    method: 'post',
    data
  })
}
