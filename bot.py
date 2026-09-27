"""Offline entrypoint required by the brief: compose(category, merchant, trigger, customer) -> dict."""
from vera import planner

def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    p = planner.plan(category, merchant, trigger, customer, lever_hist={}, prior_bodies=[])
    if not p:
        return {"body": "", "cta": "none", "send_as": "vera", "suppression_key": trigger.get("suppression_key", ""),
                "rationale": "no verified candidate for this trigger; restraint"}
    c = p.candidate
    return {"body": c.body, "cta": c.cta, "send_as": c.send_as, "suppression_key": trigger.get("suppression_key", ""),
            "rationale": p.explain(trigger)}

from vera.api import app  # noqa: E402  (uvicorn bot:app)
