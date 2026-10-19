"""breaker_state.py — current combined-stream regime state: is anything in breaker right now?"""
import importlib.util, sys
sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("etp", "scripts/early_taker_probe.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
l, n = m.combined_roll10()
print(f"COMBINED roll10 = {l} losses / {n} fills  (armed={n>=10})")
taker = "PAUSED (hot)" if (n >= 10 and l >= m.BREAKER_K) else "ACTIVE (normal)"
print(f"  taker breaker  K={m.BREAKER_K}: {taker}")
if n >= 10 and l >= 2:   cell = "BREAKER -> cell downsized to 5sh"
elif n >= 10 and l == 0: cell = "DEEP-CALM -> cell upsized to 28sh"
else:                    cell = "NORMAL -> cell 20sh"
print(f"  zmaker cell    K=2: {cell}")
