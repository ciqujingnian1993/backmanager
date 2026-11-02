<template>
  <div class="progress-panel">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">任务总数（按执照拆分）</div>
          <div class="stat-value">{{ summary.tasks }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">已完成任务</div>
          <div class="stat-value ok">{{ summary.done }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">缺进度</div>
          <div class="stat-value warn">{{ summary.missing }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">最近阶段分布</div>
          <div class="stat-steps">
            <el-tag
              v-for="item in summary.by_step.slice(0, 3)"
              :key="item.step"
              size="mini"
              class="step-tag"
              :type="stepTagType(item.step)"
            >
              {{ item.step }} {{ item.count }}
            </el-tag>
            <span v-if="!summary.by_step.length" class="stat-empty">暂无</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="filter-container">
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
        placeholder="任务状态"
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
      <el-button class="filter-item" icon="el-icon-refresh" @click="refresh">刷新</el-button>
      <span class="filter-tip">一个订单按执照拆成多条任务，每条任务单独跟进</span>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column label="订单" width="62" align="center">
        <template slot-scope="{ row }">#{{ row.account_id }}</template>
      </el-table-column>
      <el-table-column label="客户 / 执照" min-width="240" show-overflow-tooltip>
        <template slot-scope="{ row }">
          <div class="cell-main">{{ row.license_name || '未填执照' }}</div>
          <div class="cell-sub">{{ row.client || '—' }}<span v-if="row.items"> · {{ row.items }}</span></div>
        </template>
      </el-table-column>
      <el-table-column label="工商状态" width="88" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.biz_status" size="mini" :type="bizStatusType(row.biz_status)" effect="plain">
            {{ row.biz_status }}
          </el-tag>
          <span v-else class="muted-text">—</span>
        </template>
      </el-table-column>
      <el-table-column label="税务状态" width="92" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.tax_status" size="mini" :type="taxStatusType(row.tax_status)" effect="plain">
            {{ row.tax_status }}
          </el-tag>
          <span v-else class="muted-text">—</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="80" align="right">
        <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
      </el-table-column>
      <el-table-column label="当前进度" width="150" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.last_step" :type="progressTagType(row.last_step, row.last_status)" size="mini">
            {{ row.last_step }}
          </el-tag>
          <el-tag v-else type="info" size="mini">未跟进</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近更新" width="132">
        <template slot-scope="{ row }">{{ row.last_timestamp ? formatFull(row.last_timestamp) : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="102" align="center" fixed="right">
        <template slot-scope="{ row }">
          <el-button type="primary" size="mini" @click="openTimeline(row)">跟进记录</el-button>
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

    <el-dialog
      :title="dialogTitle"
      :visible.sync="dialogVisible"
      width="820px"
      top="5vh"
    >
      <div v-if="current" class="task-summary">
        <div class="task-cell"><span class="task-label">客户</span>{{ current.client || '—' }}</div>
        <div class="task-cell"><span class="task-label">手机号</span>{{ current.phone || '—' }}</div>
        <div class="task-cell"><span class="task-label">业务项</span>{{ current.items || '—' }}</div>
        <div class="task-cell"><span class="task-label">工商状态</span>{{ current.biz_status || '—' }}</div>
        <div class="task-cell"><span class="task-label">税务状态</span>{{ current.tax_status || '—' }}</div>
        <div class="task-cell"><span class="task-label">任务金额</span>{{ amount(current.revenue) }}</div>
      </div>

      <!-- 办理流程轨道：按这一单的业务项展示工商 / 税务节点，点节点可直接填进下方表单 -->
      <div v-if="current" class="flow-panel">
        <div class="flow-title">
          办理流程
          <span class="flow-tip">点节点可快速填入阶段；绿色为已完成，蓝色为最新进度</span>
        </div>
        <div v-for="group in orderedGroups" :key="group.key" class="flow-row">
          <div class="flow-head">
            <span class="flow-dot" :style="{ background: groupColor(group.key) }" />
            <span class="flow-label">{{ group.label }}</span>
            <span v-if="group.matched" class="flow-badge">本单适用</span>
            <span class="flow-count">{{ groupDoneCount(group) }}/{{ group.stages.length }}</span>
          </div>
          <div class="flow-stages">
            <span
              v-for="stage in group.stages"
              :key="stage"
              class="flow-chip"
              :class="{ 'is-done': doneStepSet.has(stage), 'is-current': currentStep === stage }"
              :title="stage"
              @click="pickStage(stage)"
            >{{ shortStage(stage) }}</span>
          </div>
        </div>
      </div>

      <div v-loading="timelineLoading" class="timeline-wrap">
        <div v-if="!timeline.length && !timelineLoading" class="timeline-empty">
          这条任务还没有进度记录，可以在下方补一条
        </div>
        <el-timeline v-else>
          <el-timeline-item
            v-for="item in timeline"
            :key="item.id"
            :timestamp="formatFull(item.timestamp)"
            placement="top"
            :color="dotColor(item.status)"
          >
            <div class="timeline-card">
              <div class="timeline-head">
                <span v-if="groupKeyOfStep(item.step) !== 'common'" class="group-badge" :class="'g-' + groupKeyOfStep(item.step)">
                  {{ groupLabel(item.step) }}
                </span>
                <span class="timeline-step">{{ shortStage(item.step) }}</span>
                <el-tag :type="tagType(item.status)" size="mini">{{ statusText(item.status) }}</el-tag>
                <span class="timeline-operator">{{ item.operator || '系统' }}</span>
                <el-button type="text" class="danger-text" @click="removeProgress(item)">删除</el-button>
              </div>
              <div v-if="item.note" class="timeline-note">{{ item.note }}</div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>

      <el-divider content-position="left">新增跟进</el-divider>
      <el-form ref="progressForm" :model="form" label-width="70px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="阶段" prop="step">
              <el-select
                v-model="form.step"
                style="width: 100%"
                filterable
                allow-create
                default-first-option
                placeholder="选择或输入阶段"
                @change="markStageTouched"
              >
                <el-option-group
                  v-for="group in orderedGroups"
                  :key="group.key"
                  :label="group.label + (group.matched ? '（本单适用）' : '')"
                >
                  <el-option
                    v-for="stage in group.stages"
                    :key="stage"
                    :label="stage"
                    :value="stage"
                  >
                    <span>{{ stage }}</span>
                    <span v-if="doneStepSet.has(stage)" class="opt-done">已完成</span>
                  </el-option>
                </el-option-group>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="待办" value="pending" />
                <el-option label="进行中" value="doing" />
                <el-option label="已完成" value="done" />
                <el-option label="受阻" value="blocked" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input
            v-model="form.note"
            type="textarea"
            :rows="2"
            placeholder="例如：客户已确认报价，等打款"
          />
        </el-form-item>
      </el-form>

      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="saving" @click="submitProgress">添加跟进</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import {
  fetchProgressOverview,
  fetchProgressList,
  fetchProgressSummary,
  createProgress,
  deleteProgress
} from '@/api/progress'
import { BIZ_STATUS_OPTIONS, TAX_STATUS_OPTIONS, bizStatusType, taxStatusType } from '@/constants/license'
import {
  STAGE_GROUPS,
  GROUP_META,
  groupKeyOfStep,
  shortStage,
  stepTagType,
  orderGroups,
  suggestStage
} from '@/constants/progress'
import refreshOnActivate from '@/mixins/refresh-on-activate'

const STATUS_MAP = {
  pending: '待办',
  doing: '进行中',
  done: '已完成',
  blocked: '受阻'
}

export default {
  name: 'ProgressTab',
  components: { Pagination },
  mixins: [refreshOnActivate],
  data() {
    return {
      loading: false,
      timelineLoading: false,
      saving: false,
      total: 0,
      list: [],
      steps: [],
      stageGroups: STAGE_GROUPS,
      bizStatusOptions: BIZ_STATUS_OPTIONS,
      taxStatusOptions: TAX_STATUS_OPTIONS,
      summary: { tasks: 0, done: 0, covered: 0, missing: 0, by_step: [] },
      listQuery: {
        page: 1,
        limit: 20,
        keyword: '',
        status: '',
        biz_status: '',
        tax_status: ''
      },
      dialogVisible: false,
      current: null,
      timeline: [],
      form: {
        step: '',
        status: 'doing',
        note: ''
      }
    }
  },
  computed: {
    dialogTitle() {
      if (!this.current) return '任务进度'
      const license = this.current.license_name || `订单 #${this.current.account_id}`
      return `任务进度 · ${this.current.client || '未命名客户'} · ${license}`
    },
    // 本单涉及工商/税务时，对应分组排到前面并打「本单适用」标记
    orderedGroups() {
      return orderGroups(this.stageGroups, this.current && this.current.items)
    },
    doneStepSet() {
      return new Set(this.timeline.filter(item => item.status === 'done').map(item => item.step))
    },
    currentStep() {
      return this.timeline.length ? this.timeline[this.timeline.length - 1].step : ''
    }
  },
  created() {
    this.__querySign = ''
    this.applyRouteQuery()
    this.refresh()
  },
  methods: {
    bizStatusType,
    taxStatusType,
    groupKeyOfStep,
    shortStage,
    stepTagType,
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新
    refreshPage() {
      this.applyRouteQuery()
      this.refresh()
    },
    // 首页「去跟进」穿透过来时带的关键字
    applyRouteQuery() {
      const q = this.$route.query || {}
      const sign = JSON.stringify(q)
      if (sign === this.__querySign) return false
      this.__querySign = sign
      if (!('keyword' in q) && !q.status) return false
      this.listQuery.keyword = q.keyword || ''
      this.listQuery.status = q.status || ''
      this.listQuery.page = 1
      return true
    },
    refresh() {
      this.getList()
      this.getSummary()
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchProgressOverview(this.listQuery)
        this.list = data.items || []
        this.total = data.total || 0
        if (data.steps && data.steps.length) this.steps = data.steps
        if (data.stage_groups && data.stage_groups.length) this.stageGroups = data.stage_groups
      } finally {
        this.loading = false
      }
    },
    async getSummary() {
      const { data } = await fetchProgressSummary()
      this.summary = data
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },
    openTimeline(row) {
      this.current = row
      this.form = { step: '', status: 'doing', note: '' }
      this.__stageTouched = false
      this.timeline = []
      this.dialogVisible = true
      this.loadTimeline(row.id)
    },
    async loadTimeline(itemId) {
      this.timelineLoading = true
      try {
        const { data } = await fetchProgressList(itemId)
        this.timeline = data.items || []
        if (data.steps && data.steps.length) this.steps = data.steps
        if (data.stage_groups && data.stage_groups.length) this.stageGroups = data.stage_groups
        if (data.item && this.current) {
          this.current = Object.assign({}, this.current, data.item)
        }
        // 还没动过阶段选择时，自动带出这条线上下一个该做的节点
        if (!this.__stageTouched) this.form.step = this.suggestNextStage()
      } finally {
        this.timelineLoading = false
      }
    },
    // 按业务项 + 已完成节点推荐下一步，例如解非单会推荐「税务 · 补申报」
    suggestNextStage() {
      const done = this.doneStepSet
      const stage = suggestStage(this.stageGroups, this.current && this.current.items, done)
      return stage || '已联系'
    },
    markStageTouched() {
      this.__stageTouched = true
    },
    pickStage(stage) {
      this.form.step = stage
      this.__stageTouched = true
    },
    groupDoneCount(group) {
      return (group.stages || []).filter(stage => this.doneStepSet.has(stage)).length
    },
    groupColor(key) {
      return (GROUP_META[key] || GROUP_META.common).color
    },
    groupLabel(step) {
      return (GROUP_META[groupKeyOfStep(step)] || GROUP_META.common).label
    },
    // 表格「当前进度」：已完成绿、受阻红，进行中沿用办理线颜色（工商蓝 / 税务橙）
    progressTagType(step, status) {
      if (status === 'done') return 'success'
      if (status === 'blocked') return 'danger'
      return stepTagType(step)
    },
    submitProgress() {
      if (!this.form.step) {
        this.$message.warning('请选择或填写阶段')
        return
      }
      this.saving = true
      createProgress({
        item_id: this.current.id,
        step: this.form.step,
        status: this.form.status,
        note: this.form.note
      })
        .then(() => {
          this.$message.success('已添加跟进')
          this.form.note = ''
          this.loadTimeline(this.current.id)
          this.refresh()
        })
        .finally(() => {
          this.saving = false
        })
    },
    removeProgress(item) {
      this.$confirm('确认删除这条跟进记录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteProgress({ id: item.id }))
        .then(() => {
          this.$message.success('已删除')
          this.loadTimeline(this.current.id)
          this.refresh()
        })
        .catch(() => {})
    },
    statusText(status) {
      return STATUS_MAP[status] || '进行中'
    },
    tagType(status) {
      return status === 'done' ? 'success' : status === 'blocked' ? 'danger' : status === 'pending' ? 'info' : 'warning'
    },
    dotColor(status) {
      return status === 'done' ? '#67c23a' : status === 'blocked' ? '#f56c6c' : '#409eff'
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    formatFull(timestamp) {
      if (!timestamp) return ''
      const date = new Date(timestamp)
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    }
  }
}
</script>

<style lang="scss" scoped>
.progress-panel {
  .stat-row {
    margin-bottom: 16px;
  }

  .stat-card {
    background: #f7f8fa;
    border-radius: 4px;
    padding: 12px 14px;
    min-height: 68px;
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

    &.ok { color: #67c23a; }
    &.warn { color: #e6a23c; }
  }

  .stat-steps {
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
  }

  .step-tag {
    margin: 0 6px 4px 0;
  }

  .stat-empty {
    color: #c0c4cc;
    font-size: 13px;
  }

  .keyword-input {
    width: 240px;
  }

  .filter-container .filter-item {
    margin-right: 8px;
    margin-bottom: 8px;
  }

  .filter-tip {
    color: #909399;
    font-size: 12px;
    margin-left: 8px;
  }

  .muted-text {
    color: #c0c4cc;
  }

  .cell-main {
    font-size: 13px;
    color: #303133;
    line-height: 20px;
  }

  .cell-sub {
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }

  .task-summary {
    display: flex;
    flex-wrap: wrap;
    background: #f7f8fa;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 12px;
    font-size: 13px;
    color: #303133;
  }

  .task-cell {
    width: 33.33%;
    padding: 3px 0;
  }

  .task-label {
    color: #909399;
    margin-right: 8px;
  }

  // 办理流程轨道
  .flow-panel {
    border: 1px solid #ebeef5;
    border-radius: 6px;
    padding: 10px 12px 4px;
    margin-bottom: 12px;
    background: #fff;
  }

  .flow-title {
    display: flex;
    align-items: baseline;
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 8px;
  }

  .flow-tip {
    margin-left: 8px;
    font-weight: 400;
    font-size: 12px;
    color: #909399;
  }

  .flow-row {
    margin-bottom: 8px;
  }

  .flow-head {
    display: flex;
    align-items: center;
    font-size: 12px;
    color: #606266;
    margin-bottom: 5px;
  }

  .flow-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 6px;
  }

  .flow-label {
    font-weight: 600;
  }

  .flow-badge {
    margin-left: 6px;
    padding: 0 5px;
    line-height: 16px;
    font-size: 11px;
    color: #409eff;
    background: #ecf5ff;
    border: 1px solid #b3d8ff;
    border-radius: 3px;
  }

  .flow-count {
    margin-left: auto;
    color: #909399;
  }

  .flow-stages {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .flow-chip {
    display: inline-flex;
    align-items: center;
    padding: 2px 9px;
    font-size: 12px;
    line-height: 18px;
    color: #606266;
    background: #f4f4f5;
    border: 1px solid #ebeef5;
    border-radius: 11px;
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      color: #409eff;
      border-color: #b3d8ff;
      background: #ecf5ff;
    }

    &.is-done {
      color: #529b2e;
      background: #f0f9eb;
      border-color: #c2e7b0;

      &::before {
        content: '✓';
        margin-right: 3px;
        font-size: 11px;
      }
    }

    &.is-current {
      color: #fff;
      background: #409eff;
      border-color: #409eff;
      box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.18);
    }
  }

  .opt-done {
    float: right;
    color: #67c23a;
    font-size: 12px;
  }

  .group-badge {
    padding: 0 5px;
    margin-right: 6px;
    font-size: 11px;
    line-height: 16px;
    border-radius: 3px;

    &.g-biz {
      color: #409eff;
      background: #ecf5ff;
      border: 1px solid #b3d8ff;
    }

    &.g-tax {
      color: #e6a23c;
      background: #fdf6ec;
      border: 1px solid #f5dab1;
    }
  }

  .timeline-wrap {
    max-height: 40vh;
    overflow-y: auto;
    padding: 4px 4px 0;
  }

  .timeline-empty {
    color: #909399;
    font-size: 13px;
    text-align: center;
    padding: 24px 0;
  }

  .timeline-card {
    background: #f7f8fa;
    border-radius: 4px;
    padding: 8px 12px;
  }

  .timeline-head {
    display: flex;
    align-items: center;

    .timeline-step {
      font-weight: 600;
      margin-right: 8px;
    }

    .el-tag {
      margin-right: 10px;
    }

    .timeline-operator {
      color: #909399;
      font-size: 12px;
      flex: 1;
    }
  }

  .timeline-note {
    margin-top: 6px;
    color: #606266;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-line;
  }

  .danger-text {
    color: #f56c6c;
  }
}
</style>
