/**
 * Hashboards Page - Full hashboard health dashboard for all miners
 */

import { useState, useMemo } from 'react';
import { Search, Thermometer, Cpu, Zap, AlertTriangle } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { formatHashrate, formatTemp } from '../utils/format';
import type { MinerDevice, MinerStats } from '../types/miner';

function BoardHealthBar({ pct }: { pct: number }) {
  const color = pct >= 90 ? '#22c55e' : pct >= 70 ? '#f59e0b' : '#ef4444';
  return (
    <div className="board-health-bar-bg">
      <div className="board-health-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

function BoardCard({ board, idx }: { board: MinerStats['hashboards'][0]; idx: number }) {
  const chipPct = board.chips_total > 0 ? (board.chips_active / board.chips_total) * 100 : 0;
  const isHot = board.temp_chip > 80;
  const isWarn = board.temp_chip > 70;
  return (
    <div className={`hb-board-card ${isHot ? 'hb-board-hot' : isWarn ? 'hb-board-warn' : 'hb-board-ok'}`}>
      <div className="hb-board-header">
        <span className="hb-board-label">Board {idx + 1}</span>
        {isHot && <AlertTriangle size={12} className="text-red" />}
      </div>
      <div className="hb-board-stats">
        <div className="hb-stat">
          <Cpu size={11} className="hb-stat-icon" />
          <span className="hb-stat-label">Hashrate</span>
          <span className="hb-stat-value">{formatHashrate(board.hashrate_rt)}</span>
        </div>
        <div className="hb-stat">
          <Thermometer size={11} className={`hb-stat-icon ${isHot ? 'text-red' : isWarn ? 'text-yellow' : ''}`} />
          <span className="hb-stat-label">Chip Temp</span>
          <span className={`hb-stat-value ${isHot ? 'text-red' : isWarn ? 'text-yellow' : ''}`}>
            {formatTemp(board.temp_chip)}
          </span>
        </div>
        <div className="hb-stat">
          <Thermometer size={11} className="hb-stat-icon" />
          <span className="hb-stat-label">PCB Temp</span>
          <span className="hb-stat-value">{formatTemp(board.temp_pcb)}</span>
        </div>
        <div className="hb-stat">
          <Zap size={11} className="hb-stat-icon" />
          <span className="hb-stat-label">HW Errors</span>
          <span className={`hb-stat-value ${board.hw_errors > 0 ? 'text-red' : ''}`}>{board.hw_errors}</span>
        </div>
      </div>
      <div className="hb-chips-row">
        <span className="hb-chips-label">Chips: {board.chips_active}/{board.chips_total}</span>
        <BoardHealthBar pct={chipPct} />
        <span className="hb-chips-pct">{chipPct.toFixed(0)}%</span>
      </div>
    </div>
  );
}

function MinerHashboardRow({ miner }: { miner: MinerDevice }) {
  const [expanded, setExpanded] = useState(false);
  const boards = miner.stats?.hashboards ?? [];
  const totalBoards = boards.length;
  const hotBoards = boards.filter(b => b.temp_chip > 80).length;
  const maxTemp = boards.reduce((m, b) => Math.max(m, b.temp_chip), 0);
  const totalHW = boards.reduce((s, b) => s + b.hw_errors, 0);

  return (
    <div className={`hb-miner-row ${expanded ? 'hb-miner-expanded' : ''}`}>
      <div className="hb-miner-header" onClick={() => setExpanded(e => !e)}>
        <div className="hb-miner-identity">
          <div className={`status-dot status-dot--${miner.status}`} />
          <button
            className="ip-link"
            onClick={e => { e.stopPropagation(); window.open(`http://${miner.ip}`, '_blank'); }}
          >
            {miner.ip}
          </button>
          <span className="hb-miner-model">{miner.model || miner.brand}</span>
        </div>
        <div className="hb-miner-summary">
          <span className="hb-summary-item">
            <Cpu size={12} /> {formatHashrate(miner.stats?.hashrate_rt ?? 0)}
          </span>
          <span className={`hb-summary-item ${maxTemp > 80 ? 'text-red' : maxTemp > 70 ? 'text-yellow' : ''}`}>
            <Thermometer size={12} /> {maxTemp > 0 ? formatTemp(maxTemp) : '—'}
          </span>
          <span className="hb-summary-item">
            <span className="hb-board-count">{totalBoards} boards</span>
            {hotBoards > 0 && <span className="hb-hot-badge">{hotBoards} hot</span>}
          </span>
          {totalHW > 0 && (
            <span className="hb-summary-item text-red">
              <AlertTriangle size={12} /> {totalHW} HW err
            </span>
          )}
          <span className="hb-expand-arrow">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div className="hb-boards-detail">
          {boards.length === 0 ? (
            <p className="hb-no-boards">No hashboard data available</p>
          ) : (
            <div className="hb-boards-grid">
              {boards.map((board, i) => (
                <BoardCard key={i} board={board} idx={i} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function HashboardsPage() {
  const { miners } = useMinerStore();
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [showOffline, setShowOffline] = useState(false);

  const filtered = useMemo(() => {
    let list = miners.filter(m => showOffline || m.status !== 'offline');
    if (filterStatus !== 'all') list = list.filter(m => m.status === filterStatus);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(m =>
        m.ip.includes(q) || m.model.toLowerCase().includes(q) ||
        (m.stats?.worker_name ?? '').toLowerCase().includes(q)
      );
    }
    // Sort: hot boards first, then by max temp desc
    return list.sort((a, b) => {
      const aMax = Math.max(...(a.stats?.hashboards ?? []).map(h => h.temp_chip), 0);
      const bMax = Math.max(...(b.stats?.hashboards ?? []).map(h => h.temp_chip), 0);
      return bMax - aMax;
    });
  }, [miners, search, filterStatus, showOffline]);

  const totalBoards = miners.reduce((s, m) => s + (m.stats?.hashboards?.length ?? 0), 0);
  const hotBoards = miners.reduce((s, m) =>
    s + (m.stats?.hashboards?.filter(b => b.temp_chip > 80).length ?? 0), 0);
  const totalHWErrors = miners.reduce((s, m) =>
    s + (m.stats?.hashboards?.reduce((ss, b) => ss + b.hw_errors, 0) ?? 0), 0);

  return (
    <div className="hashboards-page">
      <div className="page-header">
        <h1 className="page-title">Hashboard Health</h1>
        <div className="hb-summary-bar">
          <span className="hb-summary-pill hb-pill-blue">{totalBoards} Total Boards</span>
          {hotBoards > 0 && <span className="hb-summary-pill hb-pill-red">{hotBoards} Overheating</span>}
          {totalHWErrors > 0 && <span className="hb-summary-pill hb-pill-yellow">{totalHWErrors} HW Errors</span>}
        </div>
      </div>

      <div className="hb-filters">
        <div className="search-box">
          <Search size={14} className="search-icon" />
          <input
            type="text" placeholder="Search IP, model, worker..."
            value={search} onChange={e => setSearch(e.target.value)}
            className="search-input"
          />
        </div>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="filter-select">
          <option value="all">All Status</option>
          <option value="online">Online</option>
          <option value="error">Error</option>
        </select>
        <label className="checkbox-label">
          <input type="checkbox" checked={showOffline} onChange={e => setShowOffline(e.target.checked)} />
          Show Offline
        </label>
        <span className="hb-count">{filtered.length} miners</span>
      </div>

      <div className="hb-list">
        {filtered.length === 0 ? (
          <div className="empty-state">
            <Cpu size={48} className="empty-icon" />
            <p>No miners with hashboard data found.</p>
            <p className="empty-hint">Run a scan with "Collect full stats" enabled.</p>
          </div>
        ) : (
          filtered.map(miner => (
            <MinerHashboardRow key={miner.id} miner={miner} />
          ))
        )}
      </div>
    </div>
  );
}
