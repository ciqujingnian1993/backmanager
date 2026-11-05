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

    <div class="table-panel">
      <div class="panel-head">
        <span class="panel-title">订单列表</span>
        <span class="panel-count">共 {{ total }} 单</span>
      </div>
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
    </div>

    <el-dialog
      :title="dialogTitle"
      :visible.sync="dialogVisible"
      width="1120px"
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
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="平台订单编号">
              <el-input
                v-model="form.platform_order_no"
                class="platform-order-no-input"
                maxlength="64"
                clearable
                placeholder="平台后台的订单号，可不填"
              />
            </el-form-item>
          </el-col>
        </el-row>

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
          :class="{ 'is-collapsed': detail.__collapsed }"
        >
          <div class="detail-card-head">
            <i
              class="collapse-btn"
              :class="detail.__collapsed ? 'el-icon-arrow-right' : 'el-icon-arrow-down'"
              @click="toggleDetail(detail)"
            />
            <span class="detail-card-index">{{ index + 1 }}</span>
            <span class="detail-card-title">执照 {{ index + 1 }}</span>
            <span v-if="detail.license_name" class="detail-card-sub">{{ detail.license_name }}</span>
            <span v-if="detail.__collapsed" class="detail-card-sum">
              <span v-if="detail.items" class="sum-item">{{ detail.items }}</span>
              <span v-if="detail.revenue" class="sum-item">收入 ¥{{ formatMoney(detail.revenue) }}</span>
              <span v-if="!detail.items && !detail.revenue" class="sum-empty">未填写业务项</span>
            </span>
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

          <div v-show="!detail.__collapsed" class="detail-card-body">
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
              <el-col :span="8">
                <el-form-item label="法人姓名">
                  <el-input v-model="detail.legal_person" placeholder="法定代表人姓名" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="8">
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
              <el-col :span="8">
                <el-form-item
                  label="法人手机号"
                  :prop="'details.' + index + '.legal_phone'"
                  :rules="detailRules.legal_phone"
                >
                  <el-input
                    v-model="detail.legal_phone"
                    placeholder="11 位手机号"
                    clearable
                    @input="detail.legal_phone = normalizePhone(detail.legal_phone)"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="16">
                <el-form-item label="工商状态">
                  <!-- 注意：el-checkbox-group 的 change 回传的是未更新的旧值，这里必须用 input -->
                  <el-checkbox-group
                    :value="splitBizStatus(detail.biz_status)"
                    class="biz-status-group"
                    @input="values => setBizStatus(detail, values)"
                  >
                    <el-checkbox v-for="item in bizStatusOptions" :key="item" :label="item">{{ item }}</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
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
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.unit_price"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div class="money-cell">
                  <span class="money-label">数量</span>
                  <div class="money-input">
                    <el-input-number
                      v-model="detail.quantity"
                      :controls="false"
                      :min="1"
                      :precision="0"
                    />
                  </div>
                </div>
                <div class="money-cell">
                  <span class="money-label">收入</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.revenue"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div class="money-cell">
                  <span class="money-label">成本</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.cost"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div class="money-cell money-cell-profit">
                  <span class="money-label">利润</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
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
            </div>
            <el-form-item label="备注">
              <el-input v-model="detail.remark" placeholder="这个执照的特殊说明，可不填" clearable />
            </el-form-item>
          </div>
        </div>
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
import { BIZ_STATUS_OPTIONS, TAX_STATUS_OPTIONS, splitBizStatus, joinBizStatus, bizStatusText } from '@/constants/license'
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
      categoryOptions: ['同行', '代理记账', '工商注册', '变更注销'],
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
        ],
        legal_phone: [
          { validator: optionalPattern(PHONE_RE, '法人手机号为 11 位数字'), trigger: 'blur' }
        ]
      }
    }
  },
  computed: {
    monthSuffix() {
      return this.listQuery.month ? `（${this.listQuery.month}）` : '（全部）'
    },
    // 编辑时把订单编号带到标题上，方便核对；新增时编号由后端在保存后生成
    dialogTitle() {
      if (this.dialogType !== 'edit') return '新增订单'
      return this.form.order_no ? `编辑订单 · ${this.form.order_no}` : '编辑订单'
    },
    filtering() {
      return Boolean(
        this.listQuery.month || this.listQuery.keyword || this.listQuery.status ||
        this.listQuery.platform || this.listQuery.biz_status || this.listQuery.tax_status
      )
    }
  },
  created() {
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
    splitBizStatus,
    bizStatusText,
    // 工商状态多选：下拉里用数组，提交时拼回「正常,另册管理」
    setBizStatus(detail, values) {
      const prev = splitBizStatus(detail.biz_status)
      const picked = Array.isArray(values) ? values.slice() : []
      let next = picked
      if (picked.indexOf('正常') !== -1 && prev.indexOf('正常') === -1) {
        // 本次勾的是「正常」：清掉其它异常状态，只留正常
        next = ['正常']
      } else if (picked.length > 1) {
        // 勾了异常状态：把「正常」摘掉，两者互斥
        next = picked.filter(item => item !== '正常')
      }
      detail.biz_status = joinBizStatus(next)
    },
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新，保证看到最新数据
    refreshPage() {
      this.getList()
      this.getSummary()
      this.loadPlatforms()
      this.loadBizItems()
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
        legal_phone: '',
        biz_status: '',
        tax_status: '',
        items: '',
        item_list: [],
        __autoPrice: 0,
        __collapsed: false,
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
        order_no: '',
        platform_order_no: '',
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
    // 卡片折叠/展开（纯前端展示状态，不参与提交）
    toggleDetail(detail) {
      this.$set(detail, '__collapsed', !detail.__collapsed)
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
        legal_phone: item.legal_phone || '',
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
        order_no: row.order_no,
        platform_order_no: row.platform_order_no || '',
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
        if (!valid) {
          // 校验失败时先把折叠的卡片展开，否则红字藏在收起的内容里，用户看不到哪里错了
          this.form.details.forEach(detail => { detail.__collapsed = false })
          this.$nextTick(() => {
            const firstError = document.querySelector('.order-form .el-form-item.is-error')
            if (firstError && firstError.scrollIntoView) {
              firstError.scrollIntoView({ block: 'center' })
            }
          })
          return false
        }
        const details = this.form.details.map(detail => ({
          id: detail.id,
          license_name: (detail.license_name || '').trim(),
          credit_code: (detail.credit_code || '').toUpperCase(),
          legal_person: (detail.legal_person || '').trim(),
          legal_id: (detail.legal_id || '').toUpperCase(),
          legal_phone: this.normalizePhone(detail.legal_phone),
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
          platform_order_no: (this.form.platform_order_no || '').trim(),
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
    // 明细金额合计：全空返回 null（显示「待定」），否则空值按 0 计
    sumRevenue(details, key) {
      const values = details
        .map(item => this.numberOrNull(item[key]))
        .filter(value => value !== null)
      if (!values.length) return null
      return values.reduce((sum, value) => sum + value, 0)
    },
    // 手机号只留数字：粘贴「+86 138 0013 8000」这种整串也能一步收拾干净
    normalizePhone(value) {
      let digits = String(value || '').replace(/\D/g, '')
      if (digits.length > 11 && digits.indexOf('86') === 0) digits = digits.slice(2)
      return digits.slice(0, 11)
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

  .table-panel {
    .panel-head {
      display: flex;
      align-items: baseline;
      margin: 6px 0 10px;
    }

    .panel-title {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
    }

    .panel-count {
      margin-left: 8px;
      font-size: 12px;
      color: #909399;
    }
  }

  .order-no-text {
    font-family: Menlo, Consolas, monospace;
    font-size: 12px;
    color: #606266;
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

    &.is-collapsed:hover {
      box-shadow: none;
    }

    &.is-collapsed .detail-card-head {
      border-bottom-color: transparent;
    }
  }

  .detail-card-head {
    display: flex;
    align-items: center;
    height: 40px;
    padding: 0 14px;
    background: linear-gradient(180deg, #f7faff 0%, #f1f5fb 100%);
    border-bottom: 1px solid #e9eff7;

    .collapse-btn {
      flex: none;
      width: 16px;
      margin-right: 2px;
      font-size: 12px;
      color: #909399;
      cursor: pointer;

      &:hover {
        color: #409eff;
      }
    }

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

    /* 折叠后补一行摘要，收起状态也能看清业务项和金额 */
    .detail-card-sum {
      display: flex;
      align-items: center;
      margin-left: 10px;
      overflow: hidden;

      .sum-item {
        flex: none;
        margin-right: 8px;
        padding: 0 8px;
        border-radius: 10px;
        background: #ecf5ff;
        font-size: 12px;
        line-height: 20px;
        color: #409eff;
      }

      .sum-empty {
        font-size: 12px;
        color: #c0c4cc;
      }
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

      .money-input {
        position: relative;

        .money-unit {
          position: absolute;
          top: 0;
          left: 10px;
          z-index: 2;
          font-style: normal;
          font-size: 13px;
          line-height: 40px;
          color: #c0c4cc;
          pointer-events: none;
        }

        .el-input-number {
          width: 100%;
        }

        /* 去掉 controls 后 element 仍留了给加减按钮的内边距，这里改回正常留白并左对齐；
           左边留 24px 给 ¥，数量格也一起留，保证五格数字左边缘成一条线 */
        ::v-deep .el-input__inner {
          padding: 0 10px 0 24px;
          text-align: left;
        }
      }
    }

    .money-cell-profit .money-label {
      color: #409eff;
      font-weight: 600;
    }
  }

  .danger-text {
    color: #f56c6c;
  }

  .muted-text {
    color: #c0c4cc;
  }

  .items-preview {
    margin-top: 4px;
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }

  .form-hint {
    margin-top: 2px;
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }

  .platform-order-no-input ::v-deep .el-input__inner {
    font-family: Menlo, Consolas, monospace;
    letter-spacing: 0.3px;
  }

  /* 工商状态平铺勾选：5 项全部展开，不再折叠成「+N」；窄屏自动换行 */
  .biz-status-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    row-gap: 2px;

    ::v-deep .el-checkbox {
      margin-right: 18px;
      margin-left: 0;
      font-weight: normal;
    }

    ::v-deep .el-checkbox + .el-checkbox {
      margin-left: 0;
    }

    ::v-deep .el-checkbox__label {
      padding-left: 6px;
      font-size: 13px;
    }
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
