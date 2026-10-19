"""SMOOTHED lead (eebde-style continuous read) vs MIN3 SNAPSHOT. Use 1-min closes at 60/120/180s.
snap = lead at 180s (~our entry); smooth = avg lead over 60/120/180s. Bet side of each (|sig|>=8),
resolve binance. Who wins on disagreements / on strong (overextended) leads?"""
import json,httpx,math,datetime,statistics
def kl(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))  # minute_start -> (open, close)
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
t0=int(datetime.datetime(2026,6,4,12,0).timestamp()); t1=int(datetime.datetime(2026,6,6,14,0).timestamp())
rows=[]
for coin,sym in (("btc","BTCUSDT"),("eth","ETHUSDT")):
    d=kl(sym,t0-120,t1+360)
    st=(t0//300)*300
    while st<t1-300:
        m0=d.get(st); m60=d.get(st+60); m120=d.get(st+120); mfin=d.get(st+240)
        if m0 and m60 and m120 and mfin:
            op=m0[0]
            l60=math.log(m0[1]/op)*1e4; l120=math.log(m60[1]/op)*1e4; l180=math.log(m120[1]/op)*1e4
            snap=l180; smooth=statistics.mean([l60,l120,l180])
            up=mfin[1]>=op
            rows.append({"snap":snap,"smooth":smooth,"up":up})
        st+=300
print("窗口:",len(rows),"\n")
def wr(rs,key):
    e=[r for r in rs if abs(r[key])>=8]
    if not e: return 0,0
    return len(e),sum(1 for r in e if (r[key]>=0)==r["up"])/len(e)*100
n1,w1=wr(rows,"snap"); n2,w2=wr(rows,"smooth")
print("min3单点领先 (我们现在): n=%d 胜%.1f%%"%(n1,w1))
print("平滑累积领先 (eebde式):  n=%d 胜%.1f%%"%(n2,w2))
dis=[r for r in rows if abs(r["snap"])>=8 and abs(r["smooth"])>=8 and (r["snap"]>=0)!=(r["smooth"]>=0)]
if dis:
    sw=sum(1 for r in dis if (r["snap"]>=0)==r["up"])
    print("\n分歧窗口(单点vs平滑相反): %d个"%len(dis))
    print("  单点(我们)对: %d (%.0f%%) | 平滑对: %d (%.0f%%)"%(sw,sw/len(dis)*100,len(dis)-sw,(len(dis)-sw)/len(dis)*100))
strong=[r for r in rows if abs(r["snap"])>=30]
if strong:
    sw=sum(1 for r in strong if (r["snap"]>=0)==r["up"])/len(strong)*100
    smw=sum(1 for r in strong if (r["smooth"]>=0)==r["up"])/len(strong)*100
    print("\n过强领先(|snap|>=30,易反转) %d个: 单点胜%.0f%% 平滑胜%.0f%%"%(len(strong),sw,smw))
