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

// 会话心跳：只探测 token 是否被顶下线，返回体极小
export function ping(token) {
  return request({
    url: '/vue-element-admin/user/ping',
    method: 'get',
    params: { token },
    silent: true
  })
}

export function logout() {
  return request({
    url: '/vue-element-admin/user/logout',
    method: 'post'
  })
}
