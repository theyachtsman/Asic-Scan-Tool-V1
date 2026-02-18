/**
 * Firmware Manager - Upload and deploy firmware
 */

import { useState, useEffect, useRef } from 'react';
import { Upload, Trash2, Zap, CheckCircle, XCircle, Clock } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';
import { firmwareApi } from '../api/client';
import type { FirmwarePackage } from '../types/miner';

export default function FirmwareManager() {
  const { miners, firmwarePackages, setFirmwarePackages, flashJobs, addFlashJob, addAlert } = useMinerStore();
  const [uploading, setUploading] = useState(false);
  const [selectedFirmware, setSelectedFirmware] = useState<string>('');
  const [selectedMiners, setSelectedMiners] = useState<Set<string>>(new Set());
  const [brand, setBrand] = useState('Bitmain');
  const [model, setModel] = useState('');
  const [version, setVersion] = useState('');
  const [notes, setNotes] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firmwareApi.list().then(r => setFirmwarePackages(r.data)).catch(() => {});
  }, [setFirmwarePackages]);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { addAlert('error', 'Please select a firmware file'); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('brand', brand);
      fd.append('model', model);
      fd.append('version', version);
      fd.append('notes', notes);
      await firmwareApi.upload(fd);
      const res = await firmwareApi.list();
      setFirmwarePackages(res.data);
      addAlert('success', `Firmware uploaded: ${file.name}`);
      if (fileRef.current) fileRef.current.value = '';
    } catch { addAlert('error', 'Upload failed'); }
    finally { setUploading(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this firmware?')) return;
    await firmwareApi.delete(id);
    setFirmwarePackages(firmwarePackages.filter(f => f.id !== id));
    addAlert('info', 'Firmware deleted');
  };

  const handleFlash = async () => {
    if (!selectedFirmware) { addAlert('error', 'Select a firmware package'); return; }
    if (selectedMiners.size === 0) { addAlert('error', 'Select at least one miner'); return; }
    if (!confirm(`Flash firmware to ${selectedMiners.size} miner(s)? This will interrupt mining.`)) return;
    try {
      const res = await firmwareApi.flash(selectedFirmware, [...selectedMiners]);
      addFlashJob({ job_id: res.data.job_id, firmware_id: selectedFirmware, target_ips: [...selectedMiners], status: 'running', progress: {}, started_at: new Date().toISOString(), completed_at: null, errors: {} });
      addAlert('info', `Flash job started: ${res.data.job_id}`);
    } catch { addAlert('error', 'Flash failed to start'); }
  };

  const toggleMiner = (ip: string) => {
    setSelectedMiners(prev => { const n = new Set(prev); n.has(ip) ? n.delete(ip) : n.add(ip); return n; });
  };

  const onlineMiners = miners.filter(m => m.status === 'online');

  return (
    <div className="firmware-manager">
      <div className="page-header"><h1 className="page-title">Firmware Manager</h1></div>

      <div className="firmware-layout">
        {/* Upload Section */}
        <div className="card">
          <div className="card-header"><h2 className="card-title">Upload Firmware</h2></div>
          <div className="form-group">
            <label className="form-label">Firmware File</label>
            <input ref={fileRef} type="file" className="form-input" accept=".bin,.tar.gz,.img,.swu" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Brand</label>
              <select className="form-input" value={brand} onChange={e => setBrand(e.target.value)}>
                <option>Bitmain</option><option>Canaan</option><option>Bitdeer</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Model</label>
              <input type="text" className="form-input" value={model} onChange={e => setModel(e.target.value)} placeholder="S19 Pro" />
            </div>
            <div className="form-group">
              <label className="form-label">Version</label>
              <input type="text" className="form-input" value={version} onChange={e => setVersion(e.target.value)} placeholder="1.0.0" />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Notes</label>
            <input type="text" className="form-input" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional notes" />
          </div>
          <button className="btn btn-primary" onClick={handleUpload} disabled={uploading}>
            <Upload size={14} /> {uploading ? 'Uploading...' : 'Upload Firmware'}
          </button>
        </div>

        {/* Firmware Library */}
        <div className="card">
          <div className="card-header"><h2 className="card-title">Firmware Library ({firmwarePackages.length})</h2></div>
          {firmwarePackages.length === 0 ? (
            <div className="empty-state"><p>No firmware uploaded yet.</p></div>
          ) : (
            <div className="firmware-list">
              {firmwarePackages.map(pkg => (
                <div key={pkg.id} className={`firmware-item ${selectedFirmware === pkg.id ? 'selected' : ''}`}
                  onClick={() => setSelectedFirmware(pkg.id)}>
                  <div className="fw-info">
                    <span className="fw-name">{pkg.filename}</span>
                    <span className="fw-meta">{pkg.brand} · {pkg.model || 'All'} · {pkg.version || 'Unknown'}</span>
                    <span className="fw-size">{(pkg.file_size / 1024 / 1024).toFixed(1)} MB</span>
                  </div>
                  <button className="btn-icon btn-icon--danger" onClick={e => { e.stopPropagation(); handleDelete(pkg.id); }}>
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Target Miners */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">Target Miners</h2>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelectedMiners(new Set(onlineMiners.map(m => m.ip)))}>
              Select All Online
            </button>
          </div>
          <div className="miner-select-list">
            {onlineMiners.map(m => (
              <label key={m.id} className="miner-select-item">
                <input type="checkbox" checked={selectedMiners.has(m.ip)} onChange={() => toggleMiner(m.ip)} />
                <span className="miner-select-ip">{m.ip}</span>
                <span className="miner-select-model">{m.model || m.brand}</span>
              </label>
            ))}
            {onlineMiners.length === 0 && <p className="empty-text">No online miners available.</p>}
          </div>
          <div className="flash-actions">
            <button className="btn btn-danger btn-lg" onClick={handleFlash}
              disabled={!selectedFirmware || selectedMiners.size === 0}>
              <Zap size={16} /> Flash {selectedMiners.size} Miner(s)
            </button>
          </div>
        </div>

        {/* Flash Jobs */}
        {flashJobs.length > 0 && (
          <div className="card">
            <div className="card-header"><h2 className="card-title">Flash Jobs</h2></div>
            {flashJobs.map(job => (
              <div key={job.job_id} className="flash-job">
                <div className="job-header">
                  <span className="job-id">Job: {job.job_id}</span>
                  <span className={`badge ${job.status === 'complete' ? 'badge-green' : 'badge-yellow'}`}>{job.status}</span>
                </div>
                <div className="job-progress">
                  {Object.entries(job.progress).map(([ip, status]) => (
                    <div key={ip} className="job-target">
                      {status === 'complete' ? <CheckCircle size={12} className="text-green" /> :
                       status === 'error' || status === 'failed' ? <XCircle size={12} className="text-red" /> :
                       <Clock size={12} className="text-yellow" />}
                      <span className="job-ip">{ip}</span>
                      <span className="job-status">{status}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
