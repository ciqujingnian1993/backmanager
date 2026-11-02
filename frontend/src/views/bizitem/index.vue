<template>
  <div class="app-container">
    <el-alert
      class="tip"
      type="info"
      :closable="false"
      show-icon
      title="业务项字典：订单里的业务项从这里多选组合，例如「解非 + 工商注销」；单价会按所选业务项自动合计，可再手改。停用的业务项不再出现在订单下拉里，历史订单不受影响。"
    />

    <div class="filter-container">
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索业务项 / 备注"
        clearable
        @keyup.enter.native="getList"
      />
      <el-button class="filter-item" type="primary" icon="el-icon-search" @click="getList">
        查询
      </el-button>
      <el-button class="filter-item" type="primary" icon="el-icon-plus" @click="handleCreate">
        新增业务项
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column prop="sort" label="排序" width="80" align="center" />
      <el-table-column label="业务项" min-width="180">
        <template slot-scope="{ row }">
          <el-tag size="medium" effect="plain" :type="row.active ? '' : 'info'">{{ row.name }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认单价" width="130" align="right">
        <template slot-scope="{ row }">
          <span :class="{ 'muted': !row.unit_price }">{{ row.unit_price ? '¥' + formatMoney(row.unit_price) : '未设置' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="使用次数" width="110" align="center">
        <template slot-scope="{ row }">
          <span :class="{ 'muted': !row.used_count }">{{ row.used_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120" align="center">
        <template slot-scope="{ row }">
          <el-switch :value="row.active" @change="value => handleToggle(row, value)" />
          <span class="switch-label">{{ row.active ? '启用' : '停用' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="160" align="center">
        <template slot-scope="{ row }">
          <el-button type="primary" size="mini" @click="handleUpdate(row)">修改</el-button>
          <el-button type="danger" size="mini" :disabled="row.used_count > 0" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      :title="dialogType === 'edit' ? '修改业务项' : '新增业务项'"
      :visible.sync="dialogVisible"
      width="480px"
    >
      <el-form ref="bizItemForm" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="业务项" prop="name">
          <el-input v-model="form.name" maxlength="20" placeholder="单个业务项，例如 解非 / 工商注销" />
        </el-form-item>
        <el-form-item label="默认单价">
          <el-input-number
            v-model="form.unit_price"
            style="width: 100%"
            :min="0"
            :precision="2"
            :step="50"
            controls-position="right"
          />
          <div class="hint">选中该业务项时自动带入单价，0 表示不参与自动合计</div>
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
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.active" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="补充说明，可不填" />
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
import { fetchBizItemList, createBizItem, updateBizItem, deleteBizItem } from '@/api/bizitem'
import refreshOnActivate from '@/mixins/refresh-on-activate'
import { formatMoney } from '@/constants/bizitem'

export default {
  name: 'BizItemConfig',
  mixins: [refreshOnActivate],
  data() {
    return {
      loading: false,
      saving: false,
      list: [],
      listQuery: { keyword: '' },
      dialogVisible: false,
      dialogType: 'create',
      form: this.emptyForm(),
      rules: {
        name: [
          { required: true, message: '请填写业务项名称', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (/[+＋、,，/／|]/.test(value || '')) {
                callback(new Error('业务项是单个项目，不要带 + / 、等分隔符'))
              } else {
                callback()
              }
            },
            trigger: 'blur'
          }
        ]
      }
    }
  },
  created() {
    this.getList()
  },
  methods: {
    formatMoney,
    refreshPage() {
      this.getList()
    },
    emptyForm() {
      return {
        id: undefined,
        name: '',
        unit_price: 0,
        sort: 0,
        active: true,
        remark: ''
      }
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchBizItemList(this.listQuery)
        this.list = data || []
      } finally {
        this.loading = false
      }
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.bizItemForm && this.$refs.bizItemForm.clearValidate()
      })
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = Object.assign(this.emptyForm(), row)
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.bizItemForm && this.$refs.bizItemForm.clearValidate()
      })
    },
    handleToggle(row, value) {
      updateBizItem({ id: row.id, active: value, only_toggle: true })
        .then(() => {
          row.active = value
          this.$message.success(value ? '已启用' : '已停用')
        })
        .catch(() => {})
    },
    handleDelete(row) {
      this.$confirm(`确认删除业务项「${row.name}」吗？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteBizItem({ id: row.id }))
        .then(() => {
          this.$message.success('删除成功')
          this.getList()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.bizItemForm.validate(valid => {
        if (!valid) return false
        const payload = {
          id: this.form.id,
          name: (this.form.name || '').trim(),
          unit_price: this.form.unit_price === undefined || this.form.unit_price === null ? 0 : this.form.unit_price,
          sort: this.form.sort === undefined ? 0 : this.form.sort,
          active: this.form.active !== false,
          remark: this.form.remark
        }
        const request = this.dialogType === 'edit' ? updateBizItem(payload) : createBizItem(payload)
        this.saving = true
        request
          .then(() => {
            this.$message.success(this.dialogType === 'edit' ? '保存成功' : '新增成功')
            this.dialogVisible = false
            this.getList()
          })
          .finally(() => {
            this.saving = false
          })
      })
    }
  }
}
</script>

<style lang="scss" scoped>
.tip {
  margin-bottom: 16px;
}

.keyword-input {
  width: 240px;
}

.muted {
  color: #c0c4cc;
}

.hint {
  font-size: 12px;
  color: #909399;
  line-height: 18px;
}

.switch-label {
  margin-left: 6px;
  font-size: 12px;
  color: #909399;
}
</style>
