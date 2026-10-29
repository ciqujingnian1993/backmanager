<template>
  <div class="app-container">
    <div class="readonly-tip">
      <i class="el-icon-info" /> 成本查询仅供查看，如需新增或修改请到「支出管理」菜单
    </div>
    <cost-tab :readonly="true" />
  </div>
</template>

<script>
import CostTab from './components/CostTab'

export default {
  name: 'CostQuery',
  components: { CostTab }
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
