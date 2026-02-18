/**
 * Zustand Global State Store
 */

import { create } from 'zustand';
import type {
  AppSettings,
  FirmwarePackage,
  FlashJob,
  MinerDevice,
  ScanProgress,
  SummaryStats,
} from '../types/miner';

interface Alert {
  id: string;
  type: 'info' | 'warning' | 'error' | 'success';
  message: string;
  timestamp: number;
}

interface MinerStore {
  // Miners
  miners: MinerDevice[];
  selectedIds: Set<string>;
  setMiners: (miners: MinerDevice[]) => void;
  updateMiner: (miner: MinerDevice) => void;
  removeMiner: (id: string) => void;
  toggleSelect: (id: string) => void;
  selectAll: () => void;
  clearSelection: () => void;
  setSelectedIds: (ids: Set<string>) => void;

  // Scan preview results (not yet committed to store)
  scanResults: MinerDevice[];
  scanResultsId: string | null;
  setScanResults: (scanId: string, devices: MinerDevice[]) => void;
  clearScanResults: () => void;

  // Summary
  summary: SummaryStats | null;
  setSummary: (summary: SummaryStats) => void;

  // Scan
  activeScanId: string | null;
  scanProgress: ScanProgress | null;
  isScanning: boolean;
  setActiveScan: (scanId: string | null) => void;
  setScanProgress: (progress: ScanProgress | null) => void;
  setIsScanning: (v: boolean) => void;

  // Firmware
  firmwarePackages: FirmwarePackage[];
  flashJobs: FlashJob[];
  setFirmwarePackages: (pkgs: FirmwarePackage[]) => void;
  addFlashJob: (job: FlashJob) => void;
  updateFlashJob: (jobId: string, progress: Record<string, string>) => void;

  // Settings
  settings: AppSettings | null;
  setSettings: (s: AppSettings) => void;

  // UI State
  activeTab: string;
  setActiveTab: (tab: string) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  filterBrand: string;
  setFilterBrand: (b: string) => void;
  filterStatus: string;
  setFilterStatus: (s: string) => void;

  // Alerts
  alerts: Alert[];
  addAlert: (type: Alert['type'], message: string) => void;
  removeAlert: (id: string) => void;

  // Backend connection
  isConnected: boolean;
  setIsConnected: (v: boolean) => void;
}

export const useMinerStore = create<MinerStore>((set, get) => ({
  // Miners
  miners: [],
  selectedIds: new Set(),
  setMiners: (miners) => set({ miners }),
  updateMiner: (miner) =>
    set((state) => ({
      miners: state.miners.map((m) => (m.id === miner.id ? miner : m)),
    })),
  removeMiner: (id) =>
    set((state) => ({
      miners: state.miners.filter((m) => m.id !== id),
    })),
  toggleSelect: (id) =>
    set((state) => {
      const next = new Set(state.selectedIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selectedIds: next };
    }),
  selectAll: () =>
    set((state) => ({ selectedIds: new Set(state.miners.map((m) => m.id)) })),
  clearSelection: () => set({ selectedIds: new Set() }),
  setSelectedIds: (ids) => set({ selectedIds: ids }),

  // Scan preview results
  scanResults: [],
  scanResultsId: null,
  setScanResults: (scanId, devices) => set({ scanResults: devices, scanResultsId: scanId }),
  clearScanResults: () => set({ scanResults: [], scanResultsId: null }),

  // Summary
  summary: null,
  setSummary: (summary) => set({ summary }),

  // Scan
  activeScanId: null,
  scanProgress: null,
  isScanning: false,
  setActiveScan: (scanId) => set({ activeScanId: scanId }),
  setScanProgress: (progress) => set({ scanProgress: progress }),
  setIsScanning: (v) => set({ isScanning: v }),

  // Firmware
  firmwarePackages: [],
  flashJobs: [],
  setFirmwarePackages: (pkgs) => set({ firmwarePackages: pkgs }),
  addFlashJob: (job) =>
    set((state) => ({ flashJobs: [...state.flashJobs, job] })),
  updateFlashJob: (jobId, progress) =>
    set((state) => ({
      flashJobs: state.flashJobs.map((j) =>
        j.job_id === jobId ? { ...j, progress } : j
      ),
    })),

  // Settings
  settings: null,
  setSettings: (s) => set({ settings: s }),

  // UI
  activeTab: 'dashboard',
  setActiveTab: (tab) => set({ activeTab: tab }),
  searchQuery: '',
  setSearchQuery: (q) => set({ searchQuery: q }),
  filterBrand: 'all',
  setFilterBrand: (b) => set({ filterBrand: b }),
  filterStatus: 'all',
  setFilterStatus: (s) => set({ filterStatus: s }),

  // Alerts
  alerts: [],
  addAlert: (type, message) =>
    set((state) => ({
      alerts: [
        ...state.alerts.slice(-9), // Keep last 10
        { id: Date.now().toString(), type, message, timestamp: Date.now() },
      ],
    })),
  removeAlert: (id) =>
    set((state) => ({ alerts: state.alerts.filter((a) => a.id !== id) })),

  // Connection
  isConnected: false,
  setIsConnected: (v) => set({ isConnected: v }),
}));
