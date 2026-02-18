/**
 * TypeScript types matching the Python backend models
 */

export type MinerBrand = 'Bitmain' | 'Canaan' | 'Bitdeer' | 'MicroBT' | 'Unknown';
export type FirmwareType = 'Stock' | 'Braiins OS' | 'VNish' | 'LuxOS' | 'ePIC' | 'Unknown';
export type MinerStatus = 'online' | 'offline' | 'error' | 'scanning' | 'rebooting' | 'flashing';
export type DiscoveryMethod = 'ping' | 'arp' | 'dhcp' | 'mdns' | 'manual';

export interface PoolInfo {
  url: string;
  user: string;
  status: string;
  priority: number;
  accepted: number;
  rejected: number;
  stale: number;
  diff: string;
}

export interface HashboardInfo {
  index: number;
  hashrate_rt: number;
  hashrate_avg: number;
  temp_chip: number;
  temp_pcb: number;
  fan_speed: number;
  chips_total: number;
  chips_active: number;
  voltage: number;
  frequency: number;
  hw_errors: number;
  status: string;
}

export interface MinerStats {
  hashrate_rt: number;
  hashrate_avg: number;
  hashrate_ideal: number;
  power_consumption: number;
  power_limit: number;
  efficiency: number;
  temp_max: number;
  temp_min: number;
  temp_avg: number;
  temps: number[];
  fan_speeds: number[];
  fan_speed_avg: number;
  uptime_seconds: number;
  uptime_str: string;
  hw_error_rate: number;
  total_hw_errors: number;
  hashboards: HashboardInfo[];
  pools: PoolInfo[];
  active_pool: string;
  worker_name: string;
  mac_address: string;
  hostname: string;
  firmware_version: string;
  firmware_type: FirmwareType;
  raw_data: Record<string, unknown>;
  last_updated: string | null;
}

export interface MinerDevice {
  id: string;
  ip: string;
  mac: string;
  hostname: string;
  brand: MinerBrand;
  model: string;
  firmware_type: FirmwareType;
  firmware_version: string;
  status: MinerStatus;
  is_reachable: boolean;
  discovery_method: DiscoveryMethod;
  first_seen: string | null;
  last_seen: string | null;
  username: string;
  password: string;
  stats: MinerStats | null;
  tags: string[];
  location: string;
  notes: string;
}

export interface ScanProgress {
  scan_id: string;
  status: string;
  total_hosts: number;
  scanned_hosts: number;
  found_miners: number;
  current_ip: string;
  percent: number;
  elapsed_seconds: number;
  estimated_remaining: number;
  errors: string[];
}

export interface ScanConfig {
  ip_ranges: string[];
  methods: DiscoveryMethod[];
  ping_timeout: number;
  api_timeout: number;
  max_concurrent: number;
  collect_stats: boolean;
  username: string;
  password: string;
}

export interface FirmwarePackage {
  id: string;
  filename: string;
  brand: MinerBrand;
  model: string;
  version: string;
  firmware_type: FirmwareType;
  file_size: number;
  checksum_md5: string;
  checksum_sha256: string;
  upload_date: string | null;
  notes: string;
}

export interface FlashJob {
  job_id: string;
  firmware_id: string;
  target_ips: string[];
  status: string;
  progress: Record<string, string>;
  started_at: string | null;
  completed_at: string | null;
  errors: Record<string, string>;
}

export interface AppSettings {
  default_ip_range: string;
  scan_timeout: number;
  api_timeout: number;
  max_concurrent_scans: number;
  auto_refresh_interval: number;
  bitmain_user: string;
  bitmain_pass: string;
  canaan_user: string;
  canaan_pass: string;
  bitdeer_user: string;
  bitdeer_pass: string;
  theme: string;
  table_density: string;
  show_offline_miners: boolean;
  alert_temp_threshold: number;
  alert_hashrate_drop_pct: number;
  alert_offline_notify: boolean;
}

export interface SummaryStats {
  total: number;
  online: number;
  offline: number;
  total_hashrate_ths: number;
  total_power_watts: number;
  brands: Record<string, number>;
}

export interface WebSocketMessage {
  type: 'initial_state' | 'miners_update' | 'scan_progress' | 'scan_results' | 'flash_progress' | 'alert' | 'summary_update' | 'pong';
  data?: unknown;
  summary?: SummaryStats;
  scan_id?: string;
  count?: number;
  job_id?: string;
  alert_type?: string;
  message?: string;
  device_ip?: string;
}
