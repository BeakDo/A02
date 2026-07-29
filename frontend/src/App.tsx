import { useEffect, useMemo, useState } from 'react';
import {
  AppBar,
  Box,
  Button,
  Container,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  Toolbar,
  Typography
} from '@mui/material';
import TradeDashboard from './components/TradeDashboard';
import { useStrategyState } from './hooks/useStrategyState';
import { TradingMode } from './lib/types';

function App() {
  const { state, updateConfig, switchMode, startEngine, stopEngine } = useStrategyState();
  const [lossValue, setLossValue] = useState('100000');
  const [lossType, setLossType] = useState<'amount' | 'percent'>('amount');
  const [maxWeight, setMaxWeight] = useState('1.0');

  useEffect(() => {
    if (!state) return;
    setLossValue(String(state.config.loss_limit.loss_limit_value));
    setLossType(state.config.loss_limit.loss_limit_type);
    setMaxWeight(String(state.config.loss_limit.max_allocation_weight));
  }, [state]);

  const mode = state?.config.mode ?? TradingMode.PAPER;
  const isRunning = state?.is_running ?? false;

  const handleSave = async () => {
    if (!state) return;
    await updateConfig({
      ...state.config,
      loss_limit: {
        ...state.config.loss_limit,
        loss_limit_value: Number(lossValue),
        loss_limit_type: lossType,
        max_allocation_weight: Number(maxWeight)
      }
    });
  };

  const stats = useMemo(() => {
    if (!state) return null;
    const latest = state.snapshots[state.snapshots.length - 1];
    return latest;
  }, [state]);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="static" color="transparent" elevation={0}>
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Upbit Order Block Trader
          </Typography>
          <Stack direction="row" spacing={2} alignItems="center" mr={2}>
            <Typography variant="body2" color={isRunning ? 'success.main' : 'text.secondary'}>
              {isRunning ? 'Running' : 'Stopped'}
            </Typography>
            <Button
              variant={isRunning ? 'outlined' : 'contained'}
              color={isRunning ? 'warning' : 'primary'}
              onClick={isRunning ? stopEngine : startEngine}
            >
              {isRunning ? 'Stop' : 'Start'}
            </Button>
          </Stack>
          <Stack direction="row" spacing={2} alignItems="center">
            <Typography variant="body2">Paper</Typography>
            <Switch
              checked={mode === TradingMode.LIVE}
              onChange={() => switchMode(mode === TradingMode.LIVE ? TradingMode.PAPER : TradingMode.LIVE)}
            />
            <Typography variant="body2">Live</Typography>
          </Stack>
        </Toolbar>
      </AppBar>
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={4}>
          <Box flex={1}>
            <Typography variant="h6" gutterBottom>
              Risk Controls
            </Typography>
            <Stack spacing={2}>
              <FormControl fullWidth>
                <InputLabel id="loss-type-label">Loss Limit Type</InputLabel>
                <Select
                  labelId="loss-type-label"
                  label="Loss Limit Type"
                  value={lossType}
                  onChange={event => setLossType(event.target.value as 'amount' | 'percent')}
                >
                  <MenuItem value="amount">Amount</MenuItem>
                  <MenuItem value="percent">Percent</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label={lossType === 'amount' ? 'Loss Limit (KRW)' : 'Loss Limit (%)'}
                value={lossValue}
                onChange={event => setLossValue(event.target.value)}
                fullWidth
              />
              <TextField
                label="Max Allocation Weight"
                value={maxWeight}
                onChange={event => setMaxWeight(event.target.value)}
                fullWidth
              />
              <Button variant="contained" onClick={handleSave} disabled={!state}>
                Save Settings
              </Button>
            </Stack>
          </Box>
          <Box flex={3}>
            <TradeDashboard state={state} stats={stats} />
          </Box>
        </Stack>
      </Container>
    </Box>
  );
}

export default App;
