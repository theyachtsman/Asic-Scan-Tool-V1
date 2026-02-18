/**
 * Dashboard - Overview with stats cards, all miners list, and hashboard status
 */

import { useEffect, useState } from 'react';
import { Cpu, Zap, Thermometer, Activity, RefreshCw, TrendingUp, ExternalLink } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { minersApi } from '../api/client';
import { formatHashrate, formatPower } from '../utils/format';

function StatCard({ title, value, unit, icon: Icon, color, sub }: {
  title: string; value: string | number; unit?: string;
  icon: React.ElementType; color: string; sub?: string;
}) {
  return (
    <div className={`stat-card stat-card--${color}`}>
      <div className="stat-card-header">
        <span className="stat-card-title">{title}</span>
        <Icon size={20} className="stat-card-icon" />
      </div>
      <div className="stat-card-value">
        {value}<span className="stat-card-unit">{unit}</span>
      </div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { miners, summary, setSummary, setMiners, setActiveTab, addAlert } = useMinerStore();
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const [minersRes, summaryRes] = await Promise.all([
        minersApi.getAll(),
        minersApi.getSummary()
      ]);
      setMiners(minersRes.data);
      setSummary(summaryRes.data);
      addAlert('success', `Refreshed ${minersRes.data.length} miners`);
    } catch (e) {
      console.error('Refresh failed', e);
      addAlert('error', 'Failed to refresh dashboard');
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    minersApi.getAll().then(r => setMiners(r.data)).catch(() => {});
    minersApi.getSummary().then(r => setSummary(r.data)).catch(() => {});
  }, [setMiners, setSummary]);

  const online = miners.filter(m => m.status === 'online');
  const totalHashrateThs = summary?.total_hashrate_ths ?? 0;
  const totalPower = summary?.total_power_watts ?? 0;
  const avgTemp = online.length > 0
    ? online.reduce((s, m) => s + (m.stats?.temp_avg ?? 0), 0) / online.length
    : 0;

  const brandCounts = summary?.brands ?? {};

  const openWebUI = (ip: string, e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(`http://${ip}`, '_blank');
  };

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <button className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw size={14} className={refreshing ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <StatCard title="Total Miners" value={summary?.total ?? 0} icon={Cpu} color="blue"
          sub={`${summary?.online ?? 0} online · ${summary?.offline ?? 0} offline`} />
        <StatCard
          title="Total Hashrate"
          value={formatHashrate(totalHashrateThs)}
          icon={TrendingUp} color="green" sub="Real-time"
        />
        <StatCard title="Power Draw" value={formatPower(totalPower)}
          icon={Zap} color="yellow"
          sub={totalHashrateThs > 0 ? `${(totalPower / totalHashrateThs).toFixed(0)} J/TH` : ''} />
        <StatCard title="Avg Temperature" value={avgTemp.toFixed(1)} unit="°C"
          icon={Thermometer} color={avgTemp > 80 ? 'red' : 'teal'} sub="Across all boards" />
      </div>

      {/* Brand Breakdown + All Miners */}
      <div className="dashboard-row">
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">Miners by Brand</h2>
          </div>
          <div className="brand-grid">
            {Object.entries(brandCounts).map(([brand, count]) => (
              <div key={brand} className="brand-item">
                <div className={`brand-badge brand-badge--${brand.toLowerCase()}`}>{brand}</div>
                <span className="brand-count">{count as number}</span>
              </div>
            ))}
            {Object.keys(brandCounts).length === 0 && (
              <p className="empty-text">No miners discovered yet. Run a scan to find miners.</p>
            )}
          </div>
        </div>

        {/* All Miners list */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">All Miners ({miners.length})</h2>
            <button className="btn btn-link btn-sm" onClick={() => setActiveTab('miners')}>
              Full Table →
            </button>
          </div>
          <div className="recent-miners">
            {miners.map(miner => (
              <div key={miner.id} className="recent-miner-row">
                <div className={`status-dot status-dot--${miner.status}`} />
                <button className="ip-link" onClick={e => openWebUI(miner.ip, e)}>
                  {miner.ip} <ExternalLink size={10} />
                </button>
                <span className="miner-model">{miner.model || miner.brand}</span>
                <span className="miner-hashrate">
                  {miner.stats ? formatHashrate(miner.stats.hashrate_rt) : '—'}
                </span>
              </div>
            ))}
            {miners.length === 0 && (
              <div className="empty-state">
                <Activity size={32} className="empty-icon" />
                <p>No miners found yet.</p>
                <button className="btn btn-primary btn-sm" onClick={() => setActiveTab('scan')}>
                  Start Scanning
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Hashboard Status - first 10 online miners, full board info */}
      {online.length > 0 && (
        <div className="card">
          <div className="card-header">
            <button className="card-title-link" onClick={() => setActiveTab('hashboards')}>
              Hashboard Status ({online.length} miners) →
            </button>
            <button className="btn btn-link btn-sm" onClick={() => setActiveTab('hashboards')}>
              View All →
            </button>
          </div>
          <div className="hashboard-grid">
            {online.slice(0, 10).map(miner => {
              const boards = miner.stats?.hashboards ?? [];
              return (
                <div key={miner.id} className="hashboard-card">
                  <div className="hashboard-ip-row">
                    <button className="ip-link" onClick={e => openWebUI(miner.ip, e)}>
                      {miner.ip} <ExternalLink size={10} />
                    </button>
                  </div>
                  <div className="hashboard-model">{miner.model || miner.brand}</div>
                  <div className="hashboard-stats">
                    <span className="hs-hashrate">{formatHashrate(miner.stats?.hashrate_rt ?? 0)}</span>
                    <span className="hs-temp">{miner.stats?.temp_max.toFixed(0) ?? '0'}°C</span>
                    <span className="hs-power">{formatPower(miner.stats?.power_consumption ?? 0)}</span>
                  </div>
                  {/* Board chips with temp displayed */}
                  <div className="boards-row">
                    {boards.map((board, i) => (
                      <div
                        key={i}
                        className={`board-chip-ext ${board.temp_chip > 80 ? 'hot' : board.temp_chip > 70 ? 'warm' : 'ok'}`}
                      >
                        <span className="bce-num">{i + 1}</span>
                        <span className="bce-temp">{board.temp_chip > 0 ? `${board.temp_chip}°` : '—'}</span>
                        <span className="bce-hs">{board.hashrate_rt.toFixed(1)}</span>
                      </div>
                    ))}
                    {boards.length === 0 && (
                      <span className="no-boards-text">No board data</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
