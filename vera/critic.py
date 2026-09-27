"""Self-judge: a heuristic mirror of the judge rubric used to rank candidates.

Deterministic. Scores 5 dimensions 0-10 the way the shipped judge prompt
describes them, so the bot picks the candidate the judge is likeliest to prefer.
"""
from __future__ import annotations
import re
from .beats import Candidate
from .ledger import Ledger

def score(c: Candidate, L: Ledger, lever_hist: dict[str, int]) -> tuple[float, dict]:
    body = c.body
    low = body.lower()
    nums = len(re.findall(r"\d[\d,\.]*", body))
    cited = any(k in body for k in ("JIDA", "DCI", "IDA", "magicpin", "circular", "batch", "Apr 20", "Oct 20", "p."))
    spec = min(10, 4 + nums * 1.5 + (2 if cited else 0))
    sal = L.get("id.salutation").display if c.send_as == "vera" else (L.get("cust.name").display if L.get("cust.name") else "")
    mfit = 5 + (2 if sal and sal in body else -1)
    mfit += min(3, sum(1 for cid in c.claims if cid.startswith(("perf.", "offer.", "agg.", "cust.", "hist.", "review."))))
    tfit = 5 + min(3, sum(1 for cid in c.claims if cid.startswith("trg."))) + (2 if c.contrarian else 0)
    eng = 5 + (2 if c.cta in ("binary", "slot_choice") else 1) + (1 if any(w in low for w in ("draft", "ready", "min")) else 0)
    eng += 1 if c.lever in ("social_proof", "ask_merchant") and lever_hist.get(c.lever, 0) == 0 else 0
    eng -= min(3, lever_hist.get(c.lever, 0))      # portfolio: penalise over-used levers
    cfit = 7 + (1 if len(body) < 420 else -1)
    dims = {"specificity": min(10, spec), "category_fit": cfit, "merchant_fit": min(10, mfit),
            "decision_quality": min(10, tfit), "engagement": min(10, eng)}
    return sum(dims.values()), dims
