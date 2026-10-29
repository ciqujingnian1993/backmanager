import request from '@/utils/request'

export function fetchPlatformList(params) {
  return request({
    url: '/vue-element-admin/platform/list',
    method: 'get',
    params
  })
}

export function createPlatform(data) {
  return request({
    url: '/vue-element-admin/platform/create',
    method: 'post',
    data
  })
}

export function updatePlatform(data) {
  return request({
    url: '/vue-element-admin/platform/update',
    method: 'post',
    data
  })
}

export function deletePlatform(data) {
  return request({
    url: '/vue-element-admin/platform/delete',
    method: 'post',
    data
  })
}
