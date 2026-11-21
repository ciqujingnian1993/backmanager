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

// 订单级退款：item_ids 传空表示整单退，amount 传空表示把可退金额全退掉
export function refundAccount(data) {
  return request({
    url: '/vue-element-admin/account/refund',
    method: 'post',
    data
  })
}

// 订单级取消：item_ids 传空表示整单取消，clear_amount=false 表示只改状态不动金额
export function cancelAccount(data) {
  return request({
    url: '/vue-element-admin/account/cancel',
    method: 'post',
    data
  })
}
