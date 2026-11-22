<template>
  <div class="app-container account-page">
    <el-row :gutter="16" class="summary-row">
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">总收入{{ monthSuffix }}</div>
          <div class="summary-value revenue">￥{{ money(summary.done_revenue) }}</div>
          <div class="summary-tip">已完成 {{ summary.done_count }} 单 · 在途 ￥{{ money(inflightRevenue) }} 未计入</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">订单成本{{ monthSuffix }}</div>
          <div class="summary-value cost">￥{{ money(summary.done_cost) }}</div>
          <div class="summary-tip">已完成订单的成本口径</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">订单毛利{{ monthSuffix }}</div>
          <div class="summary-value profit">￥{{ money(summary.done_profit) }}</div>
          <div class="summary-tip">已完成收入 − 已完成成本</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :lg="6">
        <div class="summary-card">
          <div class="summary-label">待定笔数{{ monthSuffix }}</div>
          <div class="summary-value pending">{{ summary.pending }}</div>
          <div class="summary-tip">未填金额的订单</div>
        </div>
      </el-col>
    </el-row>

    <div class="filter-container">
      <el-date-picker
        v-model="listQuery.month"
        class="filter-item"
        type="month"
        placeholder="全部月份"
        format="yyyy-MM"
        value-format="yyyy-MM"
        :clearable="true"
        @change="handleFilter"
      />
      <el-button
        class="filter-item"
        :type="listQuery.month ? 'default' : 'primary'"
        size="small"
        @click="showAllMonths"
      >
        全部月份
      </el-button>
      <el-input
        v-model="listQuery.keyword"
        class="filter-item keyword-input"
        placeholder="搜索订单编号 / 客户 / 手机号 / 微信 / 执照 / 法人"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-select
        v-model="listQuery.status"
        class="filter-item"
        placeholder="订单状态"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select
        v-model="listQuery.biz_status"
        class="filter-item"
        placeholder="工商状态"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in bizStatusOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select
        v-model="listQuery.tax_status"
        class="filter-item"
        placeholder="税务状态"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in taxStatusOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select
        v-model="listQuery.platform"
        class="filter-item"
        placeholder="来源平台"
        clearable
        @change="handleFilter"
      >
        <el-option v-for="item in platformOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-button
        class="filter-item"
        type="primary"
        icon="el-icon-plus"
        @click="handleCreate"
      >
        新增订单
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
    </div>

    <div class="table-panel">
      <div class="panel-head">
        <span class="panel-title">订单列表</span>
        <span class="panel-count">共 {{ total }} 单</span>
      </div>
      <el-table
        v-loading="loading"
        :data="list"
        :empty-text="filtering ? '当前筛选条件下没有订单，试试切到「全部月份」' : '还没有订单'"
        border
        fit
        highlight-current-row
        style="width: 100%"
      >
        <el-table-column type="expand">
          <template slot-scope="{ row }">
            <order-items-table :details="row.details" />
          </template>
        </el-table-column>
        <el-table-column label="订单编号" width="148" align="center">
          <template slot-scope="{ row }">
            <span v-if="row.order_no" class="order-no-text">{{ row.order_no }}</span>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="biz_date" label="日期" width="88" align="center" />
        <el-table-column prop="category" label="行业" width="92" align="center" />
        <el-table-column prop="client" label="客户" min-width="100" show-overflow-tooltip />
        <el-table-column label="手机号" width="116">
          <template slot-scope="{ row }">
            <span v-if="row.phone">{{ row.phone }}</span>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column label="客户微信" min-width="120" show-overflow-tooltip>
          <template slot-scope="{ row }">
            <span v-if="row.wechat">{{ row.wechat }}</span>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="78" align="center">
          <template slot-scope="{ row }">
            <el-tag v-if="row.platform" size="mini" effect="plain">{{ row.platform }}</el-tag>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column label="执照" width="100" align="center">
          <template slot-scope="{ row }">
            <el-button type="text" size="mini" @click="handleDetail(row)">
              {{ row.license_count }} 个（完成 {{ row.done_count }}）
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="items" label="业务项" min-width="108" show-overflow-tooltip />
        <el-table-column label="收入" width="82" align="center">
          <template slot-scope="{ row }">{{ amount(row.revenue) }}</template>
        </el-table-column>
        <el-table-column label="成本" width="82" align="center">
          <template slot-scope="{ row }">
            <span class="cost-cell">{{ amount(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template slot-scope="{ row }">
            <el-tag :type="statusType(row.status)" size="mini">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="完成时间" width="138" align="center">
          <template slot-scope="{ row }">{{ completedText(row.completed_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center" fixed="right">
          <template slot-scope="{ row }">
            <el-button type="text" size="mini" @click="handleDetail(row)">详情</el-button>
            <el-button type="text" size="mini" @click="handleUpdate(row)">编辑</el-button>
            <el-button
              type="text"
              size="mini"
              class="warning-text"
              :disabled="!canCancel(row)"
              :title="cancelTip(row)"
              @click="openCancel(row)"
            >取消订单</el-button>
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
    </div>

    <el-dialog
      :title="dialogTitle"
      :visible.sync="dialogVisible"
      width="1120px"
      top="5vh"
    >
      <el-form
        ref="accountForm"
        :model="form"
        :rules="rules"
        label-width="104px"
        class="order-form"
      >
        <div class="form-section-title">订单信息</div>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="业务日期" prop="biz_date">
              <el-date-picker
                v-model="form.biz_date"
                style="width: 100%"
                type="date"
                format="MM/dd"
                value-format="MM/dd"
                placeholder="选择日期"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="行业" prop="category">
              <el-select
                v-model="form.category"
                style="width: 100%"
                allow-create
                filterable
                default-first-option
                placeholder="选择或输入行业"
              >
                <el-option
                  v-for="item in categoryOptions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="来源平台" prop="platform">
              <el-select
                v-model="form.platform"
                style="width: 100%"
                clearable
                filterable
                placeholder="可不选"
              >
                <el-option v-for="item in platformOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="客户" prop="client">
              <el-input v-model="form.client" placeholder="例如 厦门个体户" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="form.phone" maxlength="11" placeholder="11 位手机号" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="客户微信" prop="wechat">
              <el-input v-model="form.wechat" maxlength="64" clearable placeholder="客户的微信号，可不填" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="平台订单编号">
              <el-input
                v-model="form.platform_order_no"
                class="platform-order-no-input"
                maxlength="64"
                clearable
                placeholder="平台后台的订单号，可不填"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="2"
            placeholder="订单层面的补充说明，可不填"
          />
        </el-form-item>
        <el-form-item label="身份证照片">
          <div class="photo-field">
            <PhotoUploader v-model="form.id_photos" />
            <span class="photo-tip">客户身份证正反面，可传多张，编辑订单时可补传</span>
          </div>
        </el-form-item>

        <div class="form-section-title">
          执照明细与任务
          <span class="optional-tip">一个客户可挂多个执照，每个执照单独一条任务、单独跟进度</span>
          <el-button class="add-detail-btn" type="primary" size="mini" icon="el-icon-plus" @click="addDetail">
            添加执照
          </el-button>
        </div>

        <div
          v-for="(detail, index) in form.details"
          :key="index"
          class="detail-card"
          :class="{ 'is-collapsed': detail.__collapsed }"
        >
          <div class="detail-card-head">
            <i
              class="collapse-btn"
              :class="detail.__collapsed ? 'el-icon-arrow-right' : 'el-icon-arrow-down'"
              @click="toggleDetail(detail)"
            />
            <span class="detail-card-index">{{ index + 1 }}</span>
            <span class="detail-card-title">执照 {{ index + 1 }}</span>
            <span v-if="detail.license_name" class="detail-card-sub">{{ detail.license_name }}</span>
            <span v-if="detail.__collapsed" class="detail-card-sum">
              <span v-if="detail.items" class="sum-item">{{ detail.items }}</span>
              <span v-if="detail.__tasks && detail.__tasks.length" class="sum-item">
                子任务 {{ subtaskStat(detail).done }}/{{ subtaskStat(detail).total }}
              </span>
              <span v-if="detail.revenue" class="sum-item">收入 ¥{{ formatMoney(detail.revenue) }}</span>
              <span v-if="!detail.items && !detail.revenue" class="sum-empty">未填写业务项</span>
            </span>
            <div class="detail-card-tools">
              <span class="tool-label">执照照片</span>
              <PhotoUploader v-model="detail.license_photos" size="mini" />
              <span class="tool-label">任务状态</span>
              <el-select
                v-model="detail.status"
                size="mini"
                class="status-select"
                @change="value => onDetailStatusChange(detail, value)"
              >
                <el-option v-for="item in itemStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button
                type="text"
                class="danger-text delete-btn"
                :disabled="form.details.length === 1"
                @click="removeDetail(index)"
              >
                删除
              </el-button>
            </div>
          </div>

          <div v-show="!detail.__collapsed" class="detail-card-body">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="执照名称">
                  <el-input v-model="detail.license_name" placeholder="营业执照上的名称" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item
                  label="统一信用编码"
                  :prop="'details.' + index + '.credit_code'"
                  :rules="detailRules.credit_code"
                >
                  <el-input
                    v-model="detail.credit_code"
                    maxlength="18"
                    placeholder="18 位统一社会信用代码"
                    clearable
                    @input="detail.credit_code = (detail.credit_code || '').toUpperCase()"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="法人姓名">
                  <el-input v-model="detail.legal_person" placeholder="法定代表人姓名" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label="法人身份证号"
                  :prop="'details.' + index + '.legal_id'"
                  :rules="detailRules.legal_id"
                >
                  <el-input
                    v-model="detail.legal_id"
                    maxlength="18"
                    placeholder="18 位身份证号"
                    clearable
                    @input="detail.legal_id = (detail.legal_id || '').toUpperCase()"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label="法人手机号"
                  :prop="'details.' + index + '.legal_phone'"
                  :rules="detailRules.legal_phone"
                >
                  <el-input
                    v-model="detail.legal_phone"
                    placeholder="11 位手机号"
                    clearable
                    @input="detail.legal_phone = normalizePhone(detail.legal_phone)"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="16">
                <el-form-item label="工商状态">
                  <!-- 注意：el-checkbox-group 的 change 回传的是未更新的旧值，这里必须用 input -->
                  <el-checkbox-group
                    :value="splitBizStatus(detail.biz_status)"
                    class="biz-status-group"
                    @input="values => setBizStatus(detail, values)"
                  >
                    <el-checkbox v-for="item in bizStatusOptions" :key="item" :label="item">{{ item }}</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="税务状态">
                  <el-select v-model="detail.tax_status" style="width: 100%" clearable placeholder="可不选">
                    <el-option v-for="item in taxStatusOptions" :key="item" :label="item" :value="item" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="24">
                <el-form-item label="业务项">
                  <el-select
                    :value="detail.item_list"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    popper-class="biz-item-dropdown"
                    style="width: 100%"
                    placeholder="从业务项配置里多选，也可直接输入新项"
                    @change="value => handleItemsChange(detail, value)"
                  >
                    <el-option
                      v-for="item in bizItemOptions"
                      :key="item.name"
                      :label="item.name"
                      :value="item.name"
                    >
                      <span class="option-name">{{ item.name }}</span>
                      <span v-if="item.unit_price" class="option-price">¥{{ formatMoney(item.unit_price) }}</span>
                    </el-option>
                  </el-select>
                  <div v-if="detail.item_list && detail.item_list.length > 1" class="items-preview">
                    组合后：{{ joinItems(detail.item_list) }}
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
            <!-- 子任务：每个业务项拆成一条独立子任务，各自办结；这里直接看/改状态，不用跳进度页 -->
            <el-form-item label="子任务">
              <div class="subtask-box">
                <div class="subtask-head">
                  <span class="subtask-tip">按业务项自动拆成独立子任务，可逐项定价、逐项办结</span>
                  <span v-if="detail.__tasks && detail.__tasks.length" class="subtask-count">
                    合计 ¥{{ formatMoney(subtaskSum(detail)) }} · 已办结 {{ subtaskStat(detail).done }}/{{ subtaskStat(detail).total }}
                    <span v-if="subtaskStat(detail).cancelled"> · 已取消 {{ subtaskStat(detail).cancelled }}</span>
                  </span>
                </div>
                <div v-if="!(detail.__tasks && detail.__tasks.length)" class="subtask-empty">
                  还没选业务项；选好业务项后会自动拆出子任务
                </div>
                <div v-else class="subtask-list">
                  <div
                    v-for="task in detail.__tasks"
                    :key="task.id || ('new-' + task.name)"
                    class="subtask-row"
                    :class="{
                      'is-done': task.status === 'done',
                      'is-cancelled': task.status === 'cancelled',
                      'is-draft': !task.id
                    }"
                  >
                    <span class="st-line" :class="'is-' + (task.line || 'other')">{{ taskLineLabel(task.line) }}</span>
                    <span class="st-name" :title="task.name">{{ task.name }}</span>
                    <el-tag v-if="task.source === 'manual'" size="mini" type="info" effect="plain">手工</el-tag>
                    <span class="st-flex" />
                    <!-- 每条子任务可以单独指定跟进人；留空表示跟随主任务 / 按跟进记录推断 -->
                    <el-select
                      :value="task.owner || ''"
                      size="mini"
                      class="st-owner"
                      clearable
                      filterable
                      placeholder="跟进人"
                      :disabled="!canEditTask(task)"
                      :title="taskLockTip(task) || taskOwnerTip(task)"
                      @change="value => changeTaskOwner(task, value)"
                    >
                      <el-option
                        v-for="opt in ownerOptions"
                        :key="opt.username"
                        :label="opt.name"
                        :value="opt.username"
                      >
                        <span class="st-owner-opt">
                          <span class="owner-dot" :style="{ background: avatarColor(opt.name) }">{{ initial(opt.name) }}</span>
                          <span>{{ opt.name }}</span>
                        </span>
                      </el-option>
                    </el-select>
                    <div class="st-amount">
                      <span class="st-currency">¥</span>
                      <el-input-number
                        :value="task.amount"
                        :controls="false"
                        :min="0"
                        :precision="2"
                        size="mini"
                        class="st-amount-input"
                        @change="value => changeTaskAmount(detail, task, value)"
                      />
                    </div>
                    <el-select
                      :value="task.status"
                      size="mini"
                      class="st-status"
                      :disabled="!canEditTask(task)"
                      :title="taskLockTip(task)"
                      @change="value => changeTaskStatus(detail, task, value)"
                    >
                      <el-option
                        v-for="opt in taskStatusOptions"
                        :key="opt.value"
                        :label="opt.label"
                        :value="opt.value"
                      />
                    </el-select>
                    <i
                      v-if="task.id && task.source === 'manual'"
                      class="el-icon-close st-del"
                      title="删除这条手工子任务"
                      @click="removeTask(detail, task)"
                    />
                  </div>
                </div>
                <div v-if="!detail.id" class="subtask-foot-tip">子任务随订单一并保存；单价合计自动填到下面「单价」，× 数量得收入</div>
                <div v-if="detail.id" class="subtask-add">
                  <el-input
                    v-model="detail.__taskName"
                    size="mini"
                    placeholder="补一条业务项里没有的子任务，如：银行开户"
                    @keyup.enter.native="addTask(detail)"
                  />
                  <el-button size="mini" type="text" icon="el-icon-plus" @click="addTask(detail)">添加</el-button>
                </div>
              </div>
            </el-form-item>
            <div class="money-row">
              <span class="money-row-label">费用</span>
              <div class="money-panel">
                <div class="money-cell">
                  <span class="money-label">单价</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.unit_price"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div class="money-cell">
                  <span class="money-label">数量</span>
                  <div class="money-input">
                    <el-input-number
                      v-model="detail.quantity"
                      :controls="false"
                      :min="1"
                      :precision="0"
                      @change="applyTaskAmounts(detail)"
                    />
                  </div>
                </div>
                <div class="money-cell">
                  <span class="money-label">收入</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.revenue"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div class="money-cell">
                  <span class="money-label">成本</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.cost"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div class="money-cell money-cell-profit">
                  <span class="money-label">利润</span>
                  <div class="money-input">
                    <i class="money-unit">¥</i>
                    <el-input-number
                      v-model="detail.profit"
                      :controls="false"
                      :min="0"
                      :precision="2"
                      placeholder="0.00"
                    />
                  </div>
                </div>
              </div>
            </div>
            <el-form-item label="备注">
              <el-input v-model="detail.remark" placeholder="这个执照的特殊说明，可不填" clearable />
            </el-form-item>
          </div>
        </div>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </div>
    </el-dialog>

    <!-- 取消订单：退款也在这一步做（取消时把已收的钱退给客户），不再单开一个「退款」入口 -->
    <el-dialog title="取消订单" :visible.sync="cancelVisible" width="580px" append-to-body>
      <div v-if="cancelRow" class="op-head">
        <span class="op-no">{{ cancelRow.order_no || '—' }}</span>
        <el-tag size="mini" effect="plain">{{ cancelRow.client || '未填客户' }}</el-tag>
        <span class="op-meta">订单金额 <b>¥{{ amount(cancelRow.revenue) }}</b></span>
      </div>

      <div class="op-block">
        <div class="op-block-head">
          <span>取消范围</span>
          <el-button type="text" size="mini" @click="selectAllCancelItems">全选</el-button>
        </div>
        <div v-if="!cancellableItems.length" class="op-empty">这单没有可取消的任务（都已取消或已退款）</div>
        <el-checkbox-group v-model="cancelForm.item_ids" class="op-items">
          <el-checkbox v-for="item in cancellableItems" :key="item.id" :label="item.id" class="op-item">
            <span class="oi-license">{{ item.license_name || '未填执照' }}</span>
            <span class="oi-items">{{ item.items || '—' }}</span>
            <span class="oi-money">¥{{ amount(item.revenue) }}</span>
          </el-checkbox>
        </el-checkbox-group>
      </div>

      <el-form :model="cancelForm" label-width="92px" class="op-form">
        <el-form-item label="退款给客户">
          <el-checkbox v-model="cancelForm.refund">同时把已收的钱退给客户</el-checkbox>
          <div v-if="cancelForm.refund" class="refund-box">
            <div class="refund-line">
              <span class="rl-label">退款金额</span>
              <el-input-number
                v-model="cancelForm.refundAmount"
                :min="0"
                :max="cancelRefundMax"
                :precision="2"
                :step="100"
                controls-position="right"
                style="width: 168px"
              />
              <el-button
                type="text"
                size="mini"
                :disabled="!cancelRefundMax"
                @click="cancelForm.refundAmount = cancelRefundMax"
              >按所选金额全退（¥{{ amount(cancelRefundMax) }}）</el-button>
            </div>
            <div class="refund-line">
              <span class="rl-label">退款方式</span>
              <el-select v-model="cancelForm.refundMethod" clearable placeholder="可不选" style="width: 168px">
                <el-option label="微信" value="微信" />
                <el-option label="支付宝" value="支付宝" />
                <el-option label="银行转账" value="银行转账" />
                <el-option label="现金" value="现金" />
              </el-select>
            </div>
            <div class="refund-hint">
              退款会记一笔「成本管理」的现金流出，订单收入同步冲减；财务报表不会重复扣这笔支出。
            </div>
          </div>
        </el-form-item>
        <el-form-item label="取消原因" required>
          <el-select
            v-model="cancelForm.reason"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
            placeholder="选择原因，也可以直接输入"
          >
            <el-option v-for="item in cancelReasons" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="cancelForm.note"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="补充说明，例如：客户 11/09 电话告知不办了，已收定金 300 待退"
          />
        </el-form-item>
        <el-form-item label="金额处理">
          <el-checkbox v-model="cancelForm.clearAmount">把任务金额清零（不计收入，成本保留）</el-checkbox>
        </el-form-item>
      </el-form>

      <div class="op-tip">
        <i class="el-icon-warning-outline" />
        取消后任务状态变为「取消订单」，并在跟进时间线留一条记录；勾了退款会再记一条「退款」跟进。
        取消原因和备注在跟进详情里能看到。
      </div>

      <div slot="footer">
        <el-button @click="cancelVisible = false">取消</el-button>
        <el-button type="danger" :loading="cancelSaving" @click="submitCancel">确认取消订单</el-button>
      </div>
    </el-dialog>

    <order-detail-dialog :visible.sync="detailVisible" :row="detailRow" />
  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import OrderDetailDialog from './components/OrderDetailDialog'
import OrderItemsTable from './components/OrderItemsTable'
import PhotoUploader from './components/PhotoUploader'
import {
  fetchAccountList,
  fetchAccountSummary,
  createAccount,
  updateAccount,
  cancelAccount
} from '@/api/account'
import { fetchPlatformList } from '@/api/platform'
import { fetchBizItemList } from '@/api/bizitem'
import {
  fetchItemTasks,
  fetchProgressOwners,
  addProgressTask,
  deleteProgressTask
} from '@/api/progress'
import { BIZ_STATUS_OPTIONS, TAX_STATUS_OPTIONS, splitBizStatus, joinBizStatus, bizStatusText } from '@/constants/license'
import { splitItems, joinItems, formatMoney } from '@/constants/bizitem'
import {
  ORDER_STATUS_OPTIONS,
  ITEM_STATUS_OPTIONS,
  orderStatusText,
  orderStatusType,
  CANCEL_BLOCKED_STATUSES,
  CANCEL_REASON_OPTIONS
} from '@/constants/order'
import refreshOnActivate from '@/mixins/refresh-on-activate'

// 统一社会信用代码：18 位，数字与大写字母（不含 I O Z S V）
const CREDIT_CODE_RE = /^[0-9A-HJ-NPQRTUWXY]{18}$/
// 二代身份证：17 位数字 + 校验位（数字或 X）
const ID_CARD_RE = /^\d{17}[\dX]$/
// 手机号：11 位，1 开头
const PHONE_RE = /^1[3-9]\d{9}$/

// 选填字段：填了才校验格式，空着直接放过
function optionalPattern(pattern, message) {
  return (rule, value, callback) => {
    const text = String(value || '').trim()
    if (!text) return callback()
    if (!pattern.test(text)) return callback(new Error(message))
    return callback()
  }
}

export default {
  name: 'OrderList',
  components: { Pagination, OrderDetailDialog, OrderItemsTable, PhotoUploader },
  mixins: [refreshOnActivate],
  data() {
    const now = new Date()
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    return {
      currentMonth,
      loading: false,
      saving: false,
      total: 0,
      list: [],
      summary: {
        count: 0,
        revenue: 0,
        cost: 0,
        profit: 0,
        pending: 0,
        // 已完成订单口径（执照主任务全部办结才计入）
        done_count: 0,
        done_revenue: 0,
        done_cost: 0,
        done_profit: 0
      },
      categoryOptions: ['同行', '代理记账', '工商注册', '变更注销'],
      platformOptions: [],
      bizItemOptions: [],
      bizStatusOptions: BIZ_STATUS_OPTIONS,
      taxStatusOptions: TAX_STATUS_OPTIONS,
      statusOptions: ORDER_STATUS_OPTIONS,
      // 主任务（执照）只能在进行中 / 已完成 / 取消之间选，状态由子任务决定
      itemStatusOptions: ITEM_STATUS_OPTIONS,
      // 子任务状态（与后端 TASK_STATUS_LABELS 一致）
      taskStatusOptions: [
        { value: 'pending', label: '未开始' },
        { value: 'doing', label: '办理中' },
        { value: 'done', label: '已办结' },
        { value: 'cancelled', label: '已取消' }
      ],
      // 子任务可选的跟进人（系统用户 + 历史跟进人）
      ownerOptions: [],
      listQuery: {
        page: 1,
        limit: 20,
        month: currentMonth,
        keyword: '',
        status: '',
        platform: '',
        biz_status: '',
        tax_status: ''
      },
      dialogVisible: false,
      dialogType: 'create',
      detailVisible: false,
      detailRow: null,
      // 订单级取消（取消时可一并退款）：整单或按执照任务多选
      cancelVisible: false,
      cancelSaving: false,
      cancelRow: null,
      cancelReasons: CANCEL_REASON_OPTIONS,
      cancelForm: {
        item_ids: [],
        reason: '',
        note: '',
        clearAmount: true,
        refund: true,
        refundAmount: 0,
        refundMethod: ''
      },
      form: this.emptyForm(),
      rules: {
        biz_date: [{ required: true, message: '请选择业务日期', trigger: 'change' }],
        category: [{ required: true, message: '请填写行业', trigger: 'change' }],
        client: [{ required: true, message: '请填写客户', trigger: 'blur' }],
        phone: [
          { validator: optionalPattern(PHONE_RE, '手机号为 11 位数字'), trigger: 'blur' }
        ]
      },
      detailRules: {
        credit_code: [
          { validator: optionalPattern(CREDIT_CODE_RE, '统一信用编码为 18 位数字或大写字母'), trigger: 'blur' }
        ],
        legal_id: [
          { validator: optionalPattern(ID_CARD_RE, '身份证号为 18 位，最后一位可为 X'), trigger: 'blur' }
        ],
        legal_phone: [
          { validator: optionalPattern(PHONE_RE, '法人手机号为 11 位数字'), trigger: 'blur' }
        ]
      }
    }
  },
  computed: {
    monthSuffix() {
      return this.listQuery.month ? `（${this.listQuery.month}）` : '（全部）'
    },
    // 还没完成的订单金额：这部分不进总收入，卡片上提示一下
    inflightRevenue() {
      return Math.max(0, Number(this.summary.revenue || 0) - Number(this.summary.done_revenue || 0))
    },
    myUsername() {
      return this.$store.getters.username || ''
    },
    isAdmin() {
      return (this.$store.getters.roles || []).indexOf('admin') >= 0
    },
    // 编辑时把订单编号带到标题上，方便核对；新增时编号由后端在保存后生成
    dialogTitle() {
      if (this.dialogType !== 'edit') return '新增订单'
      return this.form.order_no ? `编辑订单 · ${this.form.order_no}` : '编辑订单'
    },
    filtering() {
      return Boolean(
        this.listQuery.month || this.listQuery.keyword || this.listQuery.status ||
        this.listQuery.platform || this.listQuery.biz_status || this.listQuery.tax_status
      )
    },
    // 这笔订单里还能取消的执照任务（已取消 / 已退款 的排除）
    cancellableItems() {
      const details = (this.cancelRow && this.cancelRow.details) || []
      return details.filter(item => CANCEL_BLOCKED_STATUSES.indexOf(item.status) < 0)
    },
    // 选中要取消的任务里，还能退给客户的金额上限（已收金额合计）
    cancelRefundMax() {
      const picked = this.cancelForm.item_ids || []
      const total = this.cancellableItems
        .filter(item => picked.indexOf(item.id) >= 0)
        .reduce((sum, item) => sum + Math.max(0, Number(item.revenue || 0)), 0)
      return Math.round(total * 100) / 100
    }
  },
  watch: {
    // 换取消范围时，退款金额默认跟着变成这些任务的已收合计
    'cancelForm.item_ids'() {
      this.cancelForm.refundAmount = this.cancelRefundMax
    },
    // 首页卡片再次穿透到本页时（如总收入→只看已完成），同步筛选条件
    '$route.query': {
      handler() {
        if (this.applyRouteQuery()) {
          this.getList()
          this.getSummary()
        }
      }
    }
  },
  created() {
    this.applyRouteQuery()
    this.getList()
    this.getSummary()
    this.loadPlatforms()
    this.loadBizItems()
    this.loadOwners()
  },
  methods: {
    formatMoney,
    // 读取首页卡片带过来的筛选条件（只认本页支持的项）
    applyRouteQuery() {
      const q = this.$route.query || {}
      const sign = JSON.stringify(q)
      if (sign === this.__querySign) return false
      this.__querySign = sign
      this.listQuery.keyword = q.keyword || ''
      this.listQuery.status = q.status || ''
      this.listQuery.platform = q.platform || ''
      this.listQuery.biz_status = q.biz_status || ''
      this.listQuery.tax_status = q.tax_status || ''
      if (q.month === 'all') this.listQuery.month = ''
      else if (q.month) this.listQuery.month = q.month
      this.listQuery.page = 1
      return true
    },
    joinItems,
    splitBizStatus,
    bizStatusText,
    // 工商状态多选：下拉里用数组，提交时拼回「正常,另册管理」
    setBizStatus(detail, values) {
      const prev = splitBizStatus(detail.biz_status)
      const picked = Array.isArray(values) ? values.slice() : []
      let next = picked
      if (picked.indexOf('正常') !== -1 && prev.indexOf('正常') === -1) {
        // 本次勾的是「正常」：清掉其它异常状态，只留正常
        next = ['正常']
      } else if (picked.length > 1) {
        // 勾了异常状态：把「正常」摘掉，两者互斥
        next = picked.filter(item => item !== '正常')
      }
      detail.biz_status = joinBizStatus(next)
    },
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新，保证看到最新数据
    refreshPage() {
      this.getList()
      this.getSummary()
      this.loadPlatforms()
      this.loadBizItems()
    },
    async loadPlatforms() {
      try {
        const { data } = await fetchPlatformList()
        this.platformOptions = (data || []).map(item => item.name)
      } catch (error) {
        this.platformOptions = []
      }
    },
    // 业务项字典（只取启用的），订单里多选组合
    async loadBizItems() {
      try {
        const { data } = await fetchBizItemList()
        this.bizItemOptions = (data || []).filter(item => item.active !== false)
      } catch (error) {
        this.bizItemOptions = []
      }
    },
    itemsAutoSum(list) {
      return (list || []).reduce((total, name) => {
        const found = this.bizItemOptions.find(item => item.name === name)
        return total + Number((found && found.unit_price) || 0)
      }, 0)
    },
    // 业务项单价（业务项配置里维护的默认价）
    priceOf(name) {
      const found = this.bizItemOptions.find(item => item.name === name)
      return Number((found && found.unit_price) || 0)
    },
    // 选择业务项：拼成文本，子任务跟着重拆，再把各行单价合计回填到单价/收入
    handleItemsChange(detail, list) {
      const selected = list || []
      detail.item_list = selected
      detail.items = joinItems(selected)
      // 业务项一变，卡片里的子任务跟着重新拆（新项带上默认单价）
      this.syncDetailTasks(detail)
      this.applyTaskAmounts(detail)
    },
    // 子任务各行单价合计
    subtaskSum(detail) {
      return ((detail && detail.__tasks) || []).reduce((total, task) => total + Number(task.amount || 0), 0)
    },
    // 合计写回「单价 / 收入」：只在单价没被手改过的时候覆盖，避免冲掉人工报价
    applyTaskAmounts(detail) {
      const sum = Number(this.subtaskSum(detail).toFixed(2))
      const quantity = Number(detail.quantity || 1)
      const previous = Number(detail.__autoPrice || 0)
      const current = detail.unit_price === undefined || detail.unit_price === null || detail.unit_price === ''
        ? null
        : Number(detail.unit_price)
      const revenue = detail.revenue === undefined || detail.revenue === null || detail.revenue === ''
        ? null
        : Number(detail.revenue)
      if (current === null || current === previous) {
        detail.unit_price = sum || undefined
        if (revenue === null || revenue === Number((previous * quantity).toFixed(2))) {
          detail.revenue = sum && quantity ? Number((sum * quantity).toFixed(2)) : undefined
        }
      }
      detail.__autoPrice = sum
    },
    // 改某一项的单价：改完立刻重算合计、单价、收入
    changeTaskAmount(detail, task, value) {
      const amount = value === '' || value === null || value === undefined ? 0 : Number(value)
      this.$set(task, 'amount', amount)
      this.applyTaskAmounts(detail)
    },
    // ---- 执照下的子任务：每个业务项一条独立子任务 ----
    initial(name) {
      const text = String(name || '').trim()
      return text ? text.slice(0, 1) : '?'
    },
    avatarColor(name) {
      const text = String(name || '')
      if (!text) return '#c0c4cc'
      const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#8e6cf0', '#13c2c2', '#d46b08', '#597ef7']
      return colors[text.charCodeAt(0) % colors.length]
    },
    ownerName(username) {
      const found = this.ownerOptions.find(item => item.username === username)
      return found ? found.name : username || ''
    },
    taskOwnerTip(task) {
      if (!task || !task.owner) return '未指定跟进人；谁先编辑就会自动认领'
      return '跟进人：' + this.ownerName(task.owner) + '，可点开改'
    },
    // 子任务只有跟进人本人和管理员能改；还没指定跟进人时谁都能改（保存后会自动记成跟进人）
    canEditTask(task) {
      if (!task) return false
      if (this.isAdmin) return true
      const owner = (task.owner || '').trim()
      return !owner || owner === this.myUsername
    },
    taskLockTip(task) {
      if (this.canEditTask(task)) return ''
      return '这条子任务的跟进人是 ' + (this.ownerName(task.owner) || '—') + '，只有本人或管理员能改'
    },
    async loadOwners() {
      if (this.ownerOptions.length) return
      try {
        const { data } = await fetchProgressOwners()
        this.ownerOptions = (data && data.items) || []
      } catch (error) {
        this.ownerOptions = []
      }
    },
    // 办理线判定与后端 TASK_LINE_RULES 保持一致（先税务后工商，「税务注销」不会被「注销」抢走）
    taskLine(name) {
      const text = String(name || '')
      if (/(税务|解非|非正常|清税|记账|报税|申报|发票|票种|汇算|欠税|有税|无税|个税|社保)/.test(text)) return 'tax'
      if (/(工商|执照|注销|注册|变更|地址|年报|刻章|银行|股权|增资|减资|经营范围|另册|吊销|挂靠|虚假)/.test(text)) return 'biz'
      return 'other'
    },
    taskLineLabel(line) {
      return { biz: '工商', tax: '税务' }[line] || '其他'
    },
    // 按当前业务项重排子任务：每个业务项一条，已存在的保留状态和单价，手工补的排在最后
    syncDetailTasks(detail) {
      const names = detail.item_list || []
      const existing = (detail.__tasks || []).slice()
      // 刚被去掉的业务项先放进暂存区：手滑删了又加回来，状态和单价都还在
      const stash = (detail.__taskStash || []).slice()
      const next = names.map(name => {
        let index = existing.findIndex(task => task.name === name && task.source !== 'manual')
        if (index >= 0) return existing.splice(index, 1)[0]
        index = stash.findIndex(task => task.name === name)
        if (index >= 0) return stash.splice(index, 1)[0]
        return {
          id: null,
          name,
          line: this.taskLine(name),
          status: 'pending',
          amount: this.priceOf(name),
          owner: '',
          source: 'item'
        }
      })
      existing.forEach(task => {
        if (task.source === 'manual') next.push(task)
        else stash.push(task)
      })
      detail.__tasks = next
      detail.__taskStash = stash
    },
    subtaskStat(detail) {
      const tasks = (detail && detail.__tasks) || []
      return {
        total: tasks.length,
        done: tasks.filter(task => task.status === 'done').length,
        cancelled: tasks.filter(task => task.status === 'cancelled').length
      }
    },
    // 打开编辑弹窗时按订单把各执照的细分任务一次拉回来（不做 N+1）
    async loadDetailTasks(details) {
      const list = (details || []).filter(detail => detail.id)
      if (!list.length) return
      try {
        const { data } = await fetchItemTasks({ account_id: this.form.id })
        const grouped = (data && data.tasks) || {}
        list.forEach(detail => {
          const tasks = grouped[String(detail.id)] || []
          detail.__tasks = tasks.map(task => Object.assign({}, task))
          // 业务项可能改过还没保存，按当前选择补齐
          this.syncDetailTasks(detail)
          // 以实际行单价为基准，后面改单价/加减业务项时再按差额联动
          detail.__autoPrice = this.subtaskSum(detail)
        })
      } catch (error) {
        list.forEach(detail => {
          this.syncDetailTasks(detail)
          detail.__autoPrice = this.subtaskSum(detail)
        })
      }
    },
    // 子任务跟进人同样先在本地改，点「确定」随订单一起保存
    changeTaskOwner(task, owner) {
      this.$set(task, 'owner', owner || '')
    },
    // 子任务状态先在本地改，点「确定」一起保存（新建订单时也能直接指定各条状态）
    changeTaskStatus(detail, task, status) {
      if (!status || task.status === status) return
      this.$set(task, 'status', status)
      this.syncDetailStatusByTasks(detail)
    },
    // 执照（主任务）状态变化时带着子任务走，跟后端的规则保持一致：
    // 已完成 → 全部办结；取消 → 未办结的一起取消；恢复 → 取消的回到未开始
    onDetailStatusChange(detail, value) {
      const tasks = detail.__tasks || []
      tasks.forEach(task => {
        if (value === 'done') this.$set(task, 'status', 'done')
        else if (value === 'cancelled' && task.status !== 'done') this.$set(task, 'status', 'cancelled')
        else if (value !== 'cancelled' && task.status === 'cancelled') this.$set(task, 'status', 'pending')
      })
    },
    // 反过来：子任务全办结 → 主任务已完成；主任务已完成又被重新打开 → 退回进行中
    // 反过来：主任务状态只由子任务决定 —— 全办结 = 已完成，否则一律进行中
    // （取消 / 已退款的执照不参与，避免把关单的任务又拉回进行中）
    syncDetailStatusByTasks(detail) {
      const tasks = detail.__tasks || []
      if (!tasks.length) return
      if (detail.status === 'cancelled' || detail.status === 'refunded') return
      const done = tasks.filter(task => task.status === 'done').length
      this.$set(detail, 'status', done === tasks.length ? 'done' : 'doing')
    },
    async addTask(detail) {
      const name = String(detail.__taskName || '').trim()
      if (!name) {
        this.$message.warning('先填子任务名称')
        return
      }
      if (!detail.id) {
        this.$message.warning('这条执照还没保存，先在业务项里加')
        return
      }
      try {
        const { data } = await addProgressTask({ item_id: detail.id, name })
        if (data && data.task) detail.__tasks.push(Object.assign({}, data.task))
        if (data && data.summary && data.summary.status) this.$set(detail, 'status', data.summary.status)
        this.$set(detail, '__taskName', '')
        this.$message.success('子任务已添加')
      } catch (error) {
        this.$message.error((error && error.message) || '添加失败')
      }
    },
    async removeTask(detail, task) {
      if (!task.id) return
      try {
        await this.$confirm(`删除子任务「${task.name}」？`, '删除子任务', { type: 'warning' })
      } catch (error) {
        return
      }
      try {
        const { data } = await deleteProgressTask(task.id)
        detail.__tasks = detail.__tasks.filter(item => item.id !== task.id)
        if (data && data.summary && data.summary.status) detail.status = data.summary.status
        this.$message.success('已删除')
      } catch (error) {
        this.$message.error((error && error.message) || '删除失败')
      }
    },
    emptyDetail() {
      return {
        id: undefined,
        license_name: '',
        credit_code: '',
        legal_person: '',
        legal_id: '',
        legal_phone: '',
        biz_status: '',
        tax_status: '',
        items: '',
        item_list: [],
        __autoPrice: 0,
        __collapsed: false,
        // 按业务项拆出来的子任务（列表里直接看/改状态）
        __tasks: [],
        __taskStash: [],
        __taskName: '',
        // 执照照片 [{url, name, size}]
        license_photos: [],
        unit_price: undefined,
        quantity: 1,
        revenue: undefined,
        cost: undefined,
        profit: undefined,
        // 主任务默认「进行中」；子任务全办结时自动变已完成
        status: 'doing',
        remark: ''
      }
    },
    emptyForm() {
      const now = new Date()
      const month = String(now.getMonth() + 1).padStart(2, '0')
      const day = String(now.getDate()).padStart(2, '0')
      return {
        id: undefined,
        order_no: '',
        platform_order_no: '',
        biz_date: `${month}/${day}`,
        category: '',
        client: '',
        phone: '',
        wechat: '',
        platform: '',
        remark: '',
        // 客户身份证照片 [{url, name, size}]
        id_photos: [],
        details: [this.emptyDetail()]
      }
    },
    addDetail() {
      this.form.details.push(this.emptyDetail())
    },
    // 卡片折叠/展开（纯前端展示状态，不参与提交）
    toggleDetail(detail) {
      this.$set(detail, '__collapsed', !detail.__collapsed)
    },
    removeDetail(index) {
      if (this.form.details.length <= 1) return
      this.form.details.splice(index, 1)
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchAccountList(this.listQuery)
        this.list = data.items || []
        this.total = data.total || 0
      } finally {
        this.loading = false
      }
    },
    async getSummary() {
      const params = {}
      if (this.listQuery.month) params.month = this.listQuery.month
      const { data } = await fetchAccountSummary(params)
      this.summary = data
    },
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },
    showAllMonths() {
      this.listQuery.month = ''
      this.listQuery.page = 1
      this.getList()
      this.getSummary()
    },
    resetFilters() {
      this.listQuery.month = ''
      this.listQuery.keyword = ''
      this.listQuery.status = ''
      this.listQuery.platform = ''
      this.listQuery.biz_status = ''
      this.listQuery.tax_status = ''
      this.listQuery.page = 1
      this.getList()
      this.getSummary()
    },
    // 把 "09/03" / "2026-09-03" 统一成 "2026-09"，用于判断记录属于哪个月
    dateMonth(value) {
      const text = String(value || '').trim()
      if (!text) return ''
      const full = text.match(/^(\d{4})-(\d{1,2})/)
      if (full) return `${full[1]}-${String(full[2]).padStart(2, '0')}`
      const short = text.match(/^(\d{1,2})\D/)
      if (short) return `${new Date().getFullYear()}-${String(short[1]).padStart(2, '0')}`
      return ''
    },
    handleCreate() {
      this.dialogType = 'create'
      this.form = this.emptyForm()
      this.dialogVisible = true
      this.$nextTick(() => {
        this.$refs.accountForm && this.$refs.accountForm.clearValidate()
      })
    },
    handleUpdate(row) {
      this.dialogType = 'edit'
      const details = (row.details || []).map(item => Object.assign(this.emptyDetail(), {
        id: item.id,
        license_name: item.license_name,
        credit_code: item.credit_code,
        legal_person: item.legal_person,
        legal_id: item.legal_id,
        legal_phone: item.legal_phone || '',
        license_photos: Array.isArray(item.license_photos) ? item.license_photos : [],
        biz_status: item.biz_status,
        tax_status: item.tax_status,
        items: item.items,
        item_list: splitItems(item.items),
        __autoPrice: this.itemsAutoSum(splitItems(item.items)),
        unit_price: item.unit_price === null ? undefined : item.unit_price,
        quantity: item.quantity === null ? 1 : item.quantity,
        revenue: item.revenue === null ? undefined : item.revenue,
        cost: item.cost === null ? undefined : item.cost,
        profit: item.profit === null ? undefined : item.profit,
        status: item.status || 'pending',
        remark: item.remark
      }))
      this.form = {
        id: row.id,
        order_no: row.order_no,
        platform_order_no: row.platform_order_no || '',
        biz_date: row.biz_date,
        category: row.category,
        client: row.client,
        phone: row.phone,
        wechat: row.wechat || '',
        platform: row.platform,
        remark: row.remark,
        id_photos: Array.isArray(row.id_photos) ? row.id_photos : [],
        details: details.length ? details : [this.emptyDetail()]
      }
      // 先按业务项铺一版，随后用服务端真实状态覆盖
      details.forEach(detail => this.syncDetailTasks(detail))
      this.dialogVisible = true
      this.loadDetailTasks(details)
      this.$nextTick(() => {
        this.$refs.accountForm && this.$refs.accountForm.clearValidate()
      })
    },
    handleDetail(row) {
      this.detailRow = row
      this.detailVisible = true
    },
    // ---- 取消订单 ----
    canCancel(row) {
      if (!row || !row.details) return false
      return row.details.some(item => CANCEL_BLOCKED_STATUSES.indexOf(item.status) < 0)
    },
    cancelTip(row) {
      if (this.canCancel(row)) return '取消订单，可同时把已收的钱退给客户'
      if (row && row.status === 'refunded') return '这单已全额退款，不能再取消'
      return '这单已取消'
    },
    openCancel(row) {
      if (!this.canCancel(row)) {
        this.$message.warning(this.cancelTip(row))
        return
      }
      this.cancelRow = row
      const items = (row.details || []).filter(item => CANCEL_BLOCKED_STATUSES.indexOf(item.status) < 0)
      const received = items.reduce((sum, item) => sum + Math.max(0, Number(item.revenue || 0)), 0)
      this.cancelForm = {
        item_ids: items.map(item => item.id),
        reason: '',
        note: '',
        clearAmount: true,
        // 取消一般都要退钱，默认勾上并把金额填成已收合计，不想退就取消勾选
        refund: received > 0,
        refundAmount: Math.round(received * 100) / 100,
        refundMethod: ''
      }
      this.cancelVisible = true
    },
    selectAllCancelItems() {
      this.cancelForm.item_ids = this.cancellableItems.map(item => item.id)
    },
    async submitCancel() {
      const row = this.cancelRow
      if (!row) return
      const picked = this.cancelForm.item_ids || []
      if (!picked.length) {
        this.$message.warning('请先勾选要取消的执照任务')
        return
      }
      if (!(this.cancelForm.reason || '').trim()) {
        this.$message.warning('请填写取消原因')
        return
      }
      const refundAmount = this.cancelForm.refund ? Number(this.cancelForm.refundAmount || 0) : 0
      // 退款金额允许填 0：订单没收钱也要取消时，勾了退款只是走个记录
      if (this.cancelForm.refund && refundAmount < 0) {
        this.$message.warning('退款金额不能为负数')
        return
      }
      if (refundAmount > this.cancelRefundMax + 0.001) {
        this.$message.warning(`退款金额不能超过所选任务的已收金额 ¥${this.amount(this.cancelRefundMax)}`)
        return
      }
      this.cancelSaving = true
      try {
        const { data } = await cancelAccount({
          account_id: row.id,
          item_ids: picked,
          reason: this.cancelForm.reason,
          note: this.cancelForm.note,
          clear_amount: this.cancelForm.clearAmount,
          refund_amount: refundAmount,
          refund_method: this.cancelForm.refundMethod
        })
        this.cancelVisible = false
        const count = data ? data.cancelled_count : picked.length
        const cleared = data ? data.cleared_count : 0
        const refunded = data ? Number(data.refund || 0) : 0
        let message = `已取消 ${count} 个任务`
        if (refunded > 0) message += `，退款 ¥${this.amount(refunded)}`
        if (cleared) message += `，${cleared} 个任务金额已清零`
        this.$message.success(message)
        this.getList()
        this.getSummary()
      } catch (error) {
        // 请求层已弹出错误提示
      } finally {
        this.cancelSaving = false
      }
    },
    submitForm() {
      this.$refs.accountForm.validate(valid => {
        if (!valid) {
          // 校验失败时先把折叠的卡片展开，否则红字藏在收起的内容里，用户看不到哪里错了
          this.form.details.forEach(detail => { detail.__collapsed = false })
          this.$nextTick(() => {
            const firstError = document.querySelector('.order-form .el-form-item.is-error')
            if (firstError && firstError.scrollIntoView) {
              firstError.scrollIntoView({ block: 'center' })
            }
          })
          return false
        }
        const details = this.form.details.map(detail => ({
          id: detail.id,
          license_name: (detail.license_name || '').trim(),
          credit_code: (detail.credit_code || '').toUpperCase(),
          legal_person: (detail.legal_person || '').trim(),
          legal_id: (detail.legal_id || '').toUpperCase(),
          legal_phone: this.normalizePhone(detail.legal_phone),
          biz_status: detail.biz_status || '',
          tax_status: detail.tax_status || '',
          items: joinItems(detail.item_list) || (detail.items || '').trim(),
          unit_price: this.numberOrNull(detail.unit_price),
          quantity: detail.quantity === undefined || detail.quantity === null || detail.quantity === ''
            ? 1
            : Number(detail.quantity),
          revenue: this.numberOrNull(detail.revenue),
          cost: this.numberOrNull(detail.cost),
          profit: this.numberOrNull(detail.profit),
          status: detail.status || 'pending',
          remark: (detail.remark || '').trim(),
          // 执照照片：随明细一起保存（[{url, name, size}]）
          license_photos: Array.isArray(detail.license_photos) ? detail.license_photos : [],
          // 子任务逐条的状态、单价与跟进人（业务项拆出来的 + 手工补的），保存时一起落库；
          // 别人的子任务不提交，避免改单时把别人的办理状态覆盖掉
          tasks: (detail.__tasks || [])
            .filter(task => this.canEditTask(task))
            .map(task => ({
              id: task.id || null,
              name: task.name,
              status: task.status || 'pending',
              amount: Number(task.amount || 0),
              owner: task.owner || ''
            }))
        }))
        const payload = {
          id: this.form.id,
          biz_date: this.form.biz_date,
          category: this.form.category,
          client: this.form.client,
          phone: this.form.phone || '',
          wechat: (this.form.wechat || '').trim(),
          platform: this.form.platform || '',
          platform_order_no: (this.form.platform_order_no || '').trim(),
          remark: this.form.remark,
          // 客户身份证照片（订单层面）
          id_photos: Array.isArray(this.form.id_photos) ? this.form.id_photos : [],
          details
        }
        const request = this.dialogType === 'edit'
          ? updateAccount(payload)
          : createAccount(payload)
        this.saving = true
        request
          .then((res) => {
            this.$message({
              message: this.dialogType === 'edit'
                ? '保存成功'
                : `订单录入成功，已按执照生成 ${details.length} 条任务`,
              type: 'success'
            })
            this.dialogVisible = false
            // 筛选已改为按「完成月」（与首页卡片一致）：办结的订单记到完成月，
            // 未办结的订单没有完成月、不参与任何月份筛选，就不跳转，避免保存后反而看不到
            const saved = res && res.data
            const doneMonth = saved && saved.completed_at
              ? this.completedMonth(saved.completed_at)
              : ''
            if (doneMonth && this.listQuery.month && doneMonth !== this.listQuery.month) {
              this.listQuery.month = doneMonth
              this.$message({
                message: `该订单于 ${doneMonth} 办结，已自动切换到该月份`,
                type: 'info',
                duration: 4000
              })
            }
            this.listQuery.page = 1
            this.getList()
            this.getSummary()
          })
          .finally(() => {
            this.saving = false
          })
      })
    },
    // 明细金额合计：全空返回 null（显示「待定」），否则空值按 0 计
    sumRevenue(details, key) {
      const values = details
        .map(item => this.numberOrNull(item[key]))
        .filter(value => value !== null)
      if (!values.length) return null
      return values.reduce((sum, value) => sum + value, 0)
    },
    // 手机号只留数字：粘贴「+86 138 0013 8000」这种整串也能一步收拾干净
    normalizePhone(value) {
      let digits = String(value || '').replace(/\D/g, '')
      if (digits.length > 11 && digits.indexOf('86') === 0) digits = digits.slice(2)
      return digits.slice(0, 11)
    },
    numberOrNull(value) {
      if (value === null || value === undefined || value === '') return null
      const num = Number(value)
      return Number.isNaN(num) ? null : num
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    money(value) {
      const num = Number(value || 0)
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    statusText(status) {
      return orderStatusText(status)
    },
    completedText(stamp) {
      if (!stamp) return '—'
      const date = new Date(Number(stamp))
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    },
    // 完成月（毫秒时间戳 → YYYY-MM），与后端 ms_month_key / 首页卡片口径一致
    // 后端服务器时区为 UTC，这里也按 UTC 归月，避免月初月末 8 小时边界与卡片错位
    completedMonth(stamp) {
      const value = Number(stamp)
      if (!value || value <= 0) return ''
      const date = new Date(value > 1e11 ? value : value * 1000)
      if (Number.isNaN(date.getTime())) return ''
      const pad = v => String(v).padStart(2, '0')
      return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}`
    },
    statusType(status) {
      return orderStatusType(status)
    }
  }
}
</script>

<style lang="scss" scoped>
.account-page {
  .summary-row {
    margin-bottom: 18px;
  }

  .summary-card {
    background: #fff;
    border-radius: 4px;
    padding: 16px 18px;
    box-shadow: 0 1px 4px rgba(0, 21, 255, 0.08);
  }

  .summary-label {
    color: #909399;
    font-size: 13px;
  }

  .summary-value {
    margin-top: 6px;
    font-size: 22px;
    font-weight: 600;

    &.revenue { color: #67c23a; }
    &.cost { color: #e6a23c; }
    &.profit { color: #409eff; }
    &.pending { color: #f56c6c; }
  }

  .summary-tip {
    margin-top: 6px;
    font-size: 12px;
    color: #909399;
  }

  .keyword-input {
    width: 240px;
  }

  .filter-container .filter-item {
    margin-right: 8px;
    margin-bottom: 8px;
  }

  .table-panel {
    .panel-head {
      display: flex;
      align-items: baseline;
      margin: 6px 0 10px;
    }

    .panel-title {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
    }

    .panel-count {
      margin-left: 8px;
      font-size: 12px;
      color: #909399;
    }
  }

  .order-no-text {
    font-family: Menlo, Consolas, monospace;
    font-size: 12px;
    color: #606266;
  }

  .form-section-title {
    display: flex;
    align-items: center;
    margin: 4px 0 14px;
    padding-left: 8px;
    border-left: 3px solid #409eff;
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    line-height: 20px;

    &:not(:first-child) {
      margin-top: 18px;
    }

    .optional-tip {
      flex: 1;
      min-width: 0;
      margin-left: 8px;
      font-weight: 400;
      font-size: 12px;
      color: #909399;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .add-detail-btn {
      flex: none;
      margin-left: 12px;
    }
  }

  .detail-card {
    margin-bottom: 14px;
    border: 1px solid #e6ebf2;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
    transition: border-color 0.2s, box-shadow 0.2s;

    &:hover {
      border-color: #c6dcf5;
      box-shadow: 0 2px 12px rgba(64, 158, 255, 0.1);
    }

    &.is-collapsed:hover {
      box-shadow: none;
    }

    &.is-collapsed .detail-card-head {
      border-bottom-color: transparent;
    }
  }

  .detail-card-head {
    display: flex;
    align-items: center;
    height: 40px;
    padding: 0 14px;
    background: linear-gradient(180deg, #f7faff 0%, #f1f5fb 100%);
    border-bottom: 1px solid #e9eff7;

    .collapse-btn {
      flex: none;
      width: 16px;
      margin-right: 2px;
      font-size: 12px;
      color: #909399;
      cursor: pointer;

      &:hover {
        color: #409eff;
      }
    }

    .detail-card-index {
      flex: none;
      width: 20px;
      height: 20px;
      margin-right: 8px;
      border-radius: 50%;
      background: #409eff;
      color: #fff;
      font-size: 12px;
      font-weight: 600;
      line-height: 20px;
      text-align: center;
    }

    .detail-card-title {
      flex: none;
      font-size: 13px;
      font-weight: 600;
      color: #303133;
    }

    .detail-card-sub {
      max-width: 300px;
      margin-left: 8px;
      padding-left: 8px;
      border-left: 1px solid #dcdfe6;
      font-size: 12px;
      color: #909399;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    /* 折叠后补一行摘要，收起状态也能看清业务项和金额 */
    .detail-card-sum {
      display: flex;
      align-items: center;
      margin-left: 10px;
      overflow: hidden;

      .sum-item {
        flex: none;
        margin-right: 8px;
        padding: 0 8px;
        border-radius: 10px;
        background: #ecf5ff;
        font-size: 12px;
        line-height: 20px;
        color: #409eff;
      }

      .sum-empty {
        font-size: 12px;
        color: #c0c4cc;
      }
    }

    .detail-card-tools {
      display: flex;
      align-items: center;
      margin-left: auto;

      .tool-label {
        margin-right: 6px;
        font-size: 12px;
        color: #909399;
      }

      // 执照照片小上传区：缩略图和「+」并排，不留太大空隙
      .photo-uploader {
        margin-right: 14px;
      }

      .tool-label + .photo-uploader {
        margin-right: 14px;
      }

      .status-select {
        width: 96px;
      }

      .delete-btn {
        margin-left: 12px;
        padding: 0;
        font-size: 12px;
      }
    }
  }

  .detail-card-body {
    padding: 16px 16px 2px;

    /* 留够空间给校验错误提示（绝对定位在输入框下方 16px） */
    .el-form-item {
      margin-bottom: 20px;
    }
  }

  .money-row {
    display: flex;
    align-items: center;
    margin-bottom: 20px;

    .money-row-label {
      flex: none;
      width: 104px;
      padding-right: 12px;
      box-sizing: border-box;
      text-align: right;
      font-size: 14px;
      color: #606266;
    }

    .money-panel {
      display: flex;
      flex: 1;
      min-width: 0;
      padding: 10px 12px 12px;
      border: 1px solid #eef2f7;
      border-radius: 6px;
      background: #f8fafd;
    }

    .money-cell {
      flex: 1;
      min-width: 0;

      & + .money-cell {
        margin-left: 12px;
      }

      .money-label {
        display: block;
        margin-bottom: 6px;
        font-size: 12px;
        line-height: 16px;
        color: #909399;
      }

      .money-input {
        position: relative;

        .money-unit {
          position: absolute;
          top: 0;
          left: 10px;
          z-index: 2;
          font-style: normal;
          font-size: 13px;
          line-height: 40px;
          color: #c0c4cc;
          pointer-events: none;
        }

        .el-input-number {
          width: 100%;
        }

        /* 去掉 controls 后 element 仍留了给加减按钮的内边距，这里改回正常留白并左对齐；
           左边留 24px 给 ¥，数量格也一起留，保证五格数字左边缘成一条线 */
        ::v-deep .el-input__inner {
          padding: 0 10px 0 24px;
          text-align: left;
        }
      }
    }

    .money-cell-profit .money-label {
      color: #409eff;
      font-weight: 600;
    }
  }

  .warning-text {
    color: #e6a23c;
  }

  .danger-text {
    color: #f56c6c;
  }

  .muted-text {
    color: #c0c4cc;
  }

  /* 订单退款 / 取消订单弹窗 */
  .op-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px dashed #ebeef5;

    .op-no {
      font-family: Menlo, Consolas, monospace;
      font-weight: 600;
      color: #303133;
    }

    .op-meta {
      margin-left: auto;
      font-size: 12px;
      color: #909399;

      b {
        color: #303133;
      }
    }
  }

  .op-block {
    margin-bottom: 12px;

    .op-block-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
      font-size: 13px;
      font-weight: 600;
      color: #606266;
    }

    .op-items {
      display: block;
      max-height: 198px;
      overflow-y: auto;
      padding: 4px 10px;
      border-radius: 4px;
      background: #fafafa;
    }

    ::v-deep .el-checkbox {
      display: flex;
      align-items: center;
      width: 100%;
      margin: 0 0 2px;
    }

    ::v-deep .el-checkbox__label {
      display: flex;
      align-items: center;
      flex: 1;
      min-width: 0;
      font-size: 13px;
      color: #303133;
    }

    .oi-license {
      flex: 0 0 auto;
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .oi-items {
      flex: 1;
      min-width: 0;
      margin-left: 8px;
      font-size: 12px;
      color: #909399;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .oi-money {
      flex: 0 0 auto;
      margin-left: 8px;
      font-family: Menlo, Consolas, monospace;
      color: #f56c6c;
    }

    .op-empty {
      padding: 6px 0;
      font-size: 12px;
      color: #c0c4cc;
    }
  }

  .op-form {
    margin-top: 10px;

    .op-quick {
      margin-top: 2px;
      text-align: right;
    }
  }

  /* 取消弹窗里的退款区块：勾了才展开 */
  .refund-box {
    margin-top: 8px;
    padding: 10px 12px;
    border-radius: 4px;
    background: #fafafa;
    border: 1px dashed #e4e7ed;
  }

  .refund-line {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;

    &:last-child {
      margin-bottom: 0;
    }

    .rl-label {
      flex: 0 0 auto;
      font-size: 12px;
      color: #909399;
    }
  }

  .refund-hint {
    margin-top: 2px;
    font-size: 12px;
    line-height: 18px;
    color: #909399;
  }

  .op-tip {
    margin-top: 4px;
    padding: 8px 10px;
    border-radius: 4px;
    background: #fdf6ec;
    color: #b88230;
    font-size: 12px;
    line-height: 18px;
  }

  .items-preview {
    margin-top: 4px;
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }

  /* 子任务：业务项拆出来的独立小任务，卡片里直接看状态 */
  .subtask-box {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid #ebeef5;
    border-radius: 4px;
    background: #fafbfc;
  }

  .subtask-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }

  .subtask-tip {
    font-size: 12px;
    color: #909399;
  }

  .subtask-count {
    font-size: 12px;
    font-weight: 600;
    color: #606266;
  }

  .subtask-empty {
    font-size: 12px;
    line-height: 22px;
    color: #c0c4cc;
  }

  .subtask-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .subtask-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 8px;
    border: 1px solid #f0f2f5;
    border-radius: 4px;
    background: #fff;

    &.is-done .st-name {
      color: #67c23a;
      text-decoration: line-through;
    }

    &.is-cancelled .st-name {
      color: #c0c4cc;
      text-decoration: line-through;
    }

    &.is-draft {
      border-style: dashed;
      background: #fdfcf7;
    }
  }

  .st-line {
    flex: none;
    height: 18px;
    padding: 0 5px;
    border-radius: 3px;
    font-size: 11px;
    line-height: 18px;

    &.is-biz {
      color: #b88230;
      background: #fdf6ec;
    }

    &.is-tax {
      color: #337ecc;
      background: #ecf5ff;
    }

    &.is-other {
      color: #909399;
      background: #f4f4f5;
    }
  }

  .st-name {
    overflow: hidden;
    font-size: 13px;
    color: #303133;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .st-flex {
    flex: 1;
  }

  .st-amount {
    display: flex;
    align-items: center;
    width: 108px;
    padding: 0 6px;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    background: #fff;
  }

  .st-currency {
    margin-right: 2px;
    font-size: 12px;
    color: #c0c4cc;
  }

  .st-amount-input {
    width: 100%;

    ::v-deep .el-input__inner {
      height: 24px;
      padding: 0;
      border: none;
      font-size: 12px;
      line-height: 24px;
      text-align: right;
    }
  }

  .subtask-foot-tip {
    margin-top: 6px;
    font-size: 12px;
    color: #909399;
  }

  .st-owner {
    width: 118px;

    ::v-deep .el-input__inner {
      height: 24px;
      padding: 0 22px 0 8px;
      font-size: 12px;
      line-height: 24px;
    }

    ::v-deep .el-input__icon {
      line-height: 24px;
    }
  }

  .st-owner-opt {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .owner-dot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    font-size: 10px;
    color: #fff;
    border-radius: 50%;
  }

  .st-status {
    width: 92px;
  }

  .st-draft {
    font-size: 12px;
    color: #c0c4cc;
  }

  .st-del {
    cursor: pointer;
    color: #c0c4cc;

    &:hover {
      color: #f56c6c;
    }
  }

  .subtask-add {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
  }

  .form-hint {
    margin-top: 2px;
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }

  .platform-order-no-input ::v-deep .el-input__inner {
    font-family: Menlo, Consolas, monospace;
    letter-spacing: 0.3px;
  }

  // 订单信息里的身份证照片：上传区加一句提示
  .photo-field {
    display: flex;
    align-items: center;

    .photo-tip {
      margin-left: 12px;
      font-size: 12px;
      color: #909399;
    }
  }

  /* 工商状态平铺勾选：5 项全部展开，不再折叠成「+N」；窄屏自动换行 */
  .biz-status-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    row-gap: 2px;

    ::v-deep .el-checkbox {
      margin-right: 18px;
      margin-left: 0;
      font-weight: normal;
    }

    ::v-deep .el-checkbox + .el-checkbox {
      margin-left: 0;
    }

    ::v-deep .el-checkbox__label {
      padding-left: 6px;
      font-size: 13px;
    }
  }
}

.order-form {
  max-height: 68vh;
  overflow-y: auto;
  padding-right: 8px;
}

// 成本列：橙棕色等宽字体，与收入区分
.cost-cell {
  font-family: Menlo, Consolas, monospace;
  font-size: 12px;
  color: #b88230;
}
</style>

<style lang="scss">
/* 下拉挂在 body 上，scoped 样式够不到，用 popper-class 兜一层全局规则 */
.biz-item-dropdown .el-select-dropdown__item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.biz-item-dropdown .option-name {
  flex: 1;
}

.biz-item-dropdown .option-price {
  margin-left: 16px;
  color: #f56c6c;
  font-size: 13px;
}
</style>
