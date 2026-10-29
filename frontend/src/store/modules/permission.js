import { asyncRoutes, constantRoutes } from '@/router'
import { fetchRoles } from '@/api/permission'
import { fetchMenuList } from '@/api/menu'
import { PAGE_PATHS } from '@/constants/pages'

/**
 * Use meta.role to determine if the current user has permission
 * @param roles
 * @param route
 */
function hasPermission(roles, route) {
  if (route.meta && route.meta.roles) {
    return roles.some(role => route.meta.roles.includes(role))
  } else {
    return true
  }
}

/**
 * Filter asynchronous routing tables by recursion
 * @param routes asyncRoutes
 * @param roles
 */
export function filterAsyncRoutes(routes, roles) {
  const res = []

  routes.forEach(route => {
    const tmp = { ...route }
    if (hasPermission(roles, tmp)) {
      if (tmp.children) {
        tmp.children = filterAsyncRoutes(tmp.children, roles)
      }
      res.push(tmp)
    }
  })

  return res
}

function joinPath(parent, child) {
  if (!parent || parent === '/') return '/' + String(child).replace(/^\/+/, '')
  return ('/' + parent + '/' + child).replace(/\/+/g, '/')
}

/**
 * 按「角色页面配置」再过滤一层，做到角色权限页勾选什么就显示什么
 * allowed 里既有父路径也有子路径，命中父路径即整组放行
 */
export function filterRoutesByPaths(routes, allowed) {
  const res = []

  routes.forEach(route => {
    const tmp = { ...route }
    if (allowed.has(tmp.path)) {
      res.push(tmp)
      return
    }
    if (tmp.children && tmp.children.length) {
      const children = tmp.children.filter(child => allowed.has(joinPath(tmp.path, child.path)))
      if (children.length) {
        tmp.children = children
        if (tmp.redirect && !children.some(child => joinPath(tmp.path, child.path) === tmp.redirect)) {
          tmp.redirect = joinPath(tmp.path, children[0].path)
        }
        res.push(tmp)
      }
    }
  })

  return res
}

/**
 * 深拷贝路由（保留 component 函数，只复制结构）
 */
function cloneRoutes(routes) {
  return (routes || []).map(route => ({
    ...route,
    meta: route.meta ? { ...route.meta } : route.meta,
    children: route.children ? cloneRoutes(route.children) : route.children
  }))
}

/**
 * 用「菜单管理」里的配置覆盖侧边栏：名称、图标、排序、是否显示
 * 菜单表是系统内置页面入口的唯一来源：被删除的页面菜单不再出现在侧边栏
 */
export function applyMenuConfig(routes, menus) {
  if (!menus || !menus.length) return routes

  const map = {}
  menus.forEach(menu => {
    if (menu && menu.path) map[menu.path] = menu
  })
  const registered = new Set(PAGE_PATHS)

  routes.forEach(route => {
    if (!route.children || !route.children.length) return
    route.meta = { ...(route.meta || {}) }
    route.children.forEach(child => {
      const fullPath = joinPath(route.path, child.path)
      if (!registered.has(fullPath)) return
      child.meta = { ...(child.meta || {}) }
      const menu = map[fullPath]
      if (menu) {
        child.meta.title = menu.title
        if (menu.icon) child.meta.icon = menu.icon
        child.meta.__sort = Number(menu.sort) || 0
        child.hidden = !menu.visible
      } else {
        // 菜单表里没有这一项 = 被管理员删除了入口
        child.hidden = true
      }
    })
    route.children.sort((a, b) => (a.meta.__sort || 0) - (b.meta.__sort || 0))

    if (route.children.length === 1) {
      const only = route.children[0]
      route.meta.title = only.meta.title || route.meta.title
      route.meta.icon = only.meta.icon || route.meta.icon
      route.meta.__sort = only.meta.__sort || 0
      route.hidden = !!only.hidden
    } else {
      route.hidden = route.children.every(child => child.hidden)
      const sorts = route.children.map(child => child.meta.__sort || 0)
      route.meta.__sort = 100 + Math.min.apply(null, sorts)
    }
  })

  routes.sort((a, b) => ((a.meta && a.meta.__sort) || 0) - ((b.meta && b.meta.__sort) || 0))
  return routes
}

const state = {
  routes: [],
  addRoutes: []
}
const mutations = {
  SET_ROUTES: (state, routes) => {
    state.addRoutes = routes
    state.routes = constantRoutes.concat(routes)
  }
}

const actions = {
  async generateRoutes({ commit }, roles) {
    let menus = []
    try {
      const { data } = await fetchMenuList()
      menus = data || []
    } catch (error) {
      // 菜单接口不可用时退回前端静态配置，避免整个侧边栏空掉
      console.warn('fetch menus failed, fallback to static routes', error)
    }

    let accessedRoutes
    if (roles.includes('admin')) {
      // 管理员固定全部权限，避免误配置把自己锁在门外
      accessedRoutes = cloneRoutes(asyncRoutes)
    } else {
      accessedRoutes = filterAsyncRoutes(asyncRoutes, roles)
      try {
        const { data } = await fetchRoles()
        const allowed = new Set()
        ;(data || [])
          .filter(role => roles.includes(role.key))
          .forEach(role => {
            (role.routes || []).forEach(item => {
              if (!item || !item.path) return
              allowed.add(item.path)
              ;(item.children || []).forEach(child => {
                if (child && child.path) allowed.add(joinPath(item.path, child.path))
              })
            })
          })
        if (allowed.size) {
          accessedRoutes = filterRoutesByPaths(accessedRoutes, allowed)
        }
      } catch (error) {
        // 后端不可用时退回按角色过滤的结果，至少保证菜单可用
        console.warn('fetch role routes failed, fallback to role filter', error)
      }
    }
    accessedRoutes = applyMenuConfig(accessedRoutes, menus)
    commit('SET_ROUTES', accessedRoutes)
    return accessedRoutes
  }
}

export default {
  namespaced: true,
  state,
  mutations,
  actions
}
