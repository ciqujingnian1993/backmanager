import request from '@/utils/request'

export function fetchRoles() {
  return request({
    url: '/vue-element-admin/roles',
    method: 'get'
  })
}

export function fetchAllRoutes() {
  return request({
    url: '/vue-element-admin/routes',
    method: 'get'
  })
}

export function createRole(data) {
  return request({
    url: '/vue-element-admin/role',
    method: 'post',
    data
  })
}

export function updateRole(key, data) {
  return request({
    url: `/vue-element-admin/role/${key}`,
    method: 'put',
    data
  })
}

export function deleteRole(key) {
  return request({
    url: `/vue-element-admin/role/${key}`,
    method: 'delete'
  })
}
