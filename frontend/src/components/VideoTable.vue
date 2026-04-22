<template>
  <div>
    <!-- Filter bar -->
    <el-row :gutter="12" class="filter-bar">
      <el-col :span="7">
        <el-input
          v-model="localSearch"
          placeholder="Search by filename or path…"
          :prefix-icon="Search"
          clearable
          @input="onSearchInput"
        />
      </el-col>
      <el-col :span="3">
        <el-input
          v-model="localCodec"
          placeholder="Codec"
          clearable
          @input="emitFilters"
        />
      </el-col>
      <el-col :span="6">
        <div class="range-label">Score: {{ scoreRange[0] }} – {{ scoreRange[1] }}</div>
        <el-slider
          v-model="scoreRange"
          range
          :min="0"
          :max="10"
          :step="0.5"
          @change="emitFilters"
        />
      </el-col>
      <el-col :span="6">
        <div class="range-label">
          Efficiency: {{ effRange[0] === 0 && effRange[1] === effMax ? 'all' : `${effRange[0]} – ${effRange[1]}` }}
        </div>
        <el-slider
          v-model="effRange"
          range
          :min="0"
          :max="effMax"
          :step="1"
          @change="emitFilters"
        />
      </el-col>
      <el-col :span="2" class="filter-actions">
        <el-button @click="resetFilters" :icon="Refresh" title="Reset filters" />
      </el-col>
    </el-row>

    <!-- Table -->
    <el-table
      :data="videos"
      v-loading="loading"
      stripe
      border
      highlight-current-row
      :row-class-name="({ row }) => row.is_missing ? 'row-missing' : ''"
      @row-click="(row) => emit('row-click', row)"
      @sort-change="onSortChange"
      style="width: 100%; cursor: pointer"
    >
      <el-table-column label="Score" prop="score" sortable="custom" width="100" align="center" resizable>
        <template #default="{ row }">
          <el-tag :type="scoreTagType(row.score)" size="large" effect="dark" round>
            {{ row.score ?? '–' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="Filename" prop="filename" sortable="custom" min-width="220" show-overflow-tooltip resizable />

      <el-table-column label="Resolution" width="130" align="center" resizable>
        <template #default="{ row }">
          <span v-if="row.width && row.height">
            {{ row.width }}×{{ row.height }}
            <el-tag size="small" effect="plain" style="margin-left:4px">{{ resLabel(row.height) }}</el-tag>
          </span>
          <span v-else>–</span>
        </template>
      </el-table-column>

      <el-table-column label="Codec" prop="video_codec" width="110" align="center" resizable>
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.video_codec ?? '–' }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="Bitrate" width="120" align="right" resizable>
        <template #default="{ row }">{{ formatBitrate(row.video_bitrate) }}</template>
      </el-table-column>

      <el-table-column label="Duration" width="95" align="right" resizable>
        <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
      </el-table-column>

      <el-table-column label="Size" prop="file_size" sortable="custom" width="95" align="right" resizable>
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>

      <el-table-column
        label="Efficiency"
        prop="efficiency_score"
        sortable="custom"
        width="115"
        align="right"
        resizable
      >
        <template #header>
          <el-tooltip content="Score per GB — higher means better quality relative to file size" placement="top">
            <span>Efficiency <el-icon style="vertical-align:middle"><InfoFilled /></el-icon></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.efficiency_score != null" :style="efficiencyColor(row.efficiency_score)">
            {{ row.efficiency_score.toFixed(1) }}
          </span>
          <span v-else>–</span>
        </template>
      </el-table-column>

      <el-table-column label="Path" prop="directory" sortable="custom" show-overflow-tooltip min-width="200" resizable />

      <el-table-column
        label="Last Processed"
        prop="scanned_at"
        sortable="custom"
        width="165"
        align="right"
        resizable
      >
        <template #default="{ row }">
          <span v-if="row.scanned_at" :title="row.scanned_at" style="color:#909399;font-size:12px">
            {{ formatDateTime(row.scanned_at) }}
          </span>
          <span v-else style="color:#c0c4cc">–</span>
        </template>
      </el-table-column>

      <el-table-column
        label="BRISQUE"
        prop="brisque_score"
        sortable="custom"
        width="105"
        align="right"
        resizable
      >
        <template #header>
          <el-tooltip content="Perceptual quality from frame analysis — higher is better (requires BRISQUE_ENABLED=true)" placement="top">
            <span>BRISQUE <el-icon style="vertical-align:middle"><InfoFilled /></el-icon></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.brisque_score != null" :style="brisqueColor(row.brisque_score)">
            {{ row.brisque_score.toFixed(1) }}
          </span>
          <span v-else style="color:#c0c4cc">–</span>
        </template>
      </el-table-column>

      <el-table-column label="" width="60" align="center">
        <template #default="{ row }">
          <el-button link :icon="View" @click.stop="emit('row-click', row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <el-pagination
      class="pagination"
      background
      layout="total, sizes, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="currentPage"
      :page-sizes="[25, 50, 100, 200]"
      @current-change="(p) => emit('page-change', p)"
      @size-change="(s) => emit('size-change', s)"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Search, Refresh, View, InfoFilled } from '@element-plus/icons-vue'

const props = defineProps({
  videos: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  currentPage: { type: Number, default: 1 },
  pageSize: { type: Number, default: 50 },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['filter-change', 'sort-change', 'page-change', 'size-change', 'row-click'])

const localSearch = ref('')
const localCodec = ref('')
const scoreRange = ref([0, 10])
const effMax = 15
const effRange = ref([0, effMax])

const filters = computed(() => ({
  search: localSearch.value || undefined,
  codec: localCodec.value || undefined,
  min_score: scoreRange.value[0] > 0 ? scoreRange.value[0] : undefined,
  max_score: scoreRange.value[1] < 10 ? scoreRange.value[1] : undefined,
  min_efficiency: effRange.value[0] > 0 ? effRange.value[0] : undefined,
  max_efficiency: effRange.value[1] < effMax ? effRange.value[1] : undefined,
}))

function emitFilters() {
  emit('filter-change', filters.value)
}

let searchTimer = null
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(emitFilters, 400)
}

function resetFilters() {
  localSearch.value = ''
  localCodec.value = ''
  scoreRange.value = [0, 10]
  effRange.value = [0, effMax]
  emit('filter-change', {})
}

function onSortChange({ prop, order }) {
  if (!prop) return
  emit('sort-change', {
    sort_by: prop,
    sort_order: order === 'ascending' ? 'asc' : 'desc',
  })
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function scoreTagType(score) {
  if (score == null) return 'info'
  if (score >= 8) return 'success'
  if (score >= 6) return 'warning'
  if (score >= 4) return ''
  return 'danger'
}

function efficiencyColor(v) {
  if (v >= 8)  return 'color:#67c23a;font-weight:600'  // very efficient
  if (v >= 5)  return 'color:#85ce61'                  // good
  if (v >= 3)  return 'color:#e6a23c'                  // slightly bloated
  return 'color:#f56c6c'                               // bloated
}

function brisqueColor(v) {
  if (v >= 8)  return 'color:#67c23a;font-weight:600'  // excellent perceptual quality
  if (v >= 6)  return 'color:#85ce61'                  // good
  if (v >= 4)  return 'color:#e6a23c'                  // fair
  return 'color:#f56c6c'                               // poor
}

function resLabel(height) {
  if (!height) return ''
  if (height >= 2160) return '4K'
  if (height >= 1440) return '2K'
  if (height >= 1080) return '1080p'
  if (height >= 720) return '720p'
  if (height >= 480) return '480p'
  return `${height}p`
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

function formatDateTime(iso) {
  if (!iso) return '–'
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style scoped>
.filter-bar { margin-bottom: 16px; align-items: flex-end; }
.range-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.filter-actions { display: flex; align-items: flex-end; padding-bottom: 2px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }

:deep(.row-missing) {
  color: #adb5bd !important;
  font-style: italic;
}
:deep(.row-missing td) {
  background-color: #f8f9fa !important;
  color: #adb5bd !important;
}
</style>
