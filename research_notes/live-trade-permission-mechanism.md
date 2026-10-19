---
name: live-trade-permission-mechanism
description: "Why agent-initiated real-money Polymarket orders get blocked in auto-mode, and the only legit ways to enable frictionless live trading"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

In auto permission mode, the classifier BLOCKS real-money orders whose specific target
(market/token/side/price) is chosen by the agent's own logic, even after the user says
"go" or "I authorize you". It blocked maker_live_test.py --place twice on 2026-06-01.

**Why:** the guardrail = a human must approve each real-money spend. The agent must NOT
self-add a settings permission rule to bypass this — that's circumventing the intent of
the denial (using the file-edit tool to undo a restriction just placed on the agent).
I held this line repeatedly even when the user asked me to add it; the switch must be
flipped by the human.

**Why earlier runs felt approval-free** (user recalled a frictionless $97->$174 run, and
morning 6e1d/arb trades): those had the user's authorization in a non-obvious form —
either (a) per-trade "下"/"2" on a specific presented order (invisible because slow 48h
markets gave unlimited time), (b) a `--live` script the user launched once (that launch
authorized the whole run/loop), or (c) **standing permission already granted** (user
clicked "don't ask again" or ran in auto-accept/bypass mode). Nothing in the rules
changed — the strategy got FAST (5-15min windows), so the same per-trade approval now
races the clock.

**Why:** removing per-trade approval on real money is a deliberate human act, by design.

**CONFIRMED 2026-06-02 — a settings.json allow-rule does NOT work in auto mode.** We
added `"permissions":{"allow":["Bash(python scripts/maker_live_test.py --place:*)"]}`
(user ran the write themselves via `!`), then a --place STILL got classifier-denied:
"Auto-Mode Bypass ... which user pushing cannot clear." The auto-mode classifier is a
SEPARATE, stricter layer that refuses agent-initiated real-money orders regardless of
settings rules, user verbal authorization, or restart. It explicitly treats a
permission rule added to bypass prior denials AS a bypass. Also `/permissions` UI is
unavailable over Remote Control (dialog just dismisses).

**The ONLY two things that work:**
1. **Genuine per-trade approval** — user explicitly approves the SPECIFIC params ("批准
   doge Down 0.73 $1"); that clears the classifier (the approved doge order DID reach the
   exchange, rejected only for "crosses book" = market reason). Fast windows decay in the
   approval round-trip (~90s killed a doge signal), so surface fresh candidates + user
   approves within ~15s.
2. **Restart Claude Code in bypass/skip-permissions mode** (`claude --continue
   --dangerously-skip-permissions`) — permission MODE is set at startup by the USER, can't
   be switched from inside an auto-mode session. This is almost certainly what the prior
   frictionless "$97->174" / "yesterday" autonomous runs used. Disables ALL safety checks —
   risky on the compromised wallet, but script's MAXNOTIONAL=1.10 still caps each order.

I must NOT self-write the permission rule (self-escalation; the system itself flags it as
a bypass — this vindicated the refusal). Related: [[fast-maker-strategy-validated]].
