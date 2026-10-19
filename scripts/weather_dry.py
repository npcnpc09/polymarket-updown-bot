"""Shanghai-weather DRY signal logger (Phase B, built 2026-07-03). NO ORDERS.
Every ~10 min: ZSPD METAR (current temp + running max, CST day) + met.no forecast max
+ all Polymarket shanghai strike books -> naive fair prices -> data/weather_dry.jsonl.
Purpose: calibration (model-vs-station bias, intraday warming curves) + later Phase C
benchmark vs 0x437f's actual trades. Resolution source = Wunderground ZSPD daily max (METAR-based).
"""
import json, time, os, sys, datetime, collections
import httpx

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","weather_dry.jsonl"); LOGF=os.path.join(ROOT,"data","weather_dry.log")
POLL=600  # 10 min
CST=datetime.timezone(datetime.timedelta(hours=8))

def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%m-%d %H:%M:%S')}] {m}"
    print(line,flush=True)
    try: open(LOGF,"a",encoding="utf-8").write(line+"\n")
    except: pass

C=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})

def metar_today():
    """(cur_temp, running_max, n_reports) for the current CST calendar day at ZSPD."""
    try:
        arr=C.get("https://aviationweather.gov/api/data/metar?ids=ZSPD&format=json&hours=30").json()
    except Exception as e:
        log(f"metar err {str(e)[:60]}"); return None,None,0
    today=datetime.datetime.now(CST).strftime("%Y-%m-%d")
    temps=[]; cur=None
    for r in sorted(arr,key=lambda x:str(x.get("reportTime"))):
        rt=str(r.get("reportTime",""))
        try:
            dt=datetime.datetime.fromisoformat(rt.replace("Z","+00:00"))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=datetime.timezone.utc)
        except Exception: continue
        if dt.astimezone(CST).strftime("%Y-%m-%d")!=today: continue
        t=r.get("temp")
        if t is not None: temps.append(float(t)); cur=float(t)
    return cur,(max(temps) if temps else None),len(temps)

_fc={"t":0,"v":{}}
def forecast_max():
    """met.no daily max forecast keyed by CST date (station-uncorrected; bias calibrated later)."""
    if time.time()-_fc["t"]<3600 and _fc["v"]: return _fc["v"]
    try:
        d=C.get("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=31.15&lon=121.80",
                headers={"User-Agent":"weather-research/1.0"}).json()
        days=collections.defaultdict(list)
        for row in d["properties"]["timeseries"]:
            t=row["time"]  # UTC ISO
            dt=datetime.datetime.fromisoformat(t.replace("Z","+00:00")).astimezone(CST)
            v=row["data"]["instant"]["details"].get("air_temperature")
            if v is not None: days[dt.strftime("%Y-%m-%d")].append(v)
        _fc["v"]={k:max(v) for k,v in days.items()}; _fc["t"]=time.time()
    except Exception as e: log(f"met.no err {str(e)[:60]}")
    return _fc["v"]

def strikes_for(date_slug):
    """[(strike_int, token_yes, bid, ask, bid_sz, ask_sz, mkt_price)] for e.g. 'july-3'."""
    out=[]
    try:
        ev=C.get(f"https://gamma-api.polymarket.com/events?slug=highest-temperature-in-shanghai-on-{date_slug}").json()
        if not ev: return out
        for mk in ev[0].get("markets",[]):
            slug=str(mk.get("slug",""))
            try: strike=int(slug.rsplit("-",1)[1].replace("c",""))
            except Exception: continue
            toks=json.loads(mk.get("clobTokenIds") or "[]")
            if not toks: continue
            tok=toks[0]  # Yes
            bb=ba=None; bsz=asz=0.0
            try:
                b=C.get(f"https://clob.polymarket.com/book?token_id={tok}").json()
                bids=sorted(((float(x["price"]),float(x["size"])) for x in b.get("bids",[]) if float(x["size"])>0))
                asks=sorted(((float(x["price"]),float(x["size"])) for x in b.get("asks",[]) if float(x["size"])>0))
                if bids: bb,bsz=bids[-1]
                if asks: ba,asz=asks[0]
            except Exception: pass
            try: mp=float(json.loads(mk.get("outcomePrices") or '["0"]')[0])
            except Exception: mp=None
            out.append(dict(strike=strike,token=str(tok),bid=bb,ask=ba,bid_sz=bsz,ask_sz=asz,mkt=mp))
    except Exception as e: log(f"gamma err {date_slug} {str(e)[:60]}")
    return sorted(out,key=lambda x:x["strike"])

def naive_fair(strike, running_max, hour_cst, fc_max):
    """v0 heuristic P(final daily max == strike). Intraday: anchored on running max + typical
    remaining warming (peak ~14-15 CST). Pre-day/morning: normal around forecast, sigma 1.5C.
    TO BE CALIBRATED with logged data — v0 is for logging comparison only."""
    import math
    def normpdf_int(k,mu,sig):
        # P(max rounds to k) ~ N(mu,sig) mass on [k-0.5,k+0.5)
        from math import erf,sqrt
        cdf=lambda x:0.5*(1+erf((x-mu)/(sig*sqrt(2))))
        return max(0.0,cdf(k+0.5)-cdf(k-0.5))
    if running_max is not None and hour_cst>=10:
        # remaining warming above running max shrinks with hour: rough v0 curve
        rem={10:2.5,11:2.0,12:1.5,13:1.0,14:0.6,15:0.3,16:0.15,17:0.05}.get(min(17,max(10,hour_cst)),0.0)
        mu=running_max+rem*0.6; sig=max(0.4,rem*0.8)
        p=normpdf_int(strike,mu,sig)
        if strike<int(running_max): p=0.0           # already exceeded -> impossible
        if strike==int(round(running_max)) and hour_cst>=16: p=max(p,0.85)
        return round(p,3)
    if fc_max is not None:
        return round(normpdf_int(strike,fc_max+1.0,1.5),3)   # +1.0 = provisional grid->station bias (calibrate!)
    return None

def main():
    log("weather_dry START (10min poll, NO orders) station=ZSPD src=METAR+met.no")
    while True:
        try:
            now=datetime.datetime.now(CST)
            cur,rmax,nrep=metar_today()
            fc=forecast_max()
            today=now.strftime("%Y-%m-%d"); tom=(now+datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            mon={1:"january",2:"february",3:"march",4:"april",5:"may",6:"june",7:"july",8:"august",9:"september",10:"october",11:"november",12:"december"}
            for dlab,dt_ in [("today",now),("tomorrow",now+datetime.timedelta(days=1))]:
                dslug=f"{mon[dt_.month]}-{dt_.day}-{dt_.year}"
                sts=strikes_for(dslug)
                if not sts: continue
                d=dt_.strftime("%Y-%m-%d")
                fcm=fc.get(d)
                row={"ts":int(time.time()),"day":d,"which":dlab,"cur":cur,"run_max":rmax if dlab=="today" else None,
                     "hour_cst":now.hour,"fc_max":fcm,"strikes":[]}
                for s in sts:
                    fair=naive_fair(s["strike"], rmax if dlab=="today" else None, now.hour, fcm)
                    row["strikes"].append({**s,"fair":fair})
                open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                # log interesting mispricings (fair vs ask)
                for s in row["strikes"]:
                    if s["fair"] and s["ask"] and s["fair"]-s["ask"]>0.10 and s["ask"]<0.85:
                        log(f"[SIGNAL?] {d} {s['strike']}C fair={s['fair']} ask={s['ask']} (+{s['fair']-s['ask']:.2f}) askSz={s['ask_sz']:.0f}")
            log(f"tick: cur={cur} runMax={rmax} fcToday={fc.get(today)} fcTom={fc.get(tom)}")
        except Exception as e:
            log(f"loop err {str(e)[:100]}")
        time.sleep(POLL)

if __name__=="__main__":
    main()
