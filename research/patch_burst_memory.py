from pathlib import Path
import hashlib

p = Path('research/burst_research.py')
s = p.read_text(encoding='utf-8')

s = s.replace(
    "panel = {f: pd.DataFrame(index=idx, columns=cols, dtype=float) for f in fields}",
    "panel = {f: pd.DataFrame(index=idx, columns=cols, dtype='float32') for f in fields}",
)
s = s.replace(
    "    return (x - m) / sd\n",
    "    return ((x - m) / sd).astype('float32')\n",
)

old = """    return {
          'open':o,'high':h,'low':l,'close':c,'ret':ret,'flow':flow,'flowz':flowz,
          'qz':qz,'tradez':tradez,'atr':atr,'close_pos':close_pos,'upper_wick':upper_wick,
          'lower_wick':lower_wick,'r1h':r1h,'r4h':r4h,'r12h':r12h,'r24h':r24h,
          'fund':fund,'fz':fz,'frank':frank,'tradable':tradable,'fund_av':panel['funding_available'],
          'breadth':breadth,'med4':med4,'btc4':btc4,'btc24':btc24,'residual4':residual4,
          'high6':high6,'low6':low6,'high24':high24,'low24':low24,'high48':high48,'low48':low48,
          'pump24':pump24,'dump24':dump24,'dd24':dd24,'bounce24':bounce24,'compression':compression,
          'age':age,
      }
"""
new = """    out = {
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
"""
if old not in s:
    raise SystemExit('feature block missing')
s = s.replace(old, new)

old2 = """    dev=load_group(DEV_SYMBOLS); valid=load_group(VALID_SYMBOLS); hold=load_group(HOLDOUT_SYMBOLS)
    if len(dev)<20 or len(valid)<7 or len(hold)<7:
        raise RuntimeError(f'insufficient symbols dev={len(dev)} valid={len(valid)} hold={len(hold)}')
"""
new2 = """    # Memory-bounded pre-holdout panels. Holdout prices are not loaded during selection.
    dev=load_group(DEV_SYMBOLS[:32]); valid=load_group(VALID_SYMBOLS[:14])
    hold_available=[s for s in HOLDOUT_SYMBOLS if (DATA_DIR/f'{s}_15m.parquet').exists()]
    if len(dev)<20 or len(valid)<7 or len(hold_available)<7:
        raise RuntimeError(f'insufficient symbols dev={len(dev)} valid={len(valid)} hold={len(hold_available)}')
"""
if old2 not in s:
    raise SystemExit('search block missing')
s = s.replace(old2, new2)
s = s.replace(
    "'dev_symbols':sorted(dev),'valid_symbols':sorted(valid),'holdout_symbols':sorted(hold),",
    "'dev_symbols':sorted(dev),'valid_symbols':sorted(valid),'holdout_symbols':sorted(hold_available),",
)

p.write_text(s, encoding='utf-8')
sha = hashlib.sha256(p.read_bytes()).hexdigest()
expected = 'b93954b3d1dde1e42b1e970a5643652b1ff6badb0787d236c0cce45fc410b377'
if sha != expected:
    raise SystemExit(f'patched source hash mismatch: {sha}')
print('patched source verified:', sha)
