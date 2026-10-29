<template>
  <div class="app-container account-page">
    <el-row :gutter="16" class="summary-row">
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">总收入</div>
          <div class="summary-value revenue">￥{{ money(summary.revenue) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">总成本</div>
          <div class="summary-value cost">￥{{ money(summary.cost) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">总利润</div>
          <div class="summary-value profit">￥{{ money(summary.profit) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">待定笔数</div>
          <div class="summary-value pending">{{ summary.pending }}</div>
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
        placeholder="状态"
        clearable
        @change="handleFilter"
      >
        <el-option label="待定" value="pending" />
        <el-option label="进行中" value="doing" />
        <el-option label="已完成" value="done" />
      </el-select>
      <el-button
        class="filter-item"
        type="primary"
        icon="el-icon-plus"
        @click="handleCreate"
      >
        记一笔
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
    </div>

    <el-tabs v-model="activeView" class="account-tabs" @tab-click="handleTabClick">
      <el-tab-pane label="记账群" name="chat">
        <div class="chat-panel">
          <div class="chat-title">记账群 ({{ total }})</div>
          <div v-for="item in list" :key="item.id" class="chat-item">
            <div class="chat-time">{{ formatTime(item.timestamp) }}</div>
            <div class="chat-row">
              <div class="chat-avatar">
                <svg-icon icon-class="money" />
              </div>
              <div class="chat-body">
                <div class="chat-bubble">
                  <div class="chat-text">{{ item.message }}</div>
                  <div class="chat-meta">
                    <el-tag :type="statusType(item.status)" size="mini">
                      {{ statusText(item.status) }}
                    </el-tag>
                    <span class="chat-ops">
                      <el-button type="text" size="mini" @click="handleUpdate(item)">编辑</el-button>
                      <el-button type="text" size="mini" class="danger-text" @click="handleDelete(item)">删除</el-button>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="!list.length && !loading" class="chat-empty">
            还没有记账记录，点击「记一笔」开始记账
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="明细表格" name="table">
        <el-table
          v-loading="loading"
          :data="list"
          border
          fit
          highlight-current-row
          style="width: 100%"
        >
          <el-table-column prop="biz_date" label="日期" width="100" align="center" />
          <el-table-column prop="category" label="行业" width="120" align="center" />
          <el-table-column prop="client" label="客户" min-width="140" />
          <el-table-column prop="items" label="业务项" min-width="140" />
          <el-table-column label="单价" width="100" align="center">
            <template slot-scope="{ row }">{{ amount(row.unit_price) }}</template>
          </el-table-column>
          <el-table-column label="数量" width="80" align="center">
            <template slot-scope="{ row }">{{ row.quantity }}</template>
          </el-table-column>
          <el-table-column label="收入" width="110" align="center">
            <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
          </el-table-column>
          <el-table-column label="成本" width="110" align="center">
            <template slot-scope="{ row }">{{ amount(row.cost) }}</template>
          </el-table-column>
          <el-table-column label="利润" width="110" align="center">
            <template slot-scope="{ row }">{{ amount(row.profit) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template slot-scope="{ row }">
              <el-tag :type="statusType(row.status)" size="mini">
                {{ statusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="140" />
          <el-table-column label="操作" width="140" align="center">
            <template slot-scope="{ row }">
              <el-button type="primary" size="mini" @click="handleUpdate(row)">编辑</el-button>
              <el-button type="danger" size="mini" @click="handleDelete(row)">删除</el-button>
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
      </el-tab-pane>

      <el-tab-pane label="进度跟进" name="progress" lazy>
        <progress-tab ref="progressTab" />
      </el-tab-pane>

      <el-tab-pane label="成本记录" name="cost" lazy>
        <cost-tab ref="costTab" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      :title="dialogType === 'edit' ? '编辑记账' : '记一笔'"
      :visible.sync="dialogVisible"
      width="640px"
    >
      <el-form
        ref="accountForm"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="业务日期" prop="biz_date">
              <el-date-picker
                v-model="form.biz_date"
                style="width: 100%"
                type="date"
                format="MM/dd"
                value-format="MM/dd"
                placeholder="选择日期"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="行业" prop="category">
              <el-select
                v-model="form.category"
                style="width: 100%"
                allow-create
                filterable
                default-first-option
                placeholder="选择或输入行业"
              >
                <el-option
                  v-for="item in categoryOptions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="客户" prop="client">
              <el-input v-model="form.client" placeholder="例如 厦门个体户" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务项" prop="items">
              <el-input v-model="form.items" placeholder="例如 非+注销" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="单价">
              <el-input-number
                v-model="form.unit_price"
                style="width: 100%"
                :min="0"
                :precision="2"
                :step="50"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="数量">
              <el-input-number
                v-model="form.quantity"
                style="width: 100%"
                :min="1"
                :precision="0"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="收入">
              <el-input-number
                v-model="form.revenue"
                style="width: 100%"
                :min="0"
                :precision="2"
                :step="50"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="成本">
              <el-input-number
                v-model="form.cost"
                style="width: 100%"
                :min="0"
                :precision="2"
                :step="50"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="利润">
              <el-input-number
                v-model="form.profit"
                style="width: 100%"
                :min="0"
                :precision="2"
                :step="50"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="待定" value="pending" />
                <el-option label="进行中" value="doing" />
                <el-option label="已完成" value="done" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="2"
            placeholder="补充说明，可不填"
          />
        </el-form-item>

        <el-form-item label="群消息预览">
          <div class="preview-bubble">{{ previewMessage }}</div>
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import ProgressTab from './components/ProgressTab'
import CostTab from './components/CostTab'
import {
  fetchAccountList,
  fetchAccountSummary,
  createAccount,
  updateAccount,
  deleteAccount
} from '@/api/account'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

export default {
  name: 'AccountIndex',
  components: { Pagination, ProgressTab, CostTab },
  data() {
    return {
      activeView: 'chat',
      loading: false,
      saving: false,
      total: 0,
      list: [],
      summary: {
        count: 0,
        revenue: 0,
        cost: 0,
        profit: 0,
        pending: 0
      },
      categoryOptions: ['同行业', '代理记账', '工商注册', '变更注销'],
      listQuery: {
        page: 1,
        limit: 20,
        keyword: '',
        status: ''
      },
      dialogVisible: false,
      dialogType: 'create',
      form: this.emptyForm(),
      rules: {
        biz_date: [{ required: true, message: '请选择业务日期', trigger: 'change' }],
        category: [{ required: true, message: '请填写行业', trigger: 'change' }],
        client: [{ required: true, message: '请填写客户', trigger: 'blur' }]
      }
    }
  },
  computed: {
    previewMessage() {
      return this.buildMessage(this.form)
    }
  },
  created() {
    this.getList()
    this.getSummary()
  },
  methods: {
    emptyForm() {
      const now = new Date()
      const month = String(now.getMonth() + 1).padStart(2, '0')
      const day = String(now.getDate()).padStart(2, '0')
      return {
        id: undefined,
        biz_date: `${month}/${day}`,
        category: '',
        client: '',
        items: '',
        unit_price: undefined,
        quantity: 1,
        revenue: undefined,
        cost: undefined,
        profit: undefined,
        status: 'pending',
        remark: ''
      }
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
    async getSummary() {
      const { data } = await fetchAccountSummary()
      this.summary = data
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },
    handleTabClick(tab) {
      if (tab.name === 'progress' && this.$refs.progressTab) {
        this.$refs.progressTab.refresh()
      }
      if (tab.name === 'cost' && this.$refs.costTab) {
        this.$refs.costTab.refresh()
      }
    },
    refreshRelatedTabs() {
      if (this.$refs.progressTab) this.$refs.progressTab.refresh()
      if (this.$refs.costTab) this.$refs.costTab.refresh()
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.accountForm && this.$refs.accountForm.clearValidate()
      })
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = Object.assign(this.emptyForm(), row)
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.accountForm && this.$refs.accountForm.clearValidate()
      })
    },
    handleDelete(row) {
      this.$confirm('确认删除这条记账记录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteAccount(row.id))
        .then(() => {
          this.$message({ message: '删除成功', type: 'success' })
          this.getList()
          this.getSummary()
          this.refreshRelatedTabs()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.accountForm.validate(valid => {
        if (!valid) return false
        const payload = {
          id: this.form.id,
          biz_date: this.form.biz_date,
          category: this.form.category,
          client: this.form.client,
          items: this.form.items,
          unit_price: this.form.unit_price === undefined ? null : this.form.unit_price,
          quantity: this.form.quantity === undefined ? 1 : this.form.quantity,
          revenue: this.form.revenue === undefined ? null : this.form.revenue,
          cost: this.form.cost === undefined ? null : this.form.cost,
          profit: this.form.profit === undefined ? null : this.form.profit,
          status: this.form.status,
          remark: this.form.remark
        }
        const request = this.dialogType === 'edit'
          ? updateAccount(payload)
          : createAccount(payload)
        this.saving = true
        request
          .then(() => {
            this.$message({
              message: this.dialogType === 'edit' ? '保存成功' : '记账成功',
              type: 'success'
            })
            this.dialogVisible = false
            this.getList()
            this.getSummary()
            this.refreshRelatedTabs()
          })
          .finally(() => {
            this.saving = false
          })
      })
    },
    buildMessage(form) {
      const lines = ['【订单】']
      const head = [form.biz_date, form.category].filter(Boolean).join(' ')
      if (head) lines.push(head)
      const subject = [form.client, form.items].filter(Boolean).join('')
      if (subject) lines.push(subject)

      const unitPrice = this.numberOrNull(form.unit_price)
      const quantity = form.quantity === undefined || form.quantity === null || form.quantity === ''
        ? 1
        : Number(form.quantity)
      const revenue = this.numberOrNull(form.revenue)
      const cost = this.numberOrNull(form.cost)
      const amount = revenue === null && unitPrice !== null ? unitPrice * (quantity || 1) : revenue
      let profit = this.numberOrNull(form.profit)
      if (profit === null && amount !== null && cost !== null) {
        profit = amount - cost
      }

      lines.push(`单价：${this.amount(unitPrice)}`)
      if (quantity && quantity !== 1) {
        lines.push(`数量：${this.amount(quantity)}`)
        lines.push(`金额：${this.amount(amount)}`)
      }
      lines.push(`成本：${this.amount(cost)}`)
      lines.push(`利润：${this.amount(profit)}`)
      if (form.remark) lines.push(`备注：${form.remark}`)
      return lines.join('\n')
    },
    numberOrNull(value) {
      if (value === null || value === undefined || value === '') return null
      const num = Number(value)
      return Number.isNaN(num) ? null : num
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    money(value) {
      const num = Number(value || 0)
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    statusText(status) {
      return STATUS_MAP[status] || '待定'
    },
    statusType(status) {
      return status === 'done' ? 'success' : status === 'doing' ? 'warning' : 'info'
    },
    formatTime(timestamp) {
      if (!timestamp) return ''
      const date = new Date(timestamp)
      const now = new Date()
      const pad = v => String(v).padStart(2, '0')
      const hm = `${pad(date.getHours())}:${pad(date.getMinutes())}`
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
      const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
      const diffDays = Math.round((todayStart - dayStart) / 864e5)
      if (diffDays === 0) return hm
      if (diffDays === 1) return `昨天 ${hm}`
      return `${date.getMonth() + 1}月${date.getDate()}日 ${hm}`
    }
  }
}
</script>

<style lang="scss" scoped>
.account-page {
  .summary-row {
    margin-bottom: 18px;
  }

  .summary-card {
    background: #fff;
    border-radius: 4px;
    padding: 16px 18px;
    box-shadow: 0 1px 4px rgba(0, 21, 255, 0.08);
  }

  .summary-label {
    color: #909399;
    font-size: 13px;
  }

  .summary-value {
    margin-top: 6px;
    font-size: 22px;
    font-weight: 600;

    &.revenue { color: #67c23a; }
    &.cost { color: #e6a23c; }
    &.profit { color: #409eff; }
    &.pending { color: #f56c6c; }
  }

  .keyword-input {
    width: 260px;
  }

  .account-tabs {
    margin-top: 6px;
  }

  .chat-panel {
    background: #f5f5f5;
    border-radius: 4px;
    padding: 18px 16px;
    min-height: 320px;
  }

  .chat-title {
    font-size: 15px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 16px;
  }

  .chat-item {
    margin-bottom: 18px;
  }

  .chat-time {
    text-align: center;
    color: #9a9a9a;
    font-size: 12px;
    margin-bottom: 10px;
  }

  .chat-row {
    display: flex;
    align-items: flex-start;
  }

  .chat-avatar {
    flex: 0 0 36px;
    width: 36px;
    height: 36px;
    border-radius: 4px;
    background: #dcdfe6;
    color: #909399;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .chat-body {
    margin-left: 10px;
    max-width: 560px;
  }

  .chat-bubble {
    background: #fff;
    border-radius: 6px;
    padding: 10px 12px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  }

  .chat-text {
    white-space: pre-line;
    line-height: 1.7;
    font-size: 14px;
    color: #303133;
  }

  .chat-meta {
    margin-top: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .chat-ops .el-button + .el-button {
    margin-left: 8px;
  }

  .danger-text {
    color: #f56c6c;
  }

  .chat-empty {
    text-align: center;
    color: #909399;
    font-size: 13px;
    padding: 40px 0;
  }

  .preview-bubble {
    background: #f5f5f5;
    border-radius: 6px;
    padding: 10px 12px;
    white-space: pre-line;
    line-height: 1.7;
    font-size: 14px;
    color: #303133;
    width: 100%;
  }
}
</style>
