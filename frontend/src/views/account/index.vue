<template>
  <div class="app-container account-page">
    <el-row :gutter="16" class="summary-row">
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">总收入{{ monthSuffix }}</div>
          <div class="summary-value revenue">￥{{ money(summary.revenue) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">订单成本{{ monthSuffix }}</div>
          <div class="summary-value cost">￥{{ money(summary.cost) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">订单毛利{{ monthSuffix }}</div>
          <div class="summary-value profit">￥{{ money(summary.profit) }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">待定笔数{{ monthSuffix }}</div>
          <div class="summary-value pending">{{ summary.pending }}</div>
        </div>
      </el-col>
    </el-row>

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
        size="small"
        @click="showAllMonths"
      >
        全部月份
      </el-button>
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
      <el-button
        class="filter-item"
        type="primary"
        icon="el-icon-plus"
        @click="handleCreate"
      >
        新增订单
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
    </div>

    <el-tabs v-model="activeView" class="account-tabs" @tab-click="handleTabClick">
      <el-tab-pane label="订单动态" name="chat">
        <div class="chat-panel">
          <div class="chat-title">订单动态 ({{ total }})</div>
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
                    <span class="chat-tags">
                      <el-tag :type="statusType(item.status)" size="mini">
                        {{ statusText(item.status) }}
                      </el-tag>
                      <el-tag v-if="item.license_count" size="mini" effect="plain" class="license-tag">
                        {{ item.license_count }} 个执照 · 完成 {{ item.done_count }}
                      </el-tag>
                    </span>
                    <span class="chat-ops">
                      <el-button type="text" size="mini" @click="handleDetail(item)">详情</el-button>
                      <el-button type="text" size="mini" @click="handleUpdate(item)">编辑</el-button>
                      <el-button type="text" size="mini" class="danger-text" @click="handleDelete(item)">删除</el-button>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="!list.length && !loading" class="chat-empty">
            <template v-if="filtering">
              当前筛选条件下没有订单
              <el-button type="text" @click="resetFilters">清除筛选条件</el-button>
            </template>
            <template v-else>
              还没有订单，点击「新增订单」开始录入
            </template>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="明细表格" name="table">
        <el-table
          v-loading="loading"
          :data="list"
          :empty-text="filtering ? '当前筛选条件下没有订单，试试切到「全部月份」' : '还没有订单'"
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
          <el-table-column label="操作" width="128" align="center" fixed="right">
            <template slot-scope="{ row }">
              <el-button type="text" size="mini" @click="handleDetail(row)">详情</el-button>
              <el-button type="text" size="mini" @click="handleUpdate(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="handleDelete(row)">删除</el-button>
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

    </el-tabs>

    <el-dialog
      :title="dialogType === 'edit' ? '编辑订单' : '新增订单'"
      :visible.sync="dialogVisible"
      width="1020px"
      top="5vh"
    >
      <el-form
        ref="accountForm"
        :model="form"
        :rules="rules"
        label-width="104px"
        class="order-form"
      >
        <div class="form-section-title">订单信息</div>
        <el-row :gutter="16">
          <el-col :span="8">
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
          <el-col :span="8">
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
          <el-col :span="8">
            <el-form-item label="来源平台" prop="platform">
              <el-select
                v-model="form.platform"
                style="width: 100%"
                clearable
                filterable
                placeholder="可不选"
              >
                <el-option v-for="item in platformOptions" :key="item" :label="item" :value="item" />
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
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" maxlength="11" placeholder="11 位手机号" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="2"
            placeholder="订单层面的补充说明，可不填"
          />
        </el-form-item>

        <div class="form-section-title">
          执照明细与任务
          <span class="optional-tip">一个客户可挂多个执照，每个执照单独一条任务、单独跟进度</span>
          <el-button class="add-detail-btn" type="primary" size="mini" icon="el-icon-plus" @click="addDetail">
            添加执照
          </el-button>
        </div>

        <div
          v-for="(detail, index) in form.details"
          :key="index"
          class="detail-card"
        >
          <div class="detail-card-head">
            <span class="detail-card-index">{{ index + 1 }}</span>
            <span class="detail-card-title">执照 {{ index + 1 }}</span>
            <span v-if="detail.license_name" class="detail-card-sub">{{ detail.license_name }}</span>
            <div class="detail-card-tools">
              <span class="tool-label">任务状态</span>
              <el-select v-model="detail.status" size="mini" class="status-select">
                <el-option label="待定" value="pending" />
                <el-option label="进行中" value="doing" />
                <el-option label="已完成" value="done" />
              </el-select>
              <el-button
                type="text"
                class="danger-text delete-btn"
                :disabled="form.details.length === 1"
                @click="removeDetail(index)"
              >
                删除
              </el-button>
            </div>
          </div>

          <div class="detail-card-body">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="执照名称">
                  <el-input v-model="detail.license_name" placeholder="营业执照上的名称" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item
                  label="统一信用编码"
                  :prop="'details.' + index + '.credit_code'"
                  :rules="detailRules.credit_code"
                >
                  <el-input
                    v-model="detail.credit_code"
                    maxlength="18"
                    placeholder="18 位统一社会信用代码"
                    clearable
                    @input="detail.credit_code = (detail.credit_code || '').toUpperCase()"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="法人姓名">
                  <el-input v-model="detail.legal_person" placeholder="法定代表人姓名" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item
                  label="法人身份证号"
                  :prop="'details.' + index + '.legal_id'"
                  :rules="detailRules.legal_id"
                >
                  <el-input
                    v-model="detail.legal_id"
                    maxlength="18"
                    placeholder="18 位身份证号"
                    clearable
                    @input="detail.legal_id = (detail.legal_id || '').toUpperCase()"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="工商状态">
                  <el-select v-model="detail.biz_status" style="width: 100%" clearable placeholder="可不选">
                    <el-option v-for="item in bizStatusOptions" :key="item" :label="item" :value="item" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="税务状态">
                  <el-select v-model="detail.tax_status" style="width: 100%" clearable placeholder="可不选">
                    <el-option v-for="item in taxStatusOptions" :key="item" :label="item" :value="item" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="24">
                <el-form-item label="业务项">
                  <el-select
                    :value="detail.item_list"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    popper-class="biz-item-dropdown"
                    style="width: 100%"
                    placeholder="从业务项配置里多选，也可直接输入新项"
                    @change="value => handleItemsChange(detail, value)"
                  >
                    <el-option
                      v-for="item in bizItemOptions"
                      :key="item.name"
                      :label="item.name"
                      :value="item.name"
                    >
                      <span class="option-name">{{ item.name }}</span>
                      <span v-if="item.unit_price" class="option-price">¥{{ formatMoney(item.unit_price) }}</span>
                    </el-option>
                  </el-select>
                  <div v-if="detail.item_list && detail.item_list.length > 1" class="items-preview">
                    组合后：{{ joinItems(detail.item_list) }}
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
            <div class="money-row">
              <span class="money-row-label">费用</span>
              <div class="money-panel">
                <div class="money-cell">
                  <span class="money-label">单价</span>
                  <el-input-number
                    v-model="detail.unit_price"
                    :controls="false"
                    :min="0"
                    :precision="2"
                    placeholder="0.00"
                  />
                </div>
                <div class="money-cell">
                  <span class="money-label">数量</span>
                  <el-input-number
                    v-model="detail.quantity"
                    :controls="false"
                    :min="1"
                    :precision="0"
                  />
                </div>
                <div class="money-cell">
                  <span class="money-label">收入</span>
                  <el-input-number
                    v-model="detail.revenue"
                    :controls="false"
                    :min="0"
                    :precision="2"
                    placeholder="0.00"
                  />
                </div>
                <div class="money-cell">
                  <span class="money-label">成本</span>
                  <el-input-number
                    v-model="detail.cost"
                    :controls="false"
                    :min="0"
                    :precision="2"
                    placeholder="0.00"
                  />
                </div>
                <div class="money-cell money-cell-profit">
                  <span class="money-label">利润</span>
                  <el-input-number
                    v-model="detail.profit"
                    :controls="false"
                    :min="0"
                    :precision="2"
                    placeholder="0.00"
                  />
                </div>
              </div>
            </div>
            <el-form-item label="备注">
              <el-input v-model="detail.remark" placeholder="这个执照的特殊说明，可不填" clearable />
            </el-form-item>
          </div>
        </div>

        <el-form-item label="消息预览">
          <div class="preview-bubble">{{ previewMessage }}</div>
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </div>
    </el-dialog>

    <order-detail-dialog :visible.sync="detailVisible" :row="detailRow" />
  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import OrderDetailDialog from './components/OrderDetailDialog'
import OrderItemsTable from './components/OrderItemsTable'
import {
  fetchAccountList,
  fetchAccountSummary,
  createAccount,
  updateAccount,
  deleteAccount
} from '@/api/account'
import { fetchPlatformList } from '@/api/platform'
import { fetchBizItemList } from '@/api/bizitem'
import { BIZ_STATUS_OPTIONS, TAX_STATUS_OPTIONS } from '@/constants/license'
import { splitItems, joinItems, formatMoney } from '@/constants/bizitem'
import refreshOnActivate from '@/mixins/refresh-on-activate'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

// 统一社会信用代码：18 位，数字与大写字母（不含 I O Z S V）
const CREDIT_CODE_RE = /^[0-9A-HJ-NPQRTUWXY]{18}$/
// 二代身份证：17 位数字 + 校验位（数字或 X）
const ID_CARD_RE = /^\d{17}[\dX]$/
// 手机号：11 位，1 开头
const PHONE_RE = /^1[3-9]\d{9}$/

// 选填字段：填了才校验格式，空着直接放过
function optionalPattern(pattern, message) {
  return (rule, value, callback) => {
    const text = String(value || '').trim()
    if (!text) return callback()
    if (!pattern.test(text)) return callback(new Error(message))
    return callback()
  }
}

export default {
  name: 'OrderList',
  components: { Pagination, OrderDetailDialog, OrderItemsTable },
  mixins: [refreshOnActivate],
  data() {
    const now = new Date()
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    return {
      activeView: 'chat',
      currentMonth,
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
      platformOptions: [],
      bizItemOptions: [],
      bizStatusOptions: BIZ_STATUS_OPTIONS,
      taxStatusOptions: TAX_STATUS_OPTIONS,
      listQuery: {
        page: 1,
        limit: 20,
        month: currentMonth,
        keyword: '',
        status: '',
        platform: '',
        biz_status: '',
        tax_status: ''
      },
      dialogVisible: false,
      dialogType: 'create',
      detailVisible: false,
      detailRow: null,
      form: this.emptyForm(),
      rules: {
        biz_date: [{ required: true, message: '请选择业务日期', trigger: 'change' }],
        category: [{ required: true, message: '请填写行业', trigger: 'change' }],
        client: [{ required: true, message: '请填写客户', trigger: 'blur' }],
        phone: [
          { validator: optionalPattern(PHONE_RE, '手机号为 11 位数字'), trigger: 'blur' }
        ]
      },
      detailRules: {
        credit_code: [
          { validator: optionalPattern(CREDIT_CODE_RE, '统一信用编码为 18 位数字或大写字母'), trigger: 'blur' }
        ],
        legal_id: [
          { validator: optionalPattern(ID_CARD_RE, '身份证号为 18 位，最后一位可为 X'), trigger: 'blur' }
        ]
      }
    }
  },
  computed: {
    previewMessage() {
      return this.buildMessage(this.form)
    },
    monthSuffix() {
      return this.listQuery.month ? `（${this.listQuery.month}）` : '（全部）'
    },
    filtering() {
      return Boolean(
        this.listQuery.month || this.listQuery.keyword || this.listQuery.status ||
        this.listQuery.platform || this.listQuery.biz_status || this.listQuery.tax_status
      )
    }
  },
  created() {
    const tab = this.$route.query.tab
    if (['chat', 'table'].indexOf(tab) > -1) {
      this.activeView = tab
    }
    const keyword = this.$route.query.keyword
    if (keyword) this.listQuery.keyword = keyword
    this.getList()
    this.getSummary()
    this.loadPlatforms()
    this.loadBizItems()
  },
  methods: {
    formatMoney,
    joinItems,
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新，保证看到最新数据
    refreshPage() {
      this.getList()
      this.getSummary()
      this.loadPlatforms()
      this.loadBizItems()
    },
    handleTabClick() {
      if (this.$route.query.tab !== this.activeView) {
        const query = { ...this.$route.query, tab: this.activeView }
        this.$router.replace({ query })
      }
    },
    async loadPlatforms() {
      try {
        const { data } = await fetchPlatformList()
        this.platformOptions = (data || []).map(item => item.name)
      } catch (error) {
        this.platformOptions = []
      }
    },
    // 业务项字典（只取启用的），订单里多选组合
    async loadBizItems() {
      try {
        const { data } = await fetchBizItemList()
        this.bizItemOptions = (data || []).filter(item => item.active !== false)
      } catch (error) {
        this.bizItemOptions = []
      }
    },
    itemsAutoSum(list) {
      return (list || []).reduce((total, name) => {
        const found = this.bizItemOptions.find(item => item.name === name)
        return total + Number((found && found.unit_price) || 0)
      }, 0)
    },
    // 选择业务项：拼成文本，并在「单价还没被手改」时按默认单价合计联动收入
    handleItemsChange(detail, list) {
      const selected = list || []
      detail.item_list = selected
      detail.items = joinItems(selected)
      const sum = this.itemsAutoSum(selected)
      const previous = Number(detail.__autoPrice || 0)
      const current = detail.unit_price === undefined || detail.unit_price === null || detail.unit_price === ''
        ? null
        : Number(detail.unit_price)
      const quantity = Number(detail.quantity || 1)
      const revenue = detail.revenue === undefined || detail.revenue === null || detail.revenue === ''
        ? null
        : Number(detail.revenue)
      if (current === null || current === previous) {
        detail.unit_price = sum || undefined
        if (revenue === null || revenue === Number((previous * quantity).toFixed(2))) {
          detail.revenue = sum && quantity ? Number((sum * quantity).toFixed(2)) : undefined
        }
      }
      detail.__autoPrice = sum
    },
    emptyDetail() {
      return {
        id: undefined,
        license_name: '',
        credit_code: '',
        legal_person: '',
        legal_id: '',
        biz_status: '',
        tax_status: '',
        items: '',
        item_list: [],
        __autoPrice: 0,
        unit_price: undefined,
        quantity: 1,
        revenue: undefined,
        cost: undefined,
        profit: undefined,
        status: 'pending',
        remark: ''
      }
    },
    emptyForm() {
      const now = new Date()
      const month = String(now.getMonth() + 1).padStart(2, '0')
      const day = String(now.getDate()).padStart(2, '0')
      return {
        id: undefined,
        biz_date: `${month}/${day}`,
        category: '',
        client: '',
        phone: '',
        platform: '',
        remark: '',
        details: [this.emptyDetail()]
      }
    },
    addDetail() {
      this.form.details.push(this.emptyDetail())
    },
    removeDetail(index) {
      if (this.form.details.length <= 1) return
      this.form.details.splice(index, 1)
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
      const params = {}
      if (this.listQuery.month) params.month = this.listQuery.month
      const { data } = await fetchAccountSummary(params)
      this.summary = data
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },
    showAllMonths() {
      this.listQuery.month = ''
      this.listQuery.page = 1
      this.getList()
      this.getSummary()
    },
    resetFilters() {
      this.listQuery.month = ''
      this.listQuery.keyword = ''
      this.listQuery.status = ''
      this.listQuery.platform = ''
      this.listQuery.biz_status = ''
      this.listQuery.tax_status = ''
      this.listQuery.page = 1
      this.getList()
      this.getSummary()
    },
    // 把 "09/03" / "2026-09-03" 统一成 "2026-09"，用于判断记录属于哪个月
    dateMonth(value) {
      const text = String(value || '').trim()
      if (!text) return ''
      const full = text.match(/^(\d{4})-(\d{1,2})/)
      if (full) return `${full[1]}-${String(full[2]).padStart(2, '0')}`
      const short = text.match(/^(\d{1,2})\D/)
      if (short) return `${new Date().getFullYear()}-${String(short[1]).padStart(2, '0')}`
      return ''
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
      const details = (row.details || []).map(item => Object.assign(this.emptyDetail(), {
        id: item.id,
        license_name: item.license_name,
        credit_code: item.credit_code,
        legal_person: item.legal_person,
        legal_id: item.legal_id,
        biz_status: item.biz_status,
        tax_status: item.tax_status,
        items: item.items,
        item_list: splitItems(item.items),
        __autoPrice: this.itemsAutoSum(splitItems(item.items)),
        unit_price: item.unit_price === null ? undefined : item.unit_price,
        quantity: item.quantity === null ? 1 : item.quantity,
        revenue: item.revenue === null ? undefined : item.revenue,
        cost: item.cost === null ? undefined : item.cost,
        profit: item.profit === null ? undefined : item.profit,
        status: item.status || 'pending',
        remark: item.remark
      }))
      this.form = {
        id: row.id,
        biz_date: row.biz_date,
        category: row.category,
        client: row.client,
        phone: row.phone,
        platform: row.platform,
        remark: row.remark,
        details: details.length ? details : [this.emptyDetail()]
      }
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.accountForm && this.$refs.accountForm.clearValidate()
      })
    },
    handleDetail(row) {
      this.detailRow = row
      this.detailVisible = true
    },
    handleDelete(row) {
      const suffix = row.license_count > 1 ? `（含 ${row.license_count} 个执照任务，进度一并删除）` : ''
      this.$confirm(`确认删除这条订单吗？${suffix}`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteAccount(row.id))
        .then(() => {
          this.$message({ message: '删除成功', type: 'success' })
          this.getList()
          this.getSummary()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.accountForm.validate(valid => {
        if (!valid) return false
        const details = this.form.details.map(detail => ({
          id: detail.id,
          license_name: (detail.license_name || '').trim(),
          credit_code: (detail.credit_code || '').toUpperCase(),
          legal_person: (detail.legal_person || '').trim(),
          legal_id: (detail.legal_id || '').toUpperCase(),
          biz_status: detail.biz_status || '',
          tax_status: detail.tax_status || '',
          items: joinItems(detail.item_list) || (detail.items || '').trim(),
          unit_price: this.numberOrNull(detail.unit_price),
          quantity: detail.quantity === undefined || detail.quantity === null || detail.quantity === ''
            ? 1
            : Number(detail.quantity),
          revenue: this.numberOrNull(detail.revenue),
          cost: this.numberOrNull(detail.cost),
          profit: this.numberOrNull(detail.profit),
          status: detail.status || 'pending',
          remark: (detail.remark || '').trim()
        }))
        const payload = {
          id: this.form.id,
          biz_date: this.form.biz_date,
          category: this.form.category,
          client: this.form.client,
          phone: this.form.phone || '',
          platform: this.form.platform || '',
          remark: this.form.remark,
          details
        }
        const request = this.dialogType === 'edit'
          ? updateAccount(payload)
          : createAccount(payload)
        this.saving = true
        request
          .then(() => {
            this.$message({
              message: this.dialogType === 'edit'
                ? '保存成功'
                : `订单录入成功，已按执照生成 ${details.length} 条任务`,
              type: 'success'
            })
            this.dialogVisible = false
            // 记录月份和当前筛选不一致时，自动切到该记录所在月份，
            // 避免「明明保存成功，列表里却看不到」
            const target = this.dateMonth(this.form.biz_date)
            if (target && this.listQuery.month && target !== this.listQuery.month) {
              this.listQuery.month = target
              this.$message({
                message: `该订单属于 ${target}，已自动切换到该月份`,
                type: 'info',
                duration: 4000
              })
            }
            this.listQuery.page = 1
            this.getList()
            this.getSummary()
          })
          .finally(() => {
            this.saving = false
          })
      })
    },
    buildMessage(form) {
      const details = form.details || []
      const items = details.map(item => (item.items || '').trim()).filter(Boolean)
      const lines = ['【订单】']
      const head = [form.biz_date, form.category].filter(Boolean).join(' ')
      if (head) lines.push(head)
      let subject = form.client || ''
      if (details.length <= 1 && items.length) subject += items[0]
      if (subject) lines.push(subject)
      if (details.length > 1) lines.push(`共 ${details.length} 个执照任务`)
      if (form.phone) lines.push('手机：' + form.phone)

      details.forEach((detail, index) => {
        const extras = []
        if (detail.biz_status) extras.push('工商：' + detail.biz_status)
        if (detail.tax_status) extras.push('税务：' + detail.tax_status)
        if (detail.items) extras.push('业务：' + detail.items)
        if (!detail.license_name && !extras.length) return
        const prefix = details.length > 1 ? `执照${index + 1}：` : '执照：'
        let line = prefix + (detail.license_name || '未填名称')
        if (extras.length) line += '（' + extras.join(' / ') + '）'
        lines.push(line)
      })

      const totalRevenue = this.sumRevenue(details, 'revenue')
      const totalCost = this.sumRevenue(details, 'cost')
      if (details.length === 1) {
        const single = details[0]
        const unitPrice = this.numberOrNull(single.unit_price)
        const quantity = Number(single.quantity || 1)
        const revenue = this.numberOrNull(single.revenue)
        const amount = revenue === null && unitPrice !== null ? unitPrice * quantity : revenue
        lines.push(`单价：${this.amount(unitPrice)}`)
        if (quantity && quantity !== 1) {
          lines.push(`数量：${this.amount(quantity)}`)
          lines.push(`金额：${this.amount(amount)}`)
        }
      }
      const profit = totalRevenue === null || totalCost === null ? null : totalRevenue - totalCost
      lines.push(`收入：${this.amount(totalRevenue)}`)
      lines.push(`成本：${this.amount(totalCost)}`)
      lines.push(`利润：${this.amount(profit)}`)
      if (form.remark) lines.push(`备注：${form.remark}`)
      return lines.join('\n')
    },
    // 明细金额合计：全空返回 null（显示「待定」），否则空值按 0 计
    sumRevenue(details, key) {
      const values = details
        .map(item => this.numberOrNull(item[key]))
        .filter(value => value !== null)
      if (!values.length) return null
      return values.reduce((sum, value) => sum + value, 0)
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
    completedText(stamp) {
      if (!stamp) return '—'
      const date = new Date(Number(stamp))
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
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
    width: 240px;
  }

  .filter-container .filter-item {
    margin-right: 8px;
    margin-bottom: 8px;
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
    max-width: 620px;
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

  .chat-tags .license-tag {
    margin-left: 6px;
  }

  .form-section-title {
    display: flex;
    align-items: center;
    margin: 4px 0 14px;
    padding-left: 8px;
    border-left: 3px solid #409eff;
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    line-height: 20px;

    &:not(:first-child) {
      margin-top: 18px;
    }

    .optional-tip {
      flex: 1;
      min-width: 0;
      margin-left: 8px;
      font-weight: 400;
      font-size: 12px;
      color: #909399;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .add-detail-btn {
      flex: none;
      margin-left: 12px;
    }
  }

  .detail-card {
    margin-bottom: 14px;
    border: 1px solid #e6ebf2;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
    transition: border-color 0.2s, box-shadow 0.2s;

    &:hover {
      border-color: #c6dcf5;
      box-shadow: 0 2px 12px rgba(64, 158, 255, 0.1);
    }
  }

  .detail-card-head {
    display: flex;
    align-items: center;
    height: 40px;
    padding: 0 14px;
    background: linear-gradient(180deg, #f7faff 0%, #f1f5fb 100%);
    border-bottom: 1px solid #e9eff7;

    .detail-card-index {
      flex: none;
      width: 20px;
      height: 20px;
      margin-right: 8px;
      border-radius: 50%;
      background: #409eff;
      color: #fff;
      font-size: 12px;
      font-weight: 600;
      line-height: 20px;
      text-align: center;
    }

    .detail-card-title {
      flex: none;
      font-size: 13px;
      font-weight: 600;
      color: #303133;
    }

    .detail-card-sub {
      max-width: 300px;
      margin-left: 8px;
      padding-left: 8px;
      border-left: 1px solid #dcdfe6;
      font-size: 12px;
      color: #909399;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .detail-card-tools {
      display: flex;
      align-items: center;
      margin-left: auto;

      .tool-label {
        margin-right: 6px;
        font-size: 12px;
        color: #909399;
      }

      .status-select {
        width: 96px;
      }

      .delete-btn {
        margin-left: 12px;
        padding: 0;
        font-size: 12px;
      }
    }
  }

  .detail-card-body {
    padding: 16px 16px 2px;

    /* 留够空间给校验错误提示（绝对定位在输入框下方 16px） */
    .el-form-item {
      margin-bottom: 20px;
    }
  }

  .money-row {
    display: flex;
    align-items: center;
    margin-bottom: 20px;

    .money-row-label {
      flex: none;
      width: 104px;
      padding-right: 12px;
      box-sizing: border-box;
      text-align: right;
      font-size: 14px;
      color: #606266;
    }

    .money-panel {
      display: flex;
      flex: 1;
      min-width: 0;
      padding: 10px 12px 12px;
      border: 1px solid #eef2f7;
      border-radius: 6px;
      background: #f8fafd;
    }

    .money-cell {
      flex: 1;
      min-width: 0;

      & + .money-cell {
        margin-left: 12px;
      }

      .money-label {
        display: block;
        margin-bottom: 6px;
        font-size: 12px;
        line-height: 16px;
        color: #909399;
      }

      .el-input-number {
        width: 100%;
      }

      /* 去掉 controls 后 element 仍留了给加减按钮的内边距，这里改回正常留白并左对齐 */
      ::v-deep .el-input__inner {
        padding: 0 10px;
        text-align: left;
      }
    }

    .money-cell-profit .money-label {
      color: #409eff;
      font-weight: 600;
    }
  }

  .chat-ops .el-button + .el-button {
    margin-left: 8px;
  }

  .danger-text {
    color: #f56c6c;
  }

  .muted-text {
    color: #c0c4cc;
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

  .items-preview {
    margin-top: 4px;
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }
}

.order-form {
  max-height: 68vh;
  overflow-y: auto;
  padding-right: 8px;
}
</style>

<style lang="scss">
/* 下拉挂在 body 上，scoped 样式够不到，用 popper-class 兜一层全局规则 */
.biz-item-dropdown .el-select-dropdown__item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.biz-item-dropdown .option-name {
  flex: 1;
}

.biz-item-dropdown .option-price {
  margin-left: 16px;
  color: #f56c6c;
  font-size: 13px;
}
</style>
