"""Continuous wallet snapshot logger. Every 5min append {ts, cash(collateral USDC), open_val(unsettled
position market value), total} to data/wallet_log.jsonl -> clean PnL time series, immune to the
redemption-lag confusion (cash alone dips while a 5m window is unsettled; total = cash+open_val is true)."""
import os,sys,time,json,httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,"scripts"))
for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
    if "=" in l and not l.startswith("#"):
        k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
pk,proxy=os.environ["POLY_PK"],os.environ["POLY_PROXY"]
from polymarket import SecureClient
OUT=os.path.join(ROOT,"data","wallet_log.jsonl")
def run():
    cli=SecureClient.create(private_key=pk,wallet=proxy)
    hc=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
    while True:
        rec={"ts":int(time.time())}
        try:
            rec["cash"]=round(float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6,2)
        except Exception as e:
            rec["cash"]=None; rec["err"]=repr(e)[:80]
        try:
            pos=hc.get("https://data-api.polymarket.com/positions",params={"user":proxy,"sizeThreshold":0.1}).json()
            rec["open_val"]=round(sum(float(p.get("currentValue") or 0) for p in pos),2) if isinstance(pos,list) else 0.0
        except Exception:
            rec["open_val"]=None
        if rec.get("cash") is not None:
            rec["total"]=round(rec["cash"]+(rec.get("open_val") or 0),2)
        with open(OUT,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        print("wallet $%.2f (cash %.2f + open %.2f)"%(rec.get("total") or 0,rec.get("cash") or 0,rec.get("open_val") or 0),flush=True)
        time.sleep(300)
if __name__=="__main__": run()
