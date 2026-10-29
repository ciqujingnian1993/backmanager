<template>
  <div v-loading="loading" class="app-container dashboard">
    <!-- 核心指标 -->
    <el-row :gutter="16" class="stat-row">
      <el-col v-for="card in cards" :key="card.label" :xs="12" :sm="8" :lg="4">
        <div class="stat-card">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value" :class="card.tone">{{ card.value }}</div>
          <div class="stat-foot">
            <span v-if="card.growth !== null && card.growth !== undefined" :class="card.growth >= 0 ? 'up' : 'down'">
              {{ card.growth >= 0 ? '↑' : '↓' }}{{ Math.abs(card.growth) }}%
            </span>
            <span>{{ card.foot }}</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 趋势 + 订单状态 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>收支与利润率趋势 · 近 6 个月</span>
            <span class="panel-tip">金额单位：元</span>
          </div>
          <base-chart v-if="hasTrend" :option="trendOption" height="330px" />
          <div v-else class="empty">还没有收支数据，记一笔后这里会出现趋势</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>订单状态</span>
            <span class="panel-tip">共 {{ kpi.orders }} 单</span>
          </div>
          <base-chart v-if="kpi.orders" :option="statusOption" height="330px" />
          <div v-else class="empty">暂无订单</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 结构分析 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :sm="12" :lg="8">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>收入构成</span>
            <span class="panel-tip">按行业</span>
          </div>
          <base-chart v-if="kpi.revenue" :option="revenueOption" height="290px" />
          <div v-else class="empty">暂无收入</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="8">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>成本构成</span>
            <span class="panel-tip">合计 {{ money(kpi.total_cost) }} 元</span>
          </div>
          <base-chart v-if="kpi.total_cost" :option="costOption" height="290px" />
          <div v-else class="empty">暂无成本</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="panel">
          <div slot="header" class="panel-head">
            <span>客户贡献</span>
            <span class="panel-tip">按收入排序</span>
          </div>
          <div v-if="topClients.length" class="client-list">
            <div v-for="(item, index) in topClients" :key="item.client" class="client-item">
              <span class="rank" :class="'rank-' + (index + 1)">{{ index + 1 }}</span>
              <div class="client-main">
                <div class="client-top">
                  <span class="client-name" :title="item.client">{{ item.client }}</span>
                  <span class="client-amount">{{ money(item.revenue) }}</span>
                </div>
                <div class="client-bar">
                  <i :style="{ width: clientWidth(item.revenue) }" />
                </div>
                <div class="client-meta">{{ item.orders }} 单 · 利润 {{ money(item.profit) }}</div>
              </div>
            </div>
          </div>
          <div v-else class="empty">暂无客户数据</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 待办事项 -->
    <el-card shadow="never" class="panel todo-panel">
      <div slot="header" class="panel-head">
        <span>待办事项 · 待完成订单与进度</span>
        <div class="head-tags">
          <el-tag v-for="step in stepDist" :key="step.step" size="mini" type="info" effect="plain">
            {{ step.step }} {{ step.count }}
          </el-tag>
          <el-button type="text" @click="goAccount('progress')">全部进度</el-button>
        </div>
      </div>
      <el-table :data="todos" size="medium" style="width: 100%">
        <el-table-column label="紧急度" width="92" align="center">
          <template slot-scope="{ row }">
            <el-tag :type="levelType(row.level)" size="mini">{{ levelText(row.level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="客户 / 业务项" min-width="190">
          <template slot-scope="{ row }">
            <div class="cell-main">{{ row.client || '未填客户' }}</div>
            <div class="cell-sub">{{ row.items || row.category || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="当前进度" min-width="210">
          <template slot-scope="{ row }">
            <div class="cell-main">
              {{ row.last_step || '未开始' }}
              <span v-if="row.last_status === 'blocked'" class="blocked">受阻</span>
            </div>
            <el-progress
              :percentage="stepPercent(row.last_step)"
              :stroke-width="5"
              :show-text="false"
              :color="progressColor(row.level)"
            />
          </template>
        </el-table-column>
        <el-table-column label="建议下一步" width="110">
          <template slot-scope="{ row }">
            <span class="next-step">{{ row.next_step }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template slot-scope="{ row }">{{ money(row.revenue) }}</template>
        </el-table-column>
        <el-table-column label="停滞" width="130">
          <template slot-scope="{ row }">
            <div class="cell-main">{{ row.days }} 天</div>
            <div class="cell-sub">{{ row.reason }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template slot-scope="{ row }">
            <el-button type="text" @click="goAccount('progress', row.client)">去跟进</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!todos.length" class="empty">没有待办订单，所有订单都已交付完成 🎉</div>
    </el-card>

    <!-- 最近订单 -->
    <el-card shadow="never" class="panel">
      <div slot="header" class="panel-head">
        <span>最近订单</span>
        <el-button type="text" @click="goAccount('table')">查看全部</el-button>
      </div>
      <el-table :data="recent" size="medium" style="width: 100%">
        <el-table-column prop="biz_date" label="日期" width="96" />
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
        <el-table-column label="状态" width="92" align="center">
          <template slot-scope="{ row }">
            <el-tag :type="statusType(row.status)" size="mini">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!recent.length" class="empty">还没有订单记录，去「订单列表」新增一笔吧</div>
    </el-card>
  </div>
</template>

<script>
import BaseChart from './components/BaseChart'
import { fetchDashboardOverview } from '@/api/dashboard'

const STEPS = ['已录入', '已联系', '已报价', '已付款', '办理中', '已交付', '已完成']

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

function emptyData() {
  return {
    kpi: {
      revenue: 0,
      order_cost: 0,
      extra_cost: 0,
      total_cost: 0,
      profit: 0,
      margin: 0,
      orders: 0,
      avg_ticket: 0,
      month_revenue: 0,
      month_cost: 0,
      month_profit: 0,
      month_growth: null,
      open_orders: 0,
      risk_orders: 0,
      pending_orders: 0
    },
    trend: { months: [], revenue: [], cost: [], profit: [], orders: [] },
    revenue_by_category: [],
    cost_by_category: [],
    status_dist: [],
    step_dist: [],
    todos: [],
    top_clients: [],
    recent: []
  }
}

export default {
  name: 'Dashboard',
  components: { BaseChart },
  data() {
    return {
      loading: false,
      data: emptyData()
    }
  },
  computed: {
    kpi() {
      return this.data.kpi
    },
    todos() {
      return this.data.todos || []
    },
    recent() {
      return this.data.recent || []
    },
    topClients() {
      return this.data.top_clients || []
    },
    stepDist() {
      return this.data.step_dist || []
    },
    hasTrend() {
      return this.data.trend.revenue.some(v => v) || this.data.trend.cost.some(v => v)
    },
    cards() {
      const kpi = this.kpi
      return [
        { label: '总收入', value: '￥' + this.money(kpi.revenue), tone: 'revenue', foot: '本月 ￥' + this.money(kpi.month_revenue), growth: kpi.month_growth },
        { label: '总支出', value: '￥' + this.money(kpi.total_cost), tone: 'cost', foot: '订单 ' + this.money(kpi.order_cost) + ' · 其他 ' + this.money(kpi.extra_cost) },
        { label: '净利润', value: '￥' + this.money(kpi.profit), tone: 'profit', foot: '毛利率 ' + kpi.margin + '%' },
        { label: '订单数', value: String(kpi.orders), tone: 'total', foot: '平均客单 ￥' + this.money(kpi.avg_ticket) },
        { label: '待办订单', value: String(kpi.open_orders), tone: 'warn', foot: '高风险 ' + kpi.risk_orders + ' 单' },
        { label: '本月利润', value: '￥' + this.money(kpi.month_profit), tone: 'month', foot: '本月支出 ￥' + this.money(kpi.month_cost) }
      ]
    },
    trendOption() {
      const trend = this.data.trend
      const months = trend.months.map(key => Number(key.slice(5)) + '月')
      const margins = trend.revenue.map((value, index) => {
        if (!value) return null
        return Number(((trend.profit[index] / value) * 100).toFixed(1))
      })
      return {
        color: ['#409eff', '#f0a020', '#67c23a'],
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: params => {
            const lines = [params[0].axisValue]
            params.forEach(item => {
              if (item.seriesName === '利润率') {
                lines.push(item.marker + item.seriesName + '：' + (item.value === null ? '—' : item.value + '%'))
              } else {
                lines.push(item.marker + item.seriesName + '：' + this.money(item.value) + ' 元')
              }
            })
            return lines.join('<br/>')
          }
        },
        legend: { data: ['收入', '支出', '利润率'], right: 8, top: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#606266' }},
        grid: { left: 8, right: 12, top: 44, bottom: 4, containLabel: true },
        xAxis: {
          type: 'category',
          data: months,
          axisTick: { show: false },
          axisLine: { lineStyle: { color: '#e4e7ed' }},
          axisLabel: { color: '#909399' }
        },
        yAxis: [
          {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f2f4f7' }},
            axisLabel: { color: '#909399', formatter: value => this.compact(value) }
          },
          {
            type: 'value',
            min: 0,
            max: 100,
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: false },
            axisLabel: { color: '#c0c4cc', formatter: '{value}%' }
          }
        ],
        series: [
          { name: '收入', type: 'bar', barWidth: 14, data: trend.revenue },
          { name: '支出', type: 'bar', barWidth: 14, data: trend.cost },
          {
            name: '利润率',
            type: 'line',
            yAxisIndex: 1,
            smooth: true,
            symbolSize: 6,
            connectNulls: false,
            data: margins
          }
        ]
      }
    },
    statusOption() {
      const colors = { pending: '#909399', doing: '#409eff', done: '#67c23a' }
      const items = (this.data.status_dist || []).map(item => ({
        name: item.name,
        value: item.count,
        itemStyle: { color: colors[item.key] }
      }))
      const total = this.kpi.orders
      const done = (this.data.status_dist || []).find(item => item.key === 'done')
      return {
        tooltip: { trigger: 'item', formatter: '{b}：{c} 单（{d}%）' },
        legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#606266' }},
        series: [
          {
            type: 'pie',
            radius: ['52%', '72%'],
            center: ['50%', '45%'],
            avoidLabelOverlap: false,
            label: { show: false },
            labelLine: { show: false },
            itemStyle: { borderColor: '#fff', borderWidth: 2 },
            data: items
          }
        ],
        graphic: [
          { type: 'text', left: 'center', top: '38%', style: { text: String(total), fill: '#303133', fontSize: 26, fontWeight: 600, textAlign: 'center' }},
          { type: 'text', left: 'center', top: '47%', style: { text: '订单总数', fill: '#909399', fontSize: 12, textAlign: 'center' }},
          {
            type: 'text',
            left: 'center',
            top: '55%',
            style: {
              text: '完成率 ' + (total ? Math.round(((done ? done.count : 0) / total) * 100) : 0) + '%',
              fill: '#67c23a',
              fontSize: 12,
              textAlign: 'center'
            }
          }
        ]
      }
    },
    revenueOption() {
      const items = this.data.revenue_by_category.map(item => ({ name: item.name, value: item.revenue }))
      return {
        color: ['#409eff', '#53c5f0', '#67c23a', '#f0a020', '#909399', '#b39ddb', '#f56c6c'],
        tooltip: { trigger: 'item', formatter: params => params.name + '：' + this.money(params.value) + ' 元（' + params.percent + '%）' },
        legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'center', itemWidth: 10, itemHeight: 10, textStyle: { color: '#606266', fontSize: 12 }},
        series: [
          {
            type: 'pie',
            radius: ['42%', '66%'],
            center: ['34%', '50%'],
            label: { show: false },
            labelLine: { show: false },
            itemStyle: { borderColor: '#fff', borderWidth: 2 },
            data: items
          }
        ]
      }
    },
    costOption() {
      const raw = this.data.cost_by_category.slice(0, 7).reverse()
      return {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: params => params[0].name + '：' + this.money(params[0].value) + ' 元' },
        grid: { left: 8, right: 56, top: 8, bottom: 4, containLabel: true },
        xAxis: {
          type: 'value',
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: '#f2f4f7' }},
          axisLabel: { color: '#909399', formatter: value => this.compact(value) }
        },
        yAxis: {
          type: 'category',
          data: raw.map(item => item.name),
          axisTick: { show: false },
          axisLine: { lineStyle: { color: '#e4e7ed' }},
          axisLabel: { color: '#606266' }
        },
        series: [
          {
            type: 'bar',
            barWidth: 13,
            itemStyle: { color: '#f0a020' },
            label: { show: true, position: 'right', color: '#909399', fontSize: 11, formatter: params => this.money(params.value) },
            data: raw.map(item => item.amount)
          }
        ]
      }
    }
  },
  created() {
    this.getData()
  },
  methods: {
    async getData() {
      this.loading = true
      try {
        const { data } = await fetchDashboardOverview()
        this.data = data
      } finally {
        this.loading = false
      }
    },
    goAccount(target, keyword) {
      const query = {}
      if (keyword) query.keyword = keyword
      if (target === 'progress') {
        this.$router.push({ path: '/account/progress', query })
        return
      }
      if (target === 'table') query.tab = 'table'
      this.$router.push({ path: '/account/index', query })
    },
    money(value) {
      const num = Number(value || 0)
      return num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
    },
    compact(value) {
      const num = Number(value || 0)
      if (Math.abs(num) >= 10000) return (num / 10000).toFixed(1) + '万'
      return String(num)
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return this.money(num)
    },
    clientWidth(revenue) {
      const max = this.topClients.reduce((prev, item) => Math.max(prev, Number(item.revenue || 0)), 0)
      if (!max) return '0%'
      return Math.max(6, (Number(revenue || 0) / max) * 100) + '%'
    },
    stepPercent(step) {
      const index = STEPS.indexOf(step)
      if (index < 0) return 0
      return Math.round((index / (STEPS.length - 1)) * 100)
    },
    progressColor(level) {
      if (level === 'danger') return '#f56c6c'
      if (level === 'warning') return '#e6a23c'
      return '#67c23a'
    },
    levelText(level) {
      return { danger: '风险', warning: '关注', normal: '正常' }[level] || '正常'
    },
    levelType(level) {
      return { danger: 'danger', warning: 'warning', normal: 'success' }[level] || 'info'
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
    margin-bottom: 16px;
  }

  .stat-card {
    background: #fff;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 16px;
    box-shadow: 0 1px 6px rgba(0, 21, 255, 0.06);
    border-left: 3px solid #dcdfe6;
  }

  .stat-label {
    color: #909399;
    font-size: 13px;
  }

  .stat-value {
    margin-top: 6px;
    font-size: 22px;
    font-weight: 600;
    line-height: 1.2;
    white-space: nowrap;

    &.revenue { color: #409eff; }
    &.cost { color: #f0a020; }
    &.profit { color: #67c23a; }
    &.total { color: #303133; }
    &.warn { color: #f56c6c; }
    &.month { color: #606266; }
  }

  .stat-foot {
    margin-top: 8px;
    font-size: 12px;
    color: #a8abb2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    .up { color: #f56c6c; margin-right: 6px; }
    .down { color: #67c23a; margin-right: 6px; }
  }

  .chart-row {
    .panel {
      margin-bottom: 16px;
    }
  }

  .panel {
    border-radius: 6px;
    margin-bottom: 16px;

    ::v-deep .el-card__header {
      padding: 14px 18px;
      border-bottom: 1px solid #f0f2f5;
    }

    ::v-deep .el-card__body {
      padding: 14px 18px 6px;
    }
  }

  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 600;
    color: #303133;
    font-size: 14px;
  }

  .panel-tip {
    font-weight: 400;
    font-size: 12px;
    color: #a8abb2;
  }

  .head-tags {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .client-list {
    padding-bottom: 8px;
  }

  .client-item {
    display: flex;
    align-items: flex-start;
    padding: 7px 0;
  }

  .rank {
    width: 18px;
    height: 18px;
    line-height: 18px;
    text-align: center;
    border-radius: 4px;
    font-size: 11px;
    color: #fff;
    background: #c0c4cc;
    margin-right: 10px;
    flex-shrink: 0;
    margin-top: 2px;

    &.rank-1 { background: #f56c6c; }
    &.rank-2 { background: #f0a020; }
    &.rank-3 { background: #409eff; }
  }

  .client-main {
    flex: 1;
    min-width: 0;
  }

  .client-top {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: #303133;
  }

  .client-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 130px;
  }

  .client-amount {
    color: #409eff;
    font-weight: 600;
  }

  .client-bar {
    height: 5px;
    background: #f5f7fa;
    border-radius: 3px;
    margin: 5px 0 4px;

    i {
      display: block;
      height: 5px;
      border-radius: 3px;
      background: linear-gradient(90deg, #79bbff, #409eff);
    }
  }

  .client-meta {
    font-size: 12px;
    color: #a8abb2;
  }

  .cell-main {
    color: #303133;
    font-size: 13px;
  }

  .cell-sub {
    color: #a8abb2;
    font-size: 12px;
    margin-top: 2px;
  }

  .blocked {
    margin-left: 6px;
    padding: 0 5px;
    font-size: 11px;
    color: #f56c6c;
    border: 1px solid #fbc4c4;
    border-radius: 3px;
  }

  .next-step {
    color: #409eff;
  }

  .todo-panel ::v-deep .el-progress {
    margin-top: 6px;
  }

  .empty {
    text-align: center;
    color: #a8abb2;
    font-size: 13px;
    padding: 60px 0;
  }
}
</style>
