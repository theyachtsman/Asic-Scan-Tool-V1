/**
 * Miners Table - Full sortable/filterable miner list with bulk actions
 */

import { useState, useEffect, useMemo } from 'react';
import { RefreshCw, RotateCcw, PowerOff, Trash2, ExternalLink, ChevronUp, ChevronDown, Search, Filter, Trash, FileText, Download } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { minersApi } from '../api/client';
import type { MinerDevice } from '../types/miner';

type SortKey = keyof MinerDevice | 'hashrate' | 'temp' | 'power';
type SortDir = 'asc' | 'desc';

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    online: 'badge-green', offline: 'badge-gray', error: 'badge-red',
    rebooting: 'badge-yellow', flashing: 'badge-blue', scanning: 'badge-purple',
  };
  return <span className={`badge ${colors[status] ?? 'badge-gray'}`}>{status}</span>;
}

function BrandBadge({ brand }: { brand: string }) {
  const colors: Record<string, string> = {
    Bitmain: 'badge-orange', Canaan: 'badge-blue', Bitdeer: 'badge-purple',
    MicroBT: 'badge-green', Unknown: 'badge-gray',
  };
  return <span className={`badge ${colors[brand] ?? 'badge-gray'}`}>{brand}</span>;
}

export default function MinersTable() {
  const {
    miners, setMiners, selectedIds, toggleSelect, selectAll, clearSelection, addAlert,
    searchQuery, setSearchQuery, filterBrand, setFilterBrand, filterStatus, setFilterStatus,
  } = useMinerStore();

  const [sortKey, setSortKey] = useState<SortKey>('ip');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    minersApi.getAll().then(r => setMiners(r.data)).finally(() => setLoading(false));
  }, [setMiners]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('asc'); }
  };

  const filtered = useMemo(() => {
    let list = [...miners];
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter(m =>
        m.ip.includes(q) || m.model.toLowerCase().includes(q) ||
        m.hostname.toLowerCase().includes(q) || m.mac.toLowerCase().includes(q) ||
        (m.stats?.worker_name ?? '').toLowerCase().includes(q)
      );
    }
    if (filterBrand !== 'all') list = list.filter(m => m.brand === filterBrand);
    if (filterStatus !== 'all') list = list.filter(m => m.status === filterStatus);

    list.sort((a, b) => {
      let av: number | string = 0, bv: number | string = 0;
      if (sortKey === 'hashrate') { av = a.stats?.hashrate_rt ?? 0; bv = b.stats?.hashrate_rt ?? 0; }
      else if (sortKey === 'temp') { av = a.stats?.temp_max ?? 0; bv = b.stats?.temp_max ?? 0; }
      else if (sortKey === 'power') { av = a.stats?.power_consumption ?? 0; bv = b.stats?.power_consumption ?? 0; }
      else { av = (a as unknown as Record<string, unknown>)[sortKey] as string ?? ''; bv = (b as unknown as Record<string, unknown>)[sortKey] as string ?? ''; }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [miners, searchQuery, filterBrand, filterStatus, sortKey, sortDir]);

  const openWebUI = (ip: string) => {
    window.open(`http://${ip}`, '_blank');
  };

  const handleReboot = async (id: string) => {
    try {
      await minersApi.reboot(id);
      addAlert('success', `Reboot command sent`);
    } catch { addAlert('error', 'Reboot failed'); }
  };

  const handleShutdown = async (id: string) => {
    if (!confirm('Shutdown this miner?')) return;
    try {
      await minersApi.shutdown(id);
      addAlert('success', 'Shutdown command sent');
    } catch { addAlert('error', 'Shutdown failed'); }
  };

  const handleRefresh = async (id: string) => {
    try {
      await minersApi.refresh(id);
      const res = await minersApi.getAll();
      setMiners(res.data);
      addAlert('success', 'Miner refreshed');
    } catch { addAlert('error', 'Refresh failed'); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Remove this miner from the list?')) return;
    await minersApi.delete(id);
    setMiners(miners.filter(m => m.id !== id));
  };

  const handleBulkReboot = async () => {
    if (!confirm(`Reboot ${selectedIds.size} miners?`)) return;
    await minersApi.bulkAction([...selectedIds], 'reboot');
    addAlert('success', `Reboot sent to ${selectedIds.size} miners`);
    clearSelection();
  };

  const handleBulkShutdown = async () => {
    if (!confirm(`Shutdown ${selectedIds.size} miners?`)) return;
    await minersApi.bulkAction([...selectedIds], 'shutdown');
    addAlert('success', `Shutdown sent to ${selectedIds.size} miners`);
    clearSelection();
  };

  const handleBulkRefresh = async () => {
    setLoading(true);
    let success = 0;
    let failed = 0;
    for (const id of [...selectedIds]) {
      try {
        await minersApi.refresh(id);
        success++;
      } catch {
        failed++;
      }
    }
    const res = await minersApi.getAll();
    setMiners(res.data);
    setLoading(false);
    addAlert('success', `Refreshed ${success} miners${failed > 0 ? `, ${failed} failed` : ''}`);
    clearSelection();
  };

  const handleRefreshAll = async () => {
    setLoading(true);
    try {
      const res = await minersApi.getAll();
      setMiners(res.data);
      addAlert('success', `Refreshed ${res.data.length} miners`);
    } catch {
      addAlert('error', 'Failed to refresh miners');
    } finally {
      setLoading(false);
    }
  };

  const handleBulkRemove = async () => {
    const count = selectedIds.size;
    if (!confirm(`Remove ${count} miner${count !== 1 ? 's' : ''} from the list?`)) return;
    try {
      await minersApi.bulkDelete([...selectedIds]);
      setMiners(miners.filter(m => !selectedIds.has(m.id)));
      clearSelection();
      addAlert('success', `Removed ${count} miner${count !== 1 ? 's' : ''}`);
    } catch {
      addAlert('error', 'Bulk remove failed');
    }
  };

  const handleClearAll = async () => {
    if (!confirm(`Remove ALL ${miners.length} miners from the list? This cannot be undone.`)) return;
    try {
      await minersApi.clearAll();
      setMiners([]);
      clearSelection();
      addAlert('success', 'All miners cleared');
    } catch {
      addAlert('error', 'Clear all failed');
    }
  };

  const handleExportCSV = () => {
    const headers = ['IP', 'Brand', 'Model', 'Status', 'Hashrate (TH/s)', 'Temp (C)', 'Power (W)', 'Worker', 'Firmware', 'MAC', 'Hostname'];
    const rows = filtered.map(m => [
      m.ip,
      m.brand,
      m.model || '',
      m.status,
      m.stats?.hashrate_rt?.toFixed(2) || '',
      m.stats?.temp_max?.toFixed(0) || '',
      m.stats?.power_consumption?.toFixed(0) || '',
      m.stats?.worker_name || '',
      m.firmware_type || '',
      m.mac || '',
      m.hostname || '',
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `miners_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    addAlert('success', `Exported ${filtered.length} miners to CSV`);
  };

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />) : null;

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th className="th-sortable" onClick={() => handleSort(k)}>
      {label} <SortIcon k={k} />
    </th>
  );

  return (
    <div className="miners-table-page">
      <div className="page-header">
        <h1 className="page-title">Miners ({filtered.length})</h1>
        <div className="header-actions">
          {selectedIds.size > 0 && (
            <>
              <span className="selected-count">{selectedIds.size} selected</span>
              <button className="btn btn-primary btn-sm" onClick={handleBulkRefresh} disabled={loading}>
                <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh Selected
              </button>
              <button className="btn btn-warning btn-sm" onClick={handleBulkReboot}>
                <RotateCcw size={14} /> Reboot Selected
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleBulkShutdown}>
                <PowerOff size={14} /> Shutdown Selected
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleBulkRemove}>
                <Trash2 size={14} /> Remove Selected
              </button>
              <button className="btn btn-ghost btn-sm" onClick={clearSelection}>Deselect</button>
            </>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handleRefreshAll} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh All
          </button>
          {miners.length > 0 && (
            <>
              <button className="btn btn-secondary btn-sm" onClick={handleExportCSV}>
                <Download size={14} /> Export CSV
              </button>
              <button className="btn btn-ghost btn-sm" title="Remove all miners" onClick={handleClearAll}>
                <Trash size={14} /> Clear All
              </button>
            </>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <div className="search-box">
          <Search size={14} className="search-icon" />
          <input
            type="text" placeholder="Search IP, model, worker..."
            value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>
        <div className="filter-group">
          <Filter size={14} />
          <select value={filterBrand} onChange={e => setFilterBrand(e.target.value)} className="filter-select">
            <option value="all">All Brands</option>
            <option value="Bitmain">Bitmain</option>
            <option value="Canaan">Canaan</option>
            <option value="Bitdeer">Bitdeer</option>
            <option value="MicroBT">MicroBT (Whatsminer)</option>
            <option value="Unknown">Unknown</option>
          </select>
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="filter-select">
            <option value="all">All Status</option>
            <option value="online">Online</option>
            <option value="offline">Offline</option>
            <option value="error">Error</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="table-container">
        <table className="miners-table">
          <thead>
            <tr>
              <th className="th-check">
                <input type="checkbox"
                  checked={selectedIds.size === filtered.length && filtered.length > 0}
                  onChange={e => e.target.checked ? selectAll() : clearSelection()}
                />
              </th>
              <Th label="IP Address" k="ip" />
              <Th label="Model" k="model" />
              <Th label="Brand" k="brand" />
              <Th label="Status" k="status" />
              <Th label="Hashrate" k="hashrate" />
              <Th label="Temp" k="temp" />
              <Th label="Power" k="power" />
              <th>Worker</th>
              <th>Firmware</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(miner => (
              <>
                <tr key={miner.id}
                  className={`miner-row ${selectedIds.has(miner.id) ? 'selected' : ''} ${expandedId === miner.id ? 'expanded' : ''}`}
                  onClick={() => setExpandedId(expandedId === miner.id ? null : miner.id)}
                >
                  <td onClick={e => e.stopPropagation()}>
                    <input type="checkbox" checked={selectedIds.has(miner.id)}
                      onChange={() => toggleSelect(miner.id)} />
                  </td>
                  <td>
                    <button className="ip-link" onClick={e => { e.stopPropagation(); openWebUI(miner.ip); }}>
                      {miner.ip} <ExternalLink size={11} />
                    </button>
                  </td>
                  <td>{miner.model || '—'}</td>
                  <td><BrandBadge brand={miner.brand} /></td>
                  <td><StatusBadge status={miner.status} /></td>
                  <td className="num-cell">
                    {miner.stats ? `${miner.stats.hashrate_rt.toFixed(2)} TH/s` : '—'}
                  </td>
                  <td className={`num-cell ${(miner.stats?.temp_max ?? 0) > 80 ? 'text-red' : ''}`}>
                    {miner.stats ? `${miner.stats.temp_max.toFixed(0)}°C` : '—'}
                  </td>
                  <td className="num-cell">
                    {miner.stats ? `${miner.stats.power_consumption.toFixed(0)}W` : '—'}
                  </td>
                  <td className="worker-cell">{miner.stats?.worker_name || '—'}</td>
                  <td>{miner.firmware_type || '—'}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <div className="action-buttons">
                      <button className="btn-icon" title="Refresh" onClick={() => handleRefresh(miner.id)}>
                        <RefreshCw size={13} />
                      </button>
                      <button className="btn-icon" title="Reboot" onClick={() => handleReboot(miner.id)}>
                        <RotateCcw size={13} />
                      </button>
                      <button className="btn-icon btn-icon--danger" title="Shutdown" onClick={() => handleShutdown(miner.id)}>
                        <PowerOff size={13} />
                      </button>
                      <button className="btn-icon btn-icon--danger" title="Remove" onClick={() => handleDelete(miner.id)}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedId === miner.id && (
                  <tr key={`${miner.id}-detail`} className="detail-row">
                    <td colSpan={11}>
                      <MinerDetail miner={miner} />
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="table-empty">
            <p>No miners match your filters.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function LogViewer({ minerId, ip }: { minerId: string; ip: string }) {
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const res = await minersApi.getLogs(minerId, 20);
      setLogs(res.data.lines);
      setFetched(true);
    } catch {
      setLogs([`Failed to fetch logs from ${ip}`]);
      setFetched(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="log-viewer">
      <div className="log-viewer-header">
        <span className="log-viewer-title"><FileText size={13} /> Miner Logs — {ip}</span>
        <div className="log-viewer-actions">
          <button className="btn btn-secondary btn-sm" onClick={fetchLogs} disabled={loading}>
            {loading ? <><div className="spinner" style={{width:12,height:12,borderWidth:2}} /> Fetching...</> : <><RefreshCw size={12} /> {fetched ? 'Refresh' : 'Pull Logs'}</>}
          </button>
        </div>
      </div>
      {fetched && (
        <div className="log-output">
          {logs.length === 0
            ? <span className="log-empty">No log lines returned.</span>
            : logs.map((line, i) => <div key={i} className="log-line">{line}</div>)
          }
        </div>
      )}
      {!fetched && (
        <div className="log-placeholder">Click "Pull Logs" to fetch the last 20 lines from this miner.</div>
      )}
    </div>
  );
}

function MinerDetail({ miner }: { miner: MinerDevice }) {
  const s = miner.stats;
  return (
    <div className="miner-detail">
      <div className="detail-section">
        <h4>Identity</h4>
        <div className="detail-grid">
          <div><label>IP</label><span>{miner.ip}</span></div>
          <div><label>MAC</label><span>{miner.mac || '—'}</span></div>
          <div><label>Hostname</label><span>{miner.hostname || '—'}</span></div>
          <div><label>Model</label><span>{miner.model || '—'}</span></div>
          <div><label>Firmware</label><span>{miner.firmware_version || '—'}</span></div>
          <div><label>FW Type</label><span>{miner.firmware_type}</span></div>
        </div>
      </div>
      {s && (
        <>
          <div className="detail-section">
            <h4>Performance</h4>
            <div className="detail-grid">
              <div><label>RT Hashrate</label><span>{s.hashrate_rt.toFixed(2)} TH/s</span></div>
              <div><label>Avg Hashrate</label><span>{s.hashrate_avg.toFixed(2)} TH/s</span></div>
              <div><label>Power</label><span>{s.power_consumption.toFixed(0)} W</span></div>
              <div><label>Efficiency</label><span>{s.efficiency > 0 ? `${s.efficiency.toFixed(1)} J/TH` : '—'}</span></div>
              <div><label>Uptime</label><span>{s.uptime_str || '—'}</span></div>
              <div><label>HW Errors</label><span>{s.total_hw_errors}</span></div>
            </div>
          </div>
          <div className="detail-section">
            <h4>Thermal</h4>
            <div className="detail-grid">
              <div><label>Max Temp</label><span className={s.temp_max > 80 ? 'text-red' : ''}>{s.temp_max.toFixed(1)}°C</span></div>
              <div><label>Avg Temp</label><span>{s.temp_avg.toFixed(1)}°C</span></div>
              <div><label>Fan Avg</label><span>{s.fan_speed_avg} RPM</span></div>
              <div><label>Fans</label><span>{s.fan_speeds.join(', ') || '—'}</span></div>
            </div>
          </div>
          {s.pools.length > 0 && (
            <div className="detail-section">
              <h4>Pools</h4>
              {s.pools.map((pool, i) => (
                <div key={i} className="pool-row">
                  <span className="pool-priority">#{pool.priority}</span>
                  <span className="pool-url">{pool.url}</span>
                  <span className="pool-user">{pool.user}</span>
                  <span className={`badge ${pool.status === 'Alive' ? 'badge-green' : 'badge-gray'}`}>{pool.status}</span>
                  <span className="pool-stats">{pool.accepted}A / {pool.rejected}R</span>
                </div>
              ))}
            </div>
          )}
          {s.hashboards.length > 0 && (
            <div className="detail-section">
              <h4>Hashboards</h4>
              <div className="boards-detail">
                {s.hashboards.map((board, i) => (
                  <div key={i} className="board-detail-card">
                    <div className="board-index">Board {board.index + 1}</div>
                    <div><label>Hashrate</label><span>{board.hashrate_rt.toFixed(2)} TH/s</span></div>
                    <div><label>Chip Temp</label><span className={board.temp_chip > 80 ? 'text-red' : ''}>{board.temp_chip}°C</span></div>
                    <div><label>PCB Temp</label><span>{board.temp_pcb}°C</span></div>
                    <div><label>Chips</label><span>{board.chips_active}/{board.chips_total}</span></div>
                    <div><label>HW Errors</label><span>{board.hw_errors}</span></div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
      {/* Logs section - always shown */}
      <div className="detail-section detail-section--full">
        <LogViewer minerId={miner.id} ip={miner.ip} />
      </div>
    </div>
  );
}
