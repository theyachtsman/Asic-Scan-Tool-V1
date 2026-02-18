/**
 * API Client - Axios-based HTTP client for the backend
 */

import axios from 'axios';
import type {
  AppSettings,
  FirmwarePackage,
  FlashJob,
  MinerDevice,
  ScanProgress,
  SummaryStats,
} from '../types/miner';

const BASE_URL = 'http://127.0.0.1:8765';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Discovery ────────────────────────────────────────────────────────────────

export const discoveryApi = {
  startScan: (config: {
    ip_ranges: string[];
    methods?: string[];
    ping_timeout?: number;
    api_timeout?: number;
    max_concurrent?: number;
    collect_stats?: boolean;
    username?: string;
    password?: string;
  }) => api.post<{ scan_id: string; status: string; message: string }>('/api/discovery/start', config),

  cancelScan: (scanId: string) =>
    api.post(`/api/discovery/cancel/${scanId}`),

  getProgress: (scanId: string) =>
    api.get<ScanProgress>(`/api/discovery/progress/${scanId}`),

  getLocalNetworks: () =>
    api.get<{ networks: string[]; suggested: string }>('/api/discovery/local-networks'),

  getResults: (scanId: string) =>
    api.get<{ scan_id: string; count: number; devices: import('../types/miner').MinerDevice[] }>(`/api/discovery/results/${scanId}`),

  commitResults: (scanId: string, deviceIds?: string[]) =>
    api.post(`/api/discovery/commit/${scanId}`, { device_ids: deviceIds ?? null }),

  discardResults: (scanId: string) =>
    api.delete(`/api/discovery/results/${scanId}`),
};

// ─── Miners ───────────────────────────────────────────────────────────────────

export const minersApi = {
  getAll: () => api.get<MinerDevice[]>('/api/miners/'),

  getSummary: () => api.get<SummaryStats>('/api/miners/summary'),

  getOne: (id: string) => api.get<MinerDevice>(`/api/miners/${id}`),

  update: (id: string, data: Partial<MinerDevice>) =>
    api.patch(`/api/miners/${id}`, data),

  delete: (id: string) => api.delete(`/api/miners/${id}`),

  refresh: (id: string) => api.post(`/api/miners/${id}/refresh`),

  reboot: (id: string) => api.post(`/api/miners/${id}/reboot`),

  shutdown: (id: string) => api.post(`/api/miners/${id}/shutdown`),

  bulkAction: (deviceIds: string[], action: 'reboot' | 'shutdown') =>
    api.post('/api/miners/bulk/action', { device_ids: deviceIds, action }),

  bulkDelete: (deviceIds: string[]) =>
    api.post('/api/miners/bulk/delete', { device_ids: deviceIds }),

  clearAll: () => api.delete('/api/miners/'),

  getRawApi: (id: string) => api.get(`/api/miners/${id}/raw-api`),

  getLogs: (id: string, lines = 20) =>
    api.get<{ device_id: string; ip: string; lines: string[]; count: number }>(
      `/api/miners/${id}/logs?lines=${lines}`
    ),
};

// ─── Firmware ─────────────────────────────────────────────────────────────────

export const firmwareApi = {
  list: () => api.get<FirmwarePackage[]>('/api/firmware/'),

  upload: (formData: FormData) =>
    api.post('/api/firmware/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }),

  delete: (id: string) => api.delete(`/api/firmware/${id}`),

  flash: (firmwareId: string, targetIps: string[], username?: string, password?: string) =>
    api.post('/api/firmware/flash', {
      firmware_id: firmwareId,
      target_ips: targetIps,
      username: username || '',
      password: password || '',
    }),

  getJob: (jobId: string) => api.get<FlashJob>(`/api/firmware/jobs/${jobId}`),

  listJobs: () => api.get<FlashJob[]>('/api/firmware/jobs/'),
};

// ─── Settings ─────────────────────────────────────────────────────────────────

export const settingsApi = {
  get: () => api.get<AppSettings>('/api/settings/'),

  update: (settings: AppSettings) => api.put<AppSettings>('/api/settings/', settings),

  reset: () => api.post('/api/settings/reset'),

  export: () => api.get('/api/settings/export'),
};

// ─── Health ───────────────────────────────────────────────────────────────────

export const healthApi = {
  check: () => api.get<{ status: string; version: string }>('/api/health'),
};

export default api;
