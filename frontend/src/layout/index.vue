<template>
  <div :class="classObj" class="app-wrapper">
    <div v-if="device==='mobile'&&sidebar.opened" class="drawer-bg" @click="handleClickOutside" />
    <sidebar class="sidebar-container" />
    <div :class="{hasTagsView:needTagsView}" class="main-container">
      <div :class="{'fixed-header':fixedHeader}">
        <navbar />
        <tags-view v-if="needTagsView" />
      </div>
      <app-main />
      <right-panel v-if="showSettings">
        <settings />
      </right-panel>
    </div>
  </div>
</template>

<script>
import RightPanel from '@/components/RightPanel'
import { AppMain, Navbar, Settings, Sidebar, TagsView } from './components'
import ResizeMixin from './mixin/ResizeHandler'
import { mapState } from 'vuex'
import { ping } from '@/api/user'

// 与后端 IDLE_TIMEOUT_SECONDS 保持一致：3 小时无真实操作自动下线
const IDLE_MS = 3 * 60 * 60 * 1000
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart', 'scroll']

export default {
  name: 'Layout',
  components: {
    AppMain,
    Navbar,
    RightPanel,
    Settings,
    Sidebar,
    TagsView
  },
  mixins: [ResizeMixin],
  data() {
    return {
      sessionTimer: null,
      activityHandler: null,
      visibilityHandler: null,
      // 首次进入算一次活动；之后只认真实的鼠标/键盘/滚动/触摸操作
      lastActivityAt: Date.now(),
      lastPingAt: 0
    }
  },
  computed: {
    ...mapState({
      sidebar: state => state.app.sidebar,
      device: state => state.app.device,
      showSettings: state => state.settings.showSettings,
      needTagsView: state => state.settings.tagsView,
      fixedHeader: state => state.settings.fixedHeader
    }),
    classObj() {
      return {
        hideSidebar: !this.sidebar.opened,
        openSidebar: this.sidebar.opened,
        withoutAnimation: this.sidebar.withoutAnimation,
        mobile: this.device === 'mobile'
      }
    }
  },
  mounted() {
    // 记录真实操作时间：纯挂机不算活动，不能靠 15 秒心跳一直续期
    this.activityHandler = () => {
      const now = Date.now()
      // 鼠标移动会高频触发，3 秒内只更新一次，避免频繁写时间戳
      if (now - this.lastActivityAt > 3000) this.lastActivityAt = now
    }
    ACTIVITY_EVENTS.forEach(event => {
      document.addEventListener(event, this.activityHandler, { passive: true })
    })
    // 标签页切回来时立刻检查一次，后台标签页的定时器可能被浏览器降频
    this.visibilityHandler = () => {
      if (document.hidden) return
      this.activityHandler()
      this.checkSession()
    }
    document.addEventListener('visibilitychange', this.visibilityHandler)
    this.sessionTimer = setInterval(() => this.checkSession(), 15000)
  },
  beforeDestroy() {
    if (this.sessionTimer) clearInterval(this.sessionTimer)
    if (this.activityHandler) {
      ACTIVITY_EVENTS.forEach(event => document.removeEventListener(event, this.activityHandler))
    }
    if (this.visibilityHandler) document.removeEventListener('visibilitychange', this.visibilityHandler)
  },
  methods: {
    checkSession() {
      if (!this.$store.getters.token) return
      const now = Date.now()
      if (this.lastActivityAt > this.lastPingAt) {
        // 有新操作：正常心跳给会话续期，顺带探测是否被顶下线
        this.lastPingAt = now
        ping(null).catch(() => {})
      } else if (now - this.lastActivityAt >= IDLE_MS) {
        // 空闲超时后只检查状态，绝不续期；后端已踢下线时由拦截器提示并跳登录页
        ping(null, true).catch(() => {})
      }
    },
    handleClickOutside() {
      this.$store.dispatch('app/closeSideBar', { withoutAnimation: false })
    }
  }
}
</script>

<style lang="scss" scoped>
  @import "~@/styles/mixin.scss";
  @import "~@/styles/variables.scss";

  .app-wrapper {
    @include clearfix;
    position: relative;
    height: 100%;
    width: 100%;

    &.mobile.openSidebar {
      position: fixed;
      top: 0;
    }
  }

  .drawer-bg {
    background: #000;
    opacity: 0.3;
    width: 100%;
    top: 0;
    height: 100%;
    position: absolute;
    z-index: 999;
  }

  .fixed-header {
    position: fixed;
    top: 0;
    right: 0;
    z-index: 9;
    width: calc(100% - #{$sideBarWidth});
    transition: width 0.28s;
  }

  .hideSidebar .fixed-header {
    width: calc(100% - 54px)
  }

  .mobile .fixed-header {
    width: 100%;
  }
</style>
