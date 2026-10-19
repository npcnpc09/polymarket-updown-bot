"""Summarize early_taker_probe.jsonl: real achievable taker price (paid) vs win% vs ROI, by price band and
entry offset, against the real_taker_backtest targets. Answers: when lead crosses 8 early, do we actually
get <0.85 fills, and do those fills win at the backtested rate? Plus how many got SKIPped as priced-in."""
import json,os,statistics
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F=os.path.join(ROOT,"data","early_taker_probe.jsonl")
import sys
allrows=[json.loads(l) for l in open(F,encoding="utf-8")] if os.path.exists(F) else []
LIVEONLY=("--all" not in sys.argv)
rows=[r for r in allrows if r.get("live")] if LIVEONLY else allrows
ndry=len([r for r in allrows if not r.get("live") and "won" in r])
print("[%s] (DRY另有%d笔成交, 用 --all 看全部)"%("仅LIVE真盘" if LIVEONLY else "全部(live+DRY)",ndry))
skips=[r for r in rows if r.get("skip")=="priced_in"]
corr=[r for r in rows if r.get("skip")=="correlated"]
ent=[r for r in rows if "won" in r and r.get("won") is not None]
print("记录 %d | 早入成交 %d | SKIP(priced-in>=0.85) %d | CORR-SKIP(避同窗双开) %d"%(len(rows),len(ent),len(skips),len(corr)))
# === A/B: confirmed entries (cross+15s held) vs skipped SPIKES (cross faded) — forward-validate the backtest ===
conf=[r for r in rows if r.get("kind")=="entry" and r.get("won") is not None]
spk_faded=[r for r in rows if r.get("kind")=="spike" and r.get("reason")=="faded" and r.get("would_win") is not None]
spk_pi=[r for r in rows if r.get("kind")=="spike" and r.get("reason")=="priced_in" and r.get("would_win") is not None]
if conf or spk_faded:
    cw=sum(1 for r in conf if r["won"]); fw=sum(1 for r in spk_faded if r["would_win"])
    print("\n*** A/B 早得更准 (cross+%ds确认) ***"%15)
    print("  确认后真进 n=%-3d 胜%s%%"%(len(conf),("%.0f"%(cw/len(conf)*100)) if conf else "-"))
    print("  跳过的faded-spike n=%-3d 当时若进会赢%s%% %s"%(len(spk_faded),("%.0f"%(fw/len(spk_faded)*100)) if spk_faded else "-",
          "← spike明显<确认 = 过滤有效✓" if (conf and spk_faded and cw/len(conf)-fw/len(spk_faded)>0.15) else "(样本still小)"))
    if spk_pi: print("  确认了但priced-in跳过 n=%d (若进会赢%.0f%%)"%(len(spk_pi),sum(1 for r in spk_pi if r["would_win"])/len(spk_pi)*100))
    print("  → 回测预期: 确认~85%% / faded-spike~48%%")
if skips:
    print("  → 抓取率: %.0f%% 的(非相关)强lead触发拿到<0.85便宜价 (其余被晚入priced-in)"%(len(ent)/(len(ent)+len(skips))*100))
if not ent:
    print("\n还没有已结算的成交行 — 让 probe 继续跑(每个5m窗口~5分钟结算).")
    raise SystemExit
def stat(rs,lbl,tgt=""):
    if not rs: return
    wr=sum(1 for t in rs if t["won"])/len(rs); ap=statistics.mean(t["paid"] for t in rs)
    pf=sum(t["pnl"] for t in rs); sp=sum(t["paid"]*5 for t in rs)
    print("  %-12s n=%-3d 胜%2.0f%% 真付价%.3f 错价%+.0fpp ROI%+5.1f%% 累计$%+.1f %s"%(lbl,len(rs),wr*100,ap,(wr-ap)*100,pf/sp*100 if sp else 0,pf,tgt))
live=[r for r in ent if r.get("live")]; dry=[r for r in ent if not r.get("live")]
slipped=[r for r in ent if r.get("slip_c") is not None]
if slipped:
    import statistics as _s
    print("\n=== 真实成交滑点 (真付价 - 读到的ask) [仅有记录的行] ===")
    print("  均滑点 %+.2fc | 中位 %+.1fc | n=%d  (我们挂ask+1c保成交, 所以~+1c是正常缓冲, 越接近0越好)"%(_s.mean(r["slip_c"] for r in slipped),_s.median(r["slip_c"] for r in slipped),len(slipped)))
if live: print("\n  [LIVE真盘 %d笔 / DRY %d笔 — 下面汇总含全部, 需要分开说就喊我]"%(len(live),len(dry)))
print("\n=== 真实早入成交: 总览 ===")
stat(ent,"全部")
print("\n=== 按价格档 (对照回测目标) ===")
stat([r for r in ent if r["paid"]<0.5],"<0.5","[回测+42%]")
stat([r for r in ent if 0.5<=r["paid"]<0.65],"0.5-0.65","[回测+14.5%]")
stat([r for r in ent if 0.65<=r["paid"]<0.75],"0.65-0.75","[回测+13.6%]")
stat([r for r in ent if 0.75<=r["paid"]<0.85],"0.75-0.85","[回测+15.8%]")
print("\n=== 按入场时点 ===")
stat([r for r in ent if r["offset"]<60],"<60s","[回测+24.5%]")
stat([r for r in ent if 60<=r["offset"]<150],"60-150s","[回测+8.3%]")
stat([r for r in ent if r["offset"]>=150],">=150s","[回测+2.9%]")
print("\n=== binance vs coinbase (目标#2): 入场时方向是否一致 × 真实胜负 ===")
hascb=[r for r in ent if r.get("cb_lead") is not None]
if not hascb:
    print("  (还没有带 coinbase 并行记录的成交 — 改进版重启后才开始记)")
else:
    agree=[r for r in hascb if r.get("cb_agree")]; disag=[r for r in hascb if not r.get("cb_agree")]
    stat(agree,"cb也指同侧")
    stat(disag,"cb反对/中性","← 这组若仍高胜=binance抓到了cb会错过/押反的赢家")
    if disag:
        print("  → 分歧%d笔, 其中binance押中%d (%.0f%%): binance在分歧时%s"%(len(disag),sum(1 for r in disag if r["won"]),sum(1 for r in disag if r["won"])/len(disag)*100,"更准✓" if sum(1 for r in disag if r["won"])/len(disag)>0.5 else "未必更准"))
print("\n=== 按币 / vol ===")
for coin in ("btc","eth"): stat([r for r in ent if r["coin"]==coin],coin)
hv=[r for r in ent if (r.get("btc_vol") or 0)>=5]; lv=[r for r in ent if (r.get("btc_vol") or 0)<5]
stat(lv,"vol<5"); stat(hv,"vol>=5")
