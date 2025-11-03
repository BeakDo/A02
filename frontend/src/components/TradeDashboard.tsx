import { Box, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { StrategyState } from '../lib/types';

interface TradeDashboardProps {
  state: StrategyState | null;
  stats: StrategyState['snapshots'][number] | null | undefined;
}

const TradeDashboard = ({ state, stats }: TradeDashboardProps) => {
  return (
    <Stack spacing={3}>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard title="Total Equity" value={stats ? stats.total_equity.toLocaleString() + ' KRW' : '-'} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard title="Available" value={stats ? stats.available_balance.toLocaleString() + ' KRW' : '-'} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard title="1D Change" value={stats ? stats.change_1d.toLocaleString() + ' KRW' : '-'} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard title="Total Change" value={stats ? stats.change_total.toLocaleString() + ' KRW' : '-'} />
        </Grid>
      </Grid>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Active Position
          </Typography>
          {state?.position.symbol ? (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <Box>
                <Typography variant="body2">Symbol</Typography>
                <Typography variant="h5">{state.position.symbol}</Typography>
              </Box>
              <Box>
                <Typography variant="body2">Size</Typography>
                <Typography variant="h5">{state.position.size.toFixed(4)}</Typography>
              </Box>
              <Box>
                <Typography variant="body2">Average Price</Typography>
                <Typography variant="h5">{state.position.avg_price.toFixed(0)}</Typography>
              </Box>
              <Box>
                <Typography variant="body2">Stop Loss</Typography>
                <Typography variant="h5">{state.position.stop_loss?.toFixed(0)}</Typography>
              </Box>
            </Stack>
          ) : (
            <Typography variant="body2">No active position.</Typography>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Recent Logs
          </Typography>
          <Stack spacing={1} sx={{ maxHeight: 240, overflow: 'auto' }}>
            {state?.last_logs.slice(-20).map((log, index) => (
              <Typography variant="caption" key={index}>
                {log}
              </Typography>
            )) || <Typography variant="caption">No logs yet.</Typography>}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
};

export default TradeDashboard;

interface MetricCardProps {
  title: string;
  value: string;
}

const MetricCard = ({ title, value }: MetricCardProps) => (
  <Card>
    <CardContent>
      <Typography variant="body2" color="text.secondary">
        {title}
      </Typography>
      <Typography variant="h5">{value}</Typography>
    </CardContent>
  </Card>
);
