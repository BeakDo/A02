from pathlib import Path
import hashlib

p = Path('research/burst_research.py')
s = p.read_text(encoding='utf-8')

repls = [
    (
        """    riskon = (F['breadth'] > 0.48) & (F['btc4'] > -0.025)
    riskoff = (F['breadth'] < 0.52) & (F['btc4'] < 0.025)
""",
        """    riskon_s = (F['breadth'] > 0.48) & (F['btc4'] > -0.025)
    riskoff_s = (F['breadth'] < 0.52) & (F['btc4'] < 0.025)
    # Broadcast regime Series down rows explicitly; DataFrame & Series aligns to columns by default.
    riskon = pd.DataFrame(
        np.broadcast_to(riskon_s.to_numpy(dtype=bool)[:, None], c.shape),
        index=c.index, columns=c.columns,
    )
    riskoff = pd.DataFrame(
        np.broadcast_to(riskoff_s.to_numpy(dtype=bool)[:, None], c.shape),
        index=c.index, columns=c.columns,
    )
""",
    ),
    (
        "panel = {f: pd.DataFrame(index=idx, columns=cols, dtype=float) for f in fields}",
        "panel = {f: pd.DataFrame(index=idx, columns=cols, dtype='float32') for f in fields}",
    ),
    (
        "    return (x - m) / sd\n",
        "    return ((x - m) / sd).astype('float32')\n",
    ),
    (
        """    return {
        'open':o,'high':h,'low':l,'close':c,'ret':ret,'flow':flow,'flowz':flowz,
        'qz':qz,'tradez':tradez,'atr':atr,'close_pos':close_pos,'upper_wick':upper_wick,
        'lower_wick':lower_wick,'r1h':r1h,'r4h':r4h,'r12h':r12h,'r24h':r24h,
        'fund':fund,'fz':fz,'frank':frank,'tradable':tradable,'fund_av':panel['funding_available'],
        'breadth':breadth,'med4':med4,'btc4':btc4,'btc24':btc24,'residual4':residual4,
        'high6':high6,'low6':low6,'high24':high24,'low24':low24,'high48':high48,'low48':low48,
        'pump24':pump24,'dump24':dump24,'dd24':dd24,'bounce24':bounce24,'compression':compression,
        'age':age,
    }
""",
        """    out = {
        'open':o,'high':h,'low':l,'close':c,'ret':ret,'flow':flow,'flowz':flowz,
        'qz':qz,'tradez':tradez,'atr':atr,'close_pos':close_pos,'upper_wick':upper_wick,
        'lower_wick':lower_wick,'r1h':r1h,'r4h':r4h,'r12h':r12h,'r24h':r24h,
        'fund':fund,'fz':fz,'frank':frank,'tradable':tradable,'fund_av':panel['funding_available'],
        'breadth':breadth,'med4':med4,'btc4':btc4,'btc24':btc24,'residual4':residual4,
        'high6':high6,'low6':low6,'high24':high24,'low24':low24,'high48':high48,'low48':low48,
        'pump24':pump24,'dump24':dump24,'dd24':dd24,'bounce24':bounce24,'compression':compression,
        'age':age,
    }
    for k, v in list(out.items()):
        if isinstance(v, pd.DataFrame) and k not in ('tradable','fund_av'):
            out[k] = v.astype('float32')
        elif isinstance(v, pd.Series) and v.dtype.kind == 'f':
            out[k] = v.astype('float32')
    return out
""",
    ),
    (
        """    dev=load_group(DEV_SYMBOLS); valid=load_group(VALID_SYMBOLS); hold=load_group(HOLDOUT_SYMBOLS)
    if len(dev)<20 or len(valid)<7 or len(hold)<7:
        raise RuntimeError(f'insufficient symbols dev={len(dev)} valid={len(valid)} hold={len(hold)}')
""",
        """    # Limit in-memory panels before any optimization; the holdout is not loaded here.
    dev=load_group(DEV_SYMBOLS[:32]); valid=load_group(VALID_SYMBOLS[:14])
    hold_available=[s for s in HOLDOUT_SYMBOLS if (DATA_DIR/f'{s}_15m.parquet').exists()]
    if len(dev)<20 or len(valid)<7 or len(hold_available)<7:
        raise RuntimeError(f'insufficient symbols dev={len(dev)} valid={len(valid)} hold={len(hold_available)}')
""",
    ),
    (
        "frozen.update({'dev_symbols':sorted(dev),'valid_symbols':sorted(valid),'holdout_symbols':sorted(hold),",
        "frozen.update({'dev_symbols':sorted(dev),'valid_symbols':sorted(valid),'holdout_symbols':sorted(hold_available),",
    ),
]

for old, new in repls:
    if old not in s:
        raise SystemExit(f'missing patch target: {old[:80]!r}')
    s = s.replace(old, new, 1)

p.write_bytes(s.encode('utf-8'))
sha = hashlib.sha256(p.read_bytes()).hexdigest()
expected = '8e8ff8a3dbcf7a1ac8e4819e3413e67147c40ae4e932cb85c028539cc536b1b9'
if sha != expected:
    raise SystemExit(f'patched source hash mismatch: {sha}')
print('patched source verified:', sha)
