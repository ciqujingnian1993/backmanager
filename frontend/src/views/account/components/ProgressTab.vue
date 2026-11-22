<template>
  <div class="progress-panel">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">任务总数（按执照拆分）</div>
          <div class="stat-value">{{ summary.tasks }}</div>
          <div v-if="statusBreakdown" class="stat-sub">{{ statusBreakdown }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">已完成任务</div>
          <div class="stat-value ok">{{ summary.done }}</div>
          <div class="stat-sub">细分任务已办结 {{ subtaskProgress }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">缺进度</div>
          <div class="stat-value warn">{{ summary.missing }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">最近阶段分布</div>
          <div class="stat-steps">
            <el-tag
              v-for="item in summary.by_step.slice(0, 3)"
              :key="item.step"
              size="mini"
              class="step-tag"
              :type="stepTagType(item.step)"
            >
              {{ item.step }} {{ item.count }}
            </el-tag>
            <span v-if="!summary.by_step.length" class="stat-empty">暂无</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="filter-container">
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
        placeholder="任务状态"
        clearable
        @change="handleFilter"
      >
        <el-option
          v-for="item in statusOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-button class="filter-item" icon="el-icon-refresh" @click="refresh">刷新</el-button>
      <el-button class="filter-item" plain @click="expandAllRows(true)">展开细分</el-button>
      <el-button class="filter-item" plain @click="expandAllRows(false)">收起细分</el-button>
      <span class="filter-tip">一个订单按执照拆成多条主任务，每个执照再按业务项拆出细分任务；双击主任务看跟进详情，双击细分任务直接写跟进</span>
    </div>

    <!-- 筛选提示：上面「任务总数」是全部任务，这里写清楚当前筛选命中了多少条，免得以为列表少了数据 -->
    <div v-if="activeFilters.length" class="filter-banner">
      <i class="el-icon-filter" />
      <span class="fb-text">当前筛选：{{ activeFilterText }}，命中 <b>{{ total }}</b> 条任务</span>
      <span class="fb-total">全部 {{ summary.tasks }} 条任务 / {{ summary.orders }} 个订单</span>
      <el-button type="text" size="mini" @click="clearFilters">清除筛选</el-button>
    </div>

    <!-- 主任务 = 一个执照，展开箭头在这一列；点开看它下面的细分任务（业务项） -->
    <el-table
      ref="taskTable"
      v-loading="loading"
      :data="list"
      :row-key="rowKey"
      :tree-props="{ children: 'tasks' }"
      :row-class-name="rowClass"
      border
      fit
      highlight-current-row
      class="task-table"
      style="width: 100%"
      @row-dblclick="handleRowDblclick"
    >
      <!-- 序号只给主任务（执照）编号；细分任务留空，避免把子任务也数进去 -->
      <el-table-column label="序号" width="60" align="center">
        <template slot-scope="{ row }">
          <span class="row-index">{{ mainIndex(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="执照 / 客户" min-width="250" show-overflow-tooltip>
        <template slot-scope="{ row }">
          <div v-if="row._sub" class="sub-name">
            <span class="sub-arrow">↳</span>
            <span class="sub-text">{{ row.name }}</span>
            <span v-if="row.source === 'manual'" class="sub-manual">手工</span>
            <span v-if="row.owner" class="sub-owner" :title="'这条子任务的跟进人：' + (taskOwnerName(row) || row.owner)">
              <span class="owner-avatar sm" :style="{ background: avatarColor(taskOwnerName(row) || row.owner) }">{{ initial(taskOwnerName(row) || row.owner) }}</span>
              {{ taskOwnerName(row) || row.owner }}
            </span>
            <span v-else class="sub-owner is-empty">未分配</span>
          </div>
          <template v-else>
            <div class="cell-main">{{ row.license_name || '未填执照' }}</div>
            <div class="cell-sub">{{ row.client || '—' }}<span v-if="row.items"> · {{ row.items }}</span></div>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="订单" width="150" align="center">
        <template slot-scope="{ row }">
          <span
            v-if="row.order_no"
            class="order-no-text is-link"
            :title="'点击查看订单详情 ' + row.order_no + ' · 订单 #' + row.account_id"
            @click.stop="openOrderDetail(row)"
            @dblclick.stop="openOrderDetail(row)"
          >{{ row.order_no }}</span>
          <span v-else-if="!row._sub" class="muted-text">#{{ row.account_id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="104" align="right">
        <template slot-scope="{ row }">
          <template v-if="!row._sub">
            <div class="amount-cell" :class="{ 'is-refunded': row.status === 'refunded' }">
              {{ amount(row.revenue) }}
            </div>
            <!-- 取消订单优先显示：取消时可能一并退款，退款额放在悬浮提示里 -->
            <el-tag
              v-if="row.status === 'cancelled'"
              size="mini"
              type="info"
              effect="plain"
              class="refund-tag"
              :title="cancelTagTip(row)"
            >
              取消订单
            </el-tag>
            <el-tag
              v-else-if="row.refund_amount > 0"
              size="mini"
              :type="row.status === 'refunded' ? 'danger' : 'warning'"
              effect="plain"
              class="refund-tag"
              :title="refundTagTip(row)"
            >
              {{ row.status === 'refunded' ? '已退款' : '部分退款' }}
            </el-tag>
          </template>
        </template>
      </el-table-column>
      <!-- 成本：与金额同口径，显示这条执照明细的办理成本；同一订单多行累加即整单成本 -->
      <el-table-column label="成本" width="104" align="right">
        <template slot-scope="{ row }">
          <template v-if="!row._sub">
            <div class="cost-cell" title="该执照的办理成本">{{ row.cost === null || row.cost === undefined ? '—' : amount(row.cost) }}</div>
          </template>
        </template>
      </el-table-column>
      <!-- 细分任务：主任务行显示「已办结/总数」，点一下就地展开；细分行显示它属于哪条办理线 -->
      <el-table-column label="细分任务" width="104" align="center">
        <template slot-scope="{ row }">
          <span v-if="row._sub" class="line-tag" :class="'l-' + row.line">{{ lineLabel(row.line) }}</span>
          <span
            v-else
            class="task-count"
            :class="{ 'is-done': row.task_total > 0 && row.task_done >= row.task_total }"
            :title="taskCountTip(row)"
            @click.stop="toggleExpand(row)"
          >
            <template v-if="row.task_total">{{ row.task_done }}/{{ row.task_total }}</template>
            <template v-else>—</template>
          </span>
        </template>
      </el-table-column>
      <!-- 主进度：主任务行只看整单状态；细分行看它自己的办理状态 -->
      <el-table-column label="主进度" width="104" align="center">
        <template slot-scope="{ row }">
          <span
            v-if="row._sub"
            class="step-chip"
            :class="'is-' + taskState(row.status)"
            :title="taskTip(row)"
          >{{ taskText(row.status) }}</span>
          <span
            v-else
            class="step-chip"
            :class="'is-' + mainProgress(row).state"
            :title="mainProgress(row).title"
          >{{ mainProgress(row).text }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="112" align="center">
        <template slot-scope="{ row }">
          <template v-if="!row._sub">
            <span v-if="row.created_at" class="time-text" :title="formatFull(row.created_at)">
              {{ formatDate(row.created_at) }}
            </span>
            <span v-else class="muted-text">—</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="最近更新" width="132">
        <template slot-scope="{ row }">
          <span v-if="row._sub">{{ row.updated_at ? formatFull(row.updated_at) : '—' }}</span>
          <span v-else>{{ row.last_timestamp ? formatFull(row.last_timestamp) : '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="进度拖延度" width="120" align="center">
        <template slot-scope="{ row }">
          <template v-if="!row._sub">
            <el-tooltip v-if="delayInfo(row)" :content="delayTip(row)" placement="top">
              <span class="delay-wrap">
                <span class="delay-chip" :style="delayStyle(row)">{{ delayInfo(row).label }}</span>
                <span class="delay-days">{{ delayInfo(row).days }}天</span>
              </span>
            </el-tooltip>
            <span v-else class="muted-text">—</span>
          </template>
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
      :title="dialogTitle"
      :visible.sync="dialogVisible"
      width="900px"
      top="5vh"
    >
      <div v-if="current" class="task-summary">
        <div class="task-cell"><span class="task-label">订单编号</span>{{ current.order_no || '—' }}</div>
        <div class="task-cell"><span class="task-label">客户</span>{{ current.client || '—' }}</div>
        <div class="task-cell"><span class="task-label">手机号</span>{{ current.phone || '—' }}</div>
        <div class="task-cell"><span class="task-label">客户微信</span>{{ current.wechat || '—' }}</div>
        <div class="task-cell"><span class="task-label">业务项</span>{{ current.items || '—' }}</div>
        <div class="task-cell"><span class="task-label">工商状态</span>{{ bizStatusText(current.biz_status) || '—' }}</div>
        <div class="task-cell"><span class="task-label">税务状态</span>{{ current.tax_status || '—' }}</div>
        <div class="task-cell"><span class="task-label">任务金额</span>{{ amount(current.revenue) }}</div>
        <div class="task-cell">
          <span class="task-label">任务状态</span>
          <el-tag :type="orderStatusType(current.status)" size="mini">{{ orderStatusText(current.status) }}</el-tag>
        </div>
      </div>

      <!-- 已取消的任务：把取消原因 / 备注 / 取消时间摆出来，一眼看到为什么关单 -->
      <div v-if="current && current.status === 'cancelled'" class="cancel-banner">
        <div class="cb-head">
          <i class="el-icon-circle-close" />
          取消订单
          <span v-if="current.cancelled_at" class="cb-time">{{ formatFull(current.cancelled_at) }}</span>
        </div>
        <div class="cb-row"><span class="cb-label">取消原因</span>{{ current.cancel_reason || '未填写' }}</div>
        <div v-if="current.cancel_note" class="cb-row"><span class="cb-label">备注</span>{{ current.cancel_note }}</div>
      </div>

      <!-- 细分任务：跟进记录挂在子任务上；主任务不再有流程图 / 时间线 -->
      <div v-if="current" class="subtask-wrap">
        <div class="subtask-head">
          <span class="subtask-title">细分任务</span>
          <span class="subtask-count">{{ currentTaskDone }}/{{ currentTasks.length }} 已办结</span>
          <span class="subtask-hint">主任务只管拆任务和指定跟进人；改状态、写跟进点「跟进」进子任务里做</span>
          <el-button type="text" size="mini" icon="el-icon-plus" @click="addTask">添加细分任务</el-button>
        </div>
        <div v-if="!currentTasks.length" class="subtask-empty">
          这个执照还没填业务项，细分任务无从拆起；可在订单里补业务项，或直接「添加细分任务」。
        </div>
        <div v-else class="subtask-list">
          <div
            v-for="task in currentTasks"
            :key="task.id"
            class="subtask-card"
            :class="'is-' + task.status"
            title="点开子任务，在里面改状态、写跟进"
            @click="openTaskDetail(task)"
          >
            <div class="sc-head">
              <span class="line-tag" :class="'l-' + task.line">{{ lineLabel(task.line) }}</span>
              <span class="st-name" :title="task.name">{{ task.name }}</span>
              <span v-if="task.source === 'manual'" class="sub-manual">手工</span>
              <span class="sc-owner" @click.stop>
                <span class="sc-owner-label">跟进人</span>
                <el-select
                  :value="task.owner || ''"
                  size="mini"
                  class="sc-owner-select"
                  :disabled="!canEditTask(task)"
                  clearable
                  filterable
                  placeholder="未分配"
                  :title="taskEditTip(task)"
                  @change="value => setTaskOwner(task, value)"
                >
                  <el-option v-for="item in ownerOptions" :key="item.username" :label="item.name" :value="item.username" />
                </el-select>
              </span>
              <span class="sc-spacer" />
              <el-tag size="mini" :type="taskTagType(task.status)">{{ taskText(task.status) }}</el-tag>
              <el-button
                type="primary"
                size="mini"
                plain
                class="sc-open"
                @click.stop="openTaskDetail(task)"
              >跟进</el-button>
              <el-button
                v-if="task.source === 'manual'"
                type="text"
                class="danger-text st-del"
                :disabled="!canEditTask(task)"
                @click.stop="removeTask(task)"
              >删除</el-button>
            </div>

            <div class="sc-foot">
              <span class="sc-records">跟进 {{ taskRecords(task).length }} 条</span>
              <span v-if="taskLatest(task)" class="sc-latest">{{ taskLatest(task) }}</span>
              <span v-if="!canEditTask(task)" class="sc-lock">
                <i class="el-icon-lock" /> 只读 · 跟进人 {{ taskOwnerName(task) || '—' }}
              </span>
              <span class="sc-spacer" />
              <span v-if="taskLastNote(task)" class="sc-last-note">{{ taskLastNote(task) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">关闭</el-button>
      </div>
    </el-dialog>

    <!-- 子任务详情：状态更新 + 跟进时间线 + 补跟进都收进这里，主任务层只留「添加 / 改跟进人」 -->
    <el-dialog
      :title="taskDialogTitle"
      :visible.sync="taskVisible"
      width="760px"
      top="6vh"
      @closed="onTaskDetailClosed"
    >
      <div v-if="activeTask" class="task-detail">
        <div class="td-head">
          <span class="line-tag" :class="'l-' + activeTask.line">{{ lineLabel(activeTask.line) }}</span>
          <span class="td-name" :title="activeTask.name">{{ activeTask.name }}</span>
          <span v-if="activeTask.source === 'manual'" class="sub-manual">手工</span>
          <span class="sc-spacer" />
          <span class="td-owner">跟进人 {{ taskOwnerName(activeTask) || '未分配' }}</span>
          <el-select
            :value="activeTask.status"
            size="small"
            class="td-status"
            :disabled="!canEditTask(activeTask)"
            :title="taskEditTip(activeTask)"
            @change="value => setTaskStatus(activeTask, value)"
          >
            <el-option v-for="item in taskStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>

        <div class="td-meta">
          <span>跟进 {{ taskRecords(activeTask).length }} 条</span>
          <span v-if="taskLatest(activeTask)">{{ taskLatest(activeTask) }}</span>
          <span class="sc-spacer" />
          <template v-if="activeTask.line === 'biz' || activeTask.line === 'tax'">
            <el-button type="text" size="mini" class="sc-file-btn" @click="openFiles(activeTask.line)">
              <i class="el-icon-picture-outline" /> 图片 {{ (files[activeTask.line] || []).length }}
            </el-button>
            <el-button type="text" size="mini" class="sc-file-btn" @click="openFilePicker(activeTask.line)">上传图片</el-button>
          </template>
        </div>

        <div v-if="!canEditTask(activeTask)" class="td-lock">
          <i class="el-icon-lock" /> 这条子任务的跟进人是 {{ taskOwnerName(activeTask) || '—' }}，只有本人或管理员能改状态、写跟进
        </div>

        <el-timeline v-if="taskRecords(activeTask).length" class="sc-timeline">
          <el-timeline-item
            v-for="item in taskRecords(activeTask)"
            :key="item.id"
            :timestamp="formatFull(item.timestamp)"
            placement="top"
            :color="dotColor(item.status)"
          >
            <div class="timeline-card">
              <div class="timeline-head">
                <span class="op-avatar" :style="{ background: avatarColor(item.operator_name || item.operator) }">{{ initial(item.operator_name || item.operator || '系') }}</span>
                <span class="op-name">{{ item.operator_name || item.operator || '系统' }}</span>
                <span class="timeline-step">{{ shortStage(item.step) }}</span>
                <!-- 普通跟进记录不带状态；状态变更类记录才显示状态，免得每条都挂个「进行中」 -->
                <el-tag v-if="item.step !== '跟进'" :type="tagType(item.status)" size="mini">{{ statusText(item.status) }}</el-tag>
                <span class="sc-spacer" />
                <el-button
                  v-if="canEditTask(activeTask)"
                  type="text"
                  class="danger-text"
                  @click="removeProgress(item)"
                >删除</el-button>
              </div>
              <div v-if="item.note" class="timeline-note">{{ item.note }}</div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <div v-else class="sc-empty">{{ canEditTask(activeTask) ? '这条子任务还没有跟进记录，在下面补一条' : '这条子任务还没有跟进记录' }}</div>

        <!-- 跟进表单：只写备注，保存后记一条跟进（状态变更走右上角的下拉，不动表单） -->
        <div v-if="canEditTask(activeTask)" class="sc-form">
          <el-input
            v-model="taskForm(activeTask).note"
            size="small"
            class="sc-form-note"
            placeholder="写点跟进情况，例如：客户已提交材料，等受理"
            @keyup.enter.native="submitTaskProgress(activeTask)"
          />
          <el-button type="primary" size="small" :loading="saving" @click="submitTaskProgress(activeTask)">保存跟进</el-button>
        </div>
      </div>

      <div slot="footer" class="dialog-footer">
        <el-button
          v-if="activeTask && activeTask.source === 'manual'"
          type="text"
          class="danger-text td-footer-del"
          :disabled="!canEditTask(activeTask)"
          @click="removeActiveTask"
        >删除子任务</el-button>
        <el-button
          v-if="activeTask && activeTask.status !== 'cancelled'"
          type="primary"
          size="small"
          :disabled="!canEditTask(activeTask)"
          :title="taskEditTip(activeTask)"
          @click="advanceTask(activeTask)"
        >{{ taskActionText(activeTask.status) }}</el-button>
        <el-button size="small" @click="taskVisible = false">关闭</el-button>
      </div>
    </el-dialog>

    <!-- 订单详情：点订单编号打开，直接按 account_id 取整单信息 -->
    <order-detail-dialog :visible.sync="orderVisible" :row="orderRow" />

    <!-- 办理线图片上传入口：真正的 input 藏起来，点「上传图片」时触发 -->
    <input
      ref="fileInput"
      type="file"
      accept="image/*"
      multiple
      class="file-input-hidden"
      @change="handleFileChange"
    >

    <!-- 查看某条办理线的图片：点缩略图看大图，支持下载、删除误传 -->
    <el-dialog :title="filesTitle" :visible.sync="filesVisible" width="720px" append-to-body>
      <div v-if="currentFiles.length" v-loading="fileUploading" class="file-grid">
        <div v-for="file in currentFiles" :key="file.id" class="file-card">
          <el-image class="file-thumb" :src="file.url" fit="cover" :preview-src-list="previewList" />
          <div class="file-meta">
            <span class="file-name" :title="file.name">{{ file.name || '图片' }}</span>
            <span class="file-ops">
              <a class="file-op" :href="file.url" :download="file.name || 'image'">下载</a>
              <span class="file-op is-danger" @click="removeFile(file)">删除</span>
            </span>
          </div>
          <div class="file-time">{{ formatFull(file.timestamp) }}</div>
        </div>
      </div>
      <div v-else class="file-empty">这条办理线还没有图片，点「上传图片」传受理单、执照照片或办结截图</div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="filesVisible = false">关闭</el-button>
        <el-button type="primary" :loading="fileUploading" @click="openFilePicker(filesLine)">继续上传</el-button>
      </div>
    </el-dialog>

  </div>
</template>

<script>
import Pagination from '@/components/Pagination'
import OrderDetailDialog from './OrderDetailDialog'
import {
  fetchProgressOverview,
  fetchProgressList,
  fetchProgressSummary,
  fetchProgressOwners,
  createProgress,
  deleteProgress,
  addProgressFile,
  deleteProgressFile,
  uploadFile,
  updateProgressTaskStatus,
  updateProgressTaskOwner,
  addProgressTask,
  deleteProgressTask
} from '@/api/progress'
import { fetchAccountDetail } from '@/api/account'
import { bizStatusText } from '@/constants/license'
import {
  STAGE_GROUPS,
  GROUP_META,
  groupKeyOfStep,
  shortStage,
  stepTagType,
  orderGroups
} from '@/constants/progress'
import { ORDER_STATUS_OPTIONS, orderStatusText, orderStatusType } from '@/constants/order'
import refreshOnActivate from '@/mixins/refresh-on-activate'

const STATUS_MAP = {
  pending: '待办',
  doing: '进行中',
  done: '已完成',
  blocked: '受阻'
}

// 列表「主进度」的展示口径：主任务只有「进行中 / 已完成」（取消、退款来自订单），
// 颜色由 state 决定（对应 .step-chip.is-*）；历史数据里的待定也按进行中显示
const MAIN_PROGRESS = {
  pending: { state: 'running', text: '进行中' },
  doing: { state: 'running', text: '进行中' },
  done: { state: 'done', text: '已完成' },
  cancelled: { state: 'cancelled', text: '取消订单' },
  refunded: { state: 'refunded', text: '已退款' }
}

// 细分任务（执照下的业务项）：自己的状态与所属办理线
const TASK_STATUS_OPTIONS = [
  { value: 'pending', label: '未开始' },
  { value: 'doing', label: '办理中' },
  { value: 'done', label: '已办结' },
  { value: 'cancelled', label: '已取消' }
]

const TASK_STATUS_META = {
  pending: { text: '未开始', state: 'pending' },
  doing: { text: '办理中', state: 'running' },
  done: { text: '已办结', state: 'done' },
  cancelled: { text: '已取消', state: 'cancelled' }
}

const TASK_LINE_LABELS = { biz: '工商', tax: '税务', other: '其他', common: '通用' }

// 拖延度分档：≤5 天正常、≤15 天轻度、≤30 天中度、再往上重度
const DELAY_LEVELS = [
  { max: 5, label: '正常', color: '#529b2e', bg: '#f0f9eb', border: '#c2e7b0' },
  { max: 15, label: '轻度拖延', color: '#d46b08', bg: '#fff7e6', border: '#ffd591' },
  { max: 30, label: '中度拖延', color: '#cf1322', bg: '#fff1f0', border: '#ffa39e' },
  { max: Infinity, label: '重度拖延', color: '#ffffff', bg: '#cf1322', border: '#cf1322' }
]

const DAY_MS = 24 * 60 * 60 * 1000

export default {
  name: 'ProgressTab',
  components: { Pagination, OrderDetailDialog },
  mixins: [refreshOnActivate],
  data() {
    return {
      loading: false,
      timelineLoading: false,
      saving: false,
      total: 0,
      list: [],
      // 从订单详情「查看进度」带过来的任务 id，列表加载完自动打开它的跟进详情
      pendingItemId: null,
      steps: [],
      stageGroups: STAGE_GROUPS,
      statusOptions: ORDER_STATUS_OPTIONS,
      summary: { tasks: 0, done: 0, covered: 0, missing: 0, by_step: [], subtasks: { total: 0, done: 0 }},
      listQuery: {
        page: 1,
        limit: 20,
        keyword: '',
        status: '',
        biz_status: '',
        tax_status: '',
        owner: ''
      },
      dialogVisible: false,
      current: null,
      timeline: [],
      // 当前这条任务（执照）下的细分任务
      currentTasks: [],
      taskStatusOptions: TASK_STATUS_OPTIONS,
      // 办理线图片：{ biz: [...], tax: [...] }，跟着跟进详情一起返回
      files: {},
      filesVisible: false,
      filesLine: '',
      fileUploading: false,
      // 订单详情弹窗：按 account_id 单独取整单
      orderVisible: false,
      orderRow: null,
      // 跟进人候选列表（子任务的跟进人下拉用）
      ownerOptions: [],
      // 子任务详情弹窗：状态更新与跟进都在这里面做
      taskVisible: false,
      activeTaskId: 0,
      activeTaskRef: null,
      // 每条子任务各自的待提交跟进
      taskForms: {}
    }
  },
  computed: {
    // 任务总数按状态拆开写在卡片下面：任务总数是全部任务，列表可能只筛了其中一部分
    statusBreakdown() {
      const counts = (this.summary && this.summary.by_status) || {}
      const parts = [
        ['doing', '进行中'],
        ['pending', '待定'],
        ['done', '已完成'],
        ['cancelled', '取消'],
        ['refunded', '已退款']
      ]
        .filter(([key]) => Number(counts[key] || 0) > 0)
        .map(([key, label]) => `${label} ${counts[key]}`)
      return parts.join(' · ')
    },
    // 当前生效的筛选条件（用于列表上方的提示条）
    activeFilters() {
      const query = this.listQuery
      const list = []
      if (query.keyword) list.push(`关键字「${query.keyword}」`)
      if (query.status) list.push(`状态 ${orderStatusText(query.status)}`)
      if (query.biz_status) list.push(`工商 ${this.bizStatusText(query.biz_status)}`)
      if (query.tax_status) list.push(`税务 ${query.tax_status}`)
      if (query.owner) {
        const found = this.ownerOptions.find(item => item.username === query.owner)
        list.push(`主跟进人 ${found ? found.name : query.owner}`)
      }
      return list
    },
    activeFilterText() {
      return this.activeFilters.join('，')
    },
    // 细分任务的整体进度：执照按业务项拆出来的小任务一共多少、办结多少
    subtaskProgress() {
      const data = (this.summary && this.summary.subtasks) || {}
      if (!data.total) return '0/0'
      return `${data.done}/${data.total}`
    },
    dialogTitle() {
      if (!this.current) return '任务进度'
      const license = this.current.license_name || `订单 #${this.current.account_id}`
      return `任务进度 · ${this.current.client || '未命名客户'} · ${license}`
    },
    // 本单涉及工商/税务时，对应分组排到前面并打「本单适用」标记
    orderedGroups() {
      return orderGroups(this.stageGroups, this.current && this.current.items)
    },
    // 当前登录账号：子任务编辑权限按「跟进人 or 管理员」判
    myUsername() {
      return this.$store.getters.username || ''
    },
    isAdmin() {
      return (this.$store.getters.roles || []).indexOf('admin') >= 0
    },
    // 当前查看的那条办理线的图片
    currentFiles() {
      return (this.files && this.files[this.filesLine]) || []
    },
    previewList() {
      return this.currentFiles.map(file => file.url)
    },
    filesTitle() {
      const group = (this.stageGroups || []).find(item => item.key === this.filesLine)
      const label = group ? group.label : '办理线'
      return `${label} · 图片 ${this.currentFiles.length} 张`
    },
    // 时间线里真正的跟进条数（不含系统自动写的「已录入」「状态变更」）
    followCount() {
      return this.timeline.filter(item => item.step !== '已录入' && item.step !== '状态变更').length
    },
    currentTaskDone() {
      return this.currentTasks.filter(task => task.status === 'done').length
    },
    // 当前打开的子任务：优先按 id 从最新列表里取，列表被重新拉过也不会指向旧对象
    activeTask() {
      if (!this.activeTaskId) return null
      const found = (this.currentTasks || []).find(task => task.id === this.activeTaskId)
      return found || this.activeTaskRef
    },
    taskDialogTitle() {
      const task = this.activeTask
      const item = this.current || {}
      const license = item.license_name || ''
      if (!task) return '子任务'
      const head = [this.lineLabel(task.line), task.name].join(' · ')
      return license ? `子任务 · ${head}（${license}）` : `子任务 · ${head}`
    }
  },
  watch: {
    // 已经在进度页时，从订单详情再点「查看进度」只会改 URL 的 query，这里同步筛选并打开任务
    '$route.query': {
      handler() {
        if (this.applyRouteQuery()) this.refresh()
      }
    }
  },
  created() {
    this.__querySign = ''
    this.applyRouteQuery()
    this.getOwners()
    this.refresh()
  },
  methods: {
    bizStatusText,
    groupKeyOfStep,
    shortStage,
    stepTagType,
    // 任务状态标签与订单口径一致（支持取消订单 / 已退款）
    orderStatusText,
    orderStatusType,
    // 从其它菜单切回本页时（keep-alive 还原）静默刷新
    refreshPage() {
      this.applyRouteQuery()
      this.getOwners()
      this.refresh()
    },
    // 首页「去跟进」/ 订单详情「查看进度」穿透过来时带的条件
    applyRouteQuery() {
      const q = this.$route.query || {}
      const sign = JSON.stringify(q)
      if (sign === this.__querySign) return false
      this.__querySign = sign
      if (!('keyword' in q) && !q.status && !q.id) return false
      this.listQuery.keyword = q.keyword || ''
      this.listQuery.status = q.status || ''
      this.listQuery.page = 1
      this.pendingItemId = q.id ? Number(q.id) : null
      return true
    },
    refresh() {
      this.getList()
      this.getSummary()
    },
    async getList() {
      this.loading = true
      try {
        const { data } = await fetchProgressOverview(this.listQuery)
        this.list = (data.items || []).map(item => this.decorateRow(item))
        this.total = data.total || 0
        if (data.steps && data.steps.length) this.steps = data.steps
        if (data.stage_groups && data.stage_groups.length) this.stageGroups = data.stage_groups
        this.openPendingTask()
      } finally {
        this.loading = false
      }
    },
    // 主任务行挂上细分任务：细分行打 _sub 标记并记住自己属于哪条主任务，
    // 双击、点按钮时都能顺着 _parent 找回执照那条任务
    decorateRow(raw) {
      const row = Object.assign({}, raw)
      row.tasks = (raw.tasks || []).map(task => Object.assign({}, task, { _sub: true, _parent: row }))
      row.task_total = row.tasks.length
      row.task_done = row.tasks.filter(task => task.status === 'done').length
      return row
    },
    // 表格序号：细分任务跟着所属主任务走，主任务按列表顺序从 1 开始
    mainIndex(row) {
      if (!row) return ''
      const main = row._sub && row._parent ? row._parent : row
      const index = this.list.indexOf(main)
      return index >= 0 ? index + 1 : ''
    },
    // 树形表格的行 key：主任务与细分任务是两张表，id 前缀区分，避免撞号
    rowKey(row) {
      return row && row._sub ? 't' + row.id : 'i' + row.id
    },
    // 主任务行浅灰底、细分任务行白底，层级一眼分清
    rowClass({ row }) {
      return row && row._sub ? 'row-sub' : 'row-main'
    },
    lineLabel(line) {
      return TASK_LINE_LABELS[line] || TASK_LINE_LABELS.other
    },
    taskText(status) {
      return (TASK_STATUS_META[status] || TASK_STATUS_META.pending).text
    },
    taskState(status) {
      return (TASK_STATUS_META[status] || TASK_STATUS_META.pending).state
    },
    taskTip(row) {
      const head = `细分任务：${row.name || ''} · ${this.taskText(row.status)}`
      if (row.status === 'done' && row.done_at) return `${head}（${this.formatFull(row.done_at)} 办结）`
      if (row.status === 'cancelled') return `${head}（主任务取消，这一项跟着关单）`
      return head
    },
    // 子任务主按钮：未开始先「开始办理」，办理中「标记办结」，已办结可重新打开
    taskActionText(status) {
      if (status === 'pending') return '开始办理'
      if (status === 'done') return '重新打开'
      return '标记办结'
    },
    // 状态色：已办结绿、办理中蓝、未开始 / 已取消灰
    taskTagType(status) {
      if (status === 'done') return 'success'
      if (status === 'doing') return ''
      return 'info'
    },
    // 卡片第二行右侧：最近一条跟进的备注，不开弹窗也能看个大概
    taskLastNote(task) {
      const records = this.taskRecords(task)
      if (!records.length) return ''
      const last = records[records.length - 1]
      const note = (last && last.note ? last.note : '').trim()
      return note ? '最近：' + note : ''
    },
    taskCountTip(row) {
      if (!row.task_total) return '这个执照还没填业务项，展开看不到细分任务'
      const open = row.task_total - row.task_done - (row.task_cancelled || 0)
      return `细分任务已办结 ${row.task_done} / ${row.task_total}，剩 ${open} 项；点一下展开`
    },
    // 展开 / 收起这一行的细分任务
    toggleExpand(row) {
      if (!row || !row.task_total) return
      const table = this.$refs.taskTable
      if (table) table.toggleRowExpansion(row)
    },
    expandAllRows(open) {
      const table = this.$refs.taskTable
      if (!table) return
      this.list.forEach(row => {
        if (row.task_total) table.toggleRowExpansion(row, open)
      })
    },
    // 细分行的主操作按钮：未开始 → 开始；办理中 → 办结；已办结 → 重新打开
    advanceTask(row) {
      const next = row.status === 'pending' ? 'doing' : (row.status === 'done' ? 'doing' : 'done')
      return this.setTaskStatus(row, next)
    },
    async setTaskStatus(task, status) {
      if (!task || !task.id || task.status === status) return
      try {
        const { data } = await updateProgressTaskStatus({ id: task.id, status })
        const updated = data.task || { id: task.id, status }
        this.applyTaskUpdate(updated)
        const parent = task._parent || this.list.find(row => (row.tasks || []).some(item => item.id === task.id))
        if (parent && data.summary) this.applyTaskSummary(parent, data.summary)
        if (status === 'done') this.$message.success('已办结：' + (updated.name || task.name))
      } catch (error) {
        // 请求层已弹出错误提示
      }
    },
    // 细分任务状态变了：列表里的细分行、弹窗里的卡片、主任务的 x/y 一起改
    applyTaskUpdate(updated) {
      if (!updated || !updated.id) return
      const keepFlags = target => ({ _sub: target._sub, _parent: target._parent })
      const patch = target => Object.assign(target, updated, keepFlags(target))
      const hit = this.currentTasks.find(task => task.id === updated.id)
      if (hit) patch(hit)
      this.list.forEach(row => {
        const target = (row.tasks || []).find(task => task.id === updated.id)
        if (!target) return
        patch(target)
        this.recountRow(row)
      })
    },
    recountRow(row) {
      const tasks = row.tasks || []
      row.task_total = tasks.length
      row.task_done = tasks.filter(task => task.status === 'done').length
      row.task_cancelled = tasks.filter(task => task.status === 'cancelled').length
    },
    // 后端回算出来的主任务状态：细分全办结会自动把主任务标完成，这里同步到行上
    applyTaskSummary(row, summary) {
      if (!row || !summary) return
      if (summary.total !== undefined) {
        row.task_total = summary.total
        row.task_done = summary.done
      }
      if (summary.status && summary.status !== row.status) {
        row.status = summary.status
        if (summary.status === 'done') row.completed_at = Date.now()
      }
      const current = this.current
      if (current && current.id === row.id) current.status = row.status
    },
    async addTask() {
      if (!this.current) return
      let name = ''
      try {
        const result = await this.$prompt('细分任务名称（例如：工商注销、税务非正常解除）', '添加细分任务', {
          confirmButtonText: '添加',
          cancelButtonText: '取消',
          inputPlaceholder: '填写这次要办的事项',
          inputValidator: value => (String(value || '').trim() ? true : '名称不能为空')
        })
        name = String(result.value || '').trim()
      } catch (error) {
        return
      }
      try {
        const { data } = await addProgressTask({ item_id: this.current.id, name })
        if (data.task) {
          data.task._sub = true
          this.currentTasks.push(data.task)
          const row = this.list.find(item => item.id === this.current.id)
          if (row) {
            data.task._parent = row
            row.tasks.push(data.task)
            this.recountRow(row)
            if (data.summary) this.applyTaskSummary(row, data.summary)
          }
        }
        this.$message.success('已添加细分任务')
      } catch (error) {
        // 请求层已弹出错误提示
      }
    },
    async removeTask(task) {
      if (!task || !task.id) return
      try {
        await this.$confirm(`删除细分任务「${task.name}」？`, '提示', {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        })
      } catch (error) {
        return
      }
      try {
        const { data } = await deleteProgressTask(task.id)
        this.currentTasks = this.currentTasks.filter(item => item.id !== task.id)
        this.list.forEach(row => {
          row.tasks = (row.tasks || []).filter(item => item.id !== task.id)
          if (row.id === task.item_id) {
            this.recountRow(row)
            if (data.summary) this.applyTaskSummary(row, data.summary)
          }
        })
        this.$message.success('已删除')
        // 删的正好是弹窗里打开的那条，顺手把子任务详情关掉
        if (this.activeTaskId === task.id) this.taskVisible = false
      } catch (error) {
        // 请求层已弹出错误提示
      }
    },
    // 从订单详情带 id 跳过来：直接打开这条任务的跟进详情；只有一条任务时退化为打开它
    openPendingTask() {
      const id = this.pendingItemId
      if (!id) return
      this.pendingItemId = null
      const row = this.list.find(item => Number(item.id) === Number(id)) ||
        (this.list.length === 1 ? this.list[0] : null)
      if (row) this.openTimeline(row)
    },
    async getSummary() {
      const { data } = await fetchProgressSummary()
      this.summary = data
    },
    // 主跟进人候选：系统用户 + 历史跟进人
    async getOwners() {
      try {
        const { data } = await fetchProgressOwners()
        this.ownerOptions = data.items || []
      } catch (error) {
        this.ownerOptions = []
      }
    },
    // 头像取名字首字，颜色按名字散列，同一个人在全页面颜色一致
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
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },
    // 清掉所有筛选，回到全部任务
    clearFilters() {
      this.listQuery.keyword = ''
      this.listQuery.status = ''
      this.listQuery.biz_status = ''
      this.listQuery.tax_status = ''
      this.listQuery.owner = ''
      this.listQuery.page = 1
      this.getList()
    },
    refundTagTip(row) {
      const refunded = Number(row.refund_amount || 0)
      const original = Number(row.revenue || 0) + refunded
      return `累计退款 ¥${this.amount(refunded)}，原金额 ¥${this.amount(original)}`
    },
    cancelTagTip(row) {
      const parts = []
      const refunded = Number(row.refund_amount || 0)
      if (refunded > 0) parts.push(`已退款 ¥${this.amount(refunded)}`)
      if (row.cancel_reason) parts.push('原因：' + row.cancel_reason)
      if (row.cancel_note) parts.push('备注：' + row.cancel_note)
      return parts.length ? parts.join('；') : '已取消订单'
    },
    openTimeline(row) {
      // 细分行双击/点按钮时，打开的是它所属的那个执照任务
      const target = row && row._sub && row._parent ? row._parent : row
      if (!target || !target.id) return
      // 双击行 / 连点按钮时避免重复打开同一个任务
      if (this.dialogVisible && this.current && this.current.id === target.id) return
      this.current = target
      this.timeline = []
      this.files = {}
      this.taskVisible = false
      this.activeTaskId = 0
      this.activeTaskRef = null
      this.taskForms = {}
      this.currentTasks = (target.tasks || []).slice()
      this.dialogVisible = true
      this.loadTimeline(target.id)
    },
    // ---- 办理线图片（工商 / 税务）----
    openFilePicker(line) {
      this.filesLine = line || this.filesLine || 'biz'
      const input = this.$refs.fileInput
      if (!input) return
      input.value = ''
      input.click()
    },
    async handleFileChange(event) {
      const picked = Array.from(event.target.files || [])
      event.target.value = ''
      if (!picked.length || !this.current) return
      const line = this.filesLine || 'biz'
      this.fileUploading = true
      let uploaded = 0
      try {
        for (const file of picked) {
          if (!/^image\//.test(file.type)) {
            this.$message.warning(`${file.name} 不是图片，已跳过`)
            continue
          }
          if (file.size > 20 * 1024 * 1024) {
            this.$message.warning(`${file.name} 超过 20MB，已跳过`)
            continue
          }
          const form = new FormData()
          form.append('file', file)
          const { data } = await uploadFile(form)
          await addProgressFile({
            item_id: this.current.id,
            line,
            url: data.url,
            name: file.name,
            size: file.size
          })
          uploaded += 1
        }
        if (uploaded) {
          this.$message.success(`已上传 ${uploaded} 张图片`)
          await this.loadTimeline(this.current.id)
        }
      } catch (error) {
        // 请求层已经弹过错误提示
      } finally {
        this.fileUploading = false
      }
    },
    openFiles(line) {
      this.filesLine = line || 'biz'
      this.filesVisible = true
    },
    async removeFile(file) {
      try {
        await this.$confirm('删除这张图片？删除后无法恢复', '提示', {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        })
      } catch (error) {
        return
      }
      try {
        await deleteProgressFile(file.id)
        this.$message.success('已删除')
        await this.loadTimeline(this.current.id)
      } catch (error) {
        // 请求层已经弹过错误提示
      }
    },
    // 双击行：主任务进跟进详情；细分任务直接进子任务跟进弹窗（父任务铺在下面做上下文）
    handleRowDblclick(row) {
      if (!row || !row.id) return
      if (row._sub) {
        if (row.status === 'cancelled') {
          this.openTimeline(row)
          return
        }
        this.openTaskFromRow(row)
        return
      }
      this.openTimeline(row)
    },
    // 订单编号 / 「订单详情」：按 account_id 拉整单信息后弹详情
    async openOrderDetail(row) {
      const parent = row && row._sub && row._parent ? row._parent : row
      const id = parent && (parent.account_id || parent.id)
      if (!id) return
      try {
        const { data } = await fetchAccountDetail(id)
        if (!data) {
          this.$message.warning('这条订单已不存在或无权查看')
          return
        }
        this.orderRow = data
        this.orderVisible = true
      } catch (error) {
        this.$message.error('这条订单已不存在或无权查看')
      }
    },
    async loadTimeline(itemId) {
      this.timelineLoading = true
      try {
        const { data } = await fetchProgressList(itemId)
        this.timeline = data.items || []
        this.files = data.files || {}
        if (data.tasks) this.currentTasks = data.tasks.slice()
        if (data.steps && data.steps.length) this.steps = data.steps
        if (data.stage_groups && data.stage_groups.length) this.stageGroups = data.stage_groups
        if (data.item && this.current) {
          this.current = Object.assign({}, this.current, data.item)
        }
      } finally {
        this.timelineLoading = false
      }
    },
    // ---- 子任务的时间线 / 编辑权限 ----
    // 只有跟进人本人和管理员能改；还没指定跟进人时谁都能改，后端第一次改动会记成跟进人
    canEditTask(task) {
      if (!task) return false
      if (this.isAdmin) return true
      const owner = (task.owner || '').trim()
      return !owner || owner === this.myUsername
    },
    taskEditTip(task) {
      if (this.canEditTask(task)) return '子任务只有跟进人本人或管理员能编辑'
      return '这条子任务的跟进人是 ' + (this.taskOwnerName(task) || '—') + '，只有本人或管理员能改'
    },
    taskOwnerName(task) {
      if (!task || !task.owner) return ''
      const found = (this.ownerOptions || []).find(item => item.username === task.owner)
      return found ? found.name : task.owner
    },
    // 子任务的时间线：优先按 task_id 精确取；还没挂上的老记录按办理线归到同线第一条
    taskRecords(task) {
      if (!task || !task.id) return []
      const all = this.timeline || []
      const exact = all.filter(item => item.task_id === task.id)
      if (exact.length) return exact
      const first = (this.currentTasks || []).filter(item => item.line === task.line)[0]
      if (!first || first.id !== task.id) return []
      return all.filter(item => !item.task_id && groupKeyOfStep(item.step) === task.line)
    },
    taskLatest(task) {
      const records = this.taskRecords(task)
      if (!records.length) return ''
      const last = records[records.length - 1]
      return `最近 ${this.formatFull(last.timestamp)}`
    },
    // 打开子任务详情：状态更新、跟进时间线、补跟进都在这个弹窗里
    openTaskDetail(task) {
      if (!task || !task.id) return
      this.activeTaskId = task.id
      this.activeTaskRef = task
      if (!this.taskForms[task.id]) {
        this.$set(this.taskForms, task.id, { note: '' })
      }
      this.taskVisible = true
    },
    onTaskDetailClosed() {
      this.activeTaskId = 0
      this.activeTaskRef = null
    },
    // 列表里细分行的「跟进」：先把执照这条主任务拉出来当作上下文，再叠上子任务详情
    openTaskFromRow(row) {
      if (!row || !row.id) return
      const parent = row._parent || this.list.find(item => (item.tasks || []).some(task => task.id === row.id))
      if (parent) this.openTimeline(parent)
      this.openTaskDetail(row)
    },
    removeActiveTask() {
      const task = this.activeTask
      if (task) this.removeTask(task)
    },
    // 模板里直接 taskForm(task).note 取到的是响应式对象；先确保它存在
    taskForm(task) {
      if (!task || !task.id) return { note: '' }
      if (!this.taskForms[task.id]) {
        this.$set(this.taskForms, task.id, { note: '' })
      }
      return this.taskForms[task.id]
    },
    async submitTaskProgress(task) {
      if (!task || !task.id) return
      if (!this.canEditTask(task)) {
        this.$message.warning('只有这条子任务的跟进人或管理员能补跟进')
        return
      }
      const form = this.taskForm(task)
      const note = (form.note || '').trim()
      if (!note) {
        this.$message.warning('先写点跟进情况，再保存')
        return
      }
      this.saving = true
      try {
        // 表单不再选阶段和状态：过程记录统一记成「跟进」，办结走右上角状态下拉
        await createProgress({
          item_id: this.current.id,
          task_id: task.id,
          step: '跟进',
          status: 'doing',
          note
        })
        this.$message.success('已添加跟进')
        this.$set(this.taskForms, task.id, { note: '' })
        await this.loadTimeline(this.current.id)
        this.refresh()
      } catch (error) {
        // 请求层已弹出错误提示
      } finally {
        this.saving = false
      }
    },
    // 转派 / 认领子任务：管理员可以给任何人，跟进人本人可以转给别人
    async setTaskOwner(task, owner) {
      if (!task || !task.id) return
      const previous = task.owner || ''
      const next = owner || ''
      if (previous === next) return
      try {
        const { data } = await updateProgressTaskOwner({ id: task.id, owner: next })
        if (data && data.task) Object.assign(task, data.task)
        this.$message.success(next ? '跟进人已改为 ' + (this.taskOwnerName(data.task || task) || next) : '已清空跟进人')
      } catch (error) {
        this.$set(task, 'owner', previous)
      }
    },
    groupColor(key) {
      return (GROUP_META[key] || GROUP_META.common).color
    },
    groupLabel(step) {
      return (GROUP_META[groupKeyOfStep(step)] || GROUP_META.common).label
    },
    // 表格「主进度」：只展示整条任务的主状态（待定 / 进行中 / 已完成 / 取消订单 / 已退款），
    // 不再把工商、税务各条办理线的节点摊在列表里；细分节点在跟进详情的子任务时间线里看
    mainProgress(row) {
      const status = (row && row.status) || 'pending'
      const meta = MAIN_PROGRESS[status] || MAIN_PROGRESS.pending
      return {
        state: meta.state,
        text: meta.text,
        title: this.mainProgressTip(row, meta.text)
      }
    },
    // 主进度的悬浮说明：主状态一行，后面附各条办理线最后登记的节点，信息不丢但不占列表
    mainProgressTip(row, statusLabel) {
      const head = `主进度：${statusLabel}`
      const lines = (row.progress_lines || []).filter(line => line.open_step || line.last_step)
      if (!lines.length) return `${head}（还没有办理节点记录）`
      const detail = lines.map(line => {
        const step = line.open_step || line.last_step
        return `${line.label}：${step}${line.open_step ? '' : '（已走完）'}`
      })
      return `${head}｜${detail.join('　')}`
    },
    // 拖延度：未结案按「创建 → 现在」算；已结案按「创建 → 结案」定格
    delayInfo(row) {
      const created = row.created_at
      if (!created) return null
      const done = row.status === 'done'
      const end = done ? row.completed_at || row.last_timestamp || created : Date.now()
      const days = Math.max(0, Math.floor((end - created) / DAY_MS))
      const level = DELAY_LEVELS.find(item => days <= item.max) || DELAY_LEVELS[DELAY_LEVELS.length - 1]
      return { days, done, label: level.label, color: level.color, bg: level.bg, border: level.border }
    },
    delayStyle(row) {
      const info = this.delayInfo(row)
      if (!info) return {}
      return { color: info.color, background: info.bg, borderColor: info.border }
    },
    delayTip(row) {
      const info = this.delayInfo(row)
      if (!info) return ''
      const base = `创建于 ${this.formatFull(row.created_at)}`
      if (info.done) return `${base}，已结案，用时 ${info.days} 天`
      const last = row.last_timestamp ? `，最近更新 ${this.formatFull(row.last_timestamp)}` : ''
      return `${base}${last}，已等待 ${info.days} 天（5 天内正常，15 天轻度，30 天中度，超过为重度）`
    },
    formatDate(timestamp) {
      if (!timestamp) return ''
      const date = new Date(timestamp)
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    },
    removeProgress(item) {
      this.$confirm('确认删除这条跟进记录吗？删除后只是标记为「已删除」，数据仍保留在数据库里。', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => deleteProgress({ id: item.id }))
        .then(() => {
          this.$message.success('已删除')
          this.loadTimeline(this.current.id)
          this.refresh()
        })
        .catch(() => {})
    },
    statusText(status) {
      return STATUS_MAP[status] || '进行中'
    },
    tagType(status) {
      return status === 'done' ? 'success' : status === 'blocked' ? 'danger' : status === 'pending' ? 'info' : 'warning'
    },
    dotColor(status) {
      return status === 'done' ? '#67c23a' : status === 'blocked' ? '#f56c6c' : '#409eff'
    },
    amount(value) {
      if (value === null || value === undefined || value === '') return '待定'
      const num = Number(value)
      if (Number.isNaN(num)) return '待定'
      return num === Math.trunc(num) ? String(Math.trunc(num)) : String(Math.round(num * 100) / 100)
    },
    formatFull(timestamp) {
      if (!timestamp) return ''
      const date = new Date(timestamp)
      const pad = v => String(v).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    }
  }
}
</script>

<style lang="scss" scoped>
.progress-panel {
  .stat-row {
    margin-bottom: 16px;
  }

  .stat-card {
    background: #f7f8fa;
    border-radius: 4px;
    padding: 12px 14px;
    min-height: 68px;
  }

  .stat-label {
    color: #909399;
    font-size: 12px;
  }

  .stat-value {
    margin-top: 6px;
    font-size: 20px;
    font-weight: 600;
    color: #303133;

    &.ok { color: #67c23a; }
    &.warn { color: #e6a23c; }
  }

  .stat-steps {
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
  }

  // 任务总数下面那行状态拆分，用来跟列表条数对账
  .stat-sub {
    margin-top: 4px;
    font-size: 12px;
    color: #909399;
    line-height: 16px;
  }

  // 筛选提示条：命中多少条 / 全部多少条
  .filter-banner {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin: -4px 0 12px;
    padding: 7px 12px;
    background: #f4f8ff;
    border: 1px solid #d9e7ff;
    border-radius: 4px;
    font-size: 12px;
    color: #4a5a72;

    i {
      color: #409eff;
    }

    b {
      color: #2f6fe4;
      font-weight: 600;
    }

    .fb-total {
      color: #909399;
    }
  }

  .step-tag {
    margin: 0 6px 4px 0;
  }

  .stat-empty {
    color: #c0c4cc;
    font-size: 13px;
  }

  .keyword-input {
    width: 240px;
  }

  .filter-container .filter-item {
    margin-right: 8px;
    margin-bottom: 8px;
  }

  .filter-tip {
    color: #909399;
    font-size: 12px;
    margin-left: 8px;
  }

  // 双击整行可直接进跟进详情，给个手型提示
  ::v-deep .el-table__body tr {
    cursor: pointer;
  }

  .muted-text {
    color: #c0c4cc;
  }

  // 表头浅蓝灰、主任务行浅蓝、细分任务行白色，层级一眼分清
  ::v-deep .task-table {
    th {
      background: #98a4c3;
      color: #1f2d3d;
      font-weight: 600;
      border-right-color: rgba(255, 255, 255, 0.45);
    }

    th .cell {
      color: #1f2d3d;
    }

    .el-table__body tr.row-main > td {
      background: #ecf5ff;
    }

    .el-table__body tr.row-sub > td {
      background: #fff;
    }

    // 细分任务左侧一条浅色引导线，层级更清楚
    .el-table__body tr.row-sub > td:first-child {
      box-shadow: inset 3px 0 0 #e8ebf0;
    }

    .el-table__body tr.row-main:hover > td {
      background: #e0eefd;
    }

    .el-table__body tr.row-sub:hover > td {
      background: #f5faff;
    }

    // 当前选中行比主任务底色更深一档，选中状态还看得出来
    .el-table__body tr.current-row > td {
      background: #d5e8fc;
    }
  }

  // 主任务行是浅色底，行内文字统一压深，避免浅灰字看不清
  ::v-deep .task-table .el-table__body tr.row-main {
    .cell-main,
    .amount-cell {
      color: #1f2d3d;
    }

    .cell-sub {
      color: #3d4854;
    }

    .time-text,
    .order-no-text {
      color: #2b3541;
    }

    .order-no-text.is-link {
      color: #2f6fd0;
    }

    .amount-cell.is-refunded {
      color: #6b7280;
    }
  }

  // 展开箭头原来独占一行，把主任务行撑成三行；改成绝对定位后和执照名同一行
  ::v-deep .task-table > .el-table__body-wrapper tr.row-main td:first-child .cell {
    position: relative;
    padding-left: 26px;
  }

  // 箭头和执照名第一行对齐（跟着名字走，不跟着整格居中）
  ::v-deep .task-table .el-table__expand-icon {
    position: absolute;
    left: 2px;
    top: 0;
  }

  .order-no-text {
    font-family: Menlo, Consolas, monospace;
    font-size: 12px;
    color: #606266;

    // 订单编号可点：点一下穿到订单详情
    &.is-link {
      color: #409eff;
      cursor: pointer;
      border-bottom: 1px dashed transparent;
      transition: color 0.15s, border-color 0.15s;

      &:hover {
        color: #66b1ff;
        border-bottom-color: #66b1ff;
      }
    }
  }

  .time-text {
    color: #606266;
    font-size: 12px;
  }

  // 主进度：一条任务只出一个状态标签，按状态着色
  .step-chip {
    display: inline-block;
    padding: 0 8px;
    font-size: 12px;
    line-height: 20px;
    border: 1px solid transparent;
    border-radius: 3px;
    white-space: nowrap;

    // 待定：白底虚线，弱化
    &.is-pending {
      color: #909399;
      background: #fff;
      border-color: #dcdfe6;
      border-style: dashed;
    }

    // 进行中：黄
    &.is-running {
      color: #d46b08;
      background: #fff7e6;
      border-color: #ffd591;
    }

    // 已完成：绿 + ✓
    &.is-done {
      color: #529b2e;
      background: #f0f9eb;
      border-color: #c2e7b0;

      &::before {
        content: '✓';
        margin-right: 2px;
        font-size: 11px;
      }
    }

    // 取消订单：灰底删除线
    &.is-cancelled {
      color: #909399;
      background: #f4f4f5;
      border-color: #dcdfe6;
      text-decoration: line-through;
    }

    // 已退款：红
    &.is-refunded {
      color: #cf1322;
      background: #fff1f0;
      border-color: #ffa39e;
    }
  }

  // 拖延度：色块 + 天数
  .delay-wrap {
    display: inline-flex;
    align-items: center;
    cursor: default;
  }

  .delay-chip {
    padding: 0 6px;
    font-size: 12px;
    line-height: 20px;
    border: 1px solid transparent;
    border-radius: 10px;
    white-space: nowrap;
  }

  .delay-days {
    margin-left: 5px;
    font-size: 12px;
    color: #909399;
    white-space: nowrap;
  }

  .cell-main {
    font-size: 13px;
    font-weight: 500;
    color: #303133;
    line-height: 20px;
  }

  .cell-sub {
    font-size: 12px;
    color: #909399;
    line-height: 18px;
  }

  // ---- 细分任务（展开行）----
  // inline-flex 才能和 el-table 的缩进占位块待在同一行，否则会多出一行空白
  .sub-name {
    display: inline-flex;
    align-items: center;
    padding-left: 5px;
    font-size: 13px;
    color: #303133;
    line-height: 20px;
  }

  .sub-arrow {
    margin-right: 5px;
    color: #c0c4cc;
    font-size: 12px;
  }

  .sub-text {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sub-manual {
    margin-left: 6px;
    padding: 0 5px;
    font-size: 11px;
    line-height: 16px;
    color: #b88230;
    background: #fdf6ec;
    border: 1px solid #f5dab1;
    border-radius: 3px;
  }

  // 细分任务归属的办理线：工商蓝、税务橙、其他灰
  .line-tag {
    display: inline-block;
    padding: 0 6px;
    font-size: 11px;
    line-height: 18px;
    border-radius: 3px;
    border: 1px solid transparent;
    white-space: nowrap;

    &.l-biz {
      color: #1a7fdd;
      background: #ecf5ff;
      border-color: #b3d8ff;
    }

    &.l-tax {
      color: #b88230;
      background: #fdf6ec;
      border-color: #f5dab1;
    }

    &.l-other,
    &.l-common {
      color: #909399;
      background: #f4f4f5;
      border-color: #e4e7ed;
    }
  }

  // 主任务行「已办结/总数」小徽标，点一下展开细分
  .task-count {
    display: inline-block;
    min-width: 34px;
    padding: 0 6px;
    font-size: 12px;
    line-height: 20px;
    color: #1a7fdd;
    background: #ecf5ff;
    border: 1px solid #b3d8ff;
    border-radius: 10px;
    cursor: pointer;
    user-select: none;

    &:hover {
      background: #d9ecff;
    }

    &.is-done {
      color: #529b2e;
      background: #f0f9eb;
      border-color: #c2e7b0;
    }
  }

  // ---- 跟进详情里的细分任务清单 ----
  .subtask-wrap {
    margin: 4px 0 12px;
    padding: 10px 12px;
    background: #fafbfc;
    border: 1px solid #ebeef5;
    border-radius: 4px;
  }

  .subtask-head {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
  }

  .subtask-title {
    font-size: 13px;
    font-weight: 600;
    color: #303133;
  }

  .subtask-count {
    margin: 0 10px;
    font-size: 12px;
    color: #909399;
  }

  .subtask-hint {
    margin-right: 10px;
    font-size: 12px;
    color: #c0c4cc;
  }

  .subtask-empty {
    font-size: 12px;
    color: #909399;
    line-height: 22px;
  }

  .subtask-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .subtask-card {
    padding: 6px 10px;
    background: #fff;
    border: 1px solid #ebeef5;
    border-left: 3px solid #dcdfe6;
    border-radius: 3px;
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s;

    &:hover {
      border-color: #c6e2ff;
      box-shadow: 0 1px 6px rgba(64, 158, 255, 0.12);
    }

    &.is-doing {
      border-left-color: #409eff;
    }

    &.is-done {
      border-left-color: #67c23a;
      background: #fbfdf8;
    }

    &.is-cancelled {
      border-left-color: #dcdfe6;
      opacity: 0.7;
    }
  }

  // 第一行：办理线 / 名称 / 跟进人 / 图片 / 状态
  .sc-head {
    display: flex;
    align-items: center;
  }

  .sc-owner {
    display: flex;
    align-items: center;
    margin-left: 14px;
  }

  .sc-owner-label {
    margin-right: 4px;
    font-size: 12px;
    color: #909399;
  }

  .sc-owner-select {
    width: 116px;
  }

  .sc-file-btn {
    margin-left: 10px;
    padding: 0 2px;
    font-size: 12px;
    color: #606266;
  }

  .sc-head .st-status {
    margin-left: 10px;
  }

  // 第二行：跟进条数 / 最近时间 / 写跟进
  .sc-foot {
    display: flex;
    align-items: center;
    margin-top: 4px;
    font-size: 12px;
    color: #909399;
  }

  .sc-toggle {
    cursor: pointer;
    color: #409eff;

    &:hover {
      text-decoration: underline;
    }
  }

  .sc-records {
    color: #606266;
  }

  .sc-open {
    margin-left: 10px;
  }

  // 卡片右侧的最近一条跟进备注，太长就省略
  .sc-last-note {
    max-width: 380px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #c0c4cc;
  }

  .sc-latest {
    margin-left: 10px;
    color: #c0c4cc;
  }

  .sc-lock {
    margin-left: 10px;
    color: #e6a23c;
  }

  .sc-spacer {
    flex: 1;
  }

  // ---- 子任务详情弹窗：状态更新 + 跟进时间线 + 补跟进 ----
  .task-detail {
    padding: 2px 0 4px;
  }

  .td-head {
    display: flex;
    align-items: center;
    padding-bottom: 8px;
  }

  .td-name {
    max-width: 380px;
    margin-left: 8px;
    font-size: 14px;
    font-weight: 600;
    color: #303133;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .td-owner {
    margin-right: 10px;
    font-size: 12px;
    color: #909399;
  }

  .td-status {
    width: 108px;
  }

  .td-meta {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
    padding: 6px 10px;
    font-size: 12px;
    color: #909399;
    background: #fafbfc;
    border: 1px solid #ebeef5;
    border-radius: 4px;
  }

  .td-lock {
    margin-bottom: 10px;
    padding: 6px 10px;
    font-size: 12px;
    line-height: 18px;
    color: #e6a23c;
    background: #fdf6ec;
    border: 1px solid #faecd8;
    border-radius: 4px;
  }

  .td-footer-del {
    float: left;
  }

  .sc-timeline {
    padding-left: 2px;
    margin-bottom: 6px;
  }

  .sc-empty {
    padding: 6px 0 10px;
    font-size: 12px;
    color: #909399;
  }

  .sc-form {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px dashed #ebeef5;
  }

  .sc-form-note {
    flex: 1;
  }

  .st-name {
    margin-left: 8px;
    max-width: 300px;
    font-size: 13px;
    color: #303133;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .st-spacer {
    flex: 1;
  }

  .st-time {
    margin-right: 10px;
    font-size: 12px;
    color: #909399;
    white-space: nowrap;
  }

  .st-status {
    width: 96px;
  }

  .st-del {
    margin-left: 6px;
  }

  .task-summary {
    display: flex;
    flex-wrap: wrap;
    background: #f7f8fa;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 12px;
    font-size: 13px;
    color: #303133;
  }

  .task-cell {
    width: 33.33%;
    padding: 3px 0;
  }

  .task-label {
    color: #909399;
    margin-right: 8px;
  }

  // 已取消任务的原因条
  .cancel-banner {
    margin-bottom: 12px;
    padding: 9px 12px;
    background: #fdf6f6;
    border: 1px solid #fbd9d9;
    border-radius: 4px;
    font-size: 13px;
    color: #606266;
    line-height: 20px;

    .cb-head {
      display: flex;
      align-items: center;
      font-weight: 600;
      color: #f56c6c;
      margin-bottom: 4px;

      i {
        margin-right: 5px;
        font-size: 14px;
      }
    }

    .cb-time {
      margin-left: auto;
      font-weight: 400;
      font-size: 12px;
      color: #a8abb2;
    }

    .cb-label {
      display: inline-block;
      min-width: 56px;
      color: #909399;
      margin-right: 6px;
    }

    .cb-row {
      word-break: break-all;
    }
  }

  // 子任务那一行的跟进人小标签（主任务不再有主跟进人）
  .sub-owner {
    display: inline-flex;
    align-items: center;
    margin-left: 10px;
    padding-right: 6px;
    font-size: 12px;
    color: #606266;
    white-space: nowrap;

    &.is-empty {
      color: #c0c4cc;
    }
  }

  .owner-avatar {
    width: 20px;
    height: 20px;
    line-height: 20px;
    border-radius: 50%;
    color: #fff;
    font-size: 11px;
    text-align: center;
    flex: none;
    margin-right: 5px;

    &.sm {
      width: 16px;
      height: 16px;
      line-height: 16px;
      font-size: 10px;
      margin-right: 4px;
    }
  }

  .opt-done {
    float: right;
    color: #67c23a;
    font-size: 12px;
  }

  .divider-tip {
    margin-left: 8px;
    font-size: 12px;
    font-weight: 400;
    color: #909399;
  }

  // 新增跟进：工商 / 税务 / 通用三列独立
  .line-grid {
    display: flex;
    gap: 12px;
    margin-bottom: 4px;
  }

  .line-card {
    flex: 1;
    min-width: 0;
    padding: 8px 10px 10px;
    border: 1px solid #ebeef5;
    border-radius: 6px;
    background: #fafbfc;

    &.k-biz {
      border-color: #d9ecff;
      background: #f5faff;
    }

    &.k-tax {
      border-color: #faecd8;
      background: #fffbf5;
    }
  }

  .line-head {
    display: flex;
    align-items: center;
    font-size: 12px;
    color: #606266;
    margin-bottom: 7px;
  }

  .line-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 6px;
    flex: none;
  }

  .line-name {
    font-weight: 600;
  }

  .line-badge {
    margin-left: 5px;
    padding: 0 4px;
    font-size: 11px;
    line-height: 15px;
    color: #409eff;
    background: #ecf5ff;
    border: 1px solid #b3d8ff;
    border-radius: 3px;
  }

  .line-count {
    margin-left: auto;
    color: #909399;
  }

  .line-select {
    width: 100%;
  }

  .line-foot {
    display: flex;
    align-items: center;
    margin-top: 7px;
  }

  .line-status {
    width: 86px;
    flex: none;
  }

  .line-next {
    margin-left: 8px;
    font-size: 12px;
    color: #409eff;
    cursor: pointer;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;

    &:hover {
      text-decoration: underline;
    }

    &.is-done {
      color: #67c23a;
      cursor: default;
      text-decoration: none;
    }
  }

  .note-form {
    margin-top: 10px;
  }

  .group-badge {
    padding: 0 5px;
    margin-right: 6px;
    font-size: 11px;
    line-height: 16px;
    border-radius: 3px;

    &.g-biz {
      color: #409eff;
      background: #ecf5ff;
      border: 1px solid #b3d8ff;
    }

    &.g-tax {
      color: #e6a23c;
      background: #fdf6ec;
      border: 1px solid #f5dab1;
    }
  }

  .timeline-wrap {
    max-height: 40vh;
    overflow-y: auto;
    padding: 4px 4px 0;
    border-top: 1px dashed #ebeef5;
    margin-top: 4px;
  }

  .timeline-title {
    display: flex;
    align-items: baseline;
    font-size: 13px;
    font-weight: 600;
    color: #303133;
    padding: 8px 0 6px;
    position: sticky;
    top: 0;
    background: #fff;
    z-index: 2;
  }

  .timeline-tip {
    margin-left: 8px;
    font-weight: 400;
    font-size: 12px;
    color: #909399;
  }

  .timeline-empty {
    color: #909399;
    font-size: 13px;
    text-align: center;
    padding: 24px 0;
  }

  .timeline-card {
    background: #f7f8fa;
    border-radius: 4px;
    padding: 8px 12px;
  }

  .timeline-head {
    display: flex;
    align-items: center;

    .op-avatar {
      width: 20px;
      height: 20px;
      line-height: 20px;
      border-radius: 50%;
      color: #fff;
      font-size: 11px;
      text-align: center;
      flex: none;
      margin-right: 6px;
    }

    .op-name {
      font-size: 13px;
      font-weight: 600;
      color: #303133;
      margin-right: 10px;
    }

    .timeline-step {
      font-weight: 600;
      margin-right: 8px;
    }

    .el-tag {
      margin-right: 10px;
    }

    .timeline-time {
      flex: 1;
      text-align: right;
      color: #c0c4cc;
      font-size: 12px;
      margin-right: 10px;
    }
  }

  .timeline-note {
    margin-top: 6px;
    color: #606266;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-line;
  }

  .danger-text {
    color: #f56c6c;
  }
}

// 金额列：退款后金额置灰，下面挂退款/取消标签
.amount-cell {
  font-family: Menlo, Consolas, monospace;
  font-size: 12px;
  color: #303133;

  &.is-refunded {
    color: #a8abb2;
  }
}

// 成本列：等宽字体与金额列对齐，橙棕色区分「支出」语义，浅蓝底主任务行也可读
.cost-cell {
  font-family: Menlo, Consolas, monospace;
  font-size: 12px;
  color: #b26a00;
}

.refund-tag {
  margin-top: 2px;
  transform: scale(0.92);
  transform-origin: right center;
}

// 办理线图片：上传入口隐藏真实的 input；弹窗里网格展示，点缩略图看大图
.file-input-hidden {
  display: none;
}

.file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  max-height: 60vh;
  overflow-y: auto;
}

.file-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.file-thumb {
  display: block;
  width: 100%;
  height: 110px;
  cursor: zoom-in;
  background: #f5f7fa;
}

.file-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 4px 8px 0;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #606266;
}

.file-ops {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.file-op {
  font-size: 12px;
  color: #409eff;
  cursor: pointer;
  text-decoration: none;

  &.is-danger {
    color: #f56c6c;
  }
}

.file-time {
  padding: 0 8px 6px;
  font-size: 11px;
  color: #a8abb2;
}

.file-empty {
  padding: 30px 0;
  text-align: center;
  font-size: 13px;
  color: #909399;
}

</style>
