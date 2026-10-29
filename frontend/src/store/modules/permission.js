import { asyncRoutes, constantRoutes } from '@/router'
import { fetchRoles } from '@/api/permission'

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
    let accessedRoutes
    if (roles.includes('admin')) {
      // 管理员固定全部权限，避免误配置把自己锁在门外
      accessedRoutes = asyncRoutes || []
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
