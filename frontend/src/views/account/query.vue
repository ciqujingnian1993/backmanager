<template>
  <div class="app-container">
    <div class="readonly-tip">
      <i class="el-icon-info" /> 订单查询仅供查看，如需新增或修改请到「订单管理」菜单
    </div>

    <div class="filter-container">
      <el-date-picker
        v-model="listQuery.month"
        class="filter-item"
        type="month"
        placeholder="全部月份"
        format="yyyy-MM"
        value-format="yyyy-MM"
        :clearable="true"
        @change="handleFilter"
      />
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索客户 / 手机号 / 执照 / 法人"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-select
        v-model="listQuery.status"
        class="filter-item"
        placeholder="订单状态"
        clearable
        @change="handleFilter"
      >
        <el-option label="待定" value="pending" />
        <el-option label="进行中" value="doing" />
        <el-option label="已完成" value="done" />
      </el-select>
      <el-select
        v-model="listQuery.biz_status"
        class="filter-item"
        placeholder="工商状态"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in bizStatusOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select
        v-model="listQuery.tax_status"
        class="filter-item"
        placeholder="税务状态"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in taxStatusOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select
        v-model="listQuery.platform"
        class="filter-item"
        placeholder="来源平台"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in platformOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column type="expand">
        <template slot-scope="{ row }">
          <order-items-table :details="row.details" />
        </template>
      </el-table-column>
      <el-table-column prop="biz_date" label="日期" width="88" align="center" />
      <el-table-column prop="category" label="行业" width="92" align="center" />
      <el-table-column prop="client" label="客户" min-width="100" show-overflow-tooltip />
      <el-table-column label="手机号" width="116">
        <template slot-scope="{ row }">
          <span v-if="row.phone">{{ row.phone }}</span>
          <span v-else class="muted-text">—</span>
        </template>
      </el-table-column>
      <el-table-column label="平台" width="78" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.platform" size="mini" effect="plain">{{ row.platform }}</el-tag>
          <span v-else class="muted-text">—</span>
        </template>
      </el-table-column>
      <el-table-column label="执照" width="100" align="center">
        <template slot-scope="{ row }">
          <el-button type="text" size="mini" @click="handleDetail(row)">
            {{ row.license_count }} 个（完成 {{ row.done_count }}）
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="items" label="业务项" min-width="108" show-overflow-tooltip />
      <el-table-column label="收入" width="82" align="center">
        <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template slot-scope="{ row }">
          <el-tag :type="statusType(row.status)" size="mini">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="完成时间" width="138" align="center">
        <template slot-scope="{ row }">{{ completedText(row.completed_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" fixed="right">
        <template slot-scope="{ row }">
          <el-button type="text" size="mini" @click="handleDetail(row)">详情</el-button>
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

    <order-detail-dialog :visible.sync="detailVisible" :row="detailRow" />
  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import OrderDetailDialog from './components/OrderDetailDialog'
import OrderItemsTable from './components/OrderItemsTable'
import { fetchAccountList } from '@/api/account'
import { fetchPlatformList } from '@/api/platform'
import { BIZ_STATUS_OPTIONS, TAX_STATUS_OPTIONS } from '@/constants/license'
import refreshOnActivate from '@/mixins/refresh-on-activate'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

export default {
  name: 'OrderQuery',
  components: { Pagination, OrderDetailDialog, OrderItemsTable },
  mixins: [refreshOnActivate],
  data() {
    const now = new Date()
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    return {
      loading: false,
      list: [],
      total: 0,
      platformOptions: [],
      bizStatusOptions: BIZ_STATUS_OPTIONS,
      taxStatusOptions: TAX_STATUS_OPTIONS,
      detailVisible: false,
      detailRow: null,
      listQuery: {
        page: 1,
        limit: 20,
        month,
        keyword: '',
        status: '',
        platform: '',
        biz_status: '',
        tax_status: ''
      }
    }
  },
  created() {
    const keyword = this.$route.query.keyword
    if (keyword) this.listQuery.keyword = keyword
    this.getList()
    this.getPlatforms()
  },
  methods: {
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新
    refreshPage() {
      this.getList()
      this.getPlatforms()
    },
    handleDetail(row) {
      this.detailRow = row
      this.detailVisible = true
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchAccountList(this.listQuery)
        this.list = data.items || []
        this.total = data.total || 0
      } finally {
        this.loading = false
      }
    },
    async getPlatforms() {
      try {
        const { data } = await fetchPlatformList()
        this.platformOptions = (data || []).map(item => item.name)
      } catch (error) {
        this.platformOptions = []
      }
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
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
    },
    completedText(stamp) {
      if (!stamp) return '—'
      const date = new Date(Number(stamp))
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
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

.filter-container {
  padding-bottom: 10px;

  .filter-item {
    margin-right: 10px;
    margin-bottom: 10px;
  }

  .keyword-input {
    width: 220px;
  }
}

.muted-text {
  color: #c0c4cc;
}
</style>
