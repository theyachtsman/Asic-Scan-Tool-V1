/**
 * Scan Panel - Network discovery with saved IP ranges, preview/select, scan-replaces-table
 */

import { useState, useEffect, useMemo } from 'react';
import {
  Search, X, Wifi, AlertCircle, CheckCircle, Clock,
  Plus, PlusCircle, Trash2, Filter, Save, BookOpen, Trash
} from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { discoveryApi, minersApi } from '../api/client';

// ─── Saved IP Ranges (localStorage) ─────────────────────────────────────────
const LS_KEY = 'asic_saved_ranges';

interface SavedRange {
  id: string;
  name: string;
  range: string;
}

function loadSavedRanges(): SavedRange[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) ?? '[]'); } catch { return []; }
}
function saveSavedRanges(ranges: SavedRange[]) {
  localStorage.setItem(LS_KEY, JSON.stringify(ranges));
}

// ─── Progress Popup ───────────────────────────────────────────────────────────
function ProgressPopup({ current, total, label }: { current: number; total: number; label: string }) {
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
  return (
    <div className="progress-popup-overlay">
      <div className="progress-popup">
        <div className="progress-popup-header">
          <span>{label}</span>
          <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
        </div>
        <div className="progress-popup-bar-bg">
          <div className="progress-popup-bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="progress-popup-info">
          {current} / {total} &nbsp;·&nbsp; {pct}%
        </div>
      </div>
    </div>
  );
}

// ─── Badges ───────────────────────────────────────────────────────────────────
function BrandBadge({ brand }: { brand: string }) {
  const colors: Record<string, string> = {
    Bitmain: 'badge-orange', Canaan: 'badge-blue', Bitdeer: 'badge-purple',
    MicroBT: 'badge-green', Unknown: 'badge-gray',
  };
  return <span className={`badge ${colors[brand] ?? 'badge-gray'}`}>{brand}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    online: 'badge-green', offline: 'badge-gray', error: 'badge-red',
  };
  return <span className={`badge ${colors[status] ?? 'badge-gray'}`}>{status}</span>;
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function ScanPanel() {
  const {
    scanProgress, isScanning, setActiveScan, setIsScanning,
    addAlert, settings, scanResults, scanResultsId, clearScanResults, setMiners,
  } = useMinerStore();

  // Scan config
  const [ipRange, setIpRange] = useState('192.168.1.1-254');
  const [methods, setMethods] = useState(['ping', 'arp']);
  const [collectStats, setCollectStats] = useState(true);
  const [pingTimeout, setPingTimeout] = useState(1.0);
  const [apiTimeout, setApiTimeout] = useState(5.0);
  const [maxConcurrent, setMaxConcurrent] = useState(100);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // Saved ranges
  const [savedRanges, setSavedRanges] = useState<SavedRange[]>(loadSavedRanges);
  const [newRangeName, setNewRangeName] = useState('');
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [selectedSavedRangeIds, setSelectedSavedRangeIds] = useState<Set<string>>(new Set());

  // Preview selection
  const [selectedPreviewIds, setSelectedPreviewIds] = useState<Set<string>>(new Set());
  const [previewFilter, setPreviewFilter] = useState('all');

  // Progress popup state: current count + total + label
  const [progressPopup, setProgressPopup] = useState<{
    current: number; total: number; label: string;
  } | null>(null);

  useEffect(() => {
    if (settings) {
      setIpRange(settings.default_ip_range);
      setPingTimeout(settings.scan_timeout);
      setApiTimeout(settings.api_timeout);
      setMaxConcurrent(settings.max_concurrent_scans);
    }
    discoveryApi.getLocalNetworks().then(r => {
      if (r.data.suggested) setIpRange(r.data.suggested);
    }).catch(() => {});
  }, [settings]);

  // Auto-select all results when they arrive
  useEffect(() => {
    if (scanResults.length > 0) {
      setSelectedPreviewIds(new Set(scanResults.map(d => d.id)));
    }
  }, [scanResults]);

  const handleStartScan = async () => {
    if (!ipRange.trim()) { addAlert('error', 'Please enter an IP range'); return; }
    clearScanResults();
    setSelectedPreviewIds(new Set());
    try {
      const res = await discoveryApi.startScan({
        ip_ranges: ipRange.split('\n').map(s => s.trim()).filter(Boolean),
        methods,
        ping_timeout: pingTimeout,
        api_timeout: apiTimeout,
        max_concurrent: maxConcurrent,
        collect_stats: collectStats,
        username,
        password,
      });
      setActiveScan(res.data.scan_id);
      setIsScanning(true);
      addAlert('info', `Scan started: ${res.data.scan_id}`);
    } catch {
      addAlert('error', 'Failed to start scan. Is the backend running?');
    }
  };

  const handleCancelScan = async () => {
    if (scanProgress?.scan_id) {
      await discoveryApi.cancelScan(scanProgress.scan_id);
      setIsScanning(false);
      addAlert('info', 'Scan cancelled');
    }
  };

  const toggleMethod = (m: string) => {
    setMethods(prev => prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m]);
  };

  const togglePreviewSelect = (id: string) => {
    setSelectedPreviewIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredResults = useMemo(() => {
    if (previewFilter === 'all') return scanResults;
    return scanResults.filter(d => d.brand === previewFilter);
  }, [scanResults, previewFilter]);

  // ── Commit: clear old miners, add selected, show progress popup ──
  const handleAddSelected = async () => {
    if (!scanResultsId || selectedPreviewIds.size === 0) return;
    const ids = [...selectedPreviewIds];
    const total = ids.length;

    setProgressPopup({ current: 0, total, label: 'Clearing previous miners...' });
    try {
      await minersApi.clearAll();
      setProgressPopup({ current: Math.round(total * 0.1), total, label: `Committing ${total} miners...` });
      await discoveryApi.commitResults(scanResultsId, ids);
      setProgressPopup({ current: Math.round(total * 0.9), total, label: 'Loading miners list...' });
      const res = await minersApi.getAll();
      setProgressPopup({ current: total, total, label: 'Done!' });
      setMiners(res.data);
      addAlert('success', `Added ${ids.length} miner${ids.length !== 1 ? 's' : ''} to your list`);
      clearScanResults();
      setSelectedPreviewIds(new Set());
    } catch {
      addAlert('error', 'Failed to add miners');
    } finally {
      setTimeout(() => setProgressPopup(null), 400);
    }
  };

  const handleAddAll = async () => {
    if (!scanResultsId) return;
    const total = scanResults.length;
    setProgressPopup({ current: 0, total, label: 'Clearing previous miners...' });
    try {
      await minersApi.clearAll();
      setProgressPopup({ current: Math.round(total * 0.1), total, label: `Committing all ${total} miners...` });
      await discoveryApi.commitResults(scanResultsId);
      setProgressPopup({ current: Math.round(total * 0.9), total, label: 'Loading miners list...' });
      const res = await minersApi.getAll();
      setProgressPopup({ current: total, total, label: 'Done!' });
      setMiners(res.data);
      addAlert('success', `Added all ${total} miners to your list`);
      clearScanResults();
      setSelectedPreviewIds(new Set());
    } catch {
      addAlert('error', 'Failed to add miners');
    } finally {
      setTimeout(() => setProgressPopup(null), 400);
    }
  };

  const handleDiscard = async () => {
    if (scanResultsId) {
      await discoveryApi.discardResults(scanResultsId).catch(() => {});
    }
    clearScanResults();
    setSelectedPreviewIds(new Set());
    addAlert('info', 'Scan results discarded');
  };

  // ── Saved Ranges ──
  const handleSaveRange = () => {
    if (!newRangeName.trim() || !ipRange.trim()) return;
    const newRange: SavedRange = {
      id: Date.now().toString(),
      name: newRangeName.trim(),
      range: ipRange.trim(),
    };
    const updated = [...savedRanges, newRange];
    setSavedRanges(updated);
    saveSavedRanges(updated);
    setNewRangeName('');
    setShowSaveForm(false);
    addAlert('success', `Saved range "${newRange.name}"`);
  };

  const handleDeleteRange = (id: string) => {
    const updated = savedRanges.filter(r => r.id !== id);
    setSavedRanges(updated);
    saveSavedRanges(updated);
  };

  const handleLoadRange = (range: SavedRange) => {
    setIpRange(range.range);
    addAlert('info', `Loaded range: ${range.name}`);
  };

  const toggleSavedRangeSelect = (id: string) => {
    setSelectedSavedRangeIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleLoadSelectedRanges = () => {
    const selectedRanges = savedRanges.filter(r => selectedSavedRangeIds.has(r.id));
    if (selectedRanges.length === 0) return;
    const combined = selectedRanges.map(r => r.range).join('\n');
    setIpRange(combined);
    addAlert('info', `Loaded ${selectedRanges.length} range${selectedRanges.length !== 1 ? 's' : ''}`);
  };

  const pct = scanProgress?.percent ?? 0;
  const elapsed = scanProgress?.elapsed_seconds ?? 0;
  const remaining = scanProgress?.estimated_remaining ?? 0;
  const uniqueBrands = [...new Set(scanResults.map(d => d.brand))];

  return (
    <div className="scan-panel">
      {/* Progress Popup */}
      {progressPopup && (
        <ProgressPopup
          current={progressPopup.current}
          total={progressPopup.total}
          label={progressPopup.label}
        />
      )}

      <div className="page-header">
        <h1 className="page-title">Network Scan</h1>
      </div>

      <div className="scan-layout">
        {/* ── Config Panel ── */}
        <div className="card scan-config">
          <div className="card-header"><h2 className="card-title">Scan Configuration</h2></div>

          {/* Saved Ranges */}
          {savedRanges.length > 0 && (
            <div className="saved-ranges">
              <div className="saved-ranges-header">
                <BookOpen size={13} />
                <span>Saved Ranges ({savedRanges.length})</span>
                {selectedSavedRangeIds.size > 0 && (
                  <button className="btn btn-primary btn-sm" onClick={handleLoadSelectedRanges}>
                    Load Selected ({selectedSavedRangeIds.size})
                  </button>
                )}
              </div>
              <div className="saved-ranges-list saved-ranges-list--scroll">
                {[...savedRanges].sort((a, b) => a.name.localeCompare(b.name)).map(r => (
                  <div key={r.id} className={`saved-range-item ${selectedSavedRangeIds.has(r.id) ? 'selected' : ''}`}>
                    <input
                      type="checkbox"
                      checked={selectedSavedRangeIds.has(r.id)}
                      onChange={() => toggleSavedRangeSelect(r.id)}
                      title="Select to combine with others"
                    />
                    <button className="saved-range-load" onClick={() => handleLoadRange(r)}>
                      <span className="saved-range-name">{r.name}</span>
                      <span className="saved-range-val">{r.range.length > 30 ? r.range.slice(0, 30) + '…' : r.range}</span>
                    </button>
                    <button className="btn-icon btn-icon--danger" onClick={() => handleDeleteRange(r.id)} title="Delete">
                      <Trash size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="form-group">
            <div className="form-label-row">
              <label className="form-label">IP Range(s)</label>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowSaveForm(s => !s)}
                title="Save current range"
              >
                <Save size={12} /> Save
              </button>
            </div>
            {showSaveForm && (
              <div className="save-range-form">
                <input
                  type="text"
                  className="form-input"
                  placeholder="Range name (e.g. Farm A)"
                  value={newRangeName}
                  onChange={e => setNewRangeName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSaveRange()}
                />
                <button className="btn btn-primary btn-sm" onClick={handleSaveRange}>
                  <Save size={12} /> Save
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowSaveForm(false)}>
                  <X size={12} />
                </button>
              </div>
            )}
            <textarea
              className="form-textarea"
              value={ipRange}
              onChange={e => setIpRange(e.target.value)}
              placeholder={"192.168.1.1-254\n10.0.0.0/24\n172.16.0.100"}
              rows={4}
              disabled={isScanning}
            />
            <span className="form-hint">One range per line. Supports CIDR, dash ranges, single IPs.</span>
          </div>

          <div className="form-group">
            <label className="form-label">Discovery Methods</label>
            <div className="checkbox-group">
              {['ping', 'arp', 'dhcp'].map(m => (
                <label key={m} className="checkbox-label">
                  <input type="checkbox" checked={methods.includes(m)}
                    onChange={() => toggleMethod(m)} disabled={isScanning} />
                  {m.toUpperCase()}
                </label>
              ))}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Ping Timeout (s)</label>
              <input type="number" className="form-input" value={pingTimeout} min={0.1} max={5} step={0.1}
                onChange={e => setPingTimeout(parseFloat(e.target.value))} disabled={isScanning} />
            </div>
            <div className="form-group">
              <label className="form-label">API Timeout (s)</label>
              <input type="number" className="form-input" value={apiTimeout} min={1} max={30} step={1}
                onChange={e => setApiTimeout(parseFloat(e.target.value))} disabled={isScanning} />
            </div>
            <div className="form-group">
              <label className="form-label">Concurrency</label>
              <input type="number" className="form-input" value={maxConcurrent} min={10} max={500} step={10}
                onChange={e => setMaxConcurrent(parseInt(e.target.value))} disabled={isScanning} />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Username (optional)</label>
              <input type="text" className="form-input" value={username}
                onChange={e => setUsername(e.target.value)} placeholder="root / admin" disabled={isScanning} />
            </div>
            <div className="form-group">
              <label className="form-label">Password (optional)</label>
              <input type="password" className="form-input" value={password}
                onChange={e => setPassword(e.target.value)} placeholder="root / admin" disabled={isScanning} />
            </div>
          </div>

          <label className="checkbox-label">
            <input type="checkbox" checked={collectStats} onChange={e => setCollectStats(e.target.checked)} disabled={isScanning} />
            Collect full stats after discovery
          </label>

          <div className="scan-actions">
            {!isScanning ? (
              <button className="btn btn-primary btn-lg" onClick={handleStartScan}>
                <Search size={16} /> Start Scan
              </button>
            ) : (
              <button className="btn btn-danger btn-lg" onClick={handleCancelScan}>
                <X size={16} /> Cancel Scan
              </button>
            )}
          </div>
        </div>

        {/* ── Progress + Results Panel ── */}
        <div className="card scan-progress-panel">
          <div className="card-header">
            <h2 className="card-title">
              {scanResults.length > 0 ? `Scan Results (${scanResults.length} found)` : 'Scan Progress'}
            </h2>
          </div>

          {/* Empty state */}
          {!scanProgress && !isScanning && scanResults.length === 0 && (
            <div className="empty-state">
              <Wifi size={48} className="empty-icon" />
              <p>Configure and start a scan to discover miners on your network.</p>
              <p className="empty-hint">Results will appear here for review before being added to your miners list.</p>
            </div>
          )}

          {/* Progress bar (while scanning) */}
          {(isScanning || (scanProgress && scanProgress.status !== 'complete' && scanResults.length === 0)) && (
            <div className="progress-content">
              <div className="progress-status">
                {scanProgress?.status === 'error' ? (
                  <AlertCircle size={20} className="text-red" />
                ) : (
                  <div className="spinner" />
                )}
                <span className="status-text">
                  {scanProgress?.status === 'error' ? 'Scan Error' :
                   scanProgress?.status === 'cancelled' ? 'Cancelled' : 'Scanning...'}
                </span>
              </div>

              {/* Stage indicator */}
              <div className="scan-stages">
                <div className={`scan-stage ${pct <= 50 ? 'active' : 'complete'}`}>
                  <span className="stage-num">1</span>
                  <span className="stage-label">Network Sweep</span>
                </div>
                <div className="stage-connector" />
                <div className={`scan-stage ${pct > 50 ? 'active' : ''}`}>
                  <span className="stage-num">2</span>
                  <span className="stage-label">Populating Miner Data</span>
                </div>
              </div>

              <div className="progress-bar-container">
                <div className="progress-bar" style={{ width: `${pct}%` }} />
              </div>
              <div className="progress-pct">{pct.toFixed(1)}%</div>

              <div className="progress-stats">
                <div className="prog-stat">
                  <span className="prog-label">Scanned</span>
                  <span className="prog-value">{scanProgress?.scanned_hosts ?? 0} / {scanProgress?.total_hosts ?? 0}</span>
                </div>
                <div className="prog-stat">
                  <span className="prog-label">Found</span>
                  <span className="prog-value text-green">{scanProgress?.found_miners ?? 0}</span>
                </div>
                <div className="prog-stat">
                  <span className="prog-label">Current IP</span>
                  <span className="prog-value mono">{scanProgress?.current_ip || '—'}</span>
                </div>
                <div className="prog-stat">
                  <Clock size={12} />
                  <span className="prog-label">Elapsed</span>
                  <span className="prog-value">{elapsed.toFixed(0)}s</span>
                </div>
                {remaining > 0 && (
                  <div className="prog-stat">
                    <span className="prog-label">Remaining</span>
                    <span className="prog-value">~{remaining.toFixed(0)}s</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── PREVIEW RESULTS ── */}
          {scanResults.length > 0 && (
            <div className="scan-results-preview">
              <div className="preview-summary">
                <CheckCircle size={16} className="text-green" />
                <span>Found <strong>{scanResults.length}</strong> devices in {elapsed.toFixed(1)}s</span>
                <div className="preview-brands">
                  {uniqueBrands.map(b => <BrandBadge key={b} brand={b} />)}
                </div>
              </div>

              <div className="preview-note">
                <AlertCircle size={13} className="text-yellow" />
                <span>Adding miners will <strong>replace</strong> the current miners list with these results.</span>
              </div>

              <div className="preview-actions">
                <div className="preview-select-info">
                  <input
                    type="checkbox"
                    checked={selectedPreviewIds.size === filteredResults.length && filteredResults.length > 0}
                    onChange={e => {
                      if (e.target.checked) setSelectedPreviewIds(new Set(filteredResults.map(d => d.id)));
                      else setSelectedPreviewIds(new Set());
                    }}
                  />
                  <span>{selectedPreviewIds.size} of {filteredResults.length} selected</span>
                </div>

                <div className="preview-filter">
                  <Filter size={13} />
                  <select value={previewFilter} onChange={e => setPreviewFilter(e.target.value)} className="filter-select filter-select--sm">
                    <option value="all">All Brands</option>
                    {uniqueBrands.map(b => <option key={b} value={b}>{b}</option>)}
                  </select>
                </div>

                <div className="preview-btns">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleAddSelected}
                    disabled={selectedPreviewIds.size === 0}
                  >
                    <Plus size={14} /> Add Selected ({selectedPreviewIds.size})
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleAddAll}>
                    <PlusCircle size={14} /> Add All
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={handleDiscard}>
                    <Trash2 size={14} /> Discard
                  </button>
                </div>
              </div>

              <div className="preview-table-container">
                <table className="miners-table preview-table">
                  <thead>
                    <tr>
                      <th className="th-check"></th>
                      <th>IP Address</th>
                      <th>Brand</th>
                      <th>Model</th>
                      <th>Status</th>
                      <th>Hashrate</th>
                      <th>Power</th>
                      <th>Worker</th>
                      <th>Firmware</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredResults.map(device => (
                      <tr
                        key={device.id}
                        className={`miner-row ${selectedPreviewIds.has(device.id) ? 'selected' : ''}`}
                        onClick={() => togglePreviewSelect(device.id)}
                      >
                        <td onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedPreviewIds.has(device.id)}
                            onChange={() => togglePreviewSelect(device.id)}
                          />
                        </td>
                        <td className="mono">{device.ip}</td>
                        <td><BrandBadge brand={device.brand} /></td>
                        <td>{device.model || '—'}</td>
                        <td><StatusBadge status={device.status} /></td>
                        <td className="num-cell">
                          {device.stats ? `${device.stats.hashrate_rt.toFixed(2)} TH/s` : '—'}
                        </td>
                        <td className="num-cell">
                          {device.stats && device.stats.power_consumption > 0
                            ? `${device.stats.power_consumption.toFixed(0)}W`
                            : '—'}
                        </td>
                        <td className="worker-cell">{device.stats?.worker_name || '—'}</td>
                        <td>{device.firmware_type || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
