<template>
  <div class="app-container">
    <el-tabs v-model="activeTab" type="border-card" @tab-click="handleTabClick">
      <el-tab-pane label="支出管理" name="manage">
        <cost-tab />
      </el-tab-pane>

      <el-tab-pane label="查询列表" name="query" lazy>
        <div class="readonly-tip">
          <i class="el-icon-info" /> 查询列表仅供查看，如需新增或修改请到「支出管理」页签
        </div>
        <cost-tab ref="queryTab" :readonly="true" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import CostTab from './components/CostTab'

export default {
  name: 'CostManage',
  components: { CostTab },
  data() {
    return {
      activeTab: 'manage'
    }
  },
  created() {
    const tab = this.$route.query.tab
    if (tab === 'query') this.activeTab = 'query'
  },
  watch: {
    // 支持从其他页面带参数跳转到查询列表（同一路由只改 query 时组件不会重建）
    '$route.query.tab'(val) {
      if (val === 'query') this.activeTab = 'query'
    }
  },
  methods: {
    handleTabClick(tab) {
      // 切到查询页签时刷新一次，保证看到的是最新数据
      if (tab.name === 'query' && this.$refs.queryTab) {
        this.$refs.queryTab.refresh()
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.readonly-tip {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f4f4f5;
  border-radius: 4px;
  color: #909399;
  font-size: 13px;

  i {
    margin-right: 4px;
  }
}
</style>
