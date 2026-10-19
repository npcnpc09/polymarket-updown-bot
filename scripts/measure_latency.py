"""Measure REAL round-trip latency to Polymarket CLOB (network + server), to settle the speed question.
Distinguishes: (a) raw GET round-trip (network ping-ish), (b) the order-placement path is separate (signing +
POST), but GET round-trip is a good proxy for connection speed."""
import time,statistics,httpx
c=httpx.Client(timeout=15,headers={"User-Agent":"Mozilla/5.0"})
def timeit(url,params=None,n=10):
    ts=[]
    for _ in range(n):
        a=time.perf_counter()
        try: c.get(url,params=params,timeout=10)
        except: continue
        ts.append((time.perf_counter()-a)*1000)
    return ts
TOK="71321045679252212594626385532706912750332728571942532289631379312455583992563"  # a sample token
print("=== Polymarket CLOB /book 往返(ms) ===")
ts=timeit("https://clob.polymarket.com/book",{"token_id":TOK})
if ts: print("  n=%d  中位 %.0f ms  最小 %.0f  最大 %.0f  均 %.0f"%(len(ts),statistics.median(ts),min(ts),max(ts),sum(ts)/len(ts)))
print("=== Polymarket CLOB /ok (健康检查) 往返 ===")
ts=timeit("https://clob.polymarket.com/")
if ts: print("  n=%d  中位 %.0f ms  最小 %.0f"%(len(ts),statistics.median(ts),min(ts)))
print("=== 对比 binance ticker 往返 ===")
ts=timeit("https://api.binance.com/api/v3/ticker/price",{"symbol":"BTCUSDT"})
if ts: print("  n=%d  中位 %.0f ms  最小 %.0f"%(len(ts),statistics.median(ts),min(ts)))
print("\n注: 这是GET往返(网络+服务器). 下单路径另含: 本地签名(~ms) + POST往返 + CLOB撮合入账.")
