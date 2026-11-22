import request from '@/utils/request'

export function login(data) {
  return request({
    url: '/vue-element-admin/user/login',
    method: 'post',
    data
  })
}

export function getInfo(token, silent) {
  return request({
    url: '/vue-element-admin/user/info',
    method: 'get',
    params: { token },
    silent: Boolean(silent)
  })
}

// 会话心跳：check=true 时只读检查会话是否已被踢，不计入「最后活动时间」
export function ping(token, check) {
  return request({
    url: '/vue-element-admin/user/ping',
    method: 'get',
    params: { token, check: check ? 1 : 0 },
    silent: true
  })
}

export function logout() {
  return request({
    url: '/vue-element-admin/user/logout',
    method: 'post'
  })
}
