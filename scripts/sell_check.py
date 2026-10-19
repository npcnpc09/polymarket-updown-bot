"""READ-ONLY: check whether the wallet already has the approvals needed to SELL
(conditional-token ERC1155 approval to the exchange). No orders, no transactions."""
import os,sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ["POLY_PK"],os.environ["POLY_PROXY"]
pk,proxy=load_env()
from polymarket import SecureClient
cli=SecureClient.create(private_key=pk,wallet=proxy)
print("wallet:",proxy)
# collateral (USDC) baseline - known working (we buy fine)
try:
    col=cli.get_balance_allowance(asset_type="COLLATERAL")
    print("COLLATERAL balance:",getattr(col,'balance',None),"allowance-ok (we already buy)")
except Exception as e: print("collateral check err:",str(e)[:120])
# current positions (should be ~0 open now)
try:
    pos=cli.list_positions()
    n=0
    for p in (pos or []):
        n+=1
        if n<=5: print("  position:",getattr(p,'title',getattr(p,'asset',p)))
    print("positions:",n)
except Exception as e: print("positions err:",str(e)[:120])
# gasless/relayer readiness (approvals are executed via relayer if ready)
try: print("is_gasless_ready:",cli.is_gasless_ready())
except Exception as e: print("gasless check err:",str(e)[:120])
cli.close()
