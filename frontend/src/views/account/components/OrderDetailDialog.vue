<template>
  <el-dialog
    title="订单详情"
    :visible="visible"
    width="760px"
    top="6vh"
    append-to-body
    @close="$emit('update:visible', false)"
  >
    <div v-if="row" class="order-detail">
      <div class="detail-section">订单信息</div>
      <div class="detail-grid">
        <div v-for="item in basicItems" :key="item.label" class="detail-cell" :class="{ full: item.full }">
          <span class="detail-label">{{ item.label }}</span>
          <span class="detail-value">{{ item.value }}</span>
        </div>
      </div>

      <div class="detail-section">
        执照明细与任务
        <span class="section-tip">共 {{ details.length }} 个执照，各自独立跟进</span>
      </div>
      <div v-if="!details.length" class="detail-empty">这个订单还没有执照明细</div>
      <div v-for="(item, index) in details" :key="item.id || index" class="license-card">
        <div class="license-head">
          <span class="license-index">执照 {{ index + 1 }}</span>
          <span class="license-name">{{ item.license_name || '未填执照名称' }}</span>
          <el-tag :type="statusType(item.status)" size="mini">{{ statusText(item.status) }}</el-tag>
        </div>
        <div class="license-grid">
          <div class="license-cell full">
            <span class="detail-label">统一信用编码</span>
            <span class="detail-value">{{ item.credit_code || '—' }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">法人姓名</span>
            <span class="detail-value">{{ item.legal_person || '—' }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">法人身份证号</span>
            <span class="detail-value">{{ item.legal_id || '—' }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">工商状态</span>
            <span class="detail-value">
              <el-tag v-if="item.biz_status" size="mini" :type="bizStatusType(item.biz_status)" effect="plain">
                {{ item.biz_status }}
              </el-tag>
              <span v-else>—</span>
            </span>
          </div>
          <div class="license-cell">
            <span class="detail-label">税务状态</span>
            <span class="detail-value">
              <el-tag v-if="item.tax_status" size="mini" :type="taxStatusType(item.tax_status)" effect="plain">
                {{ item.tax_status }}
              </el-tag>
              <span v-else>—</span>
            </span>
          </div>
          <div class="license-cell">
            <span class="detail-label">业务项</span>
            <span class="detail-value">{{ item.items || '—' }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">收入 / 成本</span>
            <span class="detail-value">{{ money(item.revenue) }} / {{ money(item.cost) }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">利润</span>
            <span class="detail-value">{{ money(item.profit) }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">完成时间</span>
            <span class="detail-value">{{ completed(item.completed_at) }}</span>
          </div>
          <div class="license-cell full">
            <span class="detail-label">备注</span>
            <span class="detail-value">{{ item.remark || '—' }}</span>
          </div>
        </div>
      </div>
    </div>
    <div slot="footer">
      <el-button type="primary" @click="$emit('update:visible', false)">关闭</el-button>
    </div>
  </el-dialog>
</template>

<script>
import { bizStatusType, taxStatusType } from '@/constants/license'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

export default {
  name: 'OrderDetailDialog',
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    row: {
      type: Object,
      default: null
    }
  },
  computed: {
    details() {
      return (this.row && this.row.details) || []
    },
    basicItems() {
      const row = this.row || {}
      return [
        { label: '业务日期', value: row.biz_date || '—' },
        { label: '行业', value: row.category || '—' },
        { label: '客户', value: row.client || '—' },
        { label: '手机号', value: row.phone || '—' },
        { label: '来源平台', value: row.platform || '—' },
        { label: '状态', value: STATUS_MAP[row.status] || '待定' },
        { label: '收入', value: this.money(row.revenue) },
        { label: '成本', value: this.money(row.cost) },
        { label: '利润', value: this.money(row.profit) },
        { label: '完成时间', value: this.completed(row.completed_at) },
        { label: '录入人', value: row.creator || '—' },
        { label: '备注', value: row.remark || '—', full: true }
      ]
    }
  },
  methods: {
    bizStatusType,
    taxStatusType,
    statusText(status) {
      return STATUS_MAP[status] || '待定'
    },
    statusType(status) {
      return status === 'done' ? 'success' : status === 'doing' ? 'warning' : 'info'
    },
    money(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return '￥' + (num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100))
    },
    completed(stamp) {
      if (!stamp) return '—'
      const date = new Date(Number(stamp))
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    }
  }
}
</script>

<style lang="scss" scoped>
.order-detail {
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 6px;

  .detail-section {
    margin: 4px 0 12px;
    padding-left: 8px;
    border-left: 3px solid #409eff;
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    line-height: 18px;

    &:not(:first-child) {
      margin-top: 18px;
    }

    .section-tip {
      margin-left: 8px;
      font-weight: 400;
      font-size: 12px;
      color: #909399;
    }
  }

  .detail-grid {
    display: flex;
    flex-wrap: wrap;
  }

  .detail-cell {
    width: 50%;
    padding: 6px 0;
    display: flex;
    font-size: 13px;
    line-height: 20px;

    &.full {
      width: 100%;
    }
  }

  .detail-label {
    width: 104px;
    flex: none;
    color: #909399;
  }

  .detail-value {
    color: #303133;
    word-break: break-all;
  }

  .detail-empty {
    color: #909399;
    font-size: 13px;
    padding: 8px 0;
  }

  .license-card {
    border: 1px solid #ebeef5;
    border-radius: 4px;
    padding: 10px 12px;
    margin-bottom: 10px;
    background: #fafcff;
  }

  .license-head {
    display: flex;
    align-items: center;
    margin-bottom: 6px;

    .license-index {
      font-size: 12px;
      color: #409eff;
      background: #ecf5ff;
      border-radius: 3px;
      padding: 1px 6px;
      margin-right: 8px;
    }

    .license-name {
      flex: 1;
      font-size: 13px;
      font-weight: 600;
      color: #303133;
      margin-right: 8px;
      word-break: break-all;
    }
  }

  .license-grid {
    display: flex;
    flex-wrap: wrap;
  }

  .license-cell {
    width: 50%;
    display: flex;
    font-size: 13px;
    line-height: 22px;

    &.full {
      width: 100%;
    }

    .detail-label {
      width: 104px;
    }
  }
}
</style>
