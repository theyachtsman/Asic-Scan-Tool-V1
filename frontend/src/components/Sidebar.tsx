/**
 * Sidebar Navigation
 */

import { LayoutDashboard, Cpu, Search, HardDrive, Settings, Wifi, WifiOff, Zap, CircuitBoard } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { formatHashrate } from '../utils/format';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'miners', label: 'Miners', icon: Cpu },
  { id: 'scan', label: 'Scan Network', icon: Search },
  { id: 'hashboards', label: 'Hashboards', icon: CircuitBoard },
  { id: 'firmware', label: 'Firmware', icon: HardDrive },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const { activeTab, setActiveTab, isConnected, summary } = useMinerStore();

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <Zap size={24} className="logo-icon" />
        <div className="logo-text">
          <span className="logo-title">ASIC Scan</span>
          <span className="logo-subtitle">Tool v1.0</span>
        </div>
      </div>

      {/* Connection Status */}
      <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
        {isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
        <span>{isConnected ? 'Backend Connected' : 'Connecting...'}</span>
      </div>

      {/* Quick Stats */}
      {summary && (
        <div className="sidebar-stats">
          <div className="stat-item">
            <span className="stat-value online">{summary.online}</span>
            <span className="stat-label">Online</span>
          </div>
          <div className="stat-item">
            <span className="stat-value offline">{summary.offline}</span>
            <span className="stat-label">Offline</span>
          </div>
          <div className="stat-item">
            <span className="stat-value hashrate">{formatHashrate(summary.total_hashrate_ths)}</span>
            <span className="stat-label">Total</span>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`nav-item ${activeTab === id ? 'active' : ''}`}
            onClick={() => setActiveTab(id)}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className="version-text">© 2025 ASIC Scan Tool</span>
      </div>
    </aside>
  );
}
