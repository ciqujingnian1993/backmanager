<template>
  <div class="app-container role-page">
    <div class="page-header">
      <div>
        <h3 class="page-title">角色管理</h3>
        <p class="page-desc">
          角色决定用户登录后能看到哪些菜单。可以自己新增角色、勾选它能看到哪些菜单；
          管理员（admin）固定拥有全部权限，不受此处限制。
        </p>
      </div>
      <el-button type="primary" icon="el-icon-plus" @click="handleCreate">新增角色</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="list"
      border
      fit
      highlight-current-row
      style="width: 100%"
    >
      <el-table-column label="角色标识" width="130">
        <template slot-scope="{ row }">
          <code class="role-key">{{ row.key }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="角色名称" width="150" />
      <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
      <el-table-column label="可访问菜单" min-width="260">
        <template slot-scope="{ row }">
          <template v-if="row.key === 'admin'">
            <el-tag type="danger" size="mini">全部菜单</el-tag>
          </template>
          <template v-else>
            <el-tag
              v-for="path in routePaths(row.routes)"
              :key="path"
              size="mini"
              class="page-tag"
            >
              {{ pageLabel(path) }}
            </el-tag>
            <span v-if="!routePaths(row.routes).length" class="muted">未配置</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="用户数" width="90" align="center">
        <template slot-scope="{ row }">{{ row.user_count || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center">
        <template slot-scope="{ row }">
          <el-button
            type="primary"
            size="mini"
            :disabled="row.key === 'admin'"
            @click="handleUpdate(row)"
          >
            编辑
          </el-button>
          <el-button
            type="danger"
            size="mini"
            :disabled="row.key === 'admin'"
            @click="handleDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      :title="dialogType === 'edit' ? `编辑角色 · ${form.name}` : '新增角色'"
      :visible.sync="dialogVisible"
      width="580px"
    >
      <el-form ref="roleForm" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="角色标识" prop="key">
          <el-input
            v-model="form.key"
            :disabled="dialogType === 'edit'"
            placeholder="英文，如 staff，创建后不可改"
          />
        </el-form-item>
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="如 普通员工" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="菜单权限">
          <div class="perm-box">
            <div v-for="group in pageGroups" :key="group.title" class="perm-group">
              <div class="perm-title">{{ group.title }}</div>
              <el-checkbox
                v-for="page in group.pages"
                :key="page.path"
                :value="checked[page.path] === true"
                @change="value => toggle(page.path, value)"
              >
                {{ page.label }}
                <span v-if="!page.visible" class="perm-hidden">（已隐藏）</span>
              </el-checkbox>
            </div>
            <div v-if="!pageGroups.length" class="perm-tip">还没有菜单，先去「菜单管理」里添加。</div>
          </div>
          <div class="perm-tip">
            没勾选的菜单，该角色登录后左侧看不到，直接输网址也打不开。菜单本身在「菜单管理」里维护。
          </div>
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { fetchRoles, createRole, updateRole, deleteRole } from '@/api/permission'
import { fetchMenuList } from '@/api/menu'

const PARENT_LABEL = {
  '': '业务菜单',
  '/system': '系统管理'
}

export default {
  name: 'RolePermission',
  data() {
    return {
      loading: false,
      saving: false,
      list: [],
      menus: [],
      dialogVisible: false,
      dialogType: 'create',
      form: this.emptyForm(),
      checked: {},
      rules: {
        key: [
          { required: true, message: '请填写角色标识', trigger: 'blur' },
          { pattern: /^[a-zA-Z][a-zA-Z0-9_-]*$/, message: '以字母开头，只能包含字母、数字、下划线', trigger: 'blur' }
        ],
        name: [{ required: true, message: '请填写角色名称', trigger: 'blur' }]
      }
    }
  },
  computed: {
    // 菜单表 → 勾选分组（顶级业务菜单 / 系统管理）
    pageGroups() {
      const groups = []
      const buckets = {}
      this.menus.forEach(menu => {
        const parent = menu.parent || ''
        if (!buckets[parent]) buckets[parent] = []
        buckets[parent].push(menu)
      })
      Object.keys(buckets)
        .sort((a, b) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)))
        .forEach(parent => {
          groups.push({
            title: PARENT_LABEL[parent] || parent,
            pages: buckets[parent]
              .slice()
              .sort((a, b) => a.sort - b.sort)
              .map(menu => ({ path: menu.path, label: menu.title, visible: menu.visible }))
          })
        })
      return groups
    },
    menuPathSet() {
      return new Set(this.menus.map(menu => menu.path))
    }
  },
  created() {
    this.getList()
    this.getMenus()
  },
  methods: {
    emptyForm() {
      return { key: '', name: '', description: '' }
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchRoles()
        this.list = data || []
      } finally {
        this.loading = false
      }
    },
    async getMenus() {
      const { data } = await fetchMenuList()
      this.menus = data || []
    },
    // 把后端存的 routes 展开成菜单 path 列表（父级 + 子级）
    routePaths(routes) {
      const result = []
      const walk = (items, prefix) => {
        (items || []).forEach(item => {
          if (!item || !item.path) return
          const full = this.joinPath(prefix, item.path)
          if (this.menuPathSet.has(full)) result.push(full)
          if (item.children && item.children.length) {
            walk(item.children, full)
          }
        })
      }
      walk(routes, '')
      if (!result.length) {
        (routes || []).forEach(item => {
          if (item && this.menuPathSet.has(item.path)) result.push(item.path)
        })
      }
      return result
    },
    pageLabel(path) {
      const found = this.menus.find(menu => menu.path === path)
      return found ? found.title : path
    },
    joinPath(parent, child) {
      if (!parent || parent === '/') return '/' + String(child).replace(/^\/+/, '')
      return ('/' + parent + '/' + child).replace(/\/+/g, '/')
    },
    toggle(path, value) {
      this.$set(this.checked, path, !!value)
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.checked = {}
      this.dialogVisible = true
      this.$nextTick(() => this.$refs.roleForm && this.$refs.roleForm.clearValidate())
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = { key: row.key, name: row.name, description: row.description || '' }
      const checked = {}
      this.routePaths(row.routes).forEach(path => { checked[path] = true })
      this.checked = checked
      this.dialogVisible = true
      this.$nextTick(() => this.$refs.roleForm && this.$refs.roleForm.clearValidate())
    },
    buildRoutes() {
      return Object.keys(this.checked)
        .filter(path => this.checked[path])
        .map(path => ({ path, meta: { title: this.pageLabel(path) }}))
    },
    handleDelete(row) {
      this.$confirm(`确认删除角色「${row.name}」吗？使用该角色的账号将失去对应菜单权限。`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteRole(row.key))
        .then(() => {
          this.$message.success('删除成功')
          this.getList()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.roleForm.validate(valid => {
        if (!valid) return false
        const routes = this.buildRoutes()
        if (!routes.length) {
          this.$message.warning('请至少勾选一个菜单')
          return false
        }
        const payload = {
          key: this.form.key.trim(),
          name: this.form.name,
          description: this.form.description,
          routes
        }
        const request = this.dialogType === 'edit'
          ? updateRole(payload.key, payload)
          : createRole(payload)
        this.saving = true
        request
          .then(() => {
            this.$message.success('保存成功，相关账号重新登录后生效')
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
.role-page {
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
    max-width: 680px;
    line-height: 1.6;
  }

  .role-key {
    background: #f4f4f5;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 12px;
  }

  .page-tag {
    margin: 0 6px 6px 0;
  }

  .muted {
    color: #c0c4cc;
  }

  .perm-box {
    width: 100%;
    background: #f7f8fa;
    border-radius: 4px;
    padding: 12px 14px;
  }

  .perm-group + .perm-group {
    margin-top: 10px;
  }

  .perm-title {
    font-size: 13px;
    color: #909399;
    margin-bottom: 4px;
  }

  .perm-hidden {
    color: #c0c4cc;
    font-size: 12px;
  }

  .perm-tip {
    color: #909399;
    font-size: 12px;
    line-height: 1.6;
    margin-top: 6px;
  }
}
</style>
