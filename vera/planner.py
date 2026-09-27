"""Portfolio planner: decides whether to send, which candidate, and explains it."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from . import beats, critic, verify
from .ledger import mine, Ledger

@dataclass
class SendPlan:
    candidate: beats.Candidate
    ledger: Ledger
    verdict: verify.Verdict
    score: float
    dims: dict
    fresh_used: list[str]
    alternatives: int

    def explain(self, trigger: dict) -> str:
        c = self.candidate
        fresh = f"; fresh claims: {', '.join(self.fresh_used)}" if self.fresh_used else ""
        contra = " (contrarian: recommends against the obvious action)" if c.contrarian else ""
        return (f"Trigger {trigger.get('kind')} (urgency {trigger.get('urgency', '?')}). Recommendation: {c.recommendation}{contra}. "
                f"Lever: {c.lever}; CTA: {c.cta}. Claims used: {', '.join(c.claims)}{fresh}. "
                f"Chosen over {self.alternatives} alternative(s) by self-judge {self.score:.0f}/50. {self.verdict.report()}")

def plan(category: dict, merchant: dict, trigger: dict, customer: Optional[dict],
         lever_hist: dict[str, int], prior_bodies: list[str], fresh_scopes: set[str] = frozenset(),
         first_touch: bool = True) -> Optional[SendPlan]:
    customer_facing = trigger.get("scope") == "customer"
    if customer_facing and not customer:
        return None
    trigger = normalise_placeholder(trigger, merchant, customer)
    L = mine(category, merchant, trigger, customer, fresh_scopes)
    cands = beats.candidates(L, trigger.get("kind", ""), customer_facing)
    taboo = (category.get("voice") or {}).get("vocab_taboo", [])
    ranked = []
    for c in cands:
        v = verify.check(c.body, L, taboo, prior_bodies, first_touch)
        if not v.ok:
            continue
        s, dims = critic.score(c, L, lever_hist)
        # freshness bonus: candidates that use claims from newly pushed context win ties
        fresh = [cid for cid in c.claims if L.get(cid) and L.get(cid).fresh]
        s += 0.5 * len(fresh)
        ranked.append((s, dims, c, v, fresh))
    if not ranked:
        return None
    ranked.sort(key=lambda r: (-r[0], r[2].lever))       # deterministic tie-break
    s, dims, c, v, fresh = ranked[0]
    return SendPlan(c, L, v, s, dims, fresh, len(ranked) - 1)

def urgency_gate(trigger: dict, now_iso: str, open_conv_for_merchant: bool) -> bool:
    """Restraint: expired triggers never send; an open *pitch* only yields to urgency >= 3."""
    if trigger.get("expires_at") and now_iso and trigger["expires_at"] < now_iso:
        return False
    if open_conv_for_merchant and int(trigger.get("urgency", 3)) < 3:
        return False
    return True

def normalise_placeholder(trigger: dict, merchant: dict, customer: Optional[dict]) -> dict:
    """Some generated triggers carry `{placeholder: true}` and no payload. Rebuild a
    payload from the merchant's own data where a verifiable one exists; otherwise
    downgrade the kind to something we can say truthfully, or leave empty (restraint)."""
    p = trigger.get("payload") or {}
    if not p.get("placeholder"):
        return trigger
    t = dict(trigger); kind = t.get("kind")
    d7 = (merchant.get("performance") or {}).get("delta_7d") or {}
    if kind in ("perf_dip", "perf_spike") and d7:
        key = min(d7, key=lambda k: d7[k]) if kind == "perf_dip" else max(d7, key=lambda k: d7[k])
        val = d7[key]
        if (kind == "perf_dip" and val < -0.05) or (kind == "perf_spike" and val > 0.05):
            t["payload"] = {"metric": key.replace("_pct", ""), "delta_pct": val, "window": "7d"}
            return t
        t["kind"] = "curious_ask_due"; t["payload"] = {"ask_template": "what_service_in_demand_this_week"}; return t
    if kind == "recall_due" and customer:
        t["kind"] = "customer_lapsed_soft"; t["payload"] = {}; return t
    if kind == "competitor_opened":
        t["kind"] = "curious_ask_due"; t["payload"] = {"ask_template": "who_is_your_competition"}; return t
    if kind in ("milestone_reached", "festival_upcoming", "chronic_refill_due"):
        if trigger.get("scope") == "merchant":
            t["kind"] = "curious_ask_due"; t["payload"] = {"ask_template": "what_service_in_demand_this_week"}; return t
        t["payload"] = {}; return t
    t["payload"] = {}
    return t
