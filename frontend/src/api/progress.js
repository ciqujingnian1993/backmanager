import request from '@/utils/request'

// 任务总览：每条执照明细（任务）+ 最新一条进度
export function fetchProgressOverview(params) {
  return request({
    url: '/vue-element-admin/account/progress/overview',
    method: 'get',
    params
  })
}

// 单条任务（执照明细）的完整跟进记录
export function fetchProgressList(itemId) {
  return request({
    url: '/vue-element-admin/account/progress/list',
    method: 'get',
    params: { item_id: itemId }
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
