// 系统内置页面清单：菜单管理只能从这些页面里挑入口，页面本体由前端路由提供
export const PAGE_OPTIONS = [
  { path: '/account/index', label: '订单管理' },
  { path: '/account/query', label: '订单查询' },
  { path: '/progress/index', label: '订单进度' },
  { path: '/cost/index', label: '支出管理' },
  { path: '/cost/query', label: '成本查询' },
  { path: '/system/user', label: '用户管理' },
  { path: '/system/role', label: '角色管理' },
  { path: '/system/menu', label: '菜单管理' },
  { path: '/system/platform', label: '平台管理' },
  { path: '/system/bizitem', label: '业务项配置' }
]

export const PAGE_PATHS = PAGE_OPTIONS.map(item => item.path)

// 菜单可选图标（对应 src/icons/svg 里的图标名）
export const ICON_OPTIONS = [
  'money', 'tree', 'tree-table', 'list', 'table', 'user', 'peoples', 'lock',
  'dashboard', 'chart', 'form', 'excel', 'shopping', 'message', 'skill', 'star',
  'guide', 'education', 'component', 'nested', 'link', 'documentation', 'bug'
]

export const PARENT_OPTIONS = [
  { value: '', label: '顶级菜单' },
  { value: '/system', label: '系统管理' }
]
