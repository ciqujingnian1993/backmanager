import router from './router'
import store from './store'
import { Message } from 'element-ui'
import NProgress from 'nprogress' // progress bar
import 'nprogress/nprogress.css' // progress bar style
import { getToken } from '@/utils/auth' // get token from cookie
import getPageTitle from '@/utils/get-page-title'

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
      if (hasRoles) {
        next()
      } else {
        try {
          // get user info
          // note: roles must be a object array! such as: ['admin'] or ,['developer','editor']
          const { roles } = await store.dispatch('user/getInfo')

          // generate accessible routes map based on roles
          const accessRoutes = await store.dispatch('permission/generateRoutes', roles)

          // dynamically add accessible routes
          router.addRoutes(accessRoutes)

          // 刷新页面或直接打开深链接时，constantRoutes 末尾的 * 兜底会先把地址
          // 重定向成 /404（此时动态路由还没注册），导致已登录用户一刷新就落到 404。
          // 这里取 redirect 前的原始地址重新导航，真正不存在的地址仍会回到 404 页。
          if (to.path === '/404' && to.redirectedFrom) {
            next({ path: to.redirectedFrom, replace: true })
          } else {
            // hack method to ensure that addRoutes is complete
            // set the replace: true, so the navigation will not leave a history record
            next({ ...to, replace: true })
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
      next(`/login?redirect=${encodeURIComponent(target)}`)
      NProgress.done()
    }
  }
})

router.afterEach(() => {
  // finish progress bar
  NProgress.done()
})
