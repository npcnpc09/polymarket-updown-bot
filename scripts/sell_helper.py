"""SELL capability for the copy-trade executor (built 2026-07-02).
Polymarket CLOB selling needs: (1) one-time ERC1155 approval of conditional tokens to the
exchange (gasless via relayer — is_gasless_ready=True), (2) place_limit_order(side="SELL").

Usage:
  python scripts/sell_helper.py --check                     # read-only: approvals + sellable positions
  python scripts/sell_helper.py --approve                   # one-time: set trading approvals (incl. ERC1155)
  python scripts/sell_helper.py --sell TOKEN_ID PRICE SIZE  # place a SELL limit order (real money!)
Also importable: ensure_approvals(cli), sell(cli, token_id, price, size).
"""
import os, sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ["POLY_PK"],os.environ["POLY_PROXY"]

def client():
    pk,proxy=load_env()
    from polymarket import SecureClient
    return SecureClient.create(private_key=pk,wallet=proxy)

def ensure_approvals(cli):
    """Idempotent: sets all trading approvals (USDC + conditional ERC1155) via relayer."""
    try:
        r=cli.setup_trading_approvals()
        print("setup_trading_approvals ->",r)
        return True
    except Exception as e:
        print("setup_trading_approvals err:",str(e)[:200])
        try:
            r2=cli.approve_erc1155_for_all()
            print("approve_erc1155_for_all ->",r2)
            return True
        except Exception as e2:
            print("approve_erc1155_for_all err:",str(e2)[:200]); return False

def sell(cli, token_id, price, size, post_only=False):
    """Place a SELL limit order. Returns (order_id, status/err)."""
    r=cli.place_limit_order(token_id=str(token_id),price=price,size=size,side="SELL",post_only=post_only)
    oid=getattr(r,"order_id",None) or getattr(r,"id",None)
    status=getattr(r,"status",None) or getattr(r,"error_msg",None)
    return oid,status

def best_bid(cli, token_id):
    """Top of the bid book (price, size) or (None, 0)."""
    try:
        b=cli.get_order_book(token_id=str(token_id))
        bids=sorted(((float(x.price),float(x.size)) for x in (getattr(b,'bids',None) or [])),key=lambda z:z[0])
        return (bids[-1][0],bids[-1][1]) if bids else (None,0.0)
    except Exception:
        return None,0.0

def sell_with_escalation(cli, token_id, size, floor_price, rounds=4, wait_s=8, log=print):
    """SELL-FAILURE-PROOF exit (2026-07-02, user: 防止卖出失败的手段).
    Strategy: hit the current best bid (immediate taker fill if depth exists). If unfilled after
    wait_s, cancel and re-hit the NEW bid — up to `rounds` times, chasing the market down but
    NEVER below floor_price. Partial fills tracked. If everything fails -> HOLD TO SETTLE
    (bounded loss = position size; same fallback as all our engines).
    Returns dict(sold, remaining, avg_px, gave_up_reason)."""
    import time as _t
    remaining=float(size); sold=0.0; proceeds=0.0; reason=None
    for rd in range(1,rounds+1):
        bb,bbsz=best_bid(cli,token_id)
        if bb is None: reason="no_bids"; break
        if bb<floor_price: reason=f"bid {bb}<floor {floor_price}"; break
        px=round(bb,2)
        try:
            oid,status=sell(cli,token_id,px,remaining)
        except Exception as e:
            log(f"  sell exc r{rd}: {str(e)[:80]}"); _t.sleep(2); continue
        if not oid:
            log(f"  sell REJECTED r{rd}: {status}"); reason=f"rejected:{status}"; break
        log(f"  SELL r{rd}: {remaining}sh @ {px} oid={str(oid)[:14]} (bid_sz {bbsz:.0f})")
        _t.sleep(wait_s)
        matched=0.0
        try:
            od=cli.get_order(order_id=oid); matched=float(getattr(od,"size_matched",0) or 0)
        except Exception as e: log(f"  poll exc: {str(e)[:60]}")
        if matched>0:
            sold+=matched; proceeds+=matched*px; remaining=round(remaining-matched,4)
            log(f"  filled {matched}sh @ {px} (total sold {sold}, remaining {remaining})")
        if remaining<=1e-6: break
        try: cli.cancel_order(order_id=oid)
        except Exception: pass
    if remaining>1e-6 and reason is None: reason="rounds_exhausted"
    if remaining>1e-6:
        log(f"  SELL INCOMPLETE: {remaining}sh unsold ({reason}) -> HOLD TO SETTLE (bounded)")
    return {"sold":sold,"remaining":remaining,"avg_px":(proceeds/sold if sold>0 else None),"gave_up_reason":reason}

def main():
    if len(sys.argv)<2 or sys.argv[1] not in ("--check","--approve","--sell"):
        print(__doc__); return
    cli=client()
    try:
        if sys.argv[1]=="--check":
            col=cli.get_balance_allowance(asset_type="COLLATERAL")
            print("COLLATERAL balance:",getattr(col,'balance',None))
            print("gasless_ready:",cli.is_gasless_ready())
            try:
                pos=cli.list_positions()
                sellable=[p for p in pos if float(getattr(p,'cur_price',0) or 0)>0.01 and float(getattr(p,'size',0) or 0)>0]
                print(f"sellable positions (cur_price>0.01): {len(sellable)}")
                for p in sellable[:10]:
                    print(f"  {p.title} | {p.outcome} {p.size}sh @cur {p.cur_price} (token {str(p.token_id)[:16]}..)")
            except Exception as e: print("positions err:",str(e)[:150])
        elif sys.argv[1]=="--approve":
            ensure_approvals(cli)
        elif sys.argv[1]=="--sell":
            tok,px,sz=sys.argv[2],float(sys.argv[3]),float(sys.argv[4])
            oid,status=sell(cli,tok,px,sz)
            print(f"SELL placed: oid={oid} status={status}")
    finally:
        try: cli.close()
        except: pass

if __name__=="__main__":
    main()
