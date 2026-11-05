<template>
  <div class="app-container">
    <div class="readonly-tip">
      <i class="el-icon-info" /> 订单查询仅供查看，如需新增或修改请到「订单管理」菜单
    </div>

    <div v-if="drillTip" class="drill-tip">
      <i class="el-icon-position" />
      <span class="drill-text">首页穿透：{{ drillTip }}</span>
      <el-button type="text" size="mini" @click="clearDrill">清除筛选</el-button>
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
      <el-button
        class="filter-item"
        :type="listQuery.month ? 'default' : 'primary'"
        @click="showAllMonths"
      >
        全部月份
      </el-button>
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索订单编号 / 客户 / 手机号 / 执照 / 法人"
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
        v-model="listQuery.category"
        class="filter-item"
        placeholder="行业"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
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
      <el-table-column label="订单编号" width="148" align="center">
        <template slot-scope="{ row }">
          <span v-if="row.order_no" class="order-no-text">{{ row.order_no }}</span>
          <span v-else class="muted-text">—</span>
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
import { fetchAccountList, fetchAccountDetail } from '@/api/account'
import { fetchPlatformList } from '@/api/platform'
import { BIZ_STATUS_OPTIONS, TAX_STATUS_OPTIONS } from '@/constants/license'
import refreshOnActivate from '@/mixins/refresh-on-activate'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

const CATEGORY_OPTIONS = ['同行', '代理记账', '工商注册', '变更注销']
const DRILL_KEYS = ['status', 'category', 'biz_status', 'tax_status', 'platform', 'keyword', 'id']

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
      drill: {},
      pendingDetailId: null,
      listQuery: {
        page: 1,
        limit: 20,
        month,
        keyword: '',
        status: '',
        category: '',
        platform: '',
        biz_status: '',
        tax_status: ''
      }
    }
  },
  computed: {
    categoryOptions() {
      const list = CATEGORY_OPTIONS.map(name => ({ label: name, value: name }))
      list.push({ label: '未分类', value: '__empty__' })
      const current = this.listQuery.category
      if (current && current !== '__empty__' && !CATEGORY_OPTIONS.includes(current)) {
        list.push({ label: current, value: current })
      }
      return list
    },
    drillTip() {
      const q = this.drill || {}
      const parts = []
      if (q.month === 'all') parts.push('全部月份')
      else if (q.month) parts.push(q.month + ' 月')
      if (q.status) parts.push('状态：' + (STATUS_MAP[q.status] || q.status))
      if (q.category === '__empty__') parts.push('行业：未分类')
      else if (q.category) parts.push('行业：' + q.category)
      if (q.biz_status) parts.push('工商：' + q.biz_status)
      if (q.tax_status) parts.push('税务：' + q.tax_status)
      if (q.platform) parts.push('平台：' + q.platform)
      if (q.keyword) parts.push('关键字：' + q.keyword)
      if (q.id) parts.push('订单 #' + q.id)
      return parts.join(' · ')
    }
  },
  created() {
    this.__querySign = ''
    this.applyRouteQuery()
    this.getList().then(this.openPendingDetail)
    this.getPlatforms()
  },
  methods: {
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新
    refreshPage() {
      this.applyRouteQuery()
      this.getList().then(this.openPendingDetail)
      this.getPlatforms()
    },
    // 首页图表 / 卡片穿透过来时带在 URL 上的筛选条件
    applyRouteQuery() {
      const q = this.$route.query || {}
      const sign = JSON.stringify(q)
      if (sign === this.__querySign) return false
      this.__querySign = sign
      const next = { month: '', keyword: '', status: '', category: '', platform: '', biz_status: '', tax_status: '' }
      if (q.month === 'all') next.month = ''
      else if (q.month) next.month = q.month
      DRILL_KEYS.forEach(key => {
        if (key !== 'id' && q[key]) next[key] = q[key]
      })
      Object.assign(this.listQuery, next, { page: 1 })
      this.drill = Object.assign({}, q)
      this.pendingDetailId = q.id ? Number(q.id) : null
      return true
    },
    // 带 id 跳过来时自动打开该订单详情，列表里没有就直接查详情接口
    async openPendingDetail() {
      const id = this.pendingDetailId
      if (!id) return
      this.pendingDetailId = null
      const row = this.list.find(item => Number(item.id) === id)
      if (row) {
        this.handleDetail(row)
        return
      }
      try {
        const { data } = await fetchAccountDetail(id)
        if (data) this.handleDetail(data)
      } catch (error) {
        this.$message.error('这条订单已不存在或无权查看')
      }
    },
    clearDrill() {
      this.drill = {}
      this.__querySign = ''
      this.listQuery.month = ''
      this.listQuery.keyword = ''
      this.listQuery.status = ''
      this.listQuery.category = ''
      this.listQuery.platform = ''
      this.listQuery.biz_status = ''
      this.listQuery.tax_status = ''
      this.listQuery.page = 1
      this.$router.replace({ path: this.$route.path })
      this.getList()
    },
    showAllMonths() {
      this.listQuery.month = ''
      this.handleFilter()
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

.order-no-text {
  font-family: Menlo, Consolas, monospace;
  font-size: 12px;
  color: #606266;
}
</style>
