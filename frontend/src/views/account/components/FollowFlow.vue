<template>
  <div v-loading="loading" class="follow-flow">
    <div class="ff-title">
      跟进流程图
      <span class="ff-title-tip">每个节点都标了「谁做的、什么时候做的」；点节点可把该阶段填进下方新增跟进</span>
    </div>
    <!-- 顶部：主跟进人 + 跟进概况（谁在跟、跟了多少次、最近什么时候） -->
    <div class="ff-summary">
      <div class="ff-owner" :class="{ 'is-auto': ownerAuto, 'is-empty': !ownerName }">
        <span class="ff-avatar" :style="{ background: ownerColor }">{{ ownerInitial }}</span>
        <div class="ff-owner-text">
          <span class="ff-owner-label">主跟进人</span>
          <span class="ff-owner-name">
            {{ ownerName || '未分配' }}
            <em v-if="ownerAuto" class="ff-auto-tag">自动</em>
          </span>
        </div>
      </div>
      <div class="ff-meta">
        <span class="ff-meta-item">共 <b>{{ followCount }}</b> 条跟进</span>
        <span class="ff-meta-item">最近 <b>{{ lastTimeText }}</b></span>
        <span v-if="people.length" class="ff-people">
          <span class="ff-people-label">参与人</span>
          <span v-for="person in people" :key="person.name" class="ff-person" :title="person.name + '：' + person.count + ' 条'">
            <span class="ff-person-avatar" :style="{ background: person.color }">{{ person.initial }}</span>
            {{ person.name }}<i v-if="person.count > 1">×{{ person.count }}</i>
          </span>
        </span>
      </div>
    </div>

    <!-- 每条办理线一条流水线：节点 = 阶段，节点下方是「谁、什么时候」 -->
    <div v-for="group in rows" :key="group.key" class="ff-group">
      <div class="ff-head">
        <span class="ff-dot" :style="{ background: group.color }" />
        <span class="ff-label">{{ group.label }}</span>
        <span v-if="group.matched" class="ff-badge">本单适用</span>
        <!-- 工商 / 税务两条线可以传图片：受理单、执照照片、办结截图 -->
        <span class="ff-count">{{ group.doneCount }}/{{ group.stages.length }}</span>
        <span v-if="group.key !== 'common'" class="ff-file-tools">
          <button type="button" class="ff-file-btn" @click.stop="$emit('upload', group.key)">
            <i class="el-icon-camera" /> 上传图片
          </button>
          <button
            v-if="fileCount(group.key)"
            type="button"
            class="ff-file-btn is-has"
            @click.stop="$emit('files', group.key)"
          >
            <i class="el-icon-picture-outline" /> 图片 {{ fileCount(group.key) }}
          </button>
        </span>
      </div>
      <div class="ff-track">
        <div
          v-for="(node, index) in group.nodes"
          :key="node.stage"
          class="ff-node"
          :class="['is-' + node.state, { 'is-current': node.current, 'is-last': index === group.nodes.length - 1 }]"
          :style="{ '--ff-color': group.color }"
          :title="node.tip"
          @click="$emit('pick', node.stage)"
        >
          <span class="ff-dot-line" />
          <span class="ff-node-dot" />
          <span class="ff-node-name">{{ node.name }}</span>
          <span class="ff-node-who" :class="{ 'is-empty': !node.who }">{{ node.who || '待办' }}</span>
          <span class="ff-node-time">{{ node.time || '—' }}</span>
        </div>
      </div>
    </div>

    <div v-if="!rows.length" class="ff-empty">这条任务还没有办理流程</div>

    <div class="ff-legend">
      <span class="ff-legend-item"><i class="lg is-done" />已完成</span>
      <span class="ff-legend-item"><i class="lg is-doing" />进行中</span>
      <span class="ff-legend-item"><i class="lg is-blocked" />受阻</span>
      <span class="ff-legend-item"><i class="lg is-todo" />待办</span>
      <span class="ff-legend-tip">点节点可把该阶段填进下方「新增跟进」</span>
    </div>
  </div>
</template>

<script>
import { GROUP_META, shortStage } from '@/constants/progress'

const AVATAR_COLORS = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#8e6cf0', '#13c2c2', '#d46b08']
// 系统自动写入的进度：建单的「已录入」和改任务状态产生的「状态变更」，统计跟进人时不算
const AUTO_STEPS = ['已录入', '状态变更']

function pad(value) {
  return String(value).padStart(2, '0')
}

function shortTime(stamp) {
  if (!stamp) return ''
  const date = new Date(Number(stamp))
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function fullTime(stamp) {
  if (!stamp) return ''
  const date = new Date(Number(stamp))
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export default {
  name: 'FollowFlow',
  props: {
    // 办理线分组：[{ key, label, stages, matched }]
    groups: {
      type: Array,
      default: () => []
    },
    // 该任务的完整跟进记录（按时间升序）
    records: {
      type: Array,
      default: () => []
    },
    // 主跟进人 { name, auto }
    owner: {
      type: Object,
      default: () => ({})
    },
    loading: {
      type: Boolean,
      default: false
    },
    // 各办理线的图片附件：{ biz: [...], tax: [...] }
    files: {
      type: Object,
      default: () => ({})
    }
  },
  computed: {
    ownerName() {
      return (this.owner && (this.owner.name || this.owner.owner)) || ''
    },
    ownerAuto() {
      return !!(this.owner && this.owner.auto)
    },
    ownerInitial() {
      const name = this.ownerName
      return name ? name.slice(0, 1) : '?'
    },
    ownerColor() {
      if (!this.ownerName) return '#c0c4cc'
      return AVATAR_COLORS[this.ownerName.charCodeAt(0) % AVATAR_COLORS.length]
    },
    // 阶段 → 最近一条记录（同一阶段可能补录多次，取最后一次）
    stepMap() {
      const map = {}
      this.records.forEach(item => {
        const key = item.step || ''
        if (!key) return
        map[key] = item
      })
      return map
    },
    // 真实跟进条数：系统自动写的「已录入」「状态变更」不算
    followCount() {
      return this.records.filter(item => AUTO_STEPS.indexOf(item.step) < 0).length
    },
    lastTimeText() {
      const last = this.records[this.records.length - 1]
      return last ? fullTime(last.timestamp) : '—'
    },
    // 参与人排行：谁跟得最多，一眼看出这单是谁在推
    people() {
      const counter = {}
      this.records.forEach(item => {
        if (!item.step || AUTO_STEPS.indexOf(item.step) >= 0) return
        const name = item.operator_name || item.operator
        if (!name) return
        if (!counter[name]) counter[name] = { name, count: 0, last: 0 }
        counter[name].count += 1
        counter[name].last = Math.max(counter[name].last, Number(item.timestamp) || 0)
      })
      return Object.keys(counter)
        .map(key => {
          const item = counter[key]
          return {
            name: item.name,
            count: item.count,
            initial: item.name.slice(0, 1),
            color: AVATAR_COLORS[item.name.charCodeAt(0) % AVATAR_COLORS.length]
          }
        })
        .sort((a, b) => b.count - a.count)
        .slice(0, 4)
    },
    rows() {
      const list = this.groups && this.groups.length ? this.groups : []
      return list.map(group => {
        const stages = group.stages || []
        let lastDoneIndex = -1
        const nodes = stages.map((stage, index) => {
          const record = this.stepMap[stage]
          const status = (record && record.status) || ''
          let state = 'todo'
          if (record) {
            if (status === 'done') {
              state = 'done'
              lastDoneIndex = index
            } else if (status === 'blocked') {
              state = 'blocked'
            } else {
              state = 'doing'
            }
          }
          const who = record ? (record.operator_name || record.operator || '') : ''
          return {
            stage,
            name: shortStage(stage),
            state,
            who,
            time: record ? shortTime(record.timestamp) : '',
            current: false,
            tip: record
              ? `${shortStage(stage)} · ${who || '系统'} · ${this.statusText(status)} · ${fullTime(record.timestamp)}${record.note ? ' · ' + record.note : ''}`
              : `${shortStage(stage)} · 还没开始`
          }
        })
        // 当前节点：有进行中/受阻的就取它，否则取最后一个已完成的下一个
        let currentIndex = nodes.findIndex(node => node.state === 'doing' || node.state === 'blocked')
        if (currentIndex < 0 && lastDoneIndex + 1 < nodes.length) currentIndex = lastDoneIndex + 1
        if (currentIndex >= 0) nodes[currentIndex].current = true
        return {
          key: group.key,
          label: group.label,
          matched: !!group.matched,
          stages,
          nodes,
          color: (GROUP_META[group.key] || GROUP_META.common).color,
          doneCount: nodes.filter(node => node.state === 'done').length
        }
      })
    }
  },
  methods: {
    statusText(status) {
      return { done: '已完成', doing: '进行中', pending: '待办', blocked: '受阻' }[status] || '进行中'
    },
    // 这条办理线已经传了几张图
    fileCount(line) {
      const list = (this.files && this.files[line]) || []
      return list.length
    }
  }
}
</script>

<style lang="scss" scoped>
.follow-flow {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  padding: 10px 12px 6px;
  margin-bottom: 12px;
}

// ---- 顶部概况 ----
.ff-title {
  display: flex;
  align-items: baseline;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.ff-title-tip {
  margin-left: 8px;
  font-weight: 400;
  font-size: 12px;
  color: #909399;
}

.ff-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 18px;
  padding-bottom: 10px;
  border-bottom: 1px dashed #ebeef5;
}

.ff-owner {
  display: flex;
  align-items: center;
  min-width: 150px;

  .ff-avatar {
    width: 30px;
    height: 30px;
    line-height: 30px;
    border-radius: 50%;
    color: #fff;
    font-size: 13px;
    text-align: center;
    margin-right: 8px;
    flex: none;
  }

  .ff-owner-text {
    display: flex;
    flex-direction: column;
    line-height: 16px;
  }

  .ff-owner-label {
    font-size: 11px;
    color: #909399;
  }

  .ff-owner-name {
    font-size: 13px;
    font-weight: 600;
    color: #303133;
  }

  .ff-auto-tag {
    margin-left: 5px;
    padding: 0 4px;
    font-size: 10px;
    font-style: normal;
    font-weight: 400;
    color: #909399;
    background: #f4f4f5;
    border: 1px solid #e4e4e7;
    border-radius: 3px;
  }

  &.is-empty .ff-owner-name {
    color: #c0c4cc;
    font-weight: 400;
  }
}

.ff-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: #909399;

  b {
    color: #303133;
    font-weight: 600;
  }
}

.ff-people {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.ff-people-label {
  color: #c0c4cc;
}

.ff-person {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 6px 0 2px;
  height: 20px;
  background: #f7f8fa;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  color: #606266;

  i {
    font-style: normal;
    color: #909399;
    font-size: 11px;
  }
}

.ff-person-avatar {
  width: 16px;
  height: 16px;
  line-height: 16px;
  border-radius: 50%;
  color: #fff;
  font-size: 10px;
  text-align: center;
}

// ---- 流水线 ----
.ff-group {
  padding-top: 8px;

  & + .ff-group {
    border-top: 1px dashed #f2f3f5;
    margin-top: 4px;
  }
}

.ff-head {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}

.ff-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 6px;
}

.ff-label {
  font-weight: 600;
}

.ff-badge {
  margin-left: 6px;
  padding: 0 5px;
  line-height: 16px;
  font-size: 11px;
  color: #409eff;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 3px;
}

.ff-count {
  margin-left: auto;
  color: #909399;
}

// 办理线右上角的图片工具：上传 / 查看
.ff-file-tools {
  margin-left: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ff-file-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 7px;
  height: 20px;
  font-size: 11px;
  color: #606266;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.15s;

  i {
    font-size: 12px;
  }

  &:hover {
    color: #409eff;
    border-color: #b3d8ff;
    background: #ecf5ff;
  }

  &.is-has {
    color: #409eff;
    border-color: #b3d8ff;
    background: #ecf5ff;
  }
}

.ff-track {
  display: flex;
  align-items: flex-start;
  overflow-x: auto;
  padding-bottom: 2px;
}

.ff-node {
  position: relative;
  flex: 1 1 0;
  min-width: 74px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 2px 4px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;

  &:hover {
    background: #f7faff;
  }
}

// 节点之间的连线：从左节点圆心连到右节点圆心
.ff-dot-line {
  position: absolute;
  top: 15px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: #ebeef5;
  z-index: 0;
}

.is-last .ff-dot-line {
  display: none;
}

.ff-node-dot {
  position: relative;
  z-index: 1;
  width: 10px;
  height: 10px;
  margin: 9px 0 5px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #d8dbe0;
  box-sizing: content-box;
}

.ff-node-name {
  font-size: 11px;
  color: #909399;
  line-height: 14px;
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ff-node-who {
  margin-top: 2px;
  font-size: 11px;
  line-height: 14px;
  color: #606266;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.is-empty {
    color: #d0d3d8;
  }
}

.ff-node-time {
  font-size: 10px;
  line-height: 13px;
  color: #c0c4cc;
}

// 已完成：绿点 + 绿线接到下一节点
.is-done {
  .ff-node-dot {
    background: #67c23a;
    border-color: #67c23a;
  }

  .ff-node-name {
    color: #529b2e;
  }

  .ff-node-who {
    color: #67c23a;
  }

  .ff-dot-line {
    background: #c2e7b0;
  }
}

// 进行中：本办理线主色实心 + 呼吸圈
.is-doing {
  .ff-node-dot {
    background: var(--ff-color);
    border-color: var(--ff-color);
    box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.16);
  }

  .ff-node-name {
    color: var(--ff-color);
    font-weight: 600;
  }

  .ff-node-who {
    color: var(--ff-color);
  }
}

// 受阻：红点提醒
.is-blocked {
  .ff-node-dot {
    background: #f56c6c;
    border-color: #f56c6c;
    box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.16);
  }

  .ff-node-name,
  .ff-node-who {
    color: #cf1322;
  }
}

// 当前节点整体提亮，一眼找到「卡在哪」
.ff-node.is-current {
  background: #f5faff;
}

.ff-empty {
  padding: 16px 0;
  text-align: center;
  color: #909399;
  font-size: 13px;
}

.ff-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 0 2px;
  border-top: 1px dashed #f2f3f5;
  font-size: 11px;
  color: #909399;
}

.ff-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.lg {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;

  &.is-done { background: #67c23a; }
  &.is-doing { background: #409eff; }
  &.is-blocked { background: #f56c6c; }
  &.is-todo { background: #fff; border: 2px solid #d8dbe0; box-sizing: content-box; }
}

.ff-legend-tip {
  margin-left: auto;
  color: #c0c4cc;
}
</style>
