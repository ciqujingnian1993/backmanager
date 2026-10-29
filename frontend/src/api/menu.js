import request from '@/utils/request'

export function fetchMenuList() {
  return request({
    url: '/vue-element-admin/menu/list',
    method: 'get'
  })
}

export function createMenu(data) {
  return request({
    url: '/vue-element-admin/menu/create',
    method: 'post',
    data
  })
}

export function updateMenu(data) {
  return request({
    url: '/vue-element-admin/menu/update',
    method: 'post',
    data
  })
}

export function deleteMenu(data) {
  return request({
    url: '/vue-element-admin/menu/delete',
    method: 'post',
    data
  })
}
