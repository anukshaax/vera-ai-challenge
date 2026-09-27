"""Versioned, idempotent context store + per-merchant memory (in-memory)."""
from __future__ import annotations
from collections import defaultdict
from typing import Optional
from .fsm import Conv

class Store:
    def __init__(self):
        self.ctx: dict[tuple[str, str], dict] = {}
        self.changed: dict[tuple[str, str], int] = defaultdict(int)   # bumps per (scope,id) since first put
        self.seen_version_at_send: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
        self.convs: dict[str, Conv] = {}
        self.levers: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.sent_bodies: dict[str, list[str]] = defaultdict(list)
        self.suppression: set[str] = set()
        self.sent_triggers: set[str] = set()

    def put(self, scope, cid, version, payload) -> str:
        cur = self.ctx.get((scope, cid))
        if cur and cur["version"] >= version:
            return "stale" if cur["version"] > version else "dup"
        self.ctx[(scope, cid)] = {"version": version, "payload": payload}
        if cur:
            self.changed[(scope, cid)] += 1
        return "ok"

    def get(self, scope, cid) -> Optional[dict]:
        e = self.ctx.get((scope, cid or ""))
        return e["payload"] if e else None

    def version(self, scope, cid) -> int:
        e = self.ctx.get((scope, cid)); return e["version"] if e else 0

    def counts(self):
        c = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (s, _) in self.ctx: c[s] = c.get(s, 0) + 1
        return c

    def fresh_scopes(self, mid, trg, customer) -> set[str]:
        """Scopes whose version changed since we last messaged this merchant."""
        out = set()
        merchant = self.get("merchant", mid) or {}
        keys = {"merchant": ("merchant", mid), "category": ("category", merchant.get("category_slug", "")),
                "trigger": ("trigger", trg.get("id", ""))}
        if customer: keys["customer"] = ("customer", customer.get("customer_id", ""))
        last = self.seen_version_at_send[mid]
        for scope, key in keys.items():
            v = self.version(*key)
            if key in last and v > last[key]:
                out.add(scope)
            elif key not in last and self.changed.get(key, 0) > 0:
                out.add(scope)
        return out

    def open(self, conv: Conv): self.convs[conv.conversation_id] = conv
    def conv(self, cid) -> Optional[Conv]: return self.convs.get(cid)
    def open_conversation(self, mid) -> bool:
        return any(c.merchant_id == mid and c.state not in ("ended", "wrap") for c in self.convs.values())
    def lever_hist(self, mid): return dict(self.levers[mid])
    def bodies(self, mid): return list(self.sent_bodies[mid])
    def suppressed(self, tid, suppression_key=""):
        return tid in self.sent_triggers or (suppression_key and suppression_key in self.suppression)

    def record_send(self, mid, lever, body, tid, skey):
        self.levers[mid][lever] += 1
        self.sent_bodies[mid].append(body)
        self.sent_triggers.add(tid)
        if skey: self.suppression.add(skey)
        merchant = self.get("merchant", mid) or {}
        for key in (("merchant", mid), ("category", merchant.get("category_slug", ""))):
            self.seen_version_at_send[mid][key] = self.version(*key)

    def wipe(self): self.__init__()
