import request from '@/utils/request'

// 登录管理：查询账号的登录时间、来源 IP / 归属地、设备与在线状态
export function fetchLoginLogs(params) {
  return request({
    url: '/vue-element-admin/user/login-log',
    method: 'get',
    params
  })
}
