import { useEffect, useState } from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useMinerStore } from '../store/minerStore';

export default function AlertBanner() {
  const { alerts, removeAlert } = useMinerStore();
  // Track which alerts are fading out
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (alerts.length === 0) return;
    const timers = alerts.map(a => {
      // Start fade at 4.5s, remove at 5s
      const fadeTimer = setTimeout(() => {
        setFadingIds(prev => new Set([...prev, a.id]));
      }, 4500);
      const removeTimer = setTimeout(() => {
        removeAlert(a.id);
        setFadingIds(prev => { const n = new Set(prev); n.delete(a.id); return n; });
      }, 5000);
      return [fadeTimer, removeTimer];
    });
    return () => timers.flat().forEach(clearTimeout);
  }, [alerts.map(a => a.id).join(',')]);

  if (alerts.length === 0) return null;

  const icons = { success: CheckCircle, error: AlertCircle, warning: AlertTriangle, info: Info };

  return (
    <div className="alert-banner">
      {alerts.map(a => {
        const Icon = icons[a.type] ?? Info;
        const fading = fadingIds.has(a.id);
        return (
          <div
            key={a.id}
            className={`alert alert--${a.type} ${fading ? 'alert--fading' : ''}`}
          >
            <Icon size={14} />
            <span>{a.message}</span>
            <button className="alert-close" onClick={() => removeAlert(a.id)}>
              <X size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
