import { useMinerStore } from '../store/minerStore';

export default function StatusBar() {
  const { summary, isScanning, scanProgress, isConnected } = useMinerStore();
  return (
    <div className="status-bar">
      <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
        {isConnected ? '● Connected' : '○ Disconnected'}
      </span>
      {isScanning && scanProgress && (
        <span className="status-scanning">
          Scanning... {scanProgress.scanned_hosts}/{scanProgress.total_hosts} ({scanProgress.found_miners} found)
        </span>
      )}
      {summary && (
        <>
          <span className="status-sep">|</span>
          <span>{summary.total} miners</span>
          <span className="status-sep">|</span>
          <span className="text-green">{summary.online} online</span>
          <span className="status-sep">|</span>
          <span>{summary.total_hashrate_ths.toFixed(2)} TH/s</span>
          <span className="status-sep">|</span>
          <span>{(summary.total_power_watts / 1000).toFixed(2)} kW</span>
        </>
      )}
      <span className="status-right">ASIC Scan Tool v1.0</span>
    </div>
  );
}
