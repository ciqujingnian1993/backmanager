import router from './router'
import store from './store'
import { Message } from 'element-ui'
import NProgress from 'nprogress' // progress bar
import 'nprogress/nprogress.css' // progress bar style
import { getToken } from '@/utils/auth' // get token from cookie
import getPageTitle from '@/utils/get-page-title'
import { PAGE_PATHS } from '@/constants/pages'

NProgress.configure({ showSpinner: false }) // NProgress Configuration

const whiteList = ['/login', '/auth-redirect'] // no redirect whitelist

router.beforeEach(async(to, from, next) => {
  // start progress bar
  NProgress.start()

  // set page title
  document.title = getPageTitle(to.meta.title)

  // determine whether the user has logged in
  const hasToken = getToken()

  if (hasToken) {
    if (to.path === '/login') {
      // if is logged in, redirect to the home page
      next({ path: '/' })
      NProgress.done() // hack: https://github.com/PanJiaChen/vue-element-admin/pull/2939
    } else {
      // determine whether the user has obtained his permission roles through getInfo
      const hasRoles = store.getters.roles && store.getters.roles.length > 0
      // 已有角色但还没生成过路由（刚登录就是这种情况），仍要生成一次动态路由
      const hasRoutes = store.state.permission.addRoutes.length > 0
      if (hasRoles && hasRoutes) {
        next()
      } else {
        try {
          // 登录接口已经带回过角色，只有角色缺失（刷新页面后重新取）才请求 user/info
          let roles = store.getters.roles
          if (!roles || !roles.length) {
            // note: roles must be a object array! such as: ['admin'] or ,['developer','editor']
            const info = await store.dispatch('user/getInfo')
            roles = info.roles
          }

          // generate accessible routes map based on roles
          const accessRoutes = await store.dispatch('permission/generateRoutes', roles)

          // dynamically add accessible routes
          router.addRoutes(accessRoutes)

          // 刷新页面或直接打开深链接时，constantRoutes 末尾的 * 兜底会先把地址
          // 重定向成 /404（此时动态路由还没注册），导致已登录用户一刷新就落到 404。
          // 这里取 redirect 前的原始地址重新导航。
          const target = to.path === '/404' && to.redirectedFrom ? to.redirectedFrom : to.path
          const resolved = router.resolve(target).route
          const unreachable = resolved.path === '/404' ||
            !resolved.matched.length ||
            resolved.matched.some(record => record.path === '*')

          if (!unreachable) {
            // set the replace: true, so the navigation will not leave a history record
            next({ path: target, replace: true })
          } else if (PAGE_PATHS.indexOf(String(target).split('?')[0]) > -1) {
            // 是系统内置页面但当前账号没有权限：回首页并提示，而不是展示一个莫名其妙的 404
            Message.warning('当前账号没有该页面的访问权限，已返回首页')
            next({ path: '/', replace: true })
          } else {
            // 地址确实不存在
            next({ path: '/404', replace: true })
          }
        } catch (error) {
          // remove token and go to login page to re-login
          await store.dispatch('user/resetToken')
          Message.error(error || 'Has Error')
          next(`/login?redirect=${to.path}`)
          NProgress.done()
        }
      }
    }
  } else {
    /* has no token*/

    if (whiteList.indexOf(to.path) !== -1) {
      // in the free login whitelist, go directly
      next()
    } else {
      // other pages that do not have permission to access are redirected to the login page.
      // 未登录直开深链接时同样会被 * 兜底重定向成 /404，这里取 redirect 前的原始地址，
      // 登录成功后能回到用户原本想访问的页面
      const target = to.path === '/404' && to.redirectedFrom ? to.redirectedFrom : to.path
      let loginUrl = `/login?redirect=${encodeURIComponent(target)}`
      try {
        // 被其他设备顶下线时写入的标记，带到登录页用于提示原因
        if (sessionStorage.getItem('session_expired') === '1') {
          sessionStorage.removeItem('session_expired')
          loginUrl += '&expired=1'
        }
      } catch (e) { /* 隐私模式下 sessionStorage 可能不可用，忽略 */ }
      next(loginUrl)
      NProgress.done()
    }
  }
})

router.afterEach(() => {
  // finish progress bar
  NProgress.done()
})
