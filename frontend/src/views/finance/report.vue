<template>
  <div v-loading="loading" class="app-container finance-report">
    <!-- 月份选择 -->
    <div class="toolbar">
      <el-date-picker
        v-model="month"
        type="month"
        :clearable="false"
        value-format="yyyy-MM"
        placeholder="选择自然月"
        :picker-options="monthOptions"
        @change="fetchData"
      />      <el-button icon="el-icon-d-arrow-left" @click="shiftMonth(-1)">上月</el-button>
      <el-button icon="el-icon-d-arrow-right" @click="shiftMonth(1)">下月</el-button>
      <el-button icon="el-icon-refresh" @click="fetchData">刷新</el-button>
      <el-button type="primary" icon="el-icon-download" plain @click="exportCsv">导出 CSV</el-button>
      <span class="toolbar-tip">按业务日期归属到自然月（如「10/30」按录入年份归到 10 月）</span>
    </div>

    <!-- 核心指标 -->
    <el-row :gutter="14" class="stat-row">
      <el-col v-for="card in statCards" :key="card.key" :xs="12" :sm="8" :md="4">
        <div class="stat-card">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value" :class="card.tone">{{ card.isText ? card.value : money(card.value) }}</div>
          <div v-if="card.compare !== undefined" class="stat-compare">
            <template v-if="card.compare === null">上月无数据</template>
            <template v-else>
              <span :class="compareClass(card)">
                {{ card.compare >= 0 ? '↑' : '↓' }} {{ Math.abs(card.compare) }}%
              </span>
              <span class="compare-base">环比上月</span>
            </template>
          </div>
          <div v-else-if="card.sub" class="stat-compare">{{ card.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表 -->
    <el-row :gutter="14">
      <el-col :md="24">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>每日收入与支出</span>
            <span class="panel-tip">{{ report.month }} 全月逐日 · 金额单位：元</span>
          </div>
          <base-chart :option="dailyOption" height="300px" />
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="14" class="chart-row">
      <el-col :md="12">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>收入构成（按行业）</span>
            <span class="panel-tip">合计 {{ money(report.summary.revenue) }} 元</span>
          </div>
          <base-chart v-if="revenuePieData.length" :option="revenuePieOption" height="300px" />
          <div v-else class="empty-chart">本月暂无收入数据</div>
        </el-card>
      </el-col>
      <el-col :md="12">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>支出构成（按类别）</span>
            <span class="panel-tip">合计 {{ money(report.summary.opex) }} 元</span>
          </div>
          <base-chart v-if="costPieData.length" :option="costPieOption" height="300px" />
          <div v-else class="empty-chart">本月暂无支出数据</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 排行表 -->
    <el-row :gutter="14" class="chart-row">
      <el-col :md="14">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>业务项排行</span>
            <span class="panel-tip">一条明细含多个业务项时，收入会计入每一项</span>
          </div>
          <el-table :data="report.biz_item_rank" size="small" border>
            <el-table-column label="业务项" min-width="140">
              <template slot-scope="{ row }">{{ row.name }}</template>
            </el-table-column>
            <el-table-column label="执照数" width="80" align="center">
              <template slot-scope="{ row }">{{ row.count }}</template>
            </el-table-column>
            <el-table-column label="收入" width="90" align="right">
              <template slot-scope="{ row }">{{ money(row.revenue) }}</template>
            </el-table-column>
            <el-table-column label="成本" width="90" align="right">
              <template slot-scope="{ row }">{{ money(row.cost) }}</template>
            </el-table-column>
            <el-table-column label="利润" width="90" align="right">
              <template slot-scope="{ row }">
                <span :class="row.profit < 0 ? 'danger-text' : ''">{{ money(row.profit) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :md="10">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>客户排行</span>
            <span class="panel-tip">按收入排序</span>
          </div>
          <el-table :data="report.client_rank" size="small" border>
            <el-table-column label="客户" min-width="130">
              <template slot-scope="{ row }">{{ row.name }}</template>
            </el-table-column>
            <el-table-column label="订单数" width="80" align="center">
              <template slot-scope="{ row }">{{ row.orders }}</template>
            </el-table-column>
            <el-table-column label="收入" width="100" align="right">
              <template slot-scope="{ row }">{{ money(row.revenue) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 订单明细 -->
    <el-card shadow="never" class="panel table-panel">
      <div slot="header" class="panel-head">
        <span>订单明细（{{ report.orders.length }} 单）</span>
        <span class="panel-tip">本月归属的全部订单</span>
      </div>
      <el-table :data="report.orders" size="small" border>
        <el-table-column label="订单" width="70" align="center">
          <template slot-scope="{ row }">#{{ row.id }}</template>
        </el-table-column>
        <el-table-column label="业务日期" width="95" align="center">
          <template slot-scope="{ row }">{{ row.biz_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="客户" min-width="130" show-overflow-tooltip>
          <template slot-scope="{ row }">{{ row.client || '—' }}</template>
        </el-table-column>
        <el-table-column label="行业" width="95">
          <template slot-scope="{ row }">{{ row.category || '—' }}</template>
        </el-table-column>
        <el-table-column label="业务项" min-width="150" show-overflow-tooltip>
          <template slot-scope="{ row }">{{ row.items || '—' }}</template>
        </el-table-column>
        <el-table-column label="执照数" width="75" align="center">
          <template slot-scope="{ row }">{{ row.licenses }}</template>
        </el-table-column>
        <el-table-column label="收入" width="85" align="right">
          <template slot-scope="{ row }">{{ money(row.revenue) }}</template>
        </el-table-column>
        <el-table-column label="成本" width="85" align="right">
          <template slot-scope="{ row }">{{ money(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="利润" width="85" align="right">
          <template slot-scope="{ row }">
            <span :class="row.profit < 0 ? 'danger-text' : ''">{{ money(row.profit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="85" align="center">
          <template slot-scope="{ row }">
            <el-tag size="mini" :type="orderStatusType(row.status)">{{ orderStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 支出明细 -->
    <el-card shadow="never" class="panel table-panel">
      <div slot="header" class="panel-head">
        <span>支出明细（{{ report.costs.length }} 笔）</span>
        <span class="panel-tip">其中关联订单 {{ money(relatedOpex) }} 元 · 独立支出 {{ money(report.summary.opex - relatedOpex) }} 元</span>
      </div>
      <el-table :data="report.costs" size="small" border>
        <el-table-column label="业务日期" width="95" align="center">
          <template slot-scope="{ row }">{{ row.biz_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="类别" width="95">
          <template slot-scope="{ row }">{{ row.category || '—' }}</template>
        </el-table-column>
        <el-table-column label="收款方" min-width="130" show-overflow-tooltip>
          <template slot-scope="{ row }">{{ row.payee || '—' }}</template>
        </el-table-column>
        <el-table-column label="金额" width="100" align="right">
          <template slot-scope="{ row }">{{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="方式" width="90">
          <template slot-scope="{ row }">{{ row.method || '—' }}</template>
        </el-table-column>
        <el-table-column label="关联订单" width="90" align="center">
          <template slot-scope="{ row }">{{ row.related_order ? '#' + row.related_order : '—' }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="140" show-overflow-tooltip>
          <template slot-scope="{ row }">{{ row.remark || '—' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import BaseChart from '@/views/dashboard/components/BaseChart'
import { fetchFinanceReport } from '@/api/finance'
import { formatMoney } from '@/constants/bizitem'
import refreshOnActivate from '@/mixins/refresh-on-activate'

const ORDER_STATUS_MAP = { pending: '待办', doing: '进行中', done: '已完成' }

export default {
  name: 'FinanceReport',
  components: { BaseChart },
  mixins: [refreshOnActivate],
  data() {
    return {
      loading: false,
      // 空值表示「让后端挑最近有数据的月份」，加载完成后回填
      month: '',
      report: this.emptyReport(),
      monthOptions: {
        disabledDate(time) {
          return time.getTime() > Date.now()
        }
      }
    }
  },
  computed: {
    statCards() {
      const s = this.report.summary
      const p = this.report.prev_summary
      const pct = (cur, prev) => {
        if (!prev) return null
        if (!cur) return -100
        return Math.round(((cur - prev) / prev) * 1000) / 10
      }
      const doneRate = s.licenses ? Math.round((s.done_tasks / s.licenses) * 100) : 0
      return [
        { key: 'revenue', label: '营业收入', value: s.revenue, tone: 'ok', upGood: true, compare: pct(s.revenue, p.revenue) },
        { key: 'direct', label: '订单直接成本', value: s.direct_cost, tone: '', upGood: false, compare: pct(s.direct_cost, p.direct_cost) },
        { key: 'opex', label: '运营支出', value: s.opex, tone: '', upGood: false, compare: pct(s.opex, p.opex) },
        { key: 'total', label: '总成本', value: s.total_cost, tone: '', upGood: false, compare: pct(s.total_cost, p.total_cost) },
        {
          key: 'profit', label: '净利润', value: s.net_profit,
          tone: s.net_profit >= 0 ? 'ok' : 'danger', upGood: true, compare: pct(s.net_profit, p.net_profit)
        },
        {
          key: 'tasks', label: '任务完成率', isText: true,
          value: s.licenses ? doneRate + '%' : '—',
          tone: '', upGood: true,
          sub: `${s.done_tasks}/${s.licenses} 个执照 · 平均结案 ${s.avg_close_days === null ? '—' : s.avg_close_days + ' 天'}`
        }
      ]
    },
    relatedOpex() {
      return this.report.costs
        .filter(row => row.related_order)
        .reduce((sum, row) => sum + Number(row.amount || 0), 0)
    },
    dailyOption() {
      const daily = this.report.daily || []
      return {
        tooltip: { trigger: 'axis' },
        legend: { data: ['收入', '支出'], top: 0 },
        grid: { left: 50, right: 20, top: 34, bottom: 28 },
        xAxis: { type: 'category', data: daily.map(item => item.day) },
        yAxis: { type: 'value' },
        series: [
          {
            name: '收入', type: 'line', smooth: true, data: daily.map(item => item.revenue),
            itemStyle: { color: '#67c23a' }, areaStyle: { opacity: 0.08 }
          },
          {
            name: '支出', type: 'line', smooth: true, data: daily.map(item => item.opex),
            itemStyle: { color: '#e6a23c' }, areaStyle: { opacity: 0.08 }
          }
        ]
      }
    },
    revenuePieData() {
      return (this.report.revenue_by_category || [])
        .filter(item => Number(item.amount) > 0)
        .map(item => ({ name: item.name, value: item.amount }))
    },
    costPieData() {
      return (this.report.cost_by_category || [])
        .filter(item => Number(item.amount) > 0)
        .map(item => ({ name: item.name, value: item.amount }))
    },
    revenuePieOption() {
      return this.pieOption(this.revenuePieData)
    },
    costPieOption() {
      return this.pieOption(this.costPieData)
    }
  },
  created() {
    this.fetchData()
  },
  methods: {
    money: formatMoney,
    // 环比颜色按业务含义：收入/利润涨=好(绿)；成本涨=坏(红)
    compareClass(card) {
      const good = card.compare >= 0
      const positive = card.upGood ? good : !good
      return positive ? 'is-good' : 'is-bad'
    },
    orderStatusText(status) {
      return ORDER_STATUS_MAP[status] || status
    },
    orderStatusType(status) {
      return status === 'done' ? 'success' : status === 'doing' ? '' : 'info'
    },
    pieOption(data) {
      return {
        tooltip: { trigger: 'item', formatter: '{b}: {c} 元 ({d}%)' },
        legend: { orient: 'vertical', right: 6, top: 'middle', type: 'scroll' },
        series: [{
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['38%', '50%'],
          label: { show: false },
          data
        }]
      }
    },
    emptyReport() {
      return {
        month: '',
        summary: { orders: 0, licenses: 0, revenue: 0, direct_cost: 0, opex: 0, total_cost: 0, net_profit: 0, done_tasks: 0, avg_close_days: null },
        prev_summary: { revenue: 0, direct_cost: 0, opex: 0, total_cost: 0, net_profit: 0 },
        revenue_by_category: [],
        revenue_by_platform: [],
        cost_by_category: [],
        biz_item_rank: [],
        client_rank: [],
        daily: [],
        orders: [],
        costs: []
      }
    },
    async fetchData() {
      this.loading = true
      try {
        const { data } = await fetchFinanceReport({ month: this.month || undefined })
        this.report = Object.assign(this.emptyReport(), data || {})
        if (data && data.month) this.month = data.month
      } finally {
        this.loading = false
      }
    },
    shiftMonth(delta) {
      const now = new Date()
      const pad = v => String(v).padStart(2, '0')
      const base = this.month || `${now.getFullYear()}-${pad(now.getMonth() + 1)}`
      const [year, mon] = base.split('-').map(Number)
      const date = new Date(year, mon - 1 + delta, 1)
      this.month = `${date.getFullYear()}-${pad(date.getMonth() + 1)}`
      this.fetchData()
    },
    exportCsv() {
      const d = this.report
      const s = d.summary
      const rows = [
        [`财务报表 ${d.month}`],
        ['营业收入', s.revenue, '订单直接成本', s.direct_cost, '运营支出', s.opex, '总成本', s.total_cost, '净利润', s.net_profit],
        [`订单 ${s.orders} 单 · 执照 ${s.licenses} 个 · 完成 ${s.done_tasks} 个 · 平均结案 ${s.avg_close_days === null ? '—' : s.avg_close_days + ' 天'}`],
        [],
        ['收入构成（按行业）'],
        ['行业', '订单数', '收入'],
        ...d.revenue_by_category.map(item => [item.name, item.count, item.amount]),
        [],
        ['支出构成（按类别）'],
        ['类别', '笔数', '金额'],
        ...d.cost_by_category.map(item => [item.name, item.count, item.amount]),
        [],
        ['业务项排行'],
        ['业务项', '执照数', '收入', '成本', '利润'],
        ...d.biz_item_rank.map(item => [item.name, item.count, item.revenue, item.cost, item.profit]),
        [],
        ['客户排行'],
        ['客户', '订单数', '收入'],
        ...d.client_rank.map(item => [item.name, item.orders, item.revenue]),
        [],
        ['订单明细'],
        ['订单', '业务日期', '客户', '行业', '平台', '业务项', '执照数', '收入', '成本', '利润', '状态'],
        ...d.orders.map(item => [
          '#' + item.id, item.biz_date, item.client, item.category, item.platform,
          item.items, item.licenses, item.revenue, item.cost, item.profit, this.orderStatusText(item.status)
        ]),
        [],
        ['支出明细'],
        ['业务日期', '类别', '收款方', '金额', '方式', '关联订单', '备注'],
        ...d.costs.map(item => [
          item.biz_date, item.category, item.payee, item.amount, item.method,
          item.related_order ? '#' + item.related_order : '', item.remark
        ])
      ]
      const csv = '\ufeff' + rows
        .map(row => row.map(cell => `"${String(cell === null || cell === undefined ? '' : cell).replace(/"/g, '""')}"`).join(','))
        .join('\r\n')
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `财务报表_${d.month}.csv`
      link.click()
      URL.revokeObjectURL(link.href)
    },
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新
    refreshPage() {
      this.fetchData()
    }
  }
}
</script>

<style lang="scss" scoped>
.finance-report {
  .toolbar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
  }

  .toolbar-tip {
    color: #909399;
    font-size: 12px;
  }

  .stat-row {
    margin-bottom: 14px;
  }

  .stat-card {
    background: #f7f8fa;
    border-radius: 4px;
    padding: 12px 14px;
    min-height: 84px;
  }

  .stat-label {
    color: #909399;
    font-size: 12px;
  }

  .stat-value {
    margin-top: 6px;
    font-size: 20px;
    font-weight: 600;
    color: #303133;

    &.ok { color: #529b2e; }
    &.danger { color: #cf1322; }
  }

  .stat-compare {
    margin-top: 4px;
    font-size: 12px;
    color: #909399;

    .is-good { color: #529b2e; }
    .is-bad { color: #cf1322; }

    .compare-base {
      margin-left: 4px;
      color: #c0c4cc;
    }
  }

  .chart-row {
    margin-top: 14px;
  }

  .panel {
    .panel-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      font-weight: 600;
    }

    .panel-tip {
      font-weight: 400;
      font-size: 12px;
      color: #909399;
    }
  }

  .table-panel {
    margin-top: 14px;
  }

  .empty-chart {
    height: 260px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #c0c4cc;
    font-size: 13px;
  }

  .danger-text {
    color: #cf1322;
  }
}
</style>
