/**
 * Settings Panel
 */

import { useState, useEffect } from 'react';
import { Save, RotateCcw } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { settingsApi } from '../api/client';
import type { AppSettings } from '../types/miner';

export default function SettingsPanel() {
  const { settings, setSettings, addAlert } = useMinerStore();
  const [form, setForm] = useState<AppSettings | null>(settings);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setForm(settings); }, [settings]);

  if (!form) return <div className="loading">Loading settings...</div>;

  const update = (key: keyof AppSettings, value: unknown) =>
    setForm(prev => prev ? { ...prev, [key]: value } : prev);

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const res = await settingsApi.update(form);
      setSettings(res.data);
      addAlert('success', 'Settings saved');
    } catch { addAlert('error', 'Failed to save settings'); }
    finally { setSaving(false); }
  };

  const handleReset = async () => {
    if (!confirm('Reset all settings to defaults?')) return;
    const res = await settingsApi.reset();
    setSettings(res.data.settings);
    setForm(res.data.settings);
    addAlert('info', 'Settings reset to defaults');
  };

  const handleExport = async () => {
    const res = await settingsApi.export();
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'asicscan-export.json'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="settings-panel">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <div className="header-actions">
          <button className="btn btn-ghost btn-sm" onClick={handleExport}>Export Data</button>
          <button className="btn btn-secondary btn-sm" onClick={handleReset}><RotateCcw size={14} /> Reset</button>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            <Save size={14} /> {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      <div className="settings-grid">
        {/* Network */}
        <div className="card">
          <div className="card-header"><h2 className="card-title">Network & Discovery</h2></div>
          <div className="form-group">
            <label className="form-label">Default IP Range</label>
            <input type="text" className="form-input" value={form.default_ip_range}
              onChange={e => update('default_ip_range', e.target.value)} />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Scan Timeout (s)</label>
              <input type="number" className="form-input" value={form.scan_timeout} min={0.1} max={10} step={0.1}
                onChange={e => update('scan_timeout', parseFloat(e.target.value))} />
            </div>
            <div className="form-group">
              <label className="form-label">API Timeout (s)</label>
              <input type="number" className="form-input" value={form.api_timeout} min={1} max={60} step={1}
                onChange={e => update('api_timeout', parseFloat(e.target.value))} />
            </div>
            <div className="form-group">
              <label className="form-label">Max Concurrent</label>
              <input type="number" className="form-input" value={form.max_concurrent_scans} min={10} max={500} step={10}
                onChange={e => update('max_concurrent_scans', parseInt(e.target.value))} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Auto-Refresh Interval (s, 0=off)</label>
            <input type="number" className="form-input" value={form.auto_refresh_interval} min={0} max={300} step={5}
              onChange={e => update('auto_refresh_interval', parseInt(e.target.value))} />
          </div>
        </div>

        {/* Credentials */}
        <div className="card">
          <div className="card-header"><h2 className="card-title">Default Credentials</h2></div>
          {[
            { brand: 'Bitmain', userKey: 'bitmain_user', passKey: 'bitmain_pass' },
            { brand: 'Canaan', userKey: 'canaan_user', passKey: 'canaan_pass' },
            { brand: 'Bitdeer', userKey: 'bitdeer_user', passKey: 'bitdeer_pass' },
          ].map(({ brand, userKey, passKey }) => (
            <div key={brand} className="cred-row">
              <span className="cred-brand">{brand}</span>
              <input type="text" className="form-input" placeholder="Username"
                value={(form as Record<string, unknown>)[userKey] as string}
                onChange={e => update(userKey as keyof AppSettings, e.target.value)} />
              <input type="password" className="form-input" placeholder="Password"
                value={(form as Record<string, unknown>)[passKey] as string}
                onChange={e => update(passKey as keyof AppSettings, e.target.value)} />
            </div>
          ))}
        </div>

        {/* Alerts */}
        <div className="card">
          <div className="card-header"><h2 className="card-title">Alerts & Thresholds</h2></div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Temp Alert (°C)</label>
              <input type="number" className="form-input" value={form.alert_temp_threshold} min={50} max={100}
                onChange={e => update('alert_temp_threshold', parseFloat(e.target.value))} />
            </div>
            <div className="form-group">
              <label className="form-label">Hashrate Drop Alert (%)</label>
              <input type="number" className="form-input" value={form.alert_hashrate_drop_pct} min={1} max={100}
                onChange={e => update('alert_hashrate_drop_pct', parseFloat(e.target.value))} />
            </div>
          </div>
          <label className="checkbox-label">
            <input type="checkbox" checked={form.alert_offline_notify}
              onChange={e => update('alert_offline_notify', e.target.checked)} />
            Notify when miners go offline
          </label>
        </div>

        {/* UI */}
        <div className="card">
          <div className="card-header"><h2 className="card-title">Interface</h2></div>
          <div className="form-group">
            <label className="form-label">Theme</label>
            <select className="form-input" value={form.theme} onChange={e => update('theme', e.target.value)}>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </div>
          <label className="checkbox-label">
            <input type="checkbox" checked={form.show_offline_miners}
              onChange={e => update('show_offline_miners', e.target.checked)} />
            Show offline miners in table
          </label>
        </div>
      </div>
    </div>
  );
}
