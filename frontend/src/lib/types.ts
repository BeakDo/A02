export enum TradingMode {
  PAPER = 'paper',
  LIVE = 'live'
}

export interface LossLimitConfig {
  loss_limit_type: 'amount' | 'percent';
  loss_limit_value: number;
  max_allocation_weight: number;
}

export interface StrategyConfig {
  mode: TradingMode;
  base_currency: string;
  symbols: string[];
  loss_limit: LossLimitConfig;
  cooldown_minutes: number;
  partial_tp_ratio: number;
  poc_lookback: number;
  channel_lookback: number;
}

export interface Position {
  symbol: string | null;
  size: number;
  avg_price: number;
  entry_time: string | null;
  stop_loss: number | null;
  take_profit: number | null;
  realised_pnl: number;
  floating_pnl: number;
  partial_taken: boolean;
  last_channel_id: string | null;
}

export interface OrderBlock {
  symbol: string;
  ob_type: 'bullish' | 'bearish';
  candle_time: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  lower_bound: number;
  upper_bound: number;
  weight: number;
  cancelled: boolean;
  cancellation_reason: string | null;
}

export interface ChannelLevel {
  symbol: string;
  upper: number;
  mid_upper: number;
  mid: number;
  mid_lower: number;
  lower: number;
  computed_at: string;
  source: string;
}

export interface PortfolioSnapshot {
  timestamp: string;
  total_equity: number;
  available_balance: number;
  invested_balance: number;
  positions: Record<string, Position>;
  change_1d: number;
  change_total: number;
}

export interface StrategyState {
  config: StrategyConfig;
  position: Position;
  active_order_blocks: OrderBlock[];
  channels: Record<string, ChannelLevel>;
  snapshots: PortfolioSnapshot[];
  last_logs: string[];
  is_running: boolean;
}
