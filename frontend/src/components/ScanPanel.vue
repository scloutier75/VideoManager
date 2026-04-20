<template>
  <el-dialog v-model="visible" title="Scanner" width="700px" @close="emit('close')">
    <!-- Action bar -->
    <div class="scan-actions">
      <el-button
        type="primary"
        :icon="CaretRight"
        :loading="scanning"
        @click="triggerScan"
      >
        Scan Now
      </el-button>
      <el-tag v-if="scanStatus" :type="statusTagType(scanStatus.status)" style="margin-left:12px">
        {{ statusLabel(scanStatus) }}
      </el-tag>
    </div>

    <!-- Folder config -->
    <el-divider content-position="left">Watched Folders</el-divider>
    <el-table :data="configs" size="small" style="margin-bottom:12px">
      <el-table-column prop="folder_path" label="Path" show-overflow-tooltip />
      <el-table-column label="Recursive" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.recursive ? 'success' : 'info'">
            {{ row.recursive ? 'Yes' : 'No' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="" width="60" align="center">
        <template #default="{ row }">
          <el-popconfirm
            title="Remove this folder?"
            confirm-button-text="Remove"
            confirm-button-type="danger"
            @confirm="removeConfig(row.id)"
          >
            <template #reference>
              <el-button link :icon="Delete" type="danger" />
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-form :model="newConfig" inline @submit.prevent="addConfig">
      <el-form-item label="Add folder">
        <el-input
          v-model="newConfig.folder_path"
          placeholder="/path/to/videos"
          style="width:300px"
        />
      </el-form-item>
      <el-form-item label="Recursive">
        <el-switch v-model="newConfig.recursive" />
      </el-form-item>
      <el-form-item>
        <el-button type="success" :icon="Plus" native-type="submit">Add</el-button>
      </el-form-item>
    </el-form>

    <!-- Scan history -->
    <el-divider content-position="left">Recent Scans</el-divider>
    <el-table :data="history" size="small" max-height="240">
      <el-table-column prop="id" label="#" width="50" />
      <el-table-column label="Started" width="165">
        <template #default="{ row }">{{ formatDate(row.started_at) }}</template>
      </el-table-column>
      <el-table-column label="Status" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Found" prop="files_found" width="70" align="right" />
      <el-table-column label="New" prop="files_processed" width="65" align="right" />
      <el-table-column label="Skipped" prop="files_skipped" width="70" align="right" />
      <el-table-column label="Errors" prop="files_error" width="70" align="right" />
    </el-table>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { CaretRight, Delete, Plus } from '@element-plus/icons-vue'
import {
  startScan, getScanStatus, getScanHistory,
  getScanConfigs, addScanConfig, deleteScanConfig,
} from '../api/index.js'

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue', 'close', 'scan-complete'])

const visible = ref(props.modelValue)

const scanning = ref(false)
const scanStatus = ref(null)
const history = ref([])
const configs = ref([])
const newConfig = ref({ folder_path: '', recursive: true })

async function load() {
  const [histRes, cfgRes, statusRes] = await Promise.all([
    getScanHistory().catch(() => ({ data: [] })),
    getScanConfigs().catch(() => ({ data: [] })),
    getScanStatus().catch(() => ({ data: null })),
  ])
  history.value = histRes.data
  configs.value = cfgRes.data
  scanStatus.value = statusRes.data
}

onMounted(load)

async function triggerScan() {
  scanning.value = true
  try {
    await startScan()
    ElMessage.success('Scan started in the background')
    emit('scan-complete')
    setTimeout(load, 2000)
  } catch {
    ElMessage.error('Failed to start scan')
  } finally {
    scanning.value = false
  }
}

async function addConfig() {
  if (!newConfig.value.folder_path.trim()) return
  try {
    await addScanConfig(newConfig.value)
    newConfig.value = { folder_path: '', recursive: true }
    await load()
    ElMessage.success('Folder added')
  } catch {
    ElMessage.error('Failed to add folder')
  }
}

async function removeConfig(id) {
  try {
    await deleteScanConfig(id)
    await load()
  } catch {
    ElMessage.error('Failed to remove folder')
  }
}

function statusTagType(status) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

function statusLabel(job) {
  if (!job) return ''
  if (job.status === 'running') return 'Scanning…'
  if (job.status === 'completed') return `Done (${job.files_processed} new)`
  if (job.status === 'failed') return 'Failed'
  return job.status
}

function formatDate(iso) {
  if (!iso) return '–'
  return new Date(iso).toLocaleString()
}
</script>

<style scoped>
.scan-actions { display: flex; align-items: center; margin-bottom: 8px; }
</style>
