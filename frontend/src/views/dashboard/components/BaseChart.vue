<template>
  <div ref="chart" class="base-chart" :class="{ clickable: clickable }" :style="{ height: height }" />
</template>

<script>
import echarts from 'echarts'

export default {
  name: 'BaseChart',
  props: {
    option: {
      type: Object,
      default: () => ({})
    },
    height: {
      type: String,
      default: '300px'
    },
    // 开启后鼠标移到图形上变手型，并向外抛 chart-click 事件
    clickable: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      chart: null,
      observer: null
    }
  },
  watch: {
    option: {
      deep: true,
      handler(value) {
        if (this.chart) this.chart.setOption(value, true)
      }
    }
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    this.chart.setOption(this.option, true)
    // 图形点击向外抛，用于首页下钻到订单/成本明细
    this.chart.on('click', params => this.$emit('chart-click', params))
    window.addEventListener('resize', this.resize)
    if (window.ResizeObserver) {
      this.observer = new ResizeObserver(this.resize)
      this.observer.observe(this.$refs.chart)
    }
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resize)
    if (this.observer) {
      this.observer.disconnect()
      this.observer = null
    }
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
  },
  methods: {
    resize() {
      if (this.chart) this.chart.resize()
    }
  }
}
</script>

<style scoped>
.base-chart {
  width: 100%;
}

.base-chart.clickable {
  cursor: pointer;
}
</style>
