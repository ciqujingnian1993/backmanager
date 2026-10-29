<template>
  <div class="progress-panel">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">订单总数</div>
          <div class="stat-value">{{ summary.orders }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">有待跟进记录</div>
          <div class="stat-value ok">{{ summary.covered }}</div>
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
        placeholder="搜索客户 / 业务项 / 备注"
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
      <el-button class="filter-item" icon="el-icon-refresh" @click="refresh">刷新</el-button>
      <span class="filter-tip">订单录入时会自动生成一条「已录入」进度</span>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column label="单号" width="80" align="center">
        <template slot-scope="{ row }">#{{ row.id }}</template>
      </el-table-column>
      <el-table-column prop="biz_date" label="日期" width="90" align="center" />
      <el-table-column prop="client" label="客户" min-width="130" />
      <el-table-column prop="items" label="业务项" min-width="130" />
      <el-table-column label="金额" width="110" align="right">
        <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
      </el-table-column>
      <el-table-column label="当前进度" width="120" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.last_step" :type="tagType(row.last_status)" size="mini">
            {{ row.last_step }}
          </el-tag>
          <el-tag v-else type="info" size="mini">未跟进</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近更新" width="160">
        <template slot-scope="{ row }">{{ row.last_timestamp ? formatFull(row.last_timestamp) : '—' }}</template>
      </el-table-column>
      <el-table-column label="跟进" width="80" align="center">
        <template slot-scope="{ row }">{{ row.progress_count }} 条</template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
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
      :title="current ? `订单进度 · ${current.client || '未命名客户'} #${current.id}` : '订单进度'"
      :visible.sync="dialogVisible"
      width="700px"
      top="6vh"
    >
      <div v-loading="timelineLoading" class="timeline-wrap">
        <div v-if="!timeline.length && !timelineLoading" class="timeline-empty">
          这个订单还没有进度记录，可以在下方补一条
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
                <span class="timeline-step">{{ item.step }}</span>
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
              >
                <el-option v-for="item in steps" :key="item" :label="item" :value="item" />
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

const STATUS_MAP = {
  pending: '待办',
  doing: '进行中',
  done: '已完成',
  blocked: '受阻'
}

export default {
  name: 'ProgressTab',
  components: { Pagination },
  data() {
    return {
      loading: false,
      timelineLoading: false,
      saving: false,
      total: 0,
      list: [],
      steps: [],
      summary: { orders: 0, covered: 0, missing: 0, by_step: [] },
      listQuery: {
        page: 1,
        limit: 20,
        keyword: '',
        status: ''
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
  created() {
    this.refresh()
  },
  methods: {
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
      this.form = { step: row.last_step || this.steps[1] || '已联系', status: 'doing', note: '' }
      this.dialogVisible = true
      this.loadTimeline(row.id)
    },
    async loadTimeline(accountId) {
      this.timelineLoading = true
      try {
        const { data } = await fetchProgressList(accountId)
        this.timeline = data.items || []
        if (data.steps && data.steps.length) this.steps = data.steps
      } finally {
        this.timelineLoading = false
      }
    },
    submitProgress() {
      if (!this.form.step) {
        this.$message.warning('请选择或填写阶段')
        return
      }
      this.saving = true
      createProgress({
        account_id: this.current.id,
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

  .filter-tip {
    color: #909399;
    font-size: 12px;
    margin-left: 8px;
  }

  .timeline-wrap {
    max-height: 46vh;
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
