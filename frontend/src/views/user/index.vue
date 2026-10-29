<template>
  <div class="app-container user-page">
    <div class="page-header">
      <div>
        <h3 class="page-title">用户管理</h3>
        <p class="page-desc">这里的账号就是登录后台的账号，角色决定他能看到哪些菜单。</p>
      </div>
      <el-button type="primary" icon="el-icon-plus" @click="handleCreate">新增用户</el-button>
    </div>

    <div class="filter-container">
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索账号 / 姓名"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-select
        v-model="listQuery.role"
        class="filter-item"
        placeholder="按角色筛选"
        clearable
        @change="handleFilter"
      >
        <el-option
          v-for="item in roleOptions"
          :key="item.key"
          :label="item.name"
          :value="item.key"
        />
      </el-select>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">刷新</el-button>
      <el-button class="filter-item" icon="el-icon-setting" @click="$router.push('/system/role')">
        角色权限
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
      <el-table-column label="ID" prop="id" width="70" align="center" />
      <el-table-column label="账号" min-width="130">
        <template slot-scope="{ row }">
          <span class="username">{{ row.username }}</span>
          <el-tag v-if="row.id === currentUserId" size="mini" type="success" class="self-tag">我</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="姓名" min-width="120" />
      <el-table-column label="角色" min-width="180">
        <template slot-scope="{ row }">
          <el-tag
            v-for="role in row.roles"
            :key="role"
            size="mini"
            :type="roleType(role)"
            class="role-tag"
          >
            {{ roleName(role) }}
          </el-tag>
          <span v-if="!row.roles.length" class="muted">未分配</span>
        </template>
      </el-table-column>
      <el-table-column prop="introduction" label="备注" min-width="180" />
      <el-table-column prop="created" label="创建时间" width="170" />
      <el-table-column label="操作" width="300" align="center">
        <template slot-scope="{ row }">
          <el-button type="primary" size="mini" @click="handleUpdate(row)">编辑</el-button>
          <el-button size="mini" @click="handleResetPassword(row)">重置密码</el-button>
          <el-button
            type="danger"
            size="mini"
            :disabled="row.id === currentUserId"
            @click="handleDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      :page.sync="listQuery.page"
      :limit.sync="listQuery.limit"
      @pagination="getList"
    />

    <el-dialog
      :title="dialogType === 'edit' ? '编辑用户' : '新增用户'"
      :visible.sync="dialogVisible"
      width="560px"
    >
      <el-form ref="userForm" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="登录账号" prop="username">
          <el-input
            v-model="form.username"
            :disabled="dialogType === 'edit'"
            placeholder="英文或数字，登录用"
          />
        </el-form-item>
        <el-form-item v-if="dialogType === 'create'" label="初始密码" prop="password">
          <el-input v-model="form.password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="用于界面显示" />
        </el-form-item>
        <el-form-item label="角色" prop="roles">
          <el-select v-model="form.roles" style="width: 100%" multiple placeholder="可多选">
            <el-option
              v-for="item in roleOptions"
              :key="item.key"
              :label="`${item.name}（${item.key}）`"
              :value="item.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.introduction" type="textarea" :rows="2" placeholder="可不填" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'edit'" label="修改密码">
          <el-input v-model="form.password" show-password placeholder="留空表示不修改密码" />
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
import Pagination from '@/components/Pagination'
import { fetchUserList, createUser, updateUser, deleteUser } from '@/api/user-manage'

export default {
  name: 'UserManage',
  components: { Pagination },
  data() {
    return {
      loading: false,
      saving: false,
      total: 0,
      list: [],
      roleOptions: [],
      listQuery: {
        page: 1,
        limit: 20,
        keyword: '',
        role: ''
      },
      dialogVisible: false,
      dialogType: 'create',
      form: this.emptyForm(),
      rules: {
        username: [{ required: true, message: '请填写登录账号', trigger: 'blur' }],
        password: [{ required: true, message: '请填写初始密码', trigger: 'blur' }, { min: 6, message: '密码至少 6 位', trigger: 'blur' }],
        name: [{ required: true, message: '请填写姓名', trigger: 'blur' }],
        roles: [{ required: true, type: 'array', message: '请至少选择一个角色', trigger: 'change' }]
      }
    }
  },
  computed: {
    currentUserId() {
      return this.$store.getters.userId
    }
  },
  created() {
    this.getList()
  },
  methods: {
    emptyForm() {
      return {
        id: undefined,
        username: '',
        password: '',
        name: '',
        roles: [],
        introduction: ''
      }
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchUserList(this.listQuery)
        this.list = data.items || []
        this.total = data.total || 0
        if (data.roles && data.roles.length) this.roleOptions = data.roles
      } finally {
        this.loading = false
      }
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.form.roles = []
      this.dialogVisible = true
      this.$nextTick(() => this.$refs.userForm && this.$refs.userForm.clearValidate())
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      this.form = {
        id: row.id,
        username: row.username,
        password: '',
        name: row.name,
        roles: [...(row.roles || [])],
        introduction: row.introduction
      }
      this.dialogVisible = true
      this.$nextTick(() => this.$refs.userForm && this.$refs.userForm.clearValidate())
    },
    handleResetPassword(row) {
      this.$prompt(`给「${row.name || row.username}」设置新密码`, '重置密码', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputType: 'password',
        inputPlaceholder: '至少 6 位',
        inputValidator: value => (value && value.length >= 6 ? true : '密码至少 6 位')
      })
        .then(({ value }) => updateUser({ id: row.id, password: value }))
        .then(() => {
          this.$message.success('密码已重置，该用户需要重新登录')
        })
        .catch(() => {})
    },
    handleDelete(row) {
      this.$confirm(`确认删除账号「${row.username}」吗？删除后无法登录。`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteUser({ id: row.id }))
        .then(() => {
          this.$message.success('删除成功')
          this.getList()
        })
        .catch(() => {})
    },
    submitForm() {
      this.$refs.userForm.validate(valid => {
        if (!valid) return false
        const isEdit = this.dialogType === 'edit'
        const payload = {
          id: this.form.id,
          username: this.form.username,
          name: this.form.name,
          roles: this.form.roles,
          introduction: this.form.introduction
        }
        if (this.form.password) payload.password = this.form.password
        const request = isEdit ? updateUser(payload) : createUser(payload)
        this.saving = true
        request
          .then(() => {
            this.$message.success(isEdit ? '保存成功' : '用户已创建')
            this.dialogVisible = false
            this.getList()
          })
          .finally(() => {
            this.saving = false
          })
      })
    },
    roleName(key) {
      const found = this.roleOptions.find(item => item.key === key)
      return found ? found.name : key
    },
    roleType(key) {
      return key === 'admin' ? 'danger' : key === 'editor' ? 'warning' : 'info'
    }
  }
}
</script>

<style lang="scss" scoped>
.user-page {
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
  }

  .keyword-input {
    width: 220px;
  }

  .username {
    font-weight: 600;
  }

  .self-tag {
    margin-left: 6px;
  }

  .role-tag {
    margin-right: 6px;
  }

  .muted {
    color: #c0c4cc;
  }
}
</style>
