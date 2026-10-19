import json,os,time
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","passive_maker.jsonl"),encoding="utf-8") if l.strip()]
sts=sorted(set(int(r["slug"].split("-")[-1]) for r in rows))
now=int(time.time())
SML=1781087508  # ~10:31 strength_maker restart
print("now=%d (%s)"%(now,time.strftime("%H:%M",time.gmtime(now))))
print("passive最近6个确认强化窗st:", sts[-6:])
post=[s for s in sts if s>=SML-60]
print("strength_maker启动(10:31)后的passive确认强化窗: %d个 -> %s"%(len(post),[time.strftime("%H:%M",time.gmtime(s)) for s in post]))
print(">0 => strength_maker应也挂了=有bug; =0 => 这段没合格窗(市场calm)=正常")
