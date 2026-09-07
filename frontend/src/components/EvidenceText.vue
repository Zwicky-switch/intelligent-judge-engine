<template>
  <div class="ev-wrap">
    <p class="ev-text">
      <template v-for="(seg, i) in segments" :key="i">
        <mark v-if="seg.point_id && seg.verdict" :class="['ev', seg.verdict, { active: seg.point_id === activePoint }]">
          {{ seg.text }}
        </mark>
        <span v-else>{{ seg.text }}</span>
      </template>
    </p>
    <div v-if="markers.length" class="ev-legend">
      <span class="legend-item"><span class="dot satisfied"></span>满足</span>
      <span class="legend-item"><span class="dot partial"></span>部分满足</span>
      <span class="legend-item"><span class="dot unsatisfied"></span>不满足</span>
      <span class="legend-item"><span class="dot unknown"></span>无法判断</span>
      <span class="muted small2">命中证据已在作答原文中高亮</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  markers: { type: Array, default: () => [] }, // [{start,end,verdict,point_id}]
  activePoint: { type: String, default: '' },
})

const validMarkers = computed(() =>
  (props.markers || []).filter((m) => m && typeof m.start === 'number' && typeof m.end === 'number'
    && m.start >= 0 && m.end > m.start && m.end <= props.text.length),
)

const segments = computed(() => {
  const text = props.text || ''
  const marks = validMarkers.value
  if (!marks.length) return [{ text, point_id: null, verdict: null }]
  // 每个字符归属到“文本位置靠前”的命中(首次覆盖生效)
  const owner = new Array(text.length).fill(-1)
  marks.forEach((m, idx) => {
    for (let i = m.start; i < m.end; i += 1) {
      if (owner[i] === -1) owner[i] = idx
    }
  })
  const out = []
  let cur = { text: '', point_id: null, verdict: null }
  const flush = () => { if (cur.text) out.push({ ...cur }) }
  for (let i = 0; i < text.length; i += 1) {
    const mk = owner[i] >= 0 ? marks[owner[i]] : null
    const sig = mk ? mk.point_id + ':' + mk.verdict : ''
    if (cur.text && sig !== cur.sig) { flush(); cur = { text: '', point_id: null, verdict: null } }
    cur.sig = sig
    cur.text += text[i]
    if (mk) { cur.point_id = mk.point_id; cur.verdict = mk.verdict }
  }
  flush()
  return out
})
</script>

<style scoped>
.ev-wrap { }
.ev-text { line-height: 2; font-size: 14px; white-space: pre-wrap; word-break: break-word; margin: 0; }
.ev-text .ev { padding: 1px 2px; border-radius: 3px; margin: 0 1px; border-bottom: 2px solid transparent; }
mark.ev { color: inherit; }
.ev.satisfied { background: #d9f7be; border-bottom-color: #52c41a; }
.ev.partial { background: #ffe58f; border-bottom-color: #fa8c16; }
.ev.unsatisfied { background: #ffd8d6; border-bottom-color: #ff4d4f; }
.ev.unknown { background: #d6e9ff; border-bottom-color: #1677ff; }
.ev.active { box-shadow: 0 0 0 2px rgba(24, 144, 255, .5); }
.ev-legend { margin-top: 10px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: #606266; }
.dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.dot.satisfied { background: #52c41a; }
.dot.partial { background: #fa8c16; }
.dot.unsatisfied { background: #ff4d4f; }
.dot.unknown { background: #1677ff; }
.small2 { font-size: 12px; }
</style>
