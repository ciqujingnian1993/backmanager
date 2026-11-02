<template>
  <div class="order-items">
    <el-table :data="details" border size="mini" style="width: 100%">
      <el-table-column label="#" width="42" align="center">
        <template slot-scope="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="license_name" label="执照名称" min-width="170" show-overflow-tooltip>
        <template slot-scope="{ row }">{{ row.license_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="工商状态" width="95" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.biz_status" size="mini" :type="bizStatusType(row.biz_status)" effect="plain">
            {{ row.biz_status }}
          </el-tag>
          <span v-else class="muted-text">—</span>
        </template>
      </el-table-column>
      <el-table-column label="税务状态" width="100" align="center">
        <template slot-scope="{ row }">
          <el-tag v-if="row.tax_status" size="mini" :type="taxStatusType(row.tax_status)" effect="plain">
            {{ row.tax_status }}
          </el-tag>
          <span v-else class="muted-text">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="items" label="业务项" min-width="110" show-overflow-tooltip>
        <template slot-scope="{ row }">{{ row.items || '—' }}</template>
      </el-table-column>
      <el-table-column label="收入" width="90" align="right">
        <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
      </el-table-column>
      <el-table-column label="成本" width="90" align="right">
        <template slot-scope="{ row }">{{ amount(row.cost) }}</template>
      </el-table-column>
      <el-table-column label="利润" width="90" align="right">
        <template slot-scope="{ row }">{{ amount(row.profit) }}</template>
      </el-table-column>
      <el-table-column label="任务状态" width="90" align="center">
        <template slot-scope="{ row }">
          <el-tag :type="statusType(row.status)" size="mini">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!details || !details.length" class="items-empty">
      这个订单还没有执照明细
    </div>
  </div>
</template>

<script>
import { bizStatusType, taxStatusType } from '@/constants/license'

const STATUS_MAP = {
  pending: '待定',
  doing: '进行中',
  done: '已完成'
}

export default {
  name: 'OrderItemsTable',
  props: {
    details: {
      type: Array,
      default: () => []
    }
  },
  methods: {
    bizStatusType,
    taxStatusType,
    maskId(value) {
      const text = String(value || '').trim()
      if (!text) return '—'
      if (text.length <= 10) return text
      return text.slice(0, 6) + '*'.repeat(text.length - 10) + text.slice(-4)
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    statusText(status) {
      return STATUS_MAP[status] || '待定'
    },
    statusType(status) {
      return status === 'done' ? 'success' : status === 'doing' ? 'warning' : 'info'
    },
    completedText(stamp) {
      if (!stamp) return '—'
      const date = new Date(Number(stamp))
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    }
  }
}
</script>

<style lang="scss" scoped>
.order-items {
  padding: 8px 12px 12px 48px;

  .muted-text {
    color: #c0c4cc;
  }

  .items-empty {
    color: #909399;
    font-size: 12px;
    padding: 8px 0 0;
  }
}
</style>
