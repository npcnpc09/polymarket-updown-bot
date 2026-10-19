"""Multi-factor OOS backtest (pure python logistic regression). Build a continuous P(win) model from
factors (B, cushion, max_lead, reconstructed accel), TRAIN on early days, TEST on held-out later days.
Decision rule: bet only when P_pred > B + margin (model thinks market underprices us). Report OOS EV vs
baseline. The honest test of 'does a multi-factor judgment generalize' (vs single thresholds that fail OOS)."""
import json,math,httpx,datetime,statistics
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth") and "-5m-" in r.get("slug",""):
        ROWS.append(r)
# reconstruct accel from binance
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[int(r["slug"].split("-")[-1]) for r in ROWS]
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym,lo,hi):
    out={};cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[1])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={cn:fetch(SYM[cn],min(sts)-120,max(sts)+360) for cn in SYM}
data=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1]); o=BN[cn].get(st)
    if not o: continue
    def L(off):
        p=BN[cn].get(st+off); return math.log(p/o)*1e4 if p else None
    le=L(60); l120=L(120); l180=L(180)
    if None in (le,l120,l180): continue
    lead_entry=(l120+l180)/2; accel=(lead_entry-le)*(1 if lead_entry>=0 else -1)
    day=datetime.datetime.utcfromtimestamp(st).strftime("%m-%d")
    data.append({"day":day,"won":1 if r["won"] else 0,"B":r["B"],
                 "f":[r["B"],abs(r.get("lead",0)or 0),(r.get("max_lead")or 0),accel]})
FN=["B","cushion","maxLead","accel"]
train=[d for d in data if d["day"] in ("06-04","06-05")]
test =[d for d in data if d["day"] in ("06-06","06-07")]
print("train %d (06-04/05), test %d (06-06/07)\n"%(len(train),len(test)))
# standardize on train
mu=[statistics.mean(d["f"][i] for d in train) for i in range(len(FN))]
sd=[statistics.pstdev(d["f"][i] for d in train) or 1 for i in range(len(FN))]
def z(f): return [(f[i]-mu[i])/sd[i] for i in range(len(f))]
# logistic regression (gradient descent)
w=[0.0]*len(FN); b=0.0; lr=0.3
def sig(zz): return 1/(1+math.exp(-max(-30,min(30,zz))))
for ep in range(3000):
    gw=[0.0]*len(FN); gb=0.0
    for d in train:
        x=z(d["f"]); p=sig(sum(w[i]*x[i] for i in range(len(w)))+b); e=p-d["won"]
        for i in range(len(w)): gw[i]+=e*x[i]
        gb+=e
    n=len(train)
    for i in range(len(w)): w[i]-=lr*gw[i]/n
    b-=lr*gb/n
print("学到的权重(标准化后, 正=利好赢):")
for i in range(len(FN)): print("   %-8s %+.3f"%(FN[i],w[i]))
print("   bias    %+.3f\n"%b)
def predict(d):
    x=z(d["f"]); return sig(sum(w[i]*x[i] for i in range(len(w)))+b)
def ev_set(ds,lbl):
    if not ds: print("  %-30s n=0"%lbl); return
    win=sum(d["won"] for d in ds); ev=sum((5*(1-d["B"]) if d["won"] else -5*d["B"]) for d in ds)/len(ds)
    pnl=sum((5*(1-d["B"]) if d["won"] else -5*d["B"]) for d in ds)
    print("  %-30s n=%-4d 胜%2.0f%% EV%+.2f 总$%+.1f"%(lbl,len(ds),win/len(ds)*100,ev,pnl))
print("=== TEST(06-06/07) OOS 结果 ===")
ev_set(test,"基线: 全收")
for m in (0.0,0.03,0.05,0.08):
    sel=[d for d in test if predict(d)>d["B"]+m]
    ev_set(sel,"模型选 P_pred>B+%.2f"%m)
print("\n=== 对照: 同样规则在 TRAIN(in-sample) ===")
ev_set(train,"基线: 全收(train)")
for m in (0.0,0.05):
    sel=[d for d in train if predict(d)>d["B"]+m]
    ev_set(sel,"模型选 P_pred>B+%.2f (train)"%m)
