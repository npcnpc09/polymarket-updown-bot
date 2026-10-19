"""One-off wallet read: CLOB collateral (available USDC) + open-position value (data-api) = true total,
to avoid redemption-lag confusion (locked collateral in unsettled 5m windows depresses the cash number)."""
import os,sys,httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,"scripts"))
for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
    if "=" in l and not l.startswith("#"):
        k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
pk,proxy=os.environ["POLY_PK"],os.environ["POLY_PROXY"]
from polymarket import SecureClient
cli=SecureClient.create(private_key=pk,wallet=proxy)
cash=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
print("钱包地址: %s...%s"%(proxy[:6],proxy[-4:]))
print("可用USDC(collateral): $%.2f"%cash)
# open positions value
try:
    c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
    pos=c.get("https://data-api.polymarket.com/positions",params={"user":proxy,"sizeThreshold":0.1}).json()
    if isinstance(pos,list):
        openv=sum(float(p.get("currentValue") or 0) for p in pos)
        n=len([p for p in pos if float(p.get("size") or 0)>0])
        print("未结持仓: %d个, 市值合计 $%.2f"%(n,openv))
        print("== 总计(现金+持仓): $%.2f =="%(cash+openv))
        for p in pos[:8]:
            if float(p.get("size") or 0)>0:
                print("  %s %s sz=%.1f val=$%.2f"%(p.get("title","")[:28],p.get("outcome",""),float(p.get("size") or 0),float(p.get("currentValue") or 0)))
except Exception as e:
    print("持仓查询失败:",repr(e)[:100])
