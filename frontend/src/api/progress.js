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

// 主跟进人候选（系统用户 + 历史跟进人）
export function fetchProgressOwners() {
  return request({
    url: '/vue-element-admin/account/progress/owners',
    method: 'get'
  })
}

// 设置/清空某条任务的主跟进人
export function updateProgressOwner(data) {
  return request({
    url: '/vue-element-admin/account/progress/owner',
    method: 'post',
    data
  })
}

// 退款：冲减任务金额 + 成本管理记一条退款支出 + 写跟进
export function refundProgress(data) {
  return request({
    url: '/vue-element-admin/account/progress/refund',
    method: 'post',
    data
  })
}

// 取消订单：记录取消原因/备注，可选清空金额 + 写跟进
export function cancelProgress(data) {
  return request({
    url: '/vue-element-admin/account/progress/cancel',
    method: 'post',
    data
  })
}

// 办理线附件：工商 / 税务每条线各自传图片（受理单、执照照片、办结截图）
export function fetchProgressFiles(itemId) {
  return request({
    url: '/vue-element-admin/account/progress/files',
    method: 'get',
    params: { item_id: itemId }
  })
}

export function addProgressFile(data) {
  return request({
    url: '/vue-element-admin/account/progress/files/add',
    method: 'post',
    data
  })
}

export function deleteProgressFile(id) {
  return request({
    url: '/vue-element-admin/account/progress/files/delete',
    method: 'post',
    data: { id }
  })
}

// 先传到通用上传接口，拿到 /uploads/xxx 的地址再挂到办理线上
export function uploadFile(form) {
  return request({
    url: '/upload',
    method: 'post',
    data: form
  })
}

// 细分任务：执照（主任务）下按业务项拆出来的小任务，各自独立办结
export function fetchItemTasks(params) {
  return request({
    url: '/vue-element-admin/account/progress/tasks',
    method: 'get',
    params
  })
}

export function updateProgressTaskStatus(data) {
  return request({
    url: '/vue-element-admin/account/progress/tasks/status',
    method: 'post',
    data
  })
}

export function addProgressTask(data) {
  return request({
    url: '/vue-element-admin/account/progress/tasks/add',
    method: 'post',
    data
  })
}

export function deleteProgressTask(id) {
  return request({
    url: '/vue-element-admin/account/progress/tasks/delete',
    method: 'post',
    data: { id }
  })
}

// 子任务的跟进人：管理员可转派给任何人，跟进人本人可以把任务转给别人
export function updateProgressTaskOwner(data) {
  return request({
    url: '/vue-element-admin/account/progress/tasks/owner',
    method: 'post',
    data
  })
}
