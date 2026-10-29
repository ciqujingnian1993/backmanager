<template>
  <div class="app-container menu-page">
    <div class="page-header">
      <div>
        <h3 class="page-title">菜单管理</h3>
        <p class="page-desc">
          这里管理左侧菜单的入口配置：名称、图标、所属分组、排序和是否显示。
          页面本体由系统内置，删除菜单后该页面不再出现在侧边栏（直接输网址仍可访问，管理员可在此重新添加恢复）。
        </p>
      </div>
      <el-button type="primary" icon="el-icon-plus" @click="handleCreate">新增菜单</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="sortedList"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column label="菜单名称" min-width="180">
        <template slot-scope="{ row }">
          <svg-icon v-if="row.icon" :icon-class="row.icon" class="menu-icon" />
          <span>{{ row.title }}</span>
        </template>
      </el-table-column>
      <el-table-column label="路由地址" min-width="180">
        <template slot-scope="{ row }">
          <code class="menu-path">{{ row.path }}</code>
        </template>
      </el-table-column>
      <el-table-column label="所属分组" width="130" align="center">
        <template slot-scope="{ row }">
          <el-tag size="mini" :type="row.parent ? 'warning' : 'info'">
            {{ parentLabel(row.parent) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sort" label="排序" width="80" align="center" />
      <el-table-column label="显示" width="100" align="center">
        <template slot-scope="{ row }">
          <el-switch
            :value="row.visible"
            @change="value => toggleVisible(row, value)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template slot-scope="{ row }">
          <el-button type="primary" size="mini" @click="handleUpdate(row)">编辑</el-button>
          <el-button type="danger" size="mini" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      :title="dialogType === 'edit' ? '编辑菜单' : '新增菜单'"
      :visible.sync="dialogVisible"
      width="560px"
    >
      <el-form ref="menuForm" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="对应页面" prop="path">
          <el-select v-model="form.path" style="width: 100%" placeholder="选择系统内置页面">
            <el-option
              v-for="item in pageOptions"
              :key="item.path"
              :label="`${item.label}（${item.path}）`"
              :value="item.path"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="菜单名称" prop="title">
          <el-input v-model="form.title" placeholder="显示在侧边栏的名称" />
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="form.icon" style="width: 100%" clearable placeholder="选择图标">
            <el-option v-for="icon in iconOptions" :key="icon" :label="icon" :value="icon">
              <svg-icon :icon-class="icon" class="menu-icon" />
              <span class="icon-name">{{ icon }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="所属分组">
              <el-select v-model="form.parent" style="width: 100%">
                <el-option
                  v-for="item in parentOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序">
              <el-input-number
                v-model="form.sort"
                style="width: 100%"
                :min="0"
                :max="9999"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="是否显示">
          <el-switch v-model="form.visible" />
          <span class="form-tip">关闭后该菜单不出现在侧边栏，但已有权限的角色仍可通过网址访问</span>
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
import { fetchMenuList, createMenu, updateMenu, deleteMenu } from '@/api/menu'
import { PAGE_OPTIONS, ICON_OPTIONS, PARENT_OPTIONS } from '@/constants/pages'

export default {
  name: 'MenuManage',
  data() {
    return {
      loading: false,
      saving: false,
      list: [],
      pageOptions: PAGE_OPTIONS,
      iconOptions: ICON_OPTIONS,
      parentOptions: PARENT_OPTIONS,
      dialogVisible: false,
      dialogType: 'create',
      form: this.emptyForm(),
      rules: {
        path: [{ required: true, message: '请选择对应页面', trigger: 'change' }],
        title: [{ required: true, message: '请填写菜单名称', trigger: 'blur' }]
      }
    }
  },
  computed: {
    sortedList() {
      const groupOrder = path => (path === '' ? 0 : 1)
      return [...this.list].sort((a, b) => {
        const diff = groupOrder(a.parent) - groupOrder(b.parent)
        if (diff !== 0) return diff
        if (a.sort !== b.sort) return a.sort - b.sort
        return a.id - b.id
      })
    }
  },
  created() {
    this.getList()
  },
  methods: {
    emptyForm() {
      return {
        id: undefined,
        path: '',
        title: '',
        icon: 'money',
        parent: '',
        sort: 10,
        visible: true
      }
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchMenuList()
        this.list = data || []
      } finally {
        this.loading = false
      }
    },
    parentLabel(parent) {
      const found = this.parentOptions.find(item => item.value === (parent || ''))
      return found ? found.label : parent
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      const used = this.list.map(item => item.path)
      const free = PAGE_OPTIONS.find(item => used.indexOf(item.path) === -1)
      if (free) {
        this.form.path = free.path
        this.form.title = free.label
      }
      this.dialogVisible = true
      this.$nextTick(() => this.$refs.menuForm && this.$refs.menuForm.clearValidate())
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = {
        id: row.id,
        path: row.path,
        title: row.title,
        icon: row.icon,
        parent: row.parent || '',
        sort: row.sort,
        visible: row.visible
      }
      this.dialogVisible = true
      this.$nextTick(() => this.$refs.menuForm && this.$refs.menuForm.clearValidate())
    },
    toggleVisible(row, value) {
      updateMenu({
        id: row.id,
        path: row.path,
        title: row.title,
        icon: row.icon,
        parent: row.parent,
        sort: row.sort,
        visible: value
      })
        .then(() => {
          row.visible = value
          this.$message.success(value ? '已显示该菜单' : '已隐藏该菜单，重新登录后生效')
        })
        .catch(() => {})
    },
    handleDelete(row) {
      this.$confirm(`确认删除菜单「${row.title}」吗？删除后该页面不再出现在侧边栏。`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteMenu({ id: row.id }))
        .then(() => {
          this.$message.success('删除成功')
          this.getList()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.menuForm.validate(valid => {
        if (!valid) return false
        const payload = {
          id: this.form.id,
          path: this.form.path,
          title: this.form.title,
          icon: this.form.icon,
          parent: this.form.parent,
          sort: this.form.sort,
          visible: this.form.visible
        }
        const request = this.dialogType === 'edit' ? updateMenu(payload) : createMenu(payload)
        this.saving = true
        request
          .then(() => {
            this.$message.success('保存成功，重新登录后菜单生效')
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
.menu-page {
  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .page-title {
    margin: 0;
    font-size: 18px;
    color: #303133;
  }

  .page-desc {
    margin: 6px 0 0;
    color: #909399;
    font-size: 13px;
    max-width: 720px;
    line-height: 1.6;
  }

  .menu-icon {
    margin-right: 8px;
    color: #606266;
  }

  .menu-path {
    background: #f4f4f5;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 12px;
  }

  .icon-name {
    margin-left: 8px;
    color: #606266;
  }

  .form-tip {
    color: #909399;
    font-size: 12px;
    margin-left: 10px;
  }
}
</style>
