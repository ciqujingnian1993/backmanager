<template>
  <div class="app-container">
    <div class="readonly-tip">
      <i class="el-icon-info" /> 成本查询仅供查看，如需新增或修改请到「支出管理」菜单
    </div>
    <div v-if="drillTip" class="drill-tip">
      <i class="el-icon-position" />
      <span class="drill-text">首页穿透：{{ drillTip }}</span>
      <el-button type="text" size="mini" @click="clearDrill">清除筛选</el-button>
    </div>
    <cost-tab ref="costTab" :readonly="true" />
  </div>
</template>

<script>
import CostTab from './components/CostTab'

export default {
  name: 'CostQuery',
  components: { CostTab },
  computed: {
    drillTip() {
      const q = this.$route.query || {}
      const parts = []
      if (q.month === 'all') parts.push('全部月份')
      else if (q.month) parts.push(q.month + ' 月')
      if (q.category) parts.push('成本类别：' + q.category)
      if (q.keyword) parts.push('关键字：' + q.keyword)
      return parts.join(' · ')
    }
  },
  methods: {
    clearDrill() {
      this.$router.replace({ path: this.$route.path })
      this.$nextTick(() => {
        const tab = this.$refs.costTab
        if (!tab) return
        tab.listQuery.month = ''
        tab.month = ''
        tab.listQuery.category = ''
        tab.listQuery.keyword = ''
        tab.listQuery.page = 1
        tab.__querySign = JSON.stringify({})
        tab.refresh()
      })
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

.drill-tip {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  padding: 7px 12px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
  font-size: 13px;
  color: #409eff;

  i {
    margin-right: 6px;
  }

  .drill-text {
    flex: 1;
  }

  .el-button {
    padding: 0;
    margin-left: 12px;
  }
}
</style>
