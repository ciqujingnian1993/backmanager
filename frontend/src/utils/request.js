import axios from 'axios'
import { Message } from 'element-ui'
import store from '@/store'
import { getToken } from '@/utils/auth'

let sessionExpiredHandling = false

/**
 * 会话失效（被其他设备顶下线 / token 过期）：提示后强制退回登录页，
 * 不给「继续留在页面」的选项，避免旧设备继续操作数据
 *
 * staleToken：本次请求实际带出去的 token。
 * 同一个浏览器开多个标签页时，旧标签页里在途/轮询的请求仍带着旧 token，
 * 它们返回 50008 时如果无脑重置，会把另一个标签页刚登录拿到的新 token 一起删掉，
 * 表现就是「刚登录又被踢回登录页」。所以只有失效的正是当前 token 才真的退出。
 */
function handleSessionExpired(staleToken) {
  if (sessionExpiredHandling) return
  const current = getToken()
  if (staleToken && current && staleToken !== current) return
  sessionExpiredHandling = true
  store.dispatch('user/resetToken').finally(() => {
    Message.closeAll()
    try {
      // 用 sessionStorage 传标记：reload 后路由守卫会重写 URL 的 query，URL 参数会丢
      sessionStorage.setItem('session_expired', '1')
    } catch (e) { /* 隐私模式下 sessionStorage 可能不可用，忽略 */ }
    // 只 reload 一次：路由守卫发现没有 token 会自动带去登录页，
    // 若先改 href 再 reload，会产生两次跳转把提示冲掉
    setTimeout(() => window.location.reload(), 0)
  })
}

// create an axios instance
const service = axios.create({
  baseURL: process.env.VUE_APP_BASE_API, // url = base url + request url
  // withCredentials: true, // send cookies when cross-domain requests
  // 跨境链路单次请求就成了 0.2~0.5s，5s 太紧，网络一抖就假超时（登录时会表现为「点了没反应」）
  timeout: 20000 // request timeout
})

// request interceptor
service.interceptors.request.use(
  config => {
    // do something before request is sent

    if (store.getters.token) {
      // let each request carry token
      // ['X-Token'] is a custom headers key
      // please modify it according to the actual situation
      config.headers['X-Token'] = getToken()
    }
    return config
  },
  error => {
    // do something with request error
    console.log(error) // for debug
    return Promise.reject(error)
  }
)

// response interceptor
service.interceptors.response.use(
  /**
   * If you want to get http information such as headers or status
   * Please return  response => response
  */

  /**
   * Determine the request status by custom code
   * Here is just an example
   * You can also judge the status by HTTP Status Code
   */
  response => {
    const res = response.data

    // 50008: 无效/已失效 token（含被其他设备顶下线）；50012: 其他端登录；50014: token 过期
    if (res.code === 50008 || res.code === 50012 || res.code === 50014) {
      handleSessionExpired(response.config.headers && response.config.headers['X-Token'])
      return Promise.reject(new Error(res.message || 'Error'))
    }

    // if the custom code is not 20000, it is judged as an error.
    if (res.code !== 20000) {
      Message({
        message: res.message || 'Error',
        type: 'error',
        duration: 5 * 1000
      })
      return Promise.reject(new Error(res.message || 'Error'))
    } else {
      return res
    }
  },
  error => {
    console.log('err' + error) // for debug
    // 心跳等静默请求（config.silent）不弹错误提示，避免网络抖动时反复打扰
    if (!error.config || !error.config.silent) {
      Message({
        message: error.message,
        type: 'error',
        duration: 5 * 1000
      })
    }
    return Promise.reject(error)
  }
)

export default service
