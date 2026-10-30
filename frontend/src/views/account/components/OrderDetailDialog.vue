<template>
  <el-dialog
    title="订单详情"
    :visible="visible"
    width="660px"
    append-to-body
    @close="$emit('update:visible', false)"
  >
    <div v-if="row" class="order-detail">
      <div class="detail-section">订单信息</div>
      <div class="detail-grid">
        <div v-for="item in basicItems" :key="item.label" class="detail-cell">
          <span class="detail-label">{{ item.label }}</span>
          <span class="detail-value">{{ item.value }}</span>
        </div>
      </div>

      <div class="detail-section">执照信息</div>
      <div class="detail-grid">
        <div v-for="item in licenseItems" :key="item.label" class="detail-cell" :class="{ full: item.full }">
          <span class="detail-label">{{ item.label }}</span>
          <span class="detail-value">{{ item.value }}</span>
        </div>
      </div>
    </div>
    <div slot="footer">
      <el-button type="primary" @click="$emit('update:visible', false)">关闭</el-button>
    </div>
  </el-dialog>
</template>

<script>
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
    basicItems() {
      const row = this.row || {}
      return [
        { label: '业务日期', value: row.biz_date || '—' },
        { label: '行业', value: row.category || '—' },
        { label: '客户', value: row.client || '—' },
        { label: '业务项', value: row.items || '—' },
        { label: '来源平台', value: row.platform || '—' },
        { label: '状态', value: STATUS_MAP[row.status] || '待定' },
        { label: '单价', value: this.money(row.unit_price) },
        { label: '数量', value: row.quantity === null || row.quantity === undefined ? '—' : row.quantity },
        { label: '收入', value: this.money(row.revenue) },
        { label: '成本', value: this.money(row.cost) },
        { label: '利润', value: this.money(row.profit) },
        { label: '完成时间', value: this.completed(row.completed_at) },
        { label: '录入人', value: row.creator || '—' },
        { label: '备注', value: row.remark || '—', full: true }
      ]
    },
    licenseItems() {
      const row = this.row || {}
      return [
        { label: '执照名称', value: row.license_name || '—', full: true },
        { label: '统一信用编码', value: row.credit_code || '—', full: true },
        { label: '法人姓名', value: row.legal_person || '—' },
        { label: '法人身份证号', value: row.legal_id || '—' }
      ]
    }
  },
  methods: {
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
    width: 100px;
    flex: none;
    color: #909399;
  }

  .detail-value {
    color: #303133;
    word-break: break-all;
  }
}
</style>
