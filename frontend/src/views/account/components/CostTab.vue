<template>
  <div class="cost-panel">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="24" :sm="8">
        <div class="stat-card">
          <div class="stat-label">累计支出</div>
          <div class="stat-value cost">￥{{ money(summary.total) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8">
        <div class="stat-card">
          <div class="stat-label">本月支出 {{ monthLabel }}</div>
          <div class="stat-value">￥{{ money(summary.month_total) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8">
        <div class="stat-card">
          <div class="stat-label">记录条数 / 分类</div>
          <div class="stat-value">{{ summary.count }} <span class="stat-sub">/ {{ summary.by_category.length }} 类</span></div>
        </div>
      </el-col>
    </el-row>

    <div v-if="summary.by_category.length" class="category-bar">
      <el-tag
        v-for="item in summary.by_category"
        :key="item.category"
        size="small"
        class="category-tag"
        effect="plain"
      >
        {{ item.category }} ￥{{ money(item.amount) }} · {{ item.count }}笔
      </el-tag>
    </div>

    <div class="filter-container">
      <el-date-picker
        v-model="listQuery.month"
        class="filter-item"
        type="month"
        placeholder="按月份筛选"
        format="yyyy-MM"
        value-format="yyyy-MM"
        clearable
        @change="handleFilter"
      />
      <el-select
        v-model="listQuery.category"
        class="filter-item"
        placeholder="成本类别"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in categories" :key="item" :label="item" :value="item" />
      </el-select>
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索收款方 / 备注"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-button class="filter-item" type="primary" icon="el-icon-plus" @click="handleCreate">
        记一笔支出
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="refresh">刷新</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column prop="biz_date" label="发生日期" width="120" align="center" />
      <el-table-column label="类别" width="100" align="center">
        <template slot-scope="{ row }">
          <el-tag size="mini" :type="categoryType(row.category)">{{ row.category || '未分类' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="payee" label="收款方" min-width="140" />
      <el-table-column label="金额" width="120" align="right">
        <template slot-scope="{ row }">
          <span class="amount-text">￥{{ money(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="method" label="支付方式" width="100" align="center" />
      <el-table-column label="关联订单" width="100" align="center">
        <template slot-scope="{ row }">
          <span v-if="row.related_order">#{{ row.related_order }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="150" />
      <el-table-column prop="creator" label="记录人" width="100" align="center" />
      <el-table-column label="操作" width="170" align="center">
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

    <el-dialog
      :title="dialogType === 'edit' ? '编辑成本记录' : '记一笔支出'"
      :visible.sync="dialogVisible"
      width="620px"
    >
      <el-form ref="costForm" :model="form" :rules="rules" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="发生日期" prop="biz_date">
              <el-date-picker
                v-model="form.biz_date"
                style="width: 100%"
                type="date"
                format="yyyy-MM-dd"
                value-format="yyyy-MM-dd"
                placeholder="选择日期"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类别" prop="category">
              <el-select
                v-model="form.category"
                style="width: 100%"
                filterable
                allow-create
                default-first-option
                placeholder="选择或输入类别"
              >
                <el-option v-for="item in categories" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="金额" prop="amount">
              <el-input-number
                v-model="form.amount"
                style="width: 100%"
                :min="0"
                :precision="2"
                :step="100"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="收款方">
              <el-input v-model="form.payee" placeholder="例如 文具批发 / 房东" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="支付方式">
              <el-select v-model="form.method" style="width: 100%" clearable placeholder="选择支付方式">
                <el-option v-for="item in methods" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联订单">
              <el-select
                v-model="form.related_order"
                style="width: 100%"
                clearable
                filterable
                placeholder="可不选"
              >
                <el-option
                  v-for="item in orders"
                  :key="item.id"
                  :label="`#${item.id} ${item.client || ''} ${item.items || ''}`"
                  :value="item.id"
                />
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
import { fetchCostList, fetchCostSummary, createCost, updateCost, deleteCost } from '@/api/cost'
import { fetchAccountList } from '@/api/account'

const METHOD_OPTIONS = ['微信', '支付宝', '银行转账', '现金', '其他']

export default {
  name: 'CostTab',
  components: { Pagination },
  data() {
    const now = new Date()
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    return {
      loading: false,
      saving: false,
      total: 0,
      list: [],
      orders: [],
      categories: [],
      methods: METHOD_OPTIONS,
      summary: { total: 0, count: 0, month_total: 0, month_count: 0, by_category: [] },
      month: currentMonth,
      defaultMonth: currentMonth,
      listQuery: {
        page: 1,
        limit: 20,
        month: '',
        category: '',
        keyword: ''
      },
      dialogVisible: false,
      dialogType: 'create',
      form: this.emptyForm(),
      rules: {
        biz_date: [{ required: true, message: '请选择发生日期', trigger: 'change' }],
        category: [{ required: true, message: '请选择成本类别', trigger: 'change' }],
        amount: [{ required: true, message: '请填写金额', trigger: 'blur' }]
      }
    }
  },
  computed: {
    monthLabel() {
      return this.month ? this.month.replace('-', '年') + '月' : ''
    }
  },
  created() {
    this.getSummary()
    this.getList()
    this.loadOrders()
  },
  methods: {
    emptyForm() {
      const now = new Date()
      const pad = v => String(v).padStart(2, '0')
      return {
        id: undefined,
        biz_date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
        category: '',
        payee: '',
        amount: undefined,
        method: '',
        related_order: undefined,
        remark: ''
      }
    },
    refresh() {
      this.getList()
      this.getSummary()
    },
    async getList() {
      this.loading = true
      try {
        const params = {
          page: this.listQuery.page,
          limit: this.listQuery.limit,
          category: this.listQuery.category,
          keyword: this.listQuery.keyword
        }
        if (this.listQuery.month) {
          params.start = `${this.listQuery.month}-01`
          params.end = `${this.listQuery.month}-31`
        }
        const { data } = await fetchCostList(params)
        this.list = data.items || []
        this.total = data.total || 0
        if (data.categories && data.categories.length) this.categories = data.categories
      } finally {
        this.loading = false
      }
    },
    async getSummary() {
      const params = {}
      if (this.month) params.month = this.month
      const { data } = await fetchCostSummary(params)
      this.summary = data
      if (data.categories && data.categories.length) this.categories = data.categories
    },
    async loadOrders() {
      const { data } = await fetchAccountList({ page: 1, limit: 100 })
      this.orders = data.items || []
    },
    handleFilter() {
      this.listQuery.page = 1
      this.month = this.listQuery.month || this.defaultMonth
      this.refresh()
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.costForm && this.$refs.costForm.clearValidate()
      })
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = Object.assign(this.emptyForm(), row)
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.costForm && this.$refs.costForm.clearValidate()
      })
    },
    handleDelete(row) {
      this.$confirm(`确认删除「${row.category || '该'} ￥${this.money(row.amount)}」这条成本记录吗？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteCost({ id: row.id }))
        .then(() => {
          this.$message.success('删除成功')
          this.refresh()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.costForm.validate(valid => {
        if (!valid) return false
        const payload = {
          id: this.form.id,
          biz_date: this.form.biz_date,
          category: this.form.category,
          payee: this.form.payee,
          amount: this.form.amount === undefined ? 0 : this.form.amount,
          method: this.form.method,
          related_order: this.form.related_order || null,
          remark: this.form.remark
        }
        const request = this.dialogType === 'edit' ? updateCost(payload) : createCost(payload)
        this.saving = true
        request
          .then(() => {
            this.$message.success(this.dialogType === 'edit' ? '保存成功' : '记录成功')
            this.dialogVisible = false
            this.refresh()
          })
          .finally(() => {
            this.saving = false
          })
      })
    },
    money(value) {
      const num = Number(value || 0)
      return num === Math.trunc(num) ? String(Math.trunc(num)) : num.toFixed(2)
    },
    categoryType(category) {
      const map = {
        采购: 'warning',
        物流: '',
        人工: 'success',
        房租: 'danger',
        水电: 'info',
        推广: 'warning',
        差旅: '',
        办公: 'info'
      }
      return map[category] || ''
    }
  }
}
</script>

<style lang="scss" scoped>
.cost-panel {
  .stat-row {
    margin-bottom: 12px;
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

    &.cost { color: #e6a23c; }
  }

  .stat-sub {
    font-size: 13px;
    font-weight: 400;
    color: #909399;
  }

  .category-bar {
    margin-bottom: 14px;
  }

  .category-tag {
    margin: 0 8px 8px 0;
  }

  .keyword-input {
    width: 200px;
  }

  .amount-text {
    color: #e6a23c;
    font-weight: 600;
  }

  .muted {
    color: #c0c4cc;
  }
}
</style>
