/**
 * WebSocket Hook - Real-time connection to backend
 */

import { useEffect, useRef, useCallback } from 'react';
import { useMinerStore } from '../store/minerStore';
import type { MinerDevice, ScanProgress, WebSocketMessage } from '../types/miner';

const WS_URL = 'ws://127.0.0.1:8765/ws/';
const RECONNECT_DELAY = 3000;
const MAX_RECONNECT_ATTEMPTS = 10;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMounted = useRef(true);

  const {
    setMiners,
    setSummary,
    setScanProgress,
    setIsScanning,
    setScanResults,
    updateFlashJob,
    addAlert,
    setIsConnected,
  } = useMinerStore();

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg: WebSocketMessage = JSON.parse(event.data);

      switch (msg.type) {
        case 'initial_state': {
          const data = msg.data as { miners: MinerDevice[]; summary: typeof msg.summary };
          if (data?.miners) setMiners(data.miners);
          if (data?.summary) setSummary(data.summary);
          break;
        }

        case 'miners_update': {
          const miners = msg.data as MinerDevice[];
          if (Array.isArray(miners)) setMiners(miners);
          if (msg.summary) setSummary(msg.summary);
          break;
        }

        case 'scan_progress': {
          const progress = msg.data as ScanProgress;
          if (progress) {
            setScanProgress(progress);
            setIsScanning(progress.status === 'running');
          }
          break;
        }

        case 'flash_progress': {
          if (msg.job_id && msg.data) {
            updateFlashJob(msg.job_id, msg.data as Record<string, string>);
          }
          break;
        }

        case 'alert': {
          const alertType = (msg.alert_type as 'info' | 'warning' | 'error') || 'info';
          addAlert(alertType, msg.message || '');
          break;
        }

        case 'scan_results': {
          // Scan complete — store results for preview (not auto-added to miners)
          if (msg.scan_id && Array.isArray(msg.data)) {
            setScanResults(msg.scan_id, msg.data as MinerDevice[]);
            setIsScanning(false);
          }
          break;
        }

        case 'summary_update': {
          if (msg.data) setSummary(msg.data as import('../types/miner').SummaryStats);
          break;
        }
      }
    } catch (e) {
      console.error('WebSocket message parse error:', e);
    }
  }, [setMiners, setSummary, setScanProgress, setIsScanning, setScanResults, updateFlashJob, addAlert]);

  const connect = useCallback(() => {
    if (!isMounted.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        reconnectAttempts.current = 0;
      };

      ws.onmessage = handleMessage;

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        wsRef.current = null;

        if (!isMounted.current) return;
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++;
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
        }
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
      };
    } catch (e) {
      console.error('WebSocket connection failed:', e);
      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts.current++;
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
      }
    }
  }, [handleMessage, setIsConnected]);

  const send = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const disconnect = useCallback(() => {
    isMounted.current = false;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    isMounted.current = true;
    // Delay initial connection to allow backend to start
    const timer = setTimeout(connect, 1000);
    return () => {
      clearTimeout(timer);
      disconnect();
    };
  }, [connect, disconnect]);

  return { send, isConnected: wsRef.current?.readyState === WebSocket.OPEN };
}
