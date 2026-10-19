"""How many REAL settled bets to VALIDATE the cheap-underdog edge? Power analysis: bets at the underdog
price band (0.2-0.4), win with prob = price + TRUE_EDGE (edge=0 => breakeven). For several true edges,
simulate N bets x K paths; report median ROI, p10 (bad luck), and P(final ROI>0). Find N where a real edge
RELIABLY shows (p10>0) AND separates from edge=0. Converts to capital via bet size + variance buffer."""
import random,statistics
random.seed(0)
PRICES=[0.22,0.25,0.28,0.31,0.34,0.37]  # the 0.2-0.4 underdog band
def sim(edge,N,K=4000):
    rois=[]
    for _ in range(K):
        cost=0.0; pnl=0.0
        for _ in range(N):
            p=PRICES[random.randrange(len(PRICES))]
            cost+=p
            win = random.random() < min(0.95,p+edge)   # true win prob = price + edge
            pnl+= (1-p) if win else -p
        rois.append(pnl/cost*100 if cost else 0)
    rois.sort()
    return statistics.median(rois), rois[int(K*.1)], sum(1 for r in rois if r>0)/K*100
print("=== 验证功效: 多少笔能让\"真edge\"可靠显现(p10>0) + 和零edge分开 ===\n")
print("真实edge = 胜率比价格高的pp (edge=0 => 该band breakeven)")
print("  %-8s | %s"%("N笔",  "  ".join("edge+%dpp:中位ROI/p10/盈利概率"%e for e in (0,5,10))))
for N in (100,250,500,1000,2000):
    cells=[]
    for e in (0.0,0.05,0.10):
        m,p10,pw=sim(e,N)
        cells.append("%+5.0f%%/%+5.0f%%/%2.0f%%"%(m,p10,pw))
    print("  %-8d | %s"%(N,"   ".join(cells)))
print("\n判据: 找最小N使 edge+5pp 的 p10>0(差运气也赚) 且 盈利概率>~90%, 同时 edge=0 仍≈50%(能分开)")
print("\n=== 换算成资金 (便宜side高方差, 需变现缓冲) ===")
print("每注$2-3, 5m窗recycle -> 所需本金 ≈ 并发暴露 + ~25x单注的连败缓冲")
for bet in (2,3,5):
    print("  每注$%d: 变现缓冲~$%d, 跑N笔时间(btc/eth~50-100笔/天)=N/75天"%(bet,bet*25))
