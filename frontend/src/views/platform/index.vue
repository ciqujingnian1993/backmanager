<template>
  <div class="app-container">
    <div class="filter-container">
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索平台名称 / 备注"
        clearable
        @keyup.enter.native="getList"
      />
      <el-button class="filter-item" type="primary" icon="el-icon-search" @click="getList">
        查询
      </el-button>
      <el-button class="filter-item" type="primary" icon="el-icon-plus" @click="handleCreate">
        新增平台
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
      <el-table-column prop="name" label="平台名称" min-width="160">
        <template slot-scope="{ row }">
          <el-tag size="medium" effect="plain">{{ row.name }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="order_count" label="关联订单数" width="120" align="center">
        <template slot-scope="{ row }">
          <span :class="{ 'muted': !row.order_count }">{{ row.order_count }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="170" align="center">
        <template slot-scope="{ row }">
          <el-button type="primary" size="mini" @click="handleUpdate(row)">修改</el-button>
          <el-button type="danger" size="mini" :disabled="row.order_count > 0" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      :title="dialogType === 'edit' ? '修改平台' : '新增平台'"
      :visible.sync="dialogVisible"
      width="480px"
    >
      <el-form ref="platformForm" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="平台名称" prop="name">
          <el-input v-model="form.name" maxlength="20" placeholder="例如 微信 / 抖音" />
        </el-form-item>
        <el-form-item label="排序" prop="sort">
          <el-input-number
            v-model="form.sort"
            style="width: 100%"
            :min="0"
            :precision="0"
            :step="10"
            controls-position="right"
          />
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
import { fetchPlatformList, createPlatform, updatePlatform, deletePlatform } from '@/api/platform'

export default {
  name: 'PlatformManage',
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
        name: [{ required: true, message: '请填写平台名称', trigger: 'blur' }]
      }
    }
  },
  created() {
    this.getList()
  },
  methods: {
    emptyForm() {
      return {
        id: undefined,
        name: '',
        sort: 0,
        remark: ''
      }
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchPlatformList(this.listQuery)
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
        this.$refs.platformForm && this.$refs.platformForm.clearValidate()
      })
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = Object.assign(this.emptyForm(), row, { old_name: row.name })
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.platformForm && this.$refs.platformForm.clearValidate()
      })
    },
    handleDelete(row) {
      this.$confirm(`确认删除平台「${row.name}」吗？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deletePlatform({ id: row.id }))
        .then(() => {
          this.$message.success('删除成功')
          this.getList()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.platformForm.validate(valid => {
        if (!valid) return false
        const payload = {
          id: this.form.id,
          name: this.form.name,
          sort: this.form.sort === undefined ? 0 : this.form.sort,
          remark: this.form.remark
        }
        if (this.dialogType === 'edit') payload.old_name = this.form.old_name
        const request = this.dialogType === 'edit' ? updatePlatform(payload) : createPlatform(payload)
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
.keyword-input {
  width: 220px;
}

.muted {
  color: #c0c4cc;
}
</style>
