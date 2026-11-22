<template>
  <div v-loading="loading" class="price-view">
    <!-- 概览：项目数、均价、区间、价差，业务员报价前先看这四块 -->
    <div class="pv-stats">
      <div class="stat-card">
        <div class="sc-icon is-blue"><i class="el-icon-tickets" /></div>
        <div class="sc-body">
          <div class="sc-label">启用项目</div>
          <div class="sc-value">{{ stats.active_total || 0 }}<span class="sc-unit">项</span></div>
          <div class="sc-sub">全部 {{ stats.total || 0 }} 项，停用 {{ (stats.total || 0) - (stats.active_total || 0) }} 项</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="sc-icon is-green"><i class="el-icon-money" /></div>
        <div class="sc-body">
          <div class="sc-label">平均标准价</div>
          <div class="sc-value">{{ moneyText(stats.avg_price) }}</div>
          <div class="sc-sub">全部项目加权前均值</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="sc-icon is-orange"><i class="el-icon-sort" /></div>
        <div class="sc-body">
          <div class="sc-label">价格区间</div>
          <div class="sc-value">{{ moneyText(stats.min_price) }}<span class="sc-dash">~</span>{{ moneyText(stats.max_price) }}</div>
          <div class="sc-sub">最低价 ~ 最高价</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="sc-icon is-purple"><i class="el-icon-data-analysis" /></div>
        <div class="sc-body">
          <div class="sc-label">比同行便宜</div>
          <div class="sc-value">{{ stats.cheaper_total || 0 }}<span class="sc-unit">项</span></div>
          <div class="sc-sub">标准价低于同行参考价</div>
        </div>
      </div>
    </div>

    <div class="pv-bar">
      <el-input
        v-model="keyword"
        class="keyword-input"
        placeholder="搜索服务项目 / 适用情况"
        prefix-icon="el-icon-search"
        clearable
      />
      <div class="cat-chips">
        <span class="chip" :class="{ 'is-active': !category }" @click="category = ''">
          全部<em>{{ baseItems.length }}</em>
        </span>
        <span
          v-for="item in categories"
          :key="item"
          class="chip"
          :class="{ 'is-active': category === item, 'is-dim': !countOf(item) }"
          :style="category === item ? { borderColor: colorOf(item), color: colorOf(item) } : null"
          @click="category = item"
        >
          {{ item }}<em>{{ countOf(item) }}</em>
        </span>
      </div>
      <el-checkbox v-model="showInactive" class="inactive-toggle">显示已停用</el-checkbox>
    </div>

    <div v-if="!groups.length && !loading" class="pv-empty">
      <i class="el-icon-search" />
      <p>没找到匹配的服务项目</p>
      <span>换个关键词，或把「显示已停用」打开看看</span>
    </div>

    <div v-for="group in groups" :key="group.category" class="cat-block">
      <div class="cb-head">
        <span class="cb-bar" :style="{ background: colorOf(group.category) }" />
        <span class="cb-name">{{ group.category }}</span>
        <span class="cb-count">{{ group.items.length }} 项</span>
        <span class="cb-range">{{ rangeText(group.items) }}</span>
      </div>
      <el-table :data="group.items" border class="cb-table" style="width: 100%">
        <el-table-column type="index" label="序号" width="56" align="center" />
        <el-table-column label="服务项目 / 适用情况" min-width="360">
          <template slot-scope="{ row }">
            <div class="cell-name">
              {{ row.name }}
              <el-tag v-if="!row.active" size="mini" type="info" effect="plain">已停用</el-tag>
            </div>
            <div v-if="row.condition" class="cell-sub">{{ row.condition }}</div>
          </template>
        </el-table-column>
        <el-table-column label="标准价" width="140" align="right">
          <template slot-scope="{ row }">
            <span class="price-strong">{{ moneyText(row.price) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同行参考价" width="140" align="right">
          <template slot-scope="{ row }">
            <span v-if="row.peer_price" class="price-peer">{{ moneyText(row.peer_price) }}</span>
            <span v-else class="muted">未填</span>
          </template>
        </el-table-column>
        <el-table-column label="价差" width="120" align="center">
          <template slot-scope="{ row }">
            <span class="diff" :class="'is-' + diffOf(row).type">{{ diffOf(row).text }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pv-notes">
      <div class="note-head">
        <i class="el-icon-warning-outline" />
        特别提醒
      </div>
      <ol class="note-list">
        <li v-for="(line, index) in tips" :key="index">{{ line }}</li>
      </ol>
      <div v-if="settings.notice" class="note-notice">{{ settings.notice }}</div>
    </div>
  </div>
</template>

<script>
import { formatMoney, diffInfo, categoryColor } from '@/constants/price'

const TIP_PREFIX_RE = /^\s*\d+[)）.、]\s*/

export default {
  name: 'PriceView',
  props: {
    items: { type: Array, default: () => [] },
    categories: { type: Array, default: () => [] },
    settings: { type: Object, default: () => ({ notice: '', tips: '' }) },
    stats: { type: Object, default: () => ({}) },
    loading: { type: Boolean, default: false }
  },
  data() {
    return {
      keyword: '',
      category: '',
      showInactive: false
    }
  },
  computed: {
    // 价格查看默认只给在售价，停用项目要显式打开才出现
    baseItems() {
      return this.showInactive ? this.items : this.items.filter(item => item.active)
    },
    matched() {
      const keyword = this.keyword.trim().toLowerCase()
      return this.baseItems.filter(item => {
        if (this.category && item.category !== this.category) return false
        if (!keyword) return true
        return [item.name, item.condition, item.category].some(text =>
          String(text || '').toLowerCase().includes(keyword)
        )
      })
    },
    groups() {
      return this.categories
        .map(name => ({
          category: name,
          items: this.matched.filter(item => item.category === name)
        }))
        .filter(group => group.items.length)
    },
    tips() {
      return String(this.settings.tips || '')
        .split(/\r?\n/)
        .map(line => line.trim().replace(TIP_PREFIX_RE, ''))
        .filter(Boolean)
    }
  },
  methods: {
    moneyText(value) {
      return '¥' + formatMoney(value)
    },
    diffOf(row) {
      return diffInfo(row)
    },
    colorOf(category) {
      return categoryColor(category)
    },
    countOf(category) {
      return this.baseItems.filter(item => item.category === category).length
    },
    rangeText(list) {
      const prices = list.map(item => Number(item.price || 0))
      if (!prices.length) return ''
      const min = Math.min.apply(null, prices)
      const max = Math.max.apply(null, prices)
      return min === max ? '¥' + formatMoney(min) : '¥' + formatMoney(min) + ' ~ ¥' + formatMoney(max)
    }
  }
}
</script>

<style lang="scss" scoped>
.pv-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.sc-icon {
  flex: none;
  width: 40px;
  height: 40px;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  font-size: 19px;

  &.is-blue {
    color: #2f6fe4;
    background: #ecf3ff;
  }

  &.is-green {
    color: #529b2e;
    background: #f0f9eb;
  }

  &.is-orange {
    color: #b88230;
    background: #fdf6ec;
  }

  &.is-purple {
    color: #7b52c9;
    background: #f4efff;
  }
}

.sc-label {
  font-size: 12px;
  color: #909399;
}

.sc-value {
  margin-top: 3px;
  font-size: 21px;
  font-weight: 600;
  line-height: 26px;
  color: #1f2d3d;
  font-family: Menlo, Consolas, monospace;
}

.sc-unit {
  margin-left: 3px;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  font-family: inherit;
}

.sc-dash {
  margin: 0 3px;
  font-size: 14px;
  color: #c0c4cc;
}

.sc-sub {
  margin-top: 2px;
  font-size: 11px;
  color: #a8abb2;
}

.pv-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 14px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.keyword-input {
  width: 230px;
  flex: none;
}

.cat-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  height: 26px;
  font-size: 12px;
  color: #606266;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 13px;
  cursor: pointer;
  transition: all 0.15s;

  em {
    margin-left: 5px;
    font-style: normal;
    font-size: 11px;
    color: #909399;
  }

  &:hover {
    border-color: #b3d8ff;
    color: #2f6fe4;
  }

  &.is-active {
    font-weight: 600;
    background: #f2f7ff;
  }

  &.is-dim {
    opacity: 0.55;
  }
}

.inactive-toggle {
  flex: none;
  ::v-deep .el-checkbox__label {
    font-size: 12px;
    color: #909399;
  }
}

.cat-block {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.cb-head {
  display: flex;
  align-items: center;
  padding: 11px 14px;
  background: #fafbfc;
  border-bottom: 1px solid #ebeef5;
}

.cb-bar {
  width: 3px;
  height: 14px;
  margin-right: 8px;
  border-radius: 2px;
}

.cb-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2d3d;
}

.cb-count {
  margin-left: 8px;
  padding: 0 6px;
  line-height: 18px;
  font-size: 11px;
  color: #909399;
  background: #f0f2f5;
  border-radius: 9px;
}

.cb-range {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
  font-family: Menlo, Consolas, monospace;
}

.cb-table {
  ::v-deep th {
    background: #fff;
    font-size: 12px;
    font-weight: 600;
    color: #909399;
  }

  ::v-deep td {
    padding: 9px 0;
  }
}

.cell-name {
  font-size: 13px;
  color: #303133;

  .el-tag {
    margin-left: 6px;
  }
}

.cell-sub {
  margin-top: 2px;
  font-size: 12px;
  line-height: 17px;
  color: #909399;
}

.price-strong {
  font-family: Menlo, Consolas, monospace;
  font-size: 14px;
  font-weight: 600;
  color: #2f6fe4;
}

.price-peer {
  font-family: Menlo, Consolas, monospace;
  font-size: 13px;
  color: #606266;
}

.muted {
  color: #c0c4cc;
}

.diff {
  font-size: 12px;

  &.is-down {
    color: #529b2e;
  }

  &.is-up {
    color: #f56c6c;
  }

  &.is-same,
  &.is-none {
    color: #909399;
  }
}

.pv-empty {
  padding: 48px 0 40px;
  text-align: center;
  color: #909399;

  i {
    font-size: 30px;
    color: #c0c4cc;
  }

  p {
    margin: 10px 0 4px;
    font-size: 13px;
    color: #606266;
  }

  span {
    font-size: 12px;
    color: #a8abb2;
  }
}

.pv-notes {
  margin-top: 4px;
  padding: 14px 16px 16px;
  background: #fffbf2;
  border: 1px solid #faecd8;
  border-radius: 8px;
}

.note-head {
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #b88230;

  i {
    margin-right: 5px;
  }
}

.note-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 22px;
  color: #7a6b52;
}

.note-notice {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #f0dfc0;
  font-size: 12px;
  line-height: 20px;
  color: #9c8c72;
}

@media (max-width: 1200px) {
  .pv-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
