"""analyze_confirm_timing.py — should the early_taker confirm in FEWER than 15s?
Uses the traj instrumentation (lead+ask sampled each tick during the 15s confirm wait).
COST of waiting 15s = how much the ask drifts up cross->confirm (we pay more by waiting).
BENEFIT of waiting = the faded-spike losers the 15s confirm filters out (would-win if we'd entered early).
Net: does a shorter confirm (enter ~dt=5-8s) win on cheaper ask without letting in too many fades?"""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows = [json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()]
ent = [r for r in rows if r.get("kind") == "entry" and r.get("traj") and r.get("won") is not None]
fade = [r for r in rows if r.get("kind") == "spike" and r.get("reason") == "faded" and r.get("traj")]
print(f"entries with traj: {len(ent)}  | faded-spikes with traj: {len(fade)}")

def ask_at(traj, target):
    """ask at the first traj sample with dt>=target (None if none / no ask)."""
    for p in sorted(traj, key=lambda x: x["dt"]):
        if p["dt"] >= target and p.get("ask") is not None: return p["ask"], p["dt"]
    return None, None

# COST: ask drift cross(dt~0) -> confirm(dt~15) on CONFIRMED ENTRIES
print("\n=== COST of the 15s wait: ask drift cross->confirm (confirmed entries) ===")
drifts = []
for r in ent:
    a0, d0 = ask_at(r["traj"], 0)
    aF = r.get("ask")  # the ask at confirm/entry
    if a0 is not None and aF is not None:
        drifts.append((aF - a0, r["won"]))
if drifts:
    avg = sum(d for d, _ in drifts)/len(drifts)
    rose = sum(1 for d, _ in drifts if d > 0.005); fell = sum(1 for d, _ in drifts if d < -0.005)
    print(f"  n={len(drifts)} avg ask drift = {avg*100:+.2f}c  | rose>0.5c: {rose} | fell>0.5c: {fell} | flat: {len(drifts)-rose-fell}")
    print(f"  (positive = ask climbed during the wait -> entering earlier would've been cheaper)")

# SIMULATE shorter confirm: enter at dt>=T for T in {0,5,8,10,15}. Use ask_at(T) as paid; outcome=won (same window).
print("\n=== SIMULATE confirm length T: avg paid ask + win% (confirmed-entry set) ===")
for T in (0, 5, 8, 10, 15):
    paid = []; wins = 0
    for r in ent:
        a, d = ask_at(r["traj"], T) if T < 15 else (r.get("ask"), 15)
        if a is None: continue
        paid.append(a); wins += 1 if r["won"] else 0
    if paid:
        print(f"  T={T:2d}s: n={len(paid):3d} avgAsk={sum(paid)/len(paid):.3f} win%={wins/len(paid)*100:.1f} "
              f"EV/sh={ (wins/len(paid)) - sum(paid)/len(paid):+.3f}")

# BENEFIT of waiting: faded spikes (confirm rejected them). Would a SHORTER confirm have entered them?
print("\n=== BENEFIT of the 15s wait: faded-spikes it filtered (would-win if entered early) ===")
fw = [r for r in fade if r.get("would_win") is not None]
if fw:
    ww = sum(1 for r in fw if r["would_win"])
    print(f"  faded-spikes n={len(fw)} would-win%={ww/len(fw)*100:.1f}  (LOW = the 15s confirm correctly killed losers)")
    # of the fades, how many still had |lead|>=8 at dt=5/8 (a shorter confirm would have ENTERED them)?
    for T in (5, 8):
        still = 0; stillwin = 0
        for r in fw:
            ldT = None
            for p in sorted(r["traj"], key=lambda x: x["dt"]):
                if p["dt"] >= T: ldT = p.get("lead"); break
            if ldT is not None and abs(ldT) >= 8:
                still += 1; stillwin += 1 if r["would_win"] else 0
        if still:
            print(f"    confirm=T{T}s would ENTER {still} of these fades, win%={stillwin/still*100:.0f}% "
                  f"(these are the losers a shorter confirm lets back in)")
print("\nNET: shorter confirm helps ONLY if (cheaper ask gain) > (extra fade-losers let in). Compare the "
      "EV/sh across T above vs the fade win% a shorter T re-admits.")
