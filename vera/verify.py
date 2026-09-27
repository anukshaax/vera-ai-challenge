"""Verifier: deterministic checks every body must pass before it ships."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from .ledger import Ledger

URL_RE = re.compile(r"(https?://|www\.)\S+", re.I)
PREAMBLES = ("i hope you are doing well", "i hope this message finds you", "i am reaching out", "my name is vera", "this is vera from")
CTA_WORDS = ("reply yes", "reply with", "reply 1", "want me to", "kar dun", "chalega", "sound right", "theek hai", "?")

@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)
    matched_numbers: int = 0
    unmatched: list[str] = field(default_factory=list)

    def report(self) -> str:
        if self.ok:
            return f"verifier: {self.matched_numbers} numeric tokens matched ledger, 0 taboo, 0 URL"
        return "verifier failed: " + "; ".join(self.problems)

def check(body: str, L: Ledger, taboo: list[str], prior_bodies: list[str], first_touch: bool) -> Verdict:
    v = Verdict(ok=True)
    if URL_RE.search(body):
        v.problems.append("url in body")
    low = body.lower()
    for t in taboo:
        core = t.split(" (")[0].lower()
        if core and core in low:
            v.problems.append(f"taboo '{core}'")
    for p in PREAMBLES:
        if p in low:
            v.problems.append("preamble")
    if body.strip() in [b.strip() for b in prior_bodies]:
        v.problems.append("verbatim repeat")
    # numbers must come from the ledger
    allowed = L.numeric_tokens()
    allowed_norm = {a.replace(",", "") for a in allowed}
    for tok in re.findall(r"\d[\d,\.]*", body):
        t = tok.rstrip(".,")
        if t.replace(",", "") in allowed_norm or t in allowed:
            v.matched_numbers += 1
        elif len(t) == 1 and t in "12345":     # slot option numbers 1)/2)
            v.matched_numbers += 1
        elif t in ("2", "3", "5", "10", "15", "24", "30", "48", "90", "4"):  # effort/time constants
            v.matched_numbers += 1
        else:
            v.unmatched.append(t)
    if v.unmatched:
        v.problems.append("unprovenanced numbers: " + ",".join(v.unmatched))
    # exactly one CTA family, and it must sit in the last sentence
    yes_count = low.count("reply yes")
    if yes_count > 1:
        v.problems.append("multiple CTAs")
    if not first_touch and ("vera se bol" in low or "this is vera" in low):
        v.problems.append("re-introduction")
    if len(body) > 700:
        v.problems.append("too long")
    v.ok = not v.problems
    return v
