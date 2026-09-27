"""The five endpoints. Thin: all decisions live in planner/fsm."""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from .store import Store
from . import planner, fsm
from .ledger import mine

app = FastAPI(title="vera-ledger-bot")
START = time.time()
store = Store()

class CtxBody(BaseModel):
    scope: str; context_id: str; version: int; payload: dict[str, Any]; delivered_at: str = ""
class TickBody(BaseModel):
    now: str = ""; available_triggers: list[str] = []
class ReplyBody(BaseModel):
    conversation_id: str; merchant_id: Optional[str] = None; customer_id: Optional[str] = None
    from_role: str = "merchant"; message: str; received_at: str = ""; turn_number: int = 1

@app.get("/v1/healthz")
def healthz():
    return {"status": "ok", "uptime_seconds": int(time.time() - START), "contexts_loaded": store.counts()}

@app.get("/v1/metadata")
def metadata():
    return {"team_name": "Vera Challenge Submission", "team_members": ["participant"], "model": "deterministic composer",
            "approach": "claim-ledger composition, trigger routing, rubric-aware candidate selection, verified output, FSM replies",
            "contact_email": "participant@example.com", "version": "1.0.0", "submitted_at": datetime.now(timezone.utc).isoformat()}

@app.post("/v1/context")
def push_context(b: CtxBody):
    if b.scope not in ("category", "merchant", "customer", "trigger"):
        return {"accepted": False, "reason": "invalid_scope", "details": b.scope}
    res = store.put(b.scope, b.context_id, b.version, b.payload)
    if res == "stale":
        return {"accepted": False, "reason": "stale_version", "current_version": store.version(b.scope, b.context_id)}
    return {"accepted": True, "ack_id": f"ack_{b.context_id}_v{b.version}", "stored_at": datetime.now(timezone.utc).isoformat()}

@app.post("/v1/tick")
def tick(b: TickBody):
    actions = []
    for tid in b.available_triggers:
        if len(actions) >= 20:
            continue
        trg = store.get("trigger", tid)
        if not trg or store.suppressed(tid, trg.get("suppression_key", "")):
            continue
        if not trg:
            continue
        mid = trg.get("merchant_id")
        merchant = store.get("merchant", mid)
        category = store.get("category", (merchant or {}).get("category_slug", ""))
        if not (merchant and category):
            continue
        if not planner.urgency_gate(trg, b.now, store.open_conversation(mid)):
            continue
        customer = store.get("customer", trg.get("customer_id")) if trg.get("customer_id") else None
        p = planner.plan(category, merchant, trg, customer, store.lever_hist(mid), store.bodies(mid), store.fresh_scopes(mid, trg, customer))
        if not p:
            continue
        cid = f"conv_{mid}_{trg.get('kind')}_{tid[-12:]}"
        c = p.candidate
        store.open(fsm.Conv(cid, mid, trg.get("customer_id"), trg, c.recommendation, c.lever, bodies_sent=[c.body]))
        store.record_send(mid, c.lever, c.body, tid, trg.get("suppression_key", ""))
        actions.append({"conversation_id": cid, "merchant_id": mid, "customer_id": trg.get("customer_id"), "send_as": c.send_as,
                        "trigger_id": tid, "template_name": c.template_name, "template_params": c.params, "body": c.body,
                        "cta": c.cta, "suppression_key": trg.get("suppression_key", ""), "rationale": p.explain(trg)})
    return {"actions": actions}

@app.post("/v1/reply")
def reply(b: ReplyBody):
    conv = store.conv(b.conversation_id)
    if not conv:
        return {"action": "end", "rationale": "unknown conversation_id"}
    merchant = store.get("merchant", conv.merchant_id) or {}
    category = store.get("category", merchant.get("category_slug", "")) or {}
    customer = store.get("customer", conv.customer_id) if conv.customer_id else None
    L = mine(category, merchant, conv.trigger, customer)
    return fsm.respond(conv, b.message, L, b.from_role == "customer")

@app.post("/v1/teardown")
def teardown():
    store.wipe()
    return {"ok": True}
