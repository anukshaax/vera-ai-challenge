"""Claim ledger: every fact the bot may say, with provenance.

The composer never reads raw context. It reads Claims. Each Claim carries a
JSON-pointer style `path` back into the context it came from, and a `fresh`
flag set when the context version that produced it changed since last mine.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass(frozen=True)
class Claim:
    id: str            # stable id, e.g. "perf.ctr"
    kind: str          # metric | offer | digest | trend | peer | identity | trigger | customer | signal | history
    value: Any
    display: str       # how it may appear in a message, verbatim
    path: str          # provenance, e.g. "merchant.performance.ctr"
    fresh: bool = False
    tags: tuple = ()

@dataclass
class Ledger:
    claims: dict[str, Claim] = field(default_factory=dict)

    def add(self, c: Claim) -> None:
        self.claims[c.id] = c

    def get(self, cid: str) -> Optional[Claim]:
        return self.claims.get(cid)

    def has(self, cid: str) -> bool:
        return cid in self.claims

    def by_kind(self, kind: str) -> list[Claim]:
        return [c for c in self.claims.values() if c.kind == kind]

    def displays(self) -> set[str]:
        return {c.display for c in self.claims.values()}

    def numeric_tokens(self) -> set[str]:
        """All digit strings the bot is allowed to utter."""
        out: set[str] = set()
        for c in self.claims.values():
            for t in re.findall(r"\d[\d,\.]*", c.display):
                out.add(t.rstrip(".,"))
            if isinstance(c.value, (int, float)):
                out.add(str(c.value))
        return out

def pct(x: float, signed: bool = False) -> str:
    s = f"{abs(x)*100:.0f}%" if abs(x) >= 0.01 else f"{abs(x)*100:.1f}%"
    if signed:
        s = ("+" if x >= 0 else "-") + s
    return s

def _salutation(category: dict, merchant: dict) -> str:
    ident = merchant.get("identity", {})
    first = ident.get("owner_first_name") or ""
    slug = category.get("slug", "")
    if not first:
        return ident.get("name", "there")
    if slug == "dentists" and not first.lower().startswith("dr"):
        return f"Dr. {first}"
    return first

def mine(category: dict, merchant: dict, trigger: dict, customer: Optional[dict],
         fresh_scopes: set[str] = frozenset()) -> Ledger:
    L = Ledger()
    fm, fc, ft, fu = ("merchant" in fresh_scopes, "category" in fresh_scopes,
                      "trigger" in fresh_scopes, "customer" in fresh_scopes)
    ident = merchant.get("identity", {})
    L.add(Claim("id.salutation", "identity", _salutation(category, merchant), _salutation(category, merchant), "merchant.identity.owner_first_name"))
    L.add(Claim("id.name", "identity", ident.get("name"), ident.get("name", ""), "merchant.identity.name"))
    L.add(Claim("id.locality", "identity", ident.get("locality"), ident.get("locality", ""), "merchant.identity.locality"))
    L.add(Claim("id.city", "identity", ident.get("city"), ident.get("city", ""), "merchant.identity.city"))
    L.add(Claim("id.languages", "identity", tuple(ident.get("languages", ["en"])), "", "merchant.identity.languages"))

    # performance
    perf = merchant.get("performance", {})
    for k in ("views", "calls", "directions", "leads", "ctr"):
        if k in perf and perf[k] is not None:
            disp = pct(perf[k]) if k == "ctr" else f"{perf[k]:,}"
            L.add(Claim(f"perf.{k}", "metric", perf[k], disp, f"merchant.performance.{k}", fm))
    for k, v in (perf.get("delta_7d") or {}).items():
        L.add(Claim(f"perf.delta7.{k}", "metric", v, pct(v, signed=True), f"merchant.performance.delta_7d.{k}", fm))
    L.add(Claim("perf.window", "metric", perf.get("window_days", 30), f"{perf.get('window_days', 30)}", "merchant.performance.window_days"))

    # peer stats + gap joins
    ps = category.get("peer_stats", {})
    if "avg_ctr" in ps:
        L.add(Claim("peer.avg_ctr", "peer", ps["avg_ctr"], pct(ps["avg_ctr"]), "category.peer_stats.avg_ctr", fc))
        if L.has("perf.ctr") and ps["avg_ctr"]:
            gap = (perf["ctr"] - ps["avg_ctr"]) / ps["avg_ctr"]
            L.add(Claim("join.ctr_gap", "metric", gap, pct(gap, signed=True), "derived(perf.ctr,peer.avg_ctr)", fm or fc,
                        tags=("below_peer",) if gap < -0.1 else ("above_peer",) if gap > 0.1 else ()))
    for k in ("avg_rating", "avg_review_count", "avg_calls_30d", "avg_views_30d"):
        if k in ps:
            L.add(Claim(f"peer.{k}", "peer", ps[k], f"{ps[k]:,}" if isinstance(ps[k], int) else str(ps[k]), f"category.peer_stats.{k}", fc))
    if "avg_calls_30d" in ps and L.has("perf.calls") and ps["avg_calls_30d"]:
        gap = (perf["calls"] - ps["avg_calls_30d"]) / ps["avg_calls_30d"]
        L.add(Claim("join.calls_gap", "metric", gap, pct(gap, signed=True), "derived(perf.calls,peer.avg_calls_30d)", fm or fc))

    # subscription
    sub = merchant.get("subscription", {})
    L.add(Claim("sub.status", "identity", sub.get("status"), str(sub.get("status", "")), "merchant.subscription.status", fm))
    if sub.get("days_remaining") is not None:
        L.add(Claim("sub.days_remaining", "metric", sub["days_remaining"], str(sub["days_remaining"]), "merchant.subscription.days_remaining", fm))
    if sub.get("plan"):
        L.add(Claim("sub.plan", "identity", sub["plan"], sub["plan"], "merchant.subscription.plan"))

    # offers
    for i, o in enumerate(merchant.get("offers", []) or []):
        L.add(Claim(f"offer.{o.get('id', i)}", "offer", o, o.get("title", ""), f"merchant.offers[{i}].title", fm, tags=(o.get("status", ""),)))
    for i, o in enumerate(category.get("offer_catalog", []) or []):
        L.add(Claim(f"catalog.{o.get('id', i)}", "offer", o, o.get("title", ""), f"category.offer_catalog[{i}].title", fc, tags=("catalog", o.get("type", ""))))

    # customer aggregate, signals, review themes, history
    for k, v in (merchant.get("customer_aggregate") or {}).items():
        disp = pct(v) if isinstance(v, float) and v <= 1 else f"{v:,}" if isinstance(v, (int, float)) else str(v)
        L.add(Claim(f"agg.{k}", "metric", v, disp, f"merchant.customer_aggregate.{k}", fm))
    for s in merchant.get("signals", []) or []:
        L.add(Claim(f"signal.{s.split(':')[0]}", "signal", s, s.split(":")[1] if ":" in s else s, "merchant.signals", fm))
    for i, r in enumerate(merchant.get("review_themes", []) or []):
        L.add(Claim(f"review.{r.get('theme')}", "metric", r, f"{r.get('occurrences_30d', '')}", f"merchant.review_themes[{i}]", fm,
                    tags=(r.get("sentiment", ""), r.get("theme", ""))))
    hist = merchant.get("conversation_history", []) or []
    if hist:
        last_m = [h for h in hist if h.get("from") == "merchant"]
        L.add(Claim("hist.last_vera", "history", hist[-1] if hist[-1].get("from") == "vera" else None, "", "merchant.conversation_history[-1]"))
        if last_m:
            L.add(Claim("hist.last_merchant", "history", last_m[-1], last_m[-1].get("body", ""), "merchant.conversation_history", tags=(last_m[-1].get("engagement", ""),)))

    # digest / trend / seasonal
    for i, d in enumerate(category.get("digest", []) or []):
        L.add(Claim(f"digest.{d['id']}", "digest", d, d.get("title", ""), f"category.digest[{i}]", fc, tags=(d.get("kind", ""),)))
    for i, t in enumerate(category.get("trend_signals", []) or []):
        L.add(Claim(f"trend.{i}", "trend", t, f"'{t.get('query')}' searches {pct(t.get('delta_yoy', 0), signed=True)} YoY", f"category.trend_signals[{i}]", fc))
    for i, s in enumerate(category.get("seasonal_beats", []) or []):
        L.add(Claim(f"season.{i}", "digest", s, s.get("note", ""), f"category.seasonal_beats[{i}]", fc))
    for i, c in enumerate(category.get("patient_content_library", []) or []):
        L.add(Claim(f"content.{c.get('id', i)}", "digest", c, c.get("title", ""), f"category.patient_content_library[{i}]", fc))

    # trigger payload -> claims (flat + resolved digest)
    p = trigger.get("payload", {}) or {}
    L.add(Claim("trg.kind", "trigger", trigger.get("kind"), trigger.get("kind", ""), "trigger.kind", ft))
    L.add(Claim("trg.urgency", "trigger", trigger.get("urgency", 3), str(trigger.get("urgency", 3)), "trigger.urgency"))
    for k, v in p.items():
        if isinstance(v, (str, int, float, bool)):
            disp = pct(v, signed=True) if isinstance(v, float) and k.endswith("pct") else (f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v))
            L.add(Claim(f"trg.{k}", "trigger", v, disp, f"trigger.payload.{k}", ft))
        elif isinstance(v, list):
            L.add(Claim(f"trg.{k}", "trigger", v, ", ".join(x.get("label", str(x)) if isinstance(x, dict) else str(x) for x in v), f"trigger.payload.{k}", ft))
        elif isinstance(v, dict):
            L.add(Claim(f"trg.{k}", "trigger", v, v.get("title", ""), f"trigger.payload.{k}", ft))
    for key in ("top_item_id", "alert_id", "digest_item_id"):
        did = p.get(key)
        if did and L.has(f"digest.{did}"):
            d = L.get(f"digest.{did}")
            L.add(Claim("trg.item", "digest", d.value, d.display, d.path, d.fresh or ft, tags=d.tags))
    # numbers hidden inside digest summaries become claims too (provenance kept)
    item = L.get("trg.item")
    if item:
        for j, n in enumerate(re.findall(r"[+-]?\d[\d,\.]*%?", item.value.get("summary", "") + " " + item.value.get("title", ""))):
            L.add(Claim(f"trg.item.num{j}", "digest", n, n, item.path + ".summary", item.fresh))
        if item.value.get("source"):
            L.add(Claim("trg.item.source", "digest", item.value["source"], item.value["source"], item.path + ".source", item.fresh))

    # customer
    if customer:
        ci, rel = customer.get("identity", {}), customer.get("relationship", {})
        L.add(Claim("cust.name", "customer", ci.get("name"), ci.get("name", ""), "customer.identity.name", fu))
        L.add(Claim("cust.lang", "customer", ci.get("language_pref", "en"), "", "customer.identity.language_pref"))
        L.add(Claim("cust.state", "customer", customer.get("state"), customer.get("state", ""), "customer.state", fu))
        L.add(Claim("cust.consent", "customer", tuple((customer.get("consent") or {}).get("scope", [])), "", "customer.consent.scope"))
        L.add(Claim("cust.slots_pref", "customer", (customer.get("preferences") or {}).get("preferred_slots"), "", "customer.preferences.preferred_slots"))
        if rel.get("last_visit"):
            L.add(Claim("cust.last_visit", "customer", rel["last_visit"], rel["last_visit"], "customer.relationship.last_visit"))
        if rel.get("visits_total") is not None:
            L.add(Claim("cust.visits", "customer", rel["visits_total"], str(rel["visits_total"]), "customer.relationship.visits_total"))
        svc = rel.get("services_received") or []
        if svc:
            L.add(Claim("cust.last_service", "customer", svc[-1], svc[-1].replace("_", " "), "customer.relationship.services_received[-1]"))
    return L
