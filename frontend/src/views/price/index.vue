<template>
  <div class="app-container price-page">
    <!-- 页头：一句话说明这页在管什么，右侧给两个总量，省得再往下数 -->
    <div class="page-head">
      <div class="head-main">
        <div class="head-title">
          价格配置
          <el-tag v-if="!isAdmin" size="mini" type="info" effect="plain">只读</el-tag>
        </div>
        <div class="head-desc">
          工商 / 税务代办服务的标准价与同行参考价。价格设置里改完即时生效，价格查看按类别汇总报价用。
        </div>
      </div>
      <div class="head-side">
        <div class="side-item">
          <span class="side-num">{{ stats.total || 0 }}</span>
          <span class="side-label">服务项目</span>
        </div>
        <div class="side-item">
          <span class="side-num">{{ categories.length }}</span>
          <span class="side-label">类别</span>
        </div>
      </div>
    </div>

    <el-tabs v-model="tab" class="price-tabs">
      <el-tab-pane v-if="isAdmin" label="价格设置" name="setting">
        <price-setting
          :items="items"
          :categories="categories"
          :settings="settings"
          :loading="loading"
          @refresh="load"
        />
      </el-tab-pane>
      <el-tab-pane label="价格查看" name="view">
        <price-view
          :items="items"
          :categories="categories"
          :settings="settings"
          :stats="stats"
          :loading="loading"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import { fetchPriceList } from '@/api/price'
import refreshOnActivate from '@/mixins/refresh-on-activate'
import PriceSetting from './components/PriceSetting'
import PriceView from './components/PriceView'

export default {
  name: 'PriceConfig',
  components: { PriceSetting, PriceView },
  mixins: [refreshOnActivate],
  data() {
    return {
      tab: (this.$store.getters.roles || []).includes('admin') ? 'setting' : 'view',
      loading: false,
      items: [],
      categories: [],
      settings: { notice: '', tips: '' },
      stats: {}
    }
  },
  computed: {
    isAdmin() {
      return (this.$store.getters.roles || []).includes('admin')
    }
  },
  created() {
    this.load()
  },
  methods: {
    refreshPage() {
      this.load()
    },
    async load() {
      this.loading = true
      try {
        const { data } = await fetchPriceList()
        this.items = data.items || []
        this.categories = data.categories || []
        this.settings = data.settings || { notice: '', tips: '' }
        this.stats = data.stats || {}
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.price-page {
  .page-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    margin-bottom: 16px;
    background: linear-gradient(120deg, #f4f9ff 0%, #ffffff 62%);
    border: 1px solid #e8eef7;
    border-radius: 8px;
  }

  .head-title {
    display: flex;
    align-items: center;
    font-size: 19px;
    font-weight: 600;
    color: #1f2d3d;
    letter-spacing: 0.5px;

    .el-tag {
      margin-left: 8px;
    }
  }

  .head-desc {
    margin-top: 7px;
    max-width: 660px;
    font-size: 12px;
    line-height: 19px;
    color: #7a869a;
  }

  .head-side {
    display: flex;
    align-items: center;
    flex: none;
  }

  .side-item {
    min-width: 96px;
    text-align: center;

    & + .side-item {
      border-left: 1px solid #e4ebf5;
    }
  }

  .side-num {
    display: block;
    font-size: 24px;
    font-weight: 600;
    line-height: 28px;
    color: #2f6fe4;
    font-family: Menlo, Consolas, monospace;
  }

  .side-label {
    font-size: 12px;
    color: #909399;
  }

  .price-tabs {
    ::v-deep .el-tabs__header {
      margin-bottom: 18px;
    }

    ::v-deep .el-tabs__item {
      font-size: 14px;
      height: 42px;
      line-height: 42px;
    }
  }
}
</style>
