import axios from 'axios'
import { Message } from 'element-ui'
import store from '@/store'
import { getToken } from '@/utils/auth'

let sessionExpiredHandling = false

/**
 * 会话失效（被其他设备顶下线 / token 过期）：提示后强制退回登录页，
 * 不给「继续留在页面」的选项，避免旧设备继续操作数据
 */
function handleSessionExpired() {
  if (sessionExpiredHandling) return
  sessionExpiredHandling = true
  store.dispatch('user/resetToken').finally(() => {
    Message.closeAll()
    try {
      // 用 sessionStorage 传标记：reload 后路由守卫会重写 URL 的 query，URL 参数会丢
      sessionStorage.setItem('session_expired', '1')
    } catch (e) {}
    // 只 reload 一次：路由守卫发现没有 token 会自动带去登录页，
    // 若先改 href 再 reload，会产生两次跳转把提示冲掉
    setTimeout(() => window.location.reload(), 0)
  })
}

// create an axios instance
const service = axios.create({
  baseURL: process.env.VUE_APP_BASE_API, // url = base url + request url
  // withCredentials: true, // send cookies when cross-domain requests
  timeout: 5000 // request timeout
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
      handleSessionExpired()
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
