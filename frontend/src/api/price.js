import request from '@/utils/request'

// 价目表：一次取全量（项目不多），设置页与查看页各自在本地筛选，改完统一刷新
export function fetchPriceList(params) {
  return request({
    url: '/vue-element-admin/price/list',
    method: 'get',
    params
  })
}

export function createPrice(data) {
  return request({
    url: '/vue-element-admin/price/create',
    method: 'post',
    data
  })
}

export function updatePrice(data) {
  return request({
    url: '/vue-element-admin/price/update',
    method: 'post',
    data
  })
}

export function deletePrice(data) {
  return request({
    url: '/vue-element-admin/price/delete',
    method: 'post',
    data
  })
}

// 免责声明 / 特别提醒这类整体说明文案
export function savePriceSettings(data) {
  return request({
    url: '/vue-element-admin/price/settings',
    method: 'post',
    data
  })
}
