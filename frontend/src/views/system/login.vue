<template>
  <div class="app-container login-page">
    <div class="page-header">
      <div>
        <h3 class="page-title">登录管理</h3>
        <p class="page-desc">记录每个账号什么时候登录系统、从哪里登录、用的什么设备，以及当前是否在线。连续 3 小时无操作会自动下线。</p>
      </div>
      <el-button icon="el-icon-refresh" @click="getList">刷新</el-button>
    </div>

    <div class="stat-strip">
      <div class="stat-item">
        <span class="stat-label">今日登录</span>
        <span class="stat-value">{{ stats.today_logins || 0 }}</span>
        <span class="stat-unit">次</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">在线账号</span>
        <span class="stat-value online">{{ stats.online_users || 0 }}</span>
        <span class="stat-unit">人</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">今日登录账号</span>
        <span class="stat-value">{{ stats.today_users || 0 }}</span>
        <span class="stat-unit">人</span>
      </div>
    </div>

    <div class="filter-container">
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索账号 / 姓名 / IP / 归属地"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-select
        v-model="listQuery.username"
        class="filter-item"
        placeholder="按账号筛选"
        clearable
        filterable
        @change="handleFilter"
      >
        <el-option
          v-for="item in userOptions"
          :key="item.username"
          :label="item.name ? `${item.name}（${item.username}）` : item.username"
          :value="item.username"
        />
      </el-select>
      <el-date-picker
        v-model="listQuery.date"
        class="filter-item"
        type="date"
        value-format="yyyy-MM-dd"
        placeholder="登录日期"
        clearable
        @change="handleFilter"
      />
      <el-select
        v-model="listQuery.state"
        class="filter-item state-select"
        placeholder="在线状态"
        clearable
        @change="handleFilter"
      >
        <el-option label="在线" value="online" />
        <el-option label="已离线" value="offline" />
      </el-select>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column label="账号" min-width="130" show-overflow-tooltip>
        <template slot-scope="{ row }">
          <span class="username">{{ row.username }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="姓名" min-width="110" show-overflow-tooltip />
      <el-table-column prop="login_time" label="登录时间（北京时间）" width="170" align="center" />
      <el-table-column prop="last_activity" label="最后活动（北京时间）" width="170" align="center">
        <template slot-scope="{ row }">
          <span class="muted">{{ row.last_activity || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template slot-scope="{ row }">
          <el-tag :type="row.online ? 'success' : 'info'" size="mini">
            {{ row.online ? '在线' : '已离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="来源 IP" min-width="140" show-overflow-tooltip />
      <el-table-column prop="location" label="归属地" min-width="210" show-overflow-tooltip />
      <el-table-column label="设备 / 浏览器" min-width="170" show-overflow-tooltip>
        <template slot-scope="{ row }">
          <span :title="row.user_agent">{{ row.device }}</span>
        </template>
      </el-table-column>
      <el-table-column label="退出时间" width="170" align="center">
        <template slot-scope="{ row }">
          <span class="muted">{{ row.logout_time || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结束原因" width="130" align="center">
        <template slot-scope="{ row }">
          <span class="muted">{{ row.end_reason || (row.online ? '当前会话' : '—') }}</span>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      :page.sync="listQuery.page"
      :limit.sync="listQuery.limit"
      @pagination="getList"
    />
  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import { fetchLoginLogs } from '@/api/login-log'
import refreshOnActivate from '@/mixins/refresh-on-activate'

export default {
  name: 'LoginLogManage',
  components: { Pagination },
  mixins: [refreshOnActivate],
  data() {
    return {
      loading: false,
      total: 0,
      list: [],
      userOptions: [],
      stats: {},
      listQuery: {
        page: 1,
        limit: 20,
        keyword: '',
        username: '',
        date: '',
        state: ''
      }
    }
  },
  created() {
    this.getList()
  },
  methods: {
    refreshPage() {
      this.getList()
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchLoginLogs(this.listQuery)
        this.list = data.items || []
        this.total = data.total || 0
        this.stats = data.stats || {}
        this.userOptions = data.users || []
      } finally {
        this.loading = false
      }
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    }
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .page-title {
    margin: 0 0 6px;
    font-size: 18px;
    font-weight: 600;
    color: #303133;
  }
  .page-desc {
    margin: 0;
    font-size: 13px;
    color: #909399;
  }
  .stat-strip {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
  }
  .stat-item {
    flex: 1;
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 12px 16px;
    background: #fff;
    border: 1px solid #ebeef5;
    border-radius: 6px;
  }
  .stat-label {
    flex: 1;
    font-size: 13px;
    color: #606266;
  }
  .stat-value {
    font-size: 22px;
    font-weight: 600;
    color: #303133;
    &.online { color: #67c23a; }
  }
  .stat-unit {
    font-size: 12px;
    color: #909399;
  }
  .filter-container {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 14px;
  }
  .keyword-input { width: 280px; }
  .state-select { width: 130px; }
  .username {
    font-weight: 600;
    color: #303133;
  }
  .muted {
    color: #909399;
  }
}
</style>
