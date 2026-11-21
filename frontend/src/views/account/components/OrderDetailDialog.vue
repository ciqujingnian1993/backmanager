<template>
  <el-dialog
    :visible="visible"
    width="820px"
    top="6vh"
    append-to-body
    @close="$emit('update:visible', false)"
  >
    <!-- 标题栏右侧：直接跳到这条订单的进度（带上订单号与第一条任务，过去就能看到跟进详情） -->
    <div slot="title" class="dialog-head">
      <span class="dialog-title">订单详情</span>
      <div v-if="row" class="dialog-tools">
        <el-button type="primary" size="mini" plain icon="el-icon-time" @click="goProgress">查看进度</el-button>
      </div>
    </div>
    <div v-if="row" class="order-detail">
      <div class="detail-section">订单信息</div>
      <div class="detail-grid">
        <div v-for="item in basicItems" :key="item.label" class="detail-cell" :class="{ full: item.full }">
          <span class="detail-label">{{ item.label }}</span>
          <span class="detail-value">{{ item.value }}</span>
        </div>
        <!-- 客户身份证照片：点击放大看，悬停可下载 -->
        <div v-if="idPhotos.length" class="detail-cell full photo-cell">
          <span class="detail-label">身份证照片</span>
          <span class="detail-value photo-list">
            <span v-for="(photo, index) in idPhotos" :key="'id-' + index" class="photo-item">
              <el-image
                :src="photo.url"
                :preview-src-list="idPhotoUrls"
                fit="cover"
                class="photo-img"
              />
              <i
                class="el-icon-download photo-dl"
                title="下载"
                @click="downloadPhoto(photo, '身份证-' + (index + 1))"
              />
            </span>
          </span>
        </div>
      </div>

      <div class="detail-section">
        执照明细
        <span class="section-tip">共 {{ details.length }} 个执照，各自独立跟进</span>
      </div>
      <div v-if="!details.length" class="detail-empty">这个订单还没有执照明细</div>
      <div v-for="(item, index) in details" :key="item.id || index" class="license-card">
        <div class="license-head">
          <span class="license-index">执照 {{ index + 1 }}</span>
          <span class="license-name">{{ item.license_name || '未填执照名称' }}</span>
          <el-tag :type="statusType(item.status)" size="mini">{{ statusText(item.status) }}</el-tag>
          <el-tag v-if="item.refund_amount > 0" type="danger" size="mini" effect="plain" class="refund-chip">
            已退 ¥{{ money(item.refund_amount) }}
          </el-tag>
        </div>
        <div class="license-grid">
          <div class="license-cell full">
            <span class="detail-label">统一信用编码</span>
            <span class="detail-value">{{ item.credit_code || '—' }}</span>
          </div>
          <div class="license-cell third">
            <span class="detail-label">法人姓名</span>
            <span class="detail-value">{{ item.legal_person || '—' }}</span>
          </div>
          <div class="license-cell third">
            <span class="detail-label">法人身份证号</span>
            <span class="detail-value">{{ item.legal_id || '—' }}</span>
          </div>
          <div class="license-cell third">
            <span class="detail-label">法人手机号</span>
            <span class="detail-value">{{ item.legal_phone || '—' }}</span>
          </div>
          <div class="license-cell">
            <span class="detail-label">工商状态</span>
            <span class="detail-value">
              <template v-if="splitBizStatus(item.biz_status).length">
                <el-tag
                  v-for="name in splitBizStatus(item.biz_status)"
                  :key="name"
                  size="mini"
                  :type="bizStatusType(name)"
                  effect="plain"
                  class="status-tag"
                >
                  {{ name }}
                </el-tag>
              </template>
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
          <div v-if="item.status === 'cancelled'" class="license-cell full">
            <span class="detail-label">取消原因</span>
            <span class="detail-value cancel-value">
              {{ item.cancel_reason || '未填写' }}
              <span v-if="item.cancel_note" class="cancel-note">备注：{{ item.cancel_note }}</span>
            </span>
          </div>
          <div class="license-cell full">
            <span class="detail-label">备注</span>
            <span class="detail-value">{{ item.remark || '—' }}</span>
          </div>
          <!-- 执照照片：点击放大看，悬停可下载 -->
          <div v-if="itemPhotos(item).length" class="license-cell full photo-cell">
            <span class="detail-label">执照照片</span>
            <span class="detail-value photo-list">
              <span v-for="(photo, pIndex) in itemPhotos(item)" :key="'lp-' + item.id + '-' + pIndex" class="photo-item">
                <el-image
                  :src="photo.url"
                  :preview-src-list="itemPhotos(item).map(p => p.url)"
                  fit="cover"
                  class="photo-img"
                />
                <i
                  class="el-icon-download photo-dl"
                  title="下载"
                  @click="downloadPhoto(photo, '执照-' + (index + 1) + '-' + (pIndex + 1))"
                />
              </span>
            </span>
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
import { bizStatusType, taxStatusType, splitBizStatus } from '@/constants/license'
import { orderStatusText, orderStatusType } from '@/constants/order'

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
    // 客户身份证照片（订单层面）
    idPhotos() {
      const row = this.row || {}
      return Array.isArray(row.id_photos) ? row.id_photos : []
    },
    idPhotoUrls() {
      return this.idPhotos.map(photo => photo.url)
    },
    // 整单累计退款（各执照明细的 refund_amount 之和）
    refundTotal() {
      return this.details.reduce((sum, item) => sum + Number(item.refund_amount || 0), 0)
    },
    basicItems() {
      const row = this.row || {}
      return [
        { label: '订单编号', value: row.order_no || '—' },
        { label: '平台订单编号', value: row.platform_order_no || '—' },
        { label: '业务日期', value: row.biz_date || '—' },
        { label: '行业', value: row.category || '—' },
        { label: '客户', value: row.client || '—' },
        { label: '手机号', value: row.phone || '—' },
        { label: '来源平台', value: row.platform || '—' },
        { label: '状态', value: orderStatusText(row.status) },
        { label: '收入', value: this.money(row.revenue) },
        { label: '成本', value: this.money(row.cost) },
        { label: '利润', value: this.money(row.profit) },
        { label: '已退款', value: this.money(this.refundTotal) },
        { label: '完成时间', value: this.completed(row.completed_at) },
        { label: '录入人', value: row.creator || '—' },
        { label: '备注', value: row.remark || '—', full: true }
      ]
    }
  },
  methods: {
    bizStatusType,
    taxStatusType,
    splitBizStatus,
    // 一条执照明细的执照照片
    itemPhotos(item) {
      return item && Array.isArray(item.license_photos) ? item.license_photos : []
    },
    // 同源 /uploads 图片：取 blob 触发浏览器下载，文件名优先用上传时的名字
    async downloadPhoto(photo, fallbackName) {
      if (!photo || !photo.url) return
      const name = photo.name || fallbackName
      try {
        const res = await fetch(photo.url)
        const blob = await res.blob()
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = name
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(link.href)
      } catch (error) {
        this.$message.error('下载失败，请重试')
      }
    },
    // 当前账号能不能进「订单进度」页，没权限就别跳 404
    canVisitProgress() {
      const matched = this.$router.match('/progress/index').matched
      const top = matched.length ? matched[0].path : ''
      return !!top && top !== '*' && top !== '/404'
    },
    goProgress() {
      const row = this.row || {}
      if (!row.order_no && !row.id) return
      if (!this.canVisitProgress()) {
        this.$message.warning('当前账号没有「订单进度」权限，请联系管理员开通')
        return
      }
      const query = {}
      if (row.order_no) query.keyword = row.order_no
      const first = this.details[0]
      if (first && first.id) query.id = first.id
      this.$emit('update:visible', false)
      this.$router.push({ path: '/progress/index', query })
    },
    statusText(status) {
      return orderStatusText(status)
    },
    statusType(status) {
      return orderStatusType(status)
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
.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 26px;

  .dialog-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
  }

  .dialog-tools {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

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

  // 取消订单：原因标红，备注跟在后面用灰字
  .cancel-value {
    color: #f56c6c;
  }

  .cancel-note {
    margin-left: 6px;
    color: #909399;
    font-size: 12px;
  }

  // 工商状态多选：标签逐个排列，超出换行
  .status-tag {
    margin: 0 4px 2px 0;
  }

  .detail-empty {
    color: #909399;
    font-size: 13px;
    padding: 8px 0;
  }

  // 身份证 / 执照照片：56px 缩略图，点击放大，悬停出下载按钮
  .photo-cell {
    align-items: flex-start;
  }

  .photo-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .photo-item {
    position: relative;
    width: 56px;
    height: 56px;
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid #dcdfe6;
    background: #f5f7fa;
    display: inline-block;

    .photo-img {
      width: 100%;
      height: 100%;
      display: block;
      cursor: zoom-in;
    }

    .photo-dl {
      position: absolute;
      right: 0;
      bottom: 0;
      width: 20px;
      height: 20px;
      line-height: 20px;
      text-align: center;
      background: rgba(0, 0, 0, 0.55);
      color: #fff;
      font-size: 13px;
      cursor: pointer;
      display: none;
    }

    &:hover .photo-dl {
      display: block;
    }

    &:hover .photo-dl:hover {
      background: #409eff;
    }
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

    .refund-chip {
      margin-left: 6px;
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

    /* 执照信息首行：法人姓名 / 身份证号 / 手机号 三栏并排 */
    &.third {
      width: 33.333%;

      .detail-label {
        width: 88px;
      }
    }

    .detail-label {
      width: 104px;
    }
  }
}
</style>
