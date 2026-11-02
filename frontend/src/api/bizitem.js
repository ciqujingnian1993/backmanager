import request from '@/utils/request'

export function fetchBizItemList(params) {
  return request({
    url: '/vue-element-admin/bizitem/list',
    method: 'get',
    params
  })
}

export function createBizItem(data) {
  return request({
    url: '/vue-element-admin/bizitem/create',
    method: 'post',
    data
  })
}

export function updateBizItem(data) {
  return request({
    url: '/vue-element-admin/bizitem/update',
    method: 'post',
    data
  })
}

export function deleteBizItem(data) {
  return request({
    url: '/vue-element-admin/bizitem/delete',
    method: 'post',
    data
  })
}
