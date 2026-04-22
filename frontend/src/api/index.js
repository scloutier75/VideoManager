import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
})

export const getVideos = (params) => api.get('/api/videos', { params })
export const getVideoStats = () => api.get('/api/videos/stats')
export const deleteVideo = (id) => api.delete(`/api/videos/${id}`)
export const deleteMissingVideos = () => api.delete('/api/videos/missing/all')

export const startScan = () => api.post('/api/scan/start')
export const getScanStatus = () => api.get('/api/scan/status')
export const getScanHistory = () => api.get('/api/scan/history')

export const getScanConfigs = () => api.get('/api/scan/configs')
export const addScanConfig = (data) => api.post('/api/scan/configs', data)
export const deleteScanConfig = (id) => api.delete(`/api/scan/configs/${id}`)
