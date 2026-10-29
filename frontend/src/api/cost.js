import request from '@/utils/request'

export function fetchCostList(params) {
  return request({
    url: '/vue-element-admin/cost/list',
    method: 'get',
    params
  })
}

export function fetchCostSummary(params) {
  return request({
    url: '/vue-element-admin/cost/summary',
    method: 'get',
    params
  })
}

export function createCost(data) {
  return request({
    url: '/vue-element-admin/cost/create',
    method: 'post',
    data
  })
}

export function updateCost(data) {
  return request({
    url: '/vue-element-admin/cost/update',
    method: 'post',
    data
  })
}

export function deleteCost(data) {
  return request({
    url: '/vue-element-admin/cost/delete',
    method: 'post',
    data
  })
}
