/**
 * keep-alive 页面「切回即刷新」
 *
 * 后台系统里列表数据的实时性比保留滚动位置更重要：页面被
 * keep-alive 缓存后，切走再切回只会还原离场时的快照，用户会
 * 看到旧数据，只能手动点刷新。
 *
 * 使用方式：页面实现 refreshPage()（负责重新拉取数据），并引入
 * 本 mixin。首次挂载不重复请求（created 里已经拉过一次），
 * 之后每次从其它菜单切回都会调用 refreshPage()。
 */
export default {
  created() {
    this.refreshOnActivateReady = false
  },
  activated() {
    if (!this.refreshOnActivateReady) {
      this.refreshOnActivateReady = true
      return
    }
    if (typeof this.refreshPage === 'function') {
      this.refreshPage()
    }
  }
}
