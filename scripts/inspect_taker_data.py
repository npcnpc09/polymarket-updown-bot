import json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8") if l.strip()]
ent=[r for r in rows if r.get("kind")=="entry"]
dry=[r for r in ent if not r.get("live")]; live=[r for r in ent if r.get("live")]
withask=[r for r in ent if r.get("ask") is not None and "won" in r]
print("total lines %d"%len(rows))
print("entry records %d (DRY %d / live %d)"%(len(ent),len(dry),len(live)))
print("entries with real ask + outcome: %d"%len(withask))
if ent: print("fields:", {k:ent[-1].get(k) for k in ("ask","paid","slip_c","lead","lead2","cross_off","offset","band","won","btc_vol","coin")})
sl=[r.get("slip_c") for r in live if r.get("slip_c") is not None]
if sl: print("live slippage slip_c: mean %.2fc median %.2fc n=%d"%(sum(sl)/len(sl),sorted(sl)[len(sl)//2],len(sl)))
# also count the SPIKE skip records (faded/priced_in) that tracked outcome
spk=[r for r in rows if r.get("kind")=="spike"]
print("spike/skip records (tracked, not traded): %d"%len(spk))
