<template>
  <div ref="chart" class="base-chart" :style="{ height: height }" />
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
</style>
