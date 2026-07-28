#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

START = pd.Timestamp('2022-01-01', tz='UTC')
PRE_END = pd.Timestamp('2025-01-01', tz='UTC')
END = pd.Timestamp('2026-07-01', tz='UTC')
DATA_DIR = Path('research/cross_sectional_v4/data')
RESULT_DIR = Path('research/cross_sectional_v4/results')
BASE_URL = 'https://data.binance.vision/data/futures/um/monthly/klines'
FUND_URL = 'https://data.binance.vision/data/futures/um/monthly/fundingRate'

DEV_SYMBOLS = [
    '1000SHIBUSDT','1000PEPEUSDT','1000FLOKIUSDT','1000BONKUSDT','1000SATSUSDT',
    'WIFUSDT','BOMEUSDT','FETUSDT','INJUSDT','TIAUSDT','SEIUSDT','SUIUSDT','APTUSDT',
    'ARBUSDT','OPUSDT','STXUSDT','ORDIUSDT','JUPUSDT','WLDUSDT','GALAUSDT','SANDUSDT',
    'MANAUSDT','AXSUSDT','APEUSDT','FTMUSDT','ALGOUSDT','EGLDUSDT','KAVAUSDT','KSMUSDT',
    'ZECUSDT','DASHUSDT','ZENUSDT','THETAUSDT','RLCUSDT','ENSUSDT','IMXUSDT','MKRUSDT',
    'YFIUSDT','SUSHIUSDT','1INCHUSDT','BALUSDT','MASKUSDT','PEOPLEUSDT','LPTUSDT',
    'ARUSDT','IOTAUSDT','FLOWUSDT','CHZUSDT','ENJUSDT',
]
VALID_SYMBOLS = [
    'NEOUSDT','QTUMUSDT','ONTUSDT','ZILUSDT','CELOUSDT','ANKRUSDT','COTIUSDT','KNCUSDT',
    'SKLUSDT','BELUSDT','BANDUSDT','OCEANUSDT','ICXUSDT','WAVESUSDT','RSRUSDT','LRCUSDT',
    'HOTUSDT','BLZUSDT','RVNUSDT','STORJUSDT','IOTXUSDT','ONEUSDT','DENTUSDT',
]
HOLDOUT_SYMBOLS = [
    'ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','ADAUSDT','DOGEUSDT','AVAXUSDT','LINKUSDT',
    'DOTUSDT','LTCUSDT','BCHUSDT','AAVEUSDT','UNIUSDT','ETCUSDT','FILUSDT','TRXUSDT',
    'NEARUSDT','ATOMUSDT','RUNEUSDT','CRVUSDT','DYDXUSDT','LDOUSDT','COMPUSDT','SNXUSDT',
]
ALL_PRE = DEV_SYMBOLS + VALID_SYMBOLS

FOLDS = [
    ('dev_2022H2', pd.Timestamp('2022-07-01',tz='UTC'), pd.Timestamp('2023-01-01',tz='UTC'), 'dev'),
    ('dev_2023', pd.Timestamp('2023-01-01',tz='UTC'), pd.Timestamp('2024-01-01',tz='UTC'), 'dev'),
    ('dev_2024', pd.Timestamp('2024-01-01',tz='UTC'), PRE_END, 'dev'),
    ('valid_2024', pd.Timestamp('2024-01-01',tz='UTC'), PRE_END, 'valid'),
]

SESSION = requests.Session()
SESSION.headers['User-Agent']='Mozilla/5.0 alpha-research-v4'

@dataclass(frozen=True)
class Config:
    family: str
    horizon: int
    rebalance: int
    top_k: int
    min_spread: float
    trend_w: float
    flow_w: float
    funding_w: float
    quality_w: float
    vol_target: float = 1.20
    max_leverage: float = 4.0
    regime_tilt: float = 0.0
    one_way_cost: float = 0.0008
    stress_cost: float = 0.00125
    dd_kill: float = 0.285


def months(start=START,end=END):
    cur=pd.Timestamp(start.year,start.month,1,tz='UTC')
    out=[]
    while cur<end:
        out.append(cur.strftime('%Y-%m'))
        cur=cur+pd.offsets.MonthBegin(1)
    return out


def get(url, timeout=30):
    for i in range(4):
        try:
            r=SESSION.get(url,timeout=timeout)
            if r.status_code==200:return r.content
            if r.status_code in (403,404):return None
        except requests.RequestException:
            pass
        time.sleep(1.0*(i+1))
    return None


def parse_kline(raw):
    with zipfile.ZipFile(BytesIO(raw)) as z:
        name=z.namelist()[0]
        df=pd.read_csv(z.open(name),header=None,usecols=list(range(12)))
    df.columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_base','taker_buy_quote','ignore']
    for c in ['open','high','low','close','quote_volume','taker_buy_quote']:
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df['timestamp']=pd.to_datetime(df['open_time'],unit='ms',utc=True,errors='coerce')
    return df[['timestamp','open','high','low','close','quote_volume','taker_buy_quote']].dropna(subset=['timestamp']).drop_duplicates('timestamp')


def parse_funding(raw):
    with zipfile.ZipFile(BytesIO(raw)) as z:
        name=z.namelist()[0]
        df=pd.read_csv(z.open(name))
    cols={str(c).lower():c for c in df.columns}
    tcol=cols.get('calc_time') or cols.get('fundingtime') or cols.get('time')
    rcol=cols.get('last_funding_rate') or cols.get('fundingrate') or cols.get('funding_rate')
    if tcol is None or rcol is None:return pd.DataFrame(columns=['timestamp','funding'])
    ts=pd.to_datetime(df[tcol],unit='ms',utc=True,errors='coerce')
    rate=pd.to_numeric(df[rcol],errors='coerce')
    return pd.DataFrame({'timestamp':ts.dt.floor('h'),'funding':rate}).dropna().drop_duplicates('timestamp',keep='last')


def download_symbol(symbol,start=START,end=END):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    path=DATA_DIR/f'{symbol}_1h.parquet'
    if path.exists():return symbol
    frames=[]; funds=[]
    for ym in months(start,end):
        u=f'{BASE_URL}/{symbol}/15m/{symbol}-15m-{ym}.zip'
        raw=get(u)
        if raw:
            try:frames.append(parse_kline(raw))
            except Exception:pass
        fu=f'{FUND_URL}/{symbol}/{symbol}-fundingRate-{ym}.zip'
        fr=get(fu)
        if fr:
            try:funds.append(parse_funding(fr))
            except Exception:pass
    if not frames:return None
    d=pd.concat(frames,ignore_index=True).sort_values('timestamp').drop_duplicates('timestamp').set_index('timestamp')
    agg={'open':'first','high':'max','low':'min','close':'last','quote_volume':'sum','taker_buy_quote':'sum'}
    d=d.resample('1h').agg(agg)
    if funds:
        f=pd.concat(funds,ignore_index=True).sort_values('timestamp').drop_duplicates('timestamp',keep='last').set_index('timestamp')['funding']
        d['funding']=f.reindex(d.index)
        d['funding_available']=d['funding'].notna()
        d['funding']=d['funding'].fillna(0.0)
    else:
        d['funding']=0.0; d['funding_available']=False
    d=d[(d.index>=start)&(d.index<end)]
    if len(d)<24*60:return None
    d.astype({c:'float32' for c in ['open','high','low','close','quote_volume','taker_buy_quote','funding']}).to_parquet(path)
    return symbol


def ensure(symbols,start=START,end=END):
    done=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut={ex.submit(download_symbol,s,start,end):s for s in symbols}
        for f in as_completed(fut):
            try:
                x=f.result()
                if x:done.append(x)
            except Exception:pass
    return sorted(done)


def load_panel(symbols,start=START,end=END):
    data={}
    for s in symbols:
        p=DATA_DIR/f'{s}_1h.parquet'
        if p.exists():
            d=pd.read_parquet(p)
            if d.index.tz is None:d.index=d.index.tz_localize('UTC')
            data[s]=d[(d.index>=start)&(d.index<end)]
    if not data:return {},[]
    idx=pd.date_range(start,end-pd.Timedelta(hours=1),freq='1h',tz='UTC')
    fields=['open','high','low','close','quote_volume','taker_buy_quote','funding','funding_available']
    panel={f:pd.DataFrame(index=idx,columns=sorted(data),dtype='float32' if f!='funding_available' else 'boolean') for f in fields}
    for s,d in data.items():
        for f in fields:
            if f in d:
                panel[f].loc[:,s]=d[f].reindex(idx).values
    panel['funding_available']=panel['funding_available'].fillna(False).astype(bool)
    return panel,sorted(data)


def zscore(x,w):
    m=x.rolling(w,min_periods=max(12,w//4)).mean(); sd=x.rolling(w,min_periods=max(12,w//4)).std().replace(0,np.nan)
    return ((x-m)/sd).clip(-6,6).astype('float32')


def cs_z(x):
    m=x.mean(axis=1); sd=x.std(axis=1).replace(0,np.nan)
    return x.sub(m,axis=0).div(sd,axis=0).replace([np.inf,-np.inf],np.nan).fillna(0).clip(-5,5).astype('float32')


def build_features(panel, btc: pd.DataFrame):
    c, o, h, l = panel['close'], panel['open'], panel['high'], panel['low']
    q, tb = panel['quote_volume'], panel['taker_buy_quote']
    r1 = c.pct_change()
    r4, r12, r24, r72 = c.pct_change(4), c.pct_change(12), c.pct_change(24), c.pct_change(72)
    flow = (2 * tb / q.replace(0, np.nan) - 1).clip(-1,1).rolling(3, min_periods=1).mean()
    qz = zscore(np.log1p(q), 24*30)
    flowz = zscore(flow, 24*30)
    prev = c.shift()
    tr = pd.DataFrame(np.maximum.reduce([(h-l).values, (h-prev).abs().values, (l-prev).abs().values]), index=c.index, columns=c.columns)
    atr = (tr.rolling(24, min_periods=12).mean() / c).astype('float32')
    vol24 = r1.rolling(24, min_periods=12).std().astype('float32')
    vol168 = r1.rolling(168, min_periods=72).std().astype('float32')
    eff24 = (c.diff(24).abs() / c.diff().abs().rolling(24).sum().replace(0,np.nan)).clip(0,1).astype('float32')
    hi24, lo24 = c.shift(1).rolling(24).max(), c.shift(1).rolling(24).min()
    hi72, lo72 = c.shift(1).rolling(72).max(), c.shift(1).rolling(72).min()
    range24 = ((c-lo24)/(hi24-lo24).replace(0,np.nan)).clip(0,1).astype('float32')
    range72 = ((c-lo72)/(hi72-lo72).replace(0,np.nan)).clip(0,1).astype('float32')
    fund24 = panel['funding'].rolling(24, min_periods=1).sum().astype('float32')
    qmed = q.rolling(24, min_periods=12).median()
    liq_rank = qmed.rank(axis=1, pct=True)
    age = c.notna().cumsum()
    tradable = c.notna() & o.shift(-1).notna() & (age >= 24*14) & (qmed >= 100_000) & (liq_rank >= .20)
    btc_close = btc['close'].reindex(c.index).ffill()
    btc12, btc24, btc72 = btc_close.pct_change(12).fillna(0), btc_close.pct_change(24).fillna(0), btc_close.pct_change(72).fillna(0)
    res12, res24, res72 = r12.sub(btc12,axis=0), r24.sub(btc24,axis=0), r72.sub(btc72,axis=0)
    breadth = (r24 > 0).where(tradable).mean(axis=1).fillna(.5).astype('float32')
    dispersion = r24.where(tradable).std(axis=1).fillna(0).astype('float32')
    out = {
        'open':o,'close':c,'r1':r1,'r4':r4,'r12':r12,'r24':r24,'r72':r72,
        'res12':res12,'res24':res24,'res72':res72,'flow':flow,'qz':qz,'flowz':flowz,
        'atr':atr,'vol24':vol24,'vol168':vol168,'eff24':eff24,'range24':range24,'range72':range72,
        'fund24':fund24,'fund':panel['funding'],'fund_av':panel['funding_available'],'tradable':tradable,
        'breadth':breadth,'dispersion':dispersion,'btc24':btc24.astype('float32'),'btc72':btc72.astype('float32'),
    }
    for k,v in list(out.items()):
        if isinstance(v,pd.DataFrame) and k not in ('tradable','fund_av'):
            out[k]=v.astype('float32')
    return out


def score_matrix(cfg:Config,F):
    h=cfg.horizon
    res={12:F['res12'],24:F['res24'],72:F['res72']}[h]
    trend=cs_z(res)
    flow=cs_z(F['flowz'] + .35*F['qz'])
    funding=cs_z(-F['fund24'])
    quality=cs_z(F['eff24'] - .35*F['atr'] + .20*F['range72'])
    if cfg.family=='residual_momentum':
        score=1.25*trend + cfg.flow_w*.35*flow + cfg.quality_w*quality
    elif cfg.family=='flow_momentum':
        score=.70*trend + 1.15*flow + cfg.quality_w*quality
    elif cfg.family=='funding_divergence':
        score=.65*trend + 1.10*funding + .25*flow
    elif cfg.family=='breakout_quality':
        br=cs_z((F['range24']-.5)*2 + (F['range72']-.5)*1.2)
        score=.75*trend + .85*br + .65*quality + .25*flow
    elif cfg.family=='panic_reversal':
        panic=cs_z(-F['r12'] - .35*F['r24'] - .25*F['flowz'])
        regime=((F['btc24'] < -.04) | (F['breadth'] < .25)).astype(float)
        score=panic.mul(regime,axis=0)
    else:
        score=cfg.trend_w*trend + cfg.flow_w*flow + cfg.funding_w*funding + cfg.quality_w*quality
    return score.where(F['tradable'])


def make_weights(cfg:Config,F,start,end):
    score=score_matrix(cfg,F).loc[start:end-pd.Timedelta(hours=1)]
    trad=F['tradable'].loc[score.index]
    idx=score.index; cols=score.columns
    raw=np.zeros(score.shape,dtype='float32')
    rebal=np.arange(len(idx)) % cfg.rebalance == 0
    sv=score.to_numpy(dtype='float32'); tv=trad.to_numpy(dtype=bool)
    for i in np.where(rebal)[0]:
        vals=sv[i].copy(); vals[~tv[i]]=np.nan
        ok=np.isfinite(vals)
        if ok.sum()<max(2*cfg.top_k,6):continue
        spread=np.nanpercentile(vals,80)-np.nanpercentile(vals,20)
        if not np.isfinite(spread) or spread<cfg.min_spread:continue
        order=np.argsort(np.where(ok,vals,-np.inf))
        shorts=[j for j in order if ok[j]][:cfg.top_k]
        longs=[j for j in order[::-1] if ok[j]][:cfg.top_k]
        if len(longs)<cfg.top_k or len(shorts)<cfg.top_k:continue
        raw[i,longs]=.5/cfg.top_k; raw[i,shorts]=-.5/cfg.top_k
    w=pd.DataFrame(raw,index=idx,columns=cols)
    w=w.mask(~pd.Series(rebal,index=idx),np.nan).ffill(limit=cfg.rebalance-1).fillna(0)
    if cfg.regime_tilt:
        regime=((F['btc24'].loc[idx] > 0).astype(float)*2-1).clip(-1,1)
        # Small directional tilt only; preserve mostly market-neutral structure.
        tilt=pd.DataFrame(np.broadcast_to(regime.to_numpy()[:,None],w.shape),index=idx,columns=cols)
        active=(w!=0).sum(axis=1).replace(0,np.nan)
        w=w.add(tilt.mul(cfg.regime_tilt).div(active,axis=0)).fillna(0)
    return w.astype('float32')


def metrics(curve):
    eq=curve['equity'].replace([np.inf,-np.inf],np.nan).dropna()
    if len(eq)<48:return {'cagr':-1.0,'mdd':1.0,'sharpe':-99.0,'total_return':-1.0,'years':0}
    years=(eq.index[-1]-eq.index[0]).total_seconds()/(365.25*86400)
    total=float(eq.iloc[-1]/eq.iloc[0]-1)
    cagr=float((eq.iloc[-1]/eq.iloc[0])**(1/max(years,1/365.25))-1) if eq.iloc[-1]>0 else -1.0
    mdd=float((1-eq/eq.cummax()).max())
    ret=curve.loc[eq.index,'return']
    sharpe=float(ret.mean()/ret.std()*math.sqrt(24*365.25)) if ret.std()>0 else 0.0
    return {'cagr':cagr,'mdd':mdd,'sharpe':sharpe,'total_return':total,'years':years}


def prepare(cfg:Config,F,start,end):
    w=make_weights(cfg,F,start,end)
    idx=w.index
    next_open=F['open'].shift(-1).reindex(idx)
    r_open=next_open.pct_change().shift(-1).fillna(0).clip(-.45,.45)
    fund=F['fund'].reindex(idx).fillna(0)
    fav=F['fund_av'].reindex(idx).fillna(False)
    return {'weights':w,'r_open':r_open,'fund':fund,'fund_av':fav}


def simulate(cfg:Config,prepared,start,end,stress=False):
    w=prepared['weights'].loc[start:end-pd.Timedelta(hours=1)].copy()
    idx=w.index
    r_open=prepared['r_open'].reindex(idx).fillna(0)
    fund=prepared['fund'].reindex(idx).fillna(0)
    fav=prepared['fund_av'].reindex(idx).fillna(False)
    # Scale only at rebalance changes and hold scale constant between them.
    base_port=(w.shift(1).fillna(0)*r_open).sum(axis=1)
    rv=base_port.rolling(24*14,min_periods=24*3).std()*math.sqrt(24*365.25)
    scale=(cfg.vol_target/rv.replace(0,np.nan)).clip(0,cfg.max_leverage)
    change=(w.ne(w.shift(1))).any(axis=1)
    scale=scale.where(change).ffill().fillna(min(1.0,cfg.max_leverage))
    scaled=w.mul(scale,axis=0)
    gross=scaled.abs().sum(axis=1).clip(0,cfg.max_leverage)
    over=(scaled.abs().sum(axis=1)/cfg.max_leverage).clip(lower=1)
    scaled=scaled.div(over,axis=0)
    turnover=(scaled-scaled.shift(1).fillna(0)).abs().sum(axis=1)
    cost=turnover*(cfg.stress_cost if stress else cfg.one_way_cost)
    pnl=(scaled.shift(1).fillna(0)*r_open).sum(axis=1)
    funding_cost=(scaled.shift(1).fillna(0)*fund).sum(axis=1)
    missing=(scaled.shift(1).fillna(0).abs().where(~fav,0)).sum(axis=1)
    if stress: funding_cost=funding_cost + missing*0.00002/8
    ret=(pnl-funding_cost-cost).clip(-.30,.30)
    eq=[]; e=1.0; peak=1.0; killed=False; hard_stops=0
    for x in ret.to_numpy():
        if killed:x=0.0
        e*=max(1e-8,1+float(x)); peak=max(peak,e)
        dd=1-e/peak
        if dd>=cfg.dd_kill and not killed:
            killed=True; hard_stops+=1
        eq.append(e)
    curve=pd.DataFrame({'equity':eq,'return':ret.values,'gross':gross.values,'turnover':turnover.values,'net':scaled.sum(axis=1).values,'names':(scaled!=0).sum(axis=1).values},index=idx)
    met=metrics(curve)
    active=curve['gross']>.05
    changes=(scaled.ne(scaled.shift(1))).any(axis=1)
    met.update({
        'max_gross':float(curve.gross.max()),'avg_gross':float(curve.gross.mean()),'avg_names':float(curve.names.mean()),
        'active_fraction':float(active.mean()),'rebalances':int((changes&active).sum()),
        'annual_turnover':float(curve.turnover.sum()/max(met['years'],1/365.25)),'hard_stops':hard_stops,
    })
    return curve,met


def base_configs():
    families = ['residual_momentum','flow_momentum','funding_divergence','breakout_quality','panic_reversal','hybrid']
    templates = [
        # horizon, rebalance, top_k, min_spread, trend, flow, funding, quality
        (12,4,3,.45,1.0,.35,.20,.25),
        (24,4,3,.60,1.0,.50,.25,.35),
        (24,8,4,.45,1.0,.35,.35,.25),
        (72,8,3,.60,1.0,.25,.40,.40),
        (72,12,4,.45,1.0,.40,.25,.50),
        (24,12,2,.75,1.0,.50,.40,.35),
    ]
    out=[]
    for fam in families:
        for h,rb,k,spread,tw,fw,fdw,qw in templates:
            out.append(Config(fam,h,rb,k,spread,tw,fw,fdw,qw))
    return out


def evaluate(cfg,Fdev,Fvalid):
    pdev=prepare(cfg,Fdev,START,PRE_END)
    pvalid=prepare(cfg,Fvalid,START,PRE_END)
    rows=[]
    for name,s,e,grp in FOLDS:
        prep=pdev if grp=='dev' else pvalid
        _,m=simulate(cfg,prep,s,e,False)
        rows.append({'fold':name,**m})
    _,sv=simulate(cfg,pvalid,pd.Timestamp('2024-01-01',tz='UTC'),PRE_END,True)
    c=[r['cagr'] for r in rows]; d=[r['mdd'] for r in rows]
    valid=rows[-1]
    positives=sum(x>0 for x in c[:3])
    eligible=(
        valid['cagr']>0 and sv['cagr']>0 and valid['active_fraction']>=.20 and valid['rebalances']>=40 and
        positives>=2 and max(d)<=.30 and sv['mdd']<=.30
    )
    # Strongly punish sparse/no-trade and validation weakness.
    score=(
        2.5*valid['cagr'] + 1.7*sv['cagr'] + .7*np.median(c[:3]) + .25*min(c[:3])
        - 2.2*max(d) - 1.2*sv['mdd'] + .05*valid['sharpe']
        + .2*min(valid['active_fraction'],.8)
    )
    if not eligible: score-=100
    return score,eligible,rows,sv


def search():
    RESULT_DIR.mkdir(parents=True,exist_ok=True)
    pre=ensure(ALL_PRE+['BTCUSDT'],START,PRE_END)
    dev=[s for s in DEV_SYMBOLS if s in pre]; valid=[s for s in VALID_SYMBOLS if s in pre]
    if len(dev)<25 or len(valid)<12:raise RuntimeError(f'insufficient pre symbols dev={len(dev)} valid={len(valid)}')
    btc=pd.read_parquet(DATA_DIR/'BTCUSDT_1h.parquet')
    pdev,_=load_panel(dev,START,PRE_END); pvalid,_=load_panel(valid,START,PRE_END)
    Fdev=build_features(pdev,btc); Fvalid=build_features(pvalid,btc)
    leaderboard=[]
    for cfg in base_configs():
        score,eligible,rows,sv=evaluate(cfg,Fdev,Fvalid)
        leaderboard.append({'score':score,'eligible':eligible,'config':asdict(cfg),'folds':rows,'stress_valid':sv})
    leaderboard.sort(key=lambda x:x['score'],reverse=True)
    (RESULT_DIR/'base_leaderboard.json').write_text(json.dumps(leaderboard,indent=2))
    eligible=[x for x in leaderboard if x['eligible']]
    if not eligible:
        raise RuntimeError('no eligible base candidate; fresh holdout remains unopened')
    refined=[]
    for seed in eligible[:3]:
        base=Config(**seed['config'])
        for vt,lev,tilt in itertools.product([1.2,2.4,4.0],[4.0,8.0,12.0],[0.0,.10]):
            cfg=Config(**{**asdict(base),'vol_target':vt,'max_leverage':lev,'regime_tilt':tilt})
            score,ok,rows,sv=evaluate(cfg,Fdev,Fvalid)
            refined.append({'score':score,'eligible':ok,'config':asdict(cfg),'folds':rows,'stress_valid':sv})
    refined.sort(key=lambda x:x['score'],reverse=True)
    (RESULT_DIR/'refined_leaderboard.json').write_text(json.dumps(refined,indent=2))
    finalist=next((x for x in refined if x['eligible']),None)
    if finalist is None:raise RuntimeError('no eligible refined candidate; holdout unopened')
    cfg=Config(**finalist['config'])
    # Neighbour robustness without looking at holdout.
    neighbours=[]
    for mult in [.85,1.0,1.15]:
        ncfg=Config(**{**asdict(cfg),'min_spread':cfg.min_spread*mult})
        sc,ok,rows,sv=evaluate(ncfg,Fdev,Fvalid)
        neighbours.append({'mult':mult,'score':sc,'eligible':ok,'folds':rows,'stress_valid':sv})
    if sum(n['eligible'] for n in neighbours)<2:
        raise RuntimeError('finalist lacks neighbourhood robustness; holdout unopened')
    frozen={
        'config':asdict(cfg),'selection_score':finalist['score'],'folds':finalist['folds'],
        'stress_valid':finalist['stress_valid'],'neighbours':neighbours,
        'dev_symbols':dev,'valid_symbols':valid,'holdout_symbols':HOLDOUT_SYMBOLS,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'holdout_opened':False,
    }
    (RESULT_DIR/'frozen_candidate.json').write_text(json.dumps(frozen,indent=2))
    print(json.dumps({'frozen':frozen['config'],'score':frozen['selection_score'],'valid':frozen['folds'][-1],'stress':frozen['stress_valid']},indent=2))


def holdout():
    fp=RESULT_DIR/'frozen_candidate.json'
    if not fp.exists():raise RuntimeError('candidate not frozen')
    frozen=json.loads(fp.read_text())
    if frozen.get('holdout_opened'):raise RuntimeError('holdout already opened')
    if frozen['source_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise RuntimeError('source changed after freeze')
    got=ensure(HOLDOUT_SYMBOLS+['BTCUSDT'],START,END)
    hold=[s for s in HOLDOUT_SYMBOLS if s in got]
    if len(hold)<14:raise RuntimeError(f'insufficient holdout symbols {len(hold)}')
    btc=pd.read_parquet(DATA_DIR/'BTCUSDT_1h.parquet')
    ph,_=load_panel(hold,START,END); F=build_features(ph,btc)
    cfg=Config(**frozen['config'])
    prep=prepare(cfg,F,PRE_END,END)
    curve,m=simulate(cfg,prep,PRE_END,END,False)
    stress_curve,sm=simulate(cfg,prep,PRE_END,END,True)
    result={'config':asdict(cfg),'holdout_symbols':hold,'holdout':m,'stress_holdout':sm,'pass_target':bool(m['cagr']>=10.0 and m['mdd']<=.30 and sm['mdd']<=.30)}
    curve.to_parquet(RESULT_DIR/'holdout_curve.parquet')
    stress_curve.to_parquet(RESULT_DIR/'holdout_curve_stress.parquet')
    (RESULT_DIR/'holdout_result.json').write_text(json.dumps(result,indent=2))
    frozen['holdout_opened']=True; frozen['holdout_result_sha256']=hashlib.sha256((RESULT_DIR/'holdout_result.json').read_bytes()).hexdigest()
    fp.write_text(json.dumps(frozen,indent=2))
    print(json.dumps(result,indent=2))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('mode',choices=['search','holdout']); a=ap.parse_args()
    search() if a.mode=='search' else holdout()

if __name__=='__main__':main()
