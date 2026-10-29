import request from '@/utils/request'

export function fetchUserList(params) {
  return request({
    url: '/vue-element-admin/user/list',
    method: 'get',
    params
  })
}

export function createUser(data) {
  return request({
    url: '/vue-element-admin/user/create',
    method: 'post',
    data
  })
}

export function updateUser(data) {
  return request({
    url: '/vue-element-admin/user/update',
    method: 'post',
    data
  })
}

export function deleteUser(data) {
  return request({
    url: '/vue-element-admin/user/delete',
    method: 'post',
    data
  })
}
