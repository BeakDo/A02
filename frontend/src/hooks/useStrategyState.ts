import { useCallback, useEffect, useState } from 'react';
import { StrategyConfig, StrategyState, TradingMode } from '../lib/types';

export const useStrategyState = () => {
  const [state, setState] = useState<StrategyState | null>(null);
  const [socket, setSocket] = useState<WebSocket | null>(null);

  const fetchState = useCallback(async () => {
    const response = await fetch('/api/v1/state');
    const payload = (await response.json()) as StrategyState;
    setState(payload);
  }, []);

  const updateConfig = useCallback(async (config: StrategyConfig) => {
    const response = await fetch('/api/v1/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    const payload = (await response.json()) as StrategyConfig;
    setState(prev => (prev ? { ...prev, config: payload } : prev));
  }, []);

  const switchMode = useCallback(async (mode: TradingMode) => {
    await fetch(`/api/v1/mode/${mode}`, { method: 'POST' });
    setState(prev => (prev ? { ...prev, config: { ...prev.config, mode } } : prev));
  }, []);

  const startEngine = useCallback(async () => {
    await fetch('/api/v1/control/start', { method: 'POST' });
    setState(prev => (prev ? { ...prev, is_running: true } : prev));
  }, []);

  const stopEngine = useCallback(async () => {
    await fetch('/api/v1/control/stop', { method: 'POST' });
    setState(prev => (prev ? { ...prev, is_running: false } : prev));
  }, []);

  useEffect(() => {
    fetchState();
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/v1/ws/stream`);
    ws.onmessage = event => {
      const payload = JSON.parse(event.data);
      setState(payload.state as StrategyState);
    };
    setSocket(ws);
    return () => {
      ws.close();
    };
  }, [fetchState]);

  return { state, updateConfig, switchMode, socket, startEngine, stopEngine };
};
