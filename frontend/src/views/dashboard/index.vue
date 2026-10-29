<template>
  <div class="app-container dashboard">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="stat-card">
          <div class="stat-label">总收入</div>
          <div class="stat-value revenue">￥{{ money(summary.revenue) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="stat-card">
          <div class="stat-label">总成本</div>
          <div class="stat-value cost">￥{{ money(summary.cost) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="stat-card">
          <div class="stat-label">总利润</div>
          <div class="stat-value profit">￥{{ money(summary.profit) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="stat-card">
          <div class="stat-label">记账笔数</div>
          <div class="stat-value total">
            {{ summary.count }}
            <span class="sub">待定 {{ summary.pending }}</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-card class="recent-card" shadow="never">
      <div slot="header" class="recent-header">
        <span>最近记账</span>
        <el-button type="text" @click="goAccount">查看全部</el-button>
      </div>
      <el-table
        v-loading="loading"
        :data="list"
        size="medium"
        style="width: 100%"
      >
        <el-table-column prop="biz_date" label="日期" width="90" />
        <el-table-column prop="category" label="行业" width="110" />
        <el-table-column prop="client" label="客户" min-width="130" />
        <el-table-column prop="items" label="业务项" min-width="130" />
        <el-table-column label="收入" width="100" align="right">
          <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
        </el-table-column>
        <el-table-column label="成本" width="100" align="right">
          <template slot-scope="{ row }">{{ amount(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="利润" width="100" align="right">
          <template slot-scope="{ row }">{{ amount(row.profit) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template slot-scope="{ row }">
            <el-tag :type="statusType(row.status)" size="mini">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && !list.length" class="empty">
        还没有记账记录，去「记账本」记一笔吧
      </div>
    </el-card>
  </div>
</template>

<script>
import { fetchAccountList, fetchAccountSummary } from '@/api/account'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

export default {
  name: 'Dashboard',
  data() {
    return {
      loading: false,
      list: [],
      summary: {
        count: 0,
        revenue: 0,
        cost: 0,
        profit: 0,
        pending: 0
      }
    }
  },
  created() {
    this.getSummary()
    this.getRecent()
  },
  methods: {
    async getSummary() {
      try {
        const { data } = await fetchAccountSummary()
        this.summary = data
      } catch (e) {
        // 汇总失败时保留默认零值，不阻塞页面
      }
    },
    async getRecent() {
      this.loading = true
      try {
        const { data } = await fetchAccountList({ page: 1, limit: 8 })
        this.list = data.items || []
      } finally {
        this.loading = false
      }
    },
    goAccount() {
      this.$router.push('/account/index')
    },
    money(value) {
      const num = Number(value || 0)
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    statusText(status) {
      return STATUS_MAP[status] || '待定'
    },
    statusType(status) {
      return status === 'done' ? 'success' : status === 'doing' ? 'warning' : 'info'
    }
  }
}
</script>

<style lang="scss" scoped>
.dashboard {
  .stat-row {
    margin-bottom: 18px;
  }

  .stat-card {
    background: #fff;
    border-radius: 4px;
    padding: 16px 18px;
    box-shadow: 0 1px 4px rgba(0, 21, 255, 0.08);
  }

  .stat-label {
    color: #909399;
    font-size: 13px;
  }

  .stat-value {
    margin-top: 6px;
    font-size: 22px;
    font-weight: 600;

    &.revenue { color: #67c23a; }
    &.cost { color: #e6a23c; }
    &.profit { color: #409eff; }
    &.total { color: #303133; }
  }

  .sub {
    margin-left: 8px;
    font-size: 12px;
    font-weight: 400;
    color: #f56c6c;
  }

  .recent-card {
    border-radius: 4px;
  }

  .recent-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 600;
    color: #303133;
  }

  .empty {
    text-align: center;
    color: #909399;
    font-size: 13px;
    padding: 32px 0;
  }
}
</style>
