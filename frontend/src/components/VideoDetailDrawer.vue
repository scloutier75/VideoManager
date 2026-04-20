<template>
  <el-drawer
    v-model="visible"
    :title="video?.filename ?? 'Video Details'"
    direction="rtl"
    size="480px"
    @close="emit('close')"
  >
    <template v-if="video">
      <!-- Score badge -->
      <div class="score-hero">
        <el-progress
          type="dashboard"
          :percentage="(video.score ?? 0) * 10"
          :color="progressColor(video.score)"
          :stroke-width="12"
          :width="120"
        >
          <template #default>
            <span class="score-value">{{ video.score ?? '–' }}</span>
            <span class="score-label">/ 10</span>
          </template>
        </el-progress>
      </div>

      <!-- Score breakdown -->
      <el-card v-if="video.score_breakdown" class="section-card" shadow="never">
        <template #header><b>Score Breakdown</b></template>
        <el-row v-for="(val, key) in video.score_breakdown" :key="key" class="breakdown-row">
          <el-col :span="14">{{ scoreLabel(key) }}</el-col>
          <el-col :span="10" class="breakdown-val">
            <el-progress
              :percentage="scorePercent(key, val)"
              :stroke-width="8"
              :show-text="false"
              :color="barColor(key)"
            />
            <span class="breakdown-num">{{ val }}</span>
          </el-col>
        </el-row>
      </el-card>

      <!-- File info -->
      <el-card class="section-card" shadow="never">
        <template #header><b>File</b></template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="Filename">{{ video.filename }}</el-descriptions-item>
          <el-descriptions-item label="Path">
            <span class="mono">{{ video.filepath }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="Size">{{ formatSize(video.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="Container">{{ video.container_format ?? '–' }}</el-descriptions-item>
          <el-descriptions-item label="Efficiency (score/GB)">
            <el-tooltip content="Quality score per GB — higher means better quality for the file size" placement="top">
              <span :style="efficiencyStyle(video.efficiency_score)">
                {{ video.efficiency_score != null ? video.efficiency_score.toFixed(2) : '–' }}
              </span>
            </el-tooltip>
          </el-descriptions-item>
          <el-descriptions-item label="BRISQUE Score">
            <el-tooltip content="Perceptual quality from frame analysis (0–10, higher is better). Requires ENABLE_BRISQUE=true." placement="top">
              <span :style="brisqueStyle(video.brisque_score)">
                {{ video.brisque_score != null ? video.brisque_score.toFixed(1) : '–' }}
              </span>
            </el-tooltip>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- Video stream info -->
      <el-card class="section-card" shadow="never">
        <template #header><b>Video Stream</b></template>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="Resolution">
            {{ video.width && video.height ? `${video.width}×${video.height}` : '–' }}
          </el-descriptions-item>
          <el-descriptions-item label="Codec">{{ video.video_codec ?? '–' }}</el-descriptions-item>
          <el-descriptions-item label="Bitrate">{{ formatBitrate(video.video_bitrate) }}</el-descriptions-item>
          <el-descriptions-item label="Frame Rate">
            {{ video.frame_rate ? `${video.frame_rate} fps` : '–' }}
          </el-descriptions-item>
          <el-descriptions-item label="Duration" :span="2">{{ formatDuration(video.duration) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- Audio stream info -->
      <el-card class="section-card" shadow="never">
        <template #header><b>Audio Stream</b></template>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="Codec">{{ video.audio_codec ?? '–' }}</el-descriptions-item>
          <el-descriptions-item label="Bitrate">{{ formatBitrate(video.audio_bitrate) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- Timestamps -->
      <el-card class="section-card" shadow="never">
        <template #header><b>Scan Info</b></template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="Last Scanned">{{ formatDate(video.scanned_at) }}</el-descriptions-item>
          <el-descriptions-item label="First Seen">{{ formatDate(video.created_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <div class="drawer-actions">
        <el-popconfirm
          title="Remove this record from the database?"
          confirm-button-text="Remove"
          confirm-button-type="danger"
          @confirm="emit('delete', video.id)"
        >
          <template #reference>
            <el-button type="danger" :icon="Delete" plain>Remove Record</el-button>
          </template>
        </el-popconfirm>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  video: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'close', 'delete'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const SCORE_MAX = { resolution_score: 4, bitrate_score: 3, codec_score: 2, audio_score: 1 }
const SCORE_LABELS = {
  resolution_score: 'Resolution',
  bitrate_score: 'Bitrate quality',
  codec_score: 'Codec efficiency',
  audio_score: 'Audio quality',
}
const BAR_COLORS = {
  resolution_score: '#409eff',
  bitrate_score: '#67c23a',
  codec_score: '#e6a23c',
  audio_score: '#909399',
}

function scoreLabel(key) { return SCORE_LABELS[key] ?? key }
function scorePercent(key, val) {
  const max = SCORE_MAX[key] ?? 4
  return Math.round((val / max) * 100)
}
function barColor(key) { return BAR_COLORS[key] ?? '#409eff' }

function progressColor(score) {
  if (score == null) return '#909399'
  if (score >= 8) return '#67c23a'
  if (score >= 6) return '#e6a23c'
  if (score >= 4) return '#409eff'
  return '#f56c6c'
}

function formatDuration(sec) {
  if (!sec) return '–'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatSize(bytes) {
  if (!bytes) return '–'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes; let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(1)} ${units[i]}`
}

function formatBitrate(bps) {
  if (!bps) return '–'
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`
  if (bps >= 1_000) return `${(bps / 1_000).toFixed(0)} Kbps`
  return `${bps} bps`
}

function formatDate(iso) {
  if (!iso) return '–'
  return new Date(iso).toLocaleString()
}

function efficiencyStyle(v) {
  if (v == null) return ''
  if (v >= 8)  return 'color:#67c23a;font-weight:600'
  if (v >= 5)  return 'color:#85ce61'
  if (v >= 3)  return 'color:#e6a23c'
  return 'color:#f56c6c'
}

function brisqueStyle(v) {
  if (v == null) return 'color:#c0c4cc'
  if (v >= 8)  return 'color:#67c23a;font-weight:600'
  if (v >= 6)  return 'color:#85ce61'
  if (v >= 4)  return 'color:#e6a23c'
  return 'color:#f56c6c'
}
</script>

<style scoped>
.score-hero { display: flex; justify-content: center; padding: 16px 0 8px; }
.score-value { font-size: 28px; font-weight: bold; display: block; text-align: center; }
.score-label { font-size: 12px; color: #888; display: block; text-align: center; }
.section-card { margin-bottom: 12px; }
.breakdown-row { margin-bottom: 8px; align-items: center; }
.breakdown-val { display: flex; align-items: center; gap: 8px; }
.breakdown-num { font-size: 12px; white-space: nowrap; min-width: 24px; }
.mono { font-family: monospace; font-size: 12px; word-break: break-all; }
.drawer-actions { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
