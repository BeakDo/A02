from pathlib import Path
import hashlib

p=Path("research/convex_v7.py")
raw=p.read_bytes()
expected_original="4583b815e4591d25a99dcd00a9b255abd1ebe2d1084abed99906f0cc40bf9177"
if hashlib.sha256(raw).hexdigest()!=expected_original:
    raise SystemExit("original source hash mismatch")
s=raw.decode("utf-8")
start=s.index("def simulate(weights,next_ret,start,end,cost_rate,dd_kill):")
end=s.index("\n\ndef pub(",start)
new='''def simulate(weights,next_ret,start,end,cost_rate,dd_kill):
    w=weights.loc[start:end-pd.Timedelta(hours=1)].copy();r=next_ret.reindex_like(w).fillna(0)
    pnl=(w*r).sum(axis=1);turnover=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1));gross=w.abs().sum(axis=1)
    pv=pnl.to_numpy(dtype=float);tv=turnover.to_numpy(dtype=float);gv=gross.to_numpy(dtype=float)
    eq=1.;peak=1.;killed=False;rets=np.zeros(len(pv),dtype=float);active=np.zeros(len(pv),dtype=float)
    for k in range(len(pv)):
        if killed: continue
        dd=1-eq/peak
        mult=1. if dd<.10 else (.65 if dd<.18 else (.30 if dd<.24 else .08))
        rr=mult*(pv[k]-tv[k]*cost_rate)
        rr=max(-.45,min(.45,rr));eq*=1+rr;peak=max(peak,eq)
        if 1-eq/peak>=dd_kill:killed=True
        rets[k]=rr;active[k]=float(gv[k]>.05)
    rs=pd.Series(rets,index=pnl.index);curve=(1+rs).cumprod();dd=1-curve/curve.cummax();years=max(len(rs)/(24*365.25),1/365.25)
    cagr=float(curve.iloc[-1]**(1/years)-1) if len(curve) else -1.;mdd=float(dd.max()) if len(dd) else 0.
    ann_mean=rs.mean()*24*365.25;ann_sd=rs.std()*math.sqrt(24*365.25);monthly=curve.resample('ME').last().pct_change().dropna()
    return {'cagr':cagr,'mdd':mdd,'sharpe':float(ann_mean/ann_sd) if ann_sd>0 else 0.,'final_equity':float(curve.iloc[-1]) if len(curve) else 1.,
            'active_fraction':float(active.mean()) if len(active) else 0.,'trade_events':int((tv>.10).sum()),'turnover_annual':float(tv.mean()*24*365.25),
            'min_month':float(monthly.min()) if len(monthly) else 0.,'median_month':float(monthly.median()) if len(monthly) else 0.,'killed':bool(killed),'curve':curve}
'''
s=s[:start]+new+s[end:]
p.write_bytes(s.encode("utf-8"))
actual=hashlib.sha256(p.read_bytes()).hexdigest()
expected="4bce815892a2df10d7ee4d309fddb0966e52b805c451aa160b684104c091ce55"
if actual!=expected:
    raise SystemExit(f"optimized source hash mismatch: {actual}")
print("optimized source verified",actual)
