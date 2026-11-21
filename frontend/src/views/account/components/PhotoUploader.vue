<template>
  <!-- 通用照片上传：订单身份证照片 / 执照照片共用；value 是 [{url, name, size}] 数组 -->
  <div class="photo-uploader" :class="{ 'is-mini': size === 'mini' }">
    <div
      v-for="(photo, index) in list"
      :key="photo.url + '-' + index"
      class="photo-thumb"
      title="点击预览"
      @click="previewIndex = index"
    >
      <img :src="photo.url" :alt="photo.name || '照片'">
      <i class="el-icon-close photo-remove" title="删除" @click.stop="removeAt(index)" />
    </div>
    <div v-if="uploading" class="photo-thumb is-uploading">
      <i class="el-icon-loading" />
    </div>
    <div v-else class="photo-add" title="上传照片" @click="pickFiles">
      <i class="el-icon-plus" />
    </div>
    <input
      ref="picker"
      type="file"
      accept="image/*"
      multiple
      class="photo-input"
      @change="handleChange"
    >
    <el-dialog
      :visible.sync="previewVisible"
      append-to-body
      custom-class="photo-preview-dialog"
      width="760px"
      title="照片预览"
    >
      <img v-if="previewUrl" :src="previewUrl" class="photo-preview-img" :alt="previewName">
    </el-dialog>
  </div>
</template>

<script>
import { uploadFile } from '@/api/progress'

export default {
  name: 'PhotoUploader',
  props: {
    // v-model：[{url, name, size}]
    value: { type: Array, default: () => [] },
    // mini：执照卡片头部那种小尺寸
    size: { type: String, default: 'default' }
  },
  data() {
    return {
      uploading: false,
      previewIndex: -1
    }
  },
  computed: {
    list() {
      return Array.isArray(this.value) ? this.value : []
    },
    previewVisible: {
      get() {
        return this.previewIndex >= 0 && !!this.list[this.previewIndex]
      },
      set(visible) {
        if (!visible) this.previewIndex = -1
      }
    },
    previewPhoto() {
      return this.list[this.previewIndex] || null
    },
    previewUrl() {
      return this.previewPhoto ? this.previewPhoto.url : ''
    },
    previewName() {
      return this.previewPhoto ? (this.previewPhoto.name || '照片') : '照片'
    }
  },
  methods: {
    pickFiles() {
      this.$refs.picker.click()
    },
    async handleChange(event) {
      const picked = Array.from(event.target.files || [])
      event.target.value = ''
      if (!picked.length) return
      this.uploading = true
      const added = []
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
          added.push({ url: data.url, name: file.name, size: file.size })
        }
        if (added.length) {
          this.$emit('input', [...this.list, ...added])
          this.$message.success(`已上传 ${added.length} 张照片`)
        }
      } catch (error) {
        // 请求层已弹出错误提示
      } finally {
        this.uploading = false
      }
    },
    removeAt(index) {
      const next = this.list.slice()
      next.splice(index, 1)
      this.$emit('input', next)
    }
  }
}
</script>

<style lang="scss" scoped>
.photo-uploader {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;

  .photo-thumb,
  .photo-add {
    position: relative;
    width: 72px;
    height: 72px;
    border-radius: 6px;
    overflow: hidden;
    cursor: pointer;
  }

  .photo-thumb {
    border: 1px solid #dcdfe6;
    background: #f5f7fa;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .photo-remove {
      position: absolute;
      top: 0;
      right: 0;
      display: none;
      width: 18px;
      height: 18px;
      line-height: 18px;
      text-align: center;
      background: rgba(0, 0, 0, 0.55);
      color: #fff;
      font-size: 12px;
      border-radius: 0 0 0 6px;
    }

    &:hover .photo-remove {
      display: block;
    }

    &.is-uploading {
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      color: #909399;
    }
  }

  .photo-add {
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px dashed #c0c4cc;
    color: #8c939d;
    background: #fafbfc;
    font-size: 22px;
    transition: all 0.2s;

    &:hover {
      border-color: #409eff;
      color: #409eff;
    }
  }

  .photo-input {
    display: none;
  }

  // 执照卡片头部用的小尺寸
  &.is-mini {
    gap: 6px;

    .photo-thumb,
    .photo-add {
      width: 34px;
      height: 34px;
      border-radius: 4px;
    }

    .photo-add {
      font-size: 15px;
    }

    .photo-thumb .photo-remove {
      width: 14px;
      height: 14px;
      line-height: 14px;
      font-size: 10px;
    }
  }
}
</style>

<style lang="scss">
// 预览弹窗是 append-to-body 的，样式不能 scoped
.photo-preview-dialog .photo-preview-img {
  display: block;
  max-width: 100%;
  max-height: 64vh;
  margin: 0 auto;
}
</style>
