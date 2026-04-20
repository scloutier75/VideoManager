<template>
  <div class="app-wrapper">
    <!-- Header -->
    <el-header class="app-header">
      <div class="header-left">
        <el-icon size="24" color="#409eff"><VideoPlay /></el-icon>
        <span class="app-title">VideoManager</span>
      </div>
      <div class="header-right">
        <el-statistic title="Videos" :value="stats.total" style="margin-right:24px" />
        <el-statistic
          v-if="stats.avg_score != null"
          title="Avg Score"
          :value="stats.avg_score"
          :precision="1"
          style="margin-right:24px"
        />
        <el-statistic
          v-if="stats.max_score != null"
          title="Top Score"
          :value="stats.max_score"
          :precision="1"
          style="margin-right:24px"
        />
        <el-button type="primary" :icon="Setting" @click="showScanPanel = true">
          Scanner
        </el-button>
      </div>
    </el-header>

    <!-- Main content -->
    <el-main class="app-main">
      <VideoTable
        :videos="videos"
        :total="total"
        :current-page="page"
        :page-size="limit"
        :loading="loading"
        @filter-change="onFilterChange"
        @sort-change="onSortChange"
        @page-change="onPageChange"
        @size-change="onSizeChange"
        @row-click="openDetail"
      />
    </el-main>

    <!-- Detail drawer -->
    <VideoDetailDrawer
      v-model="drawerOpen"
      :video="selectedVideo"
      @close="drawerOpen = false"
      @delete="onDelete"
    />

    <!-- Scan panel dialog -->
    <ScanPanel
      v-model="showScanPanel"
      @close="showScanPanel = false"
      @scan-complete="loadVideos"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, VideoPlay } from '@element-plus/icons-vue'
import VideoTable from './components/VideoTable.vue'
import VideoDetailDrawer from './components/VideoDetailDrawer.vue'
import ScanPanel from './components/ScanPanel.vue'
import { getVideos, getVideoStats, deleteVideo } from './api/index.js'

// ── State ──────────────────────────────────────────────────────────────────────

const videos = ref([])
const total = ref(0)
const page = ref(1)
const limit = ref(50)
const loading = ref(false)

const stats = reactive({ total: 0, avg_score: null, max_score: null })

const filters = reactive({})
const sortParams = reactive({ sort_by: 'score', sort_order: 'desc' })

const drawerOpen = ref(false)
const selectedVideo = ref(null)
const showScanPanel = ref(false)

// ── Data loading ───────────────────────────────────────────────────────────────

async function loadVideos() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      limit: limit.value,
      ...filters,
      ...sortParams,
    }
    const [videosRes, statsRes] = await Promise.all([
      getVideos(params),
      getVideoStats(),
    ])
    videos.value = videosRes.data.items
    total.value = videosRes.data.total
    Object.assign(stats, statsRes.data)
  } catch (err) {
    ElMessage.error('Failed to load videos')
  } finally {
    loading.value = false
  }
}

onMounted(loadVideos)

// ── Event handlers ─────────────────────────────────────────────────────────────

function onFilterChange(newFilters) {
  Object.keys(filters).forEach((k) => delete filters[k])
  Object.assign(filters, newFilters)
  page.value = 1
  loadVideos()
}

function onSortChange({ sort_by, sort_order }) {
  sortParams.sort_by = sort_by
  sortParams.sort_order = sort_order
  page.value = 1
  loadVideos()
}

function onPageChange(p) {
  page.value = p
  loadVideos()
}

function onSizeChange(s) {
  limit.value = s
  page.value = 1
  loadVideos()
}

function openDetail(row) {
  selectedVideo.value = row
  drawerOpen.value = true
}

async function onDelete(id) {
  try {
    await deleteVideo(id)
    drawerOpen.value = false
    selectedVideo.value = null
    ElMessage.success('Record removed')
    await loadVideos()
  } catch {
    ElMessage.error('Failed to remove record')
  }
}
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f5f7fa; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
</style>

<style scoped>
.app-wrapper { min-height: 100vh; display: flex; flex-direction: column; }

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
  height: 64px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left { display: flex; align-items: center; gap: 10px; }
.app-title { font-size: 20px; font-weight: 600; color: #303133; }

.header-right { display: flex; align-items: center; }

.app-main { padding: 24px; flex: 1; }
</style>
