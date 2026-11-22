<template>
  <div class="price-setting">
    <div class="filter-container">
      <el-input
        v-model="keyword"
        class="filter-item keyword-input"
        placeholder="搜索服务项目 / 适用情况 / 类别"
        prefix-icon="el-icon-search"
        clearable
      />
      <el-select v-model="category" class="filter-item" placeholder="全部类别" clearable>
        <el-option v-for="item in categories" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="status" class="filter-item status-select">
        <el-option label="全部状态" value="all" />
        <el-option label="启用中" value="active" />
        <el-option label="已停用" value="inactive" />
      </el-select>
      <el-button class="filter-item" type="primary" icon="el-icon-plus" @click="handleCreate">
        新增项目
      </el-button>
      <el-button class="filter-item" icon="el-icon-document" @click="openNotes">价目说明</el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="$emit('refresh')">刷新</el-button>
      <span class="filter-tip">
        共 {{ filtered.length }} 项<span v-if="filtered.length !== items.length">（全部 {{ items.length }} 项）</span>，启用中 {{ activeCount }} 项；停用的项目在「价格查看」里默认不展示
      </span>
    </div>

    <el-table
      v-loading="loading"
      :data="filtered"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column label="类别" width="120" align="center">
        <template slot-scope="{ row }">
          <span class="cat-pill" :style="pillStyle(row.category)">{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column label="服务项目 / 适用情况" min-width="330">
        <template slot-scope="{ row }">
          <div class="cell-name">{{ row.name }}</div>
          <div v-if="row.condition" class="cell-sub">{{ row.condition }}</div>
        </template>
      </el-table-column>
      <el-table-column label="标准价" width="120" align="right">
        <template slot-scope="{ row }">
          <span class="money">{{ moneyText(row.price) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="同行参考价" width="130" align="right">
        <template slot-scope="{ row }">
          <span v-if="row.peer_price" class="money peer">{{ moneyText(row.peer_price) }}</span>
          <span v-else class="muted">未填</span>
        </template>
      </el-table-column>
      <el-table-column label="价差" width="110" align="center">
        <template slot-scope="{ row }">
          <span class="diff" :class="'is-' + diffOf(row).type">{{ diffOf(row).text }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96" align="center">
        <template slot-scope="{ row }">
          <el-switch
            :value="row.active"
            @change="value => handleToggle(row, value)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="center" fixed="right">
        <template slot-scope="{ row }">
          <el-button type="primary" size="mini" @click="handleUpdate(row)">修改</el-button>
          <el-button type="danger" size="mini" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="table-note">
      <i class="el-icon-info" />
      改价只影响后续报价，历史订单金额不跟着变；新项目默认排在同类最后，可用「排序」调位置。
    </div>

    <!-- 新增 / 修改价目 -->
    <el-dialog
      :title="dialogType === 'edit' ? '修改价目' : '新增价目'"
      :visible.sync="dialogVisible"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form ref="priceForm" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="类别" prop="category">
          <el-select
            v-model="form.category"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
            placeholder="选择已有类别，或直接输入新类别"
          >
            <el-option v-for="item in categories" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务项目" prop="name">
          <el-input v-model="form.name" maxlength="60" placeholder="例如 有限公司一般注销" />
        </el-form-item>
        <el-form-item label="适用情况">
          <el-input
            v-model="form.condition"
            type="textarea"
            :rows="2"
            maxlength="120"
            placeholder="什么条件下适用这个价，例如 需清算组备案、债权人公告45日"
          />
        </el-form-item>
        <el-form-item label="标准价" prop="price">
          <el-input-number
            v-model="form.price"
            style="width: 100%"
            :min="0"
            :precision="2"
            :step="50"
            controls-position="right"
          />
          <div class="hint">对外报的标准价，价格查看页与报价都以它为准</div>
        </el-form-item>
        <el-form-item label="同行参考价">
          <el-input-number
            v-model="form.peer_price"
            style="width: 100%"
            :min="0"
            :precision="2"
            :step="50"
            controls-position="right"
          />
          <div class="hint">填同行的报价，用来算价差；不填就只看标准价</div>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number
            v-model="form.sort"
            style="width: 100%"
            :min="0"
            :precision="0"
            :step="10"
            controls-position="right"
          />
          <div class="hint">数字越小越靠前；留 0 时自动排到同类末尾</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.active" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="内部备注，可不填" />
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </div>
    </el-dialog>

    <!-- 价目说明：免责声明 + 特别提醒，价格查看页会原样展示 -->
    <el-dialog
      title="价目说明"
      :visible.sync="notesVisible"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form label-width="96px">
        <el-form-item label="免责声明">
          <el-input
            v-model="notes.notice"
            type="textarea"
            :rows="4"
            maxlength="500"
            placeholder="写在价目表顶部的价格口径说明"
          />
        </el-form-item>
        <el-form-item label="特别提醒">
          <el-input
            v-model="notes.tips"
            type="textarea"
            :rows="7"
            placeholder="一行一条，价格查看页会按条列出"
          />
          <div class="hint">每行一条，展示时自动编号</div>
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="notesVisible = false">取消</el-button>
        <el-button type="primary" :loading="notesSaving" @click="submitNotes">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { createPrice, updatePrice, deletePrice, savePriceSettings } from '@/api/price'
import { formatMoney, diffInfo, categoryColor } from '@/constants/price'

export default {
  name: 'PriceSetting',
  props: {
    items: { type: Array, default: () => [] },
    categories: { type: Array, default: () => [] },
    settings: { type: Object, default: () => ({ notice: '', tips: '' }) },
    loading: { type: Boolean, default: false }
  },
  data() {
    return {
      keyword: '',
      category: '',
      status: 'all',
      dialogVisible: false,
      dialogType: 'create',
      saving: false,
      form: this.emptyForm(),
      notesVisible: false,
      notesSaving: false,
      notes: { notice: '', tips: '' },
      rules: {
        category: [{ required: true, message: '请选择或输入类别', trigger: 'change' }],
        name: [{ required: true, message: '请填写服务项目名称', trigger: 'blur' }]
      }
    }
  },
  computed: {
    filtered() {
      const keyword = this.keyword.trim().toLowerCase()
      return this.items.filter(item => {
        if (this.category && item.category !== this.category) return false
        if (this.status === 'active' && !item.active) return false
        if (this.status === 'inactive' && item.active) return false
        if (!keyword) return true
        return [item.name, item.condition, item.category, item.remark].some(text =>
          String(text || '').toLowerCase().includes(keyword)
        )
      })
    },
    activeCount() {
      return this.items.filter(item => item.active).length
    }
  },
  methods: {
    moneyText(value) {
      return '¥' + formatMoney(value)
    },
    diffOf(row) {
      return diffInfo(row)
    },
    pillStyle(category) {
      const color = categoryColor(category)
      return {
        color,
        background: color + '14',
        borderColor: color + '33'
      }
    },
    emptyForm() {
      return {
        id: undefined,
        category: '',
        name: '',
        condition: '',
        price: 0,
        peer_price: 0,
        remark: '',
        sort: 0,
        active: true
      }
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.form.category = this.category || ''
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.priceForm && this.$refs.priceForm.clearValidate()
      })
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = Object.assign(this.emptyForm(), {
        id: row.id,
        category: row.category,
        name: row.name,
        condition: row.condition,
        price: row.price,
        peer_price: row.peer_price,
        remark: row.remark,
        sort: row.sort,
        active: row.active
      })
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.priceForm && this.$refs.priceForm.clearValidate()
      })
    },
    submitForm() {
      this.$refs.priceForm.validate(async valid => {
        if (!valid) return
        this.saving = true
        try {
          const payload = Object.assign({}, this.form)
          if (this.dialogType === 'edit') {
            await updatePrice(payload)
          } else {
            await createPrice(payload)
          }
          this.$message.success(this.dialogType === 'edit' ? '价目已更新' : '价目已新增')
          this.dialogVisible = false
          this.$emit('refresh')
        } finally {
          this.saving = false
        }
      })
    },
    handleToggle(row, value) {
      updatePrice({ id: row.id, active: value, only_toggle: true })
        .then(() => {
          row.active = value
          this.$message.success(value ? '已启用' : '已停用，价格查看页默认不展示')
        })
        .catch(() => {})
    },
    handleDelete(row) {
      this.$confirm(`确认删除「${row.name}」吗？删除后价格查看页也不再出现。`, '提示', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deletePrice({ id: row.id }))
        .then(() => {
          this.$message.success('已删除')
          this.$emit('refresh')
        })
        .catch(() => {})
    },
    openNotes() {
      this.notes = {
        notice: this.settings.notice || '',
        tips: this.settings.tips || ''
      }
      this.notesVisible = true
    },
    submitNotes() {
      this.notesSaving = true
      savePriceSettings(this.notes)
        .then(() => {
          this.$message.success('价目说明已保存')
          this.notesVisible = false
          this.$emit('refresh')
        })
        .finally(() => {
          this.notesSaving = false
        })
    }
  }
}
</script>

<style lang="scss" scoped>
.filter-container {
  display: flex;
  align-items: center;
  flex-wrap: wrap;

  .filter-item {
    margin-bottom: 10px;
  }
}

.keyword-input {
  width: 250px;
}

.status-select {
  width: 120px;
}

.filter-tip {
  flex: 1;
  min-width: 260px;
  margin: 0 0 10px 8px;
  font-size: 12px;
  line-height: 18px;
  color: #909399;
}

.cat-pill {
  display: inline-block;
  padding: 0 8px;
  line-height: 20px;
  font-size: 12px;
  border: 1px solid transparent;
  border-radius: 10px;
}

.cell-name {
  font-size: 13px;
  color: #303133;
}

.cell-sub {
  margin-top: 2px;
  font-size: 12px;
  line-height: 17px;
  color: #909399;
}

.money {
  font-family: Menlo, Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
  color: #2f6fe4;

  &.peer {
    font-weight: 400;
    color: #606266;
  }
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

.table-note {
  margin-top: 10px;
  font-size: 12px;
  line-height: 18px;
  color: #909399;

  i {
    margin-right: 4px;
    color: #409eff;
  }
}

.hint {
  font-size: 12px;
  line-height: 18px;
  color: #909399;
}
</style>
