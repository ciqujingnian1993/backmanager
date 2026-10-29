import request from '@/utils/request'

export function fetchAccountList(query) {
  return request({
    url: '/vue-element-admin/account/list',
    method: 'get',
    params: query
  })
}

export function fetchAccountSummary(params) {
  return request({
    url: '/vue-element-admin/account/summary',
    method: 'get',
    params
  })
}

export function fetchAccountDetail(id) {
  return request({
    url: '/vue-element-admin/account/detail',
    method: 'get',
    params: { id }
  })
}

export function createAccount(data) {
  return request({
    url: '/vue-element-admin/account/create',
    method: 'post',
    data
  })
}

export function updateAccount(data) {
  return request({
    url: '/vue-element-admin/account/update',
    method: 'post',
    data
  })
}

export function deleteAccount(id) {
  return request({
    url: '/vue-element-admin/account/delete',
    method: 'post',
    data: { id }
  })
}
