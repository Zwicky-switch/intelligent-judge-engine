<template>
  <div v-if="kind" class="card">
    <div class="block-title">{{ title }}</div>
    <img v-if="kind === 'image'" :src="url" class="ev-media" alt="作答原图" />
    <audio v-else-if="kind === 'audio'" :src="url" controls class="ev-audio" />
    <video v-else-if="kind === 'video'" :src="url" controls class="ev-video" />
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import axios from 'axios'

// 媒体证据回放: 调 GET /answers/{id}/media 取 blob, 按类型渲染原图/录音/视频。
// 纯文本作答(无媒体文件)或无权查看时静默隐藏, 不弹错误。
const props = defineProps({
  answerId: { type: [Number, String], default: null },
  type: { type: String, default: '' },   // item.type: subjective_text / spoken / practical_video
})

const KIND_BY_TYPE = { subjective_text: 'image', spoken: 'audio', practical_video: 'video' }
const TITLES = { image: '作答原图(OCR 识别依据)', audio: '口语录音回放', video: '实操视频证据' }

const kind = ref('')
const title = ref('')
const url = ref('')
let objectUrl = null

function revoke() {
  if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null }
}

async function load() {
  revoke()
  kind.value = ''
  const id = props.answerId
  if (!id || !KIND_BY_TYPE[props.type]) return
  const token = localStorage.getItem('insight_token')
  try {
    const res = await axios.get(`/v1/answers/${id}/media`, {
      responseType: 'blob',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const mime = (res.data?.type || '').toLowerCase()
    const k = mime.startsWith('image/') ? 'image'
      : mime.startsWith('audio/') ? 'audio'
        : mime.startsWith('video/') ? 'video' : ''
    if (k) {
      objectUrl = URL.createObjectURL(res.data)
      kind.value = k
      title.value = TITLES[k]
    }
  } catch (e) { /* 无媒体/无权/404: 静默隐藏 */ }
}

watch(() => [props.answerId, props.type], load, { immediate: true })
onBeforeUnmount(revoke)
</script>

<style scoped>
.ev-media { max-width: 100%; max-height: 420px; border: 1px solid #ebeef5; border-radius: 6px; }
.ev-audio { width: 100%; }
.ev-video { max-width: 100%; max-height: 420px; background: #000; border-radius: 6px; }
</style>
