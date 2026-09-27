"""Reply classifier + conversation state machine."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional
from .ledger import Ledger
from .beats import Voice, S, _active_offer

AUTO_LEX = ("thank you for contacting", "thanks for contacting", "our team will", "will respond shortly", "will get back to you",
            "automated", "auto-reply", "auto reply", "message has been received", "shukriya", "team tak pahuncha", "dhanyavaad aapke sandesh")
ACCEPT_LEX = ("yes", "yeah", "yep", "ok", "okay", "sure", "go ahead", "let's do it", "lets do it", "do it", "send", "bhejo", "bhej do",
              "haan", "ha ", "kar do", "karo", "theek hai", "thik hai", "chalega", "done", "start", "proceed", "please do", "ready")
DECLINE_LEX = ("not interested", "no thanks", "no thank", "stop", "don't message", "dont message", "unsubscribe", "nahi chahiye",
               "mat bhejo", "leave me", "remove me", "not now", "busy", "later")
ABUSE_LEX = ("idiot", "stupid", "shut up", "scam", "fraud", "spam", "nonsense", "bakwas", "chutiya", "useless")
OFFTOPIC_LEX = ("gst", "loan", "tax", "income tax", "itr", "insurance", "visa", "passport", "legal", "lawyer", "ca ")
QUESTION_LEX = ("how", "what", "why", "when", "kaise", "kya", "kyun", "kab", "?")

@dataclass
class Conv:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str]
    trigger: dict
    plan_recommendation: str
    lever: str
    state: str = "pitch"          # pitch | action | wrap | ended
    bodies_sent: list[str] = field(default_factory=list)
    merchant_msgs: list[str] = field(default_factory=list)
    auto_hits: int = 0
    unanswered: int = 0
    turns: int = 0

def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()

def classify(msg: str, conv: Conv) -> str:
    low = _norm(msg)
    if any(k in low for k in ABUSE_LEX):
        return "hostile"
    if any(k in low for k in AUTO_LEX):
        return "auto_reply"
    if any(_norm(m) == low for m in conv.merchant_msgs):     # verbatim repeat from same sender
        return "auto_reply"
    if any(k in low for k in DECLINE_LEX):
        return "decline"
    if any(k in low for k in OFFTOPIC_LEX) and any(q in msg.lower() for q in QUESTION_LEX):
        return "off_topic_question"
    if any(re.search(rf"\b{re.escape(k.strip())}\b", low) for k in ACCEPT_LEX):
        return "intent_go"
    if any(q in msg.lower() for q in QUESTION_LEX):
        return "question"
    return "ambiguous"

def _mirror_lang(msg: str, V: Voice) -> None:
    """Per-turn language detection: mirror the merchant's last message."""
    hindi_markers = ("hai", "haan", "nahi", "kar", "karo", "bhejo", "kya", "mujhe", "aap", "theek", "chalega", "dekh")
    toks = _norm(msg).split()
    hits = sum(1 for t in toks if t in hindi_markers)
    if toks:
        V.hi = hits / max(1, len(toks)) >= 0.2 or bool(re.search(r"[\u0900-\u097F]", msg))

def respond(conv: Conv, message: str, L: Ledger, customer_facing: bool) -> dict:
    conv.turns += 1
    kind = classify(message, conv)
    conv.merchant_msgs.append(message)
    V = Voice(L, customer_facing)
    _mirror_lang(message, V)
    who = S(L) if not customer_facing else (L.get("cust.name").display if L.get("cust.name") else "")
    rec = conv.plan_recommendation

    if conv.state == "ended":
        return {"action": "end", "rationale": "conversation already closed"}

    if kind == "auto_reply":
        conv.auto_hits += 1
        if conv.auto_hits == 1:
            body = V.pick(f"Looks like an auto-reply — no problem. {who}, when you are back, one word (YES) is enough and I will handle the rest.",
                          f"Lagta hai auto-reply hai — koi baat nahi. {who}, jab free hon, bas YES likh dijiye, baaki main dekh lungi.")
            return _send(conv, body, "binary", "auto-reply detected once; one human-addressed retry")
        if conv.auto_hits == 2:
            return {"action": "wait", "wait_seconds": 86400,
                    "rationale": "Same auto-reply twice in a row; owner is likely unavailable, so wait 24h rather than burning another turn."}
        conv.state = "ended"
        return {"action": "end", "rationale": f"Auto-reply detected {conv.auto_hits}x with no human engagement; closing the conversation."}

    if kind == "decline":
        conv.state = "ended"
        return {"action": "end", "rationale": "merchant signalled not interested; graceful exit, no persuasion"}

    if kind == "hostile":
        body = V.pick(f"Understood, {who}. I will keep it short and only message when there is a specific number worth your time. Nothing needed from you now.",
                      f"Samajh gayi, {who}. Short rakhungi aur tabhi message karungi jab koi specific number ho. Abhi kuch nahi chahiye.")
        conv.state = "wrap"
        return _send(conv, body, "none", "hostile reply; calm one-liner, stay on mission, no CTA")

    if kind == "off_topic_question":
        body = V.pick(f"That one is outside what I can do — I only handle your Google listing, offers and customer messages. On that: {rec}. Want me to go ahead? Reply YES.",
                      f"Yeh mere scope se bahar hai — main sirf Google listing, offers aur customer messages sambhalti hoon. Uspe: {rec}. Aage badhun? Reply YES.")
        return _send(conv, body, "binary", "off-topic request declined in one clause; restated the single on-mission action")

    if kind == "intent_go":
        conv.state = "action"
        off = _active_offer(L)
        anchor = f" '{off.display}'" if off else ""
        body = V.pick(f"On it. Doing now: {rec}{anchor}. You will get the draft here in 15 minutes to approve — one word back is enough.",
                      f"Kar rahi hoon. Abhi: {rec}{anchor}. Draft 15 minute mein yahin milega approve karne ke liye — ek word kaafi hai.")
        return _send(conv, body, "none", "intent detected -> switched pitch->action immediately; no qualifying question")

    if kind == "question":
        low = message.lower()
        if any(w in low for w in ("cost", "price", "charge", "paisa", "kitna", "fee")):
            plan = L.get("sub.plan")
            pl = f" on your {plan.display} plan" if plan and plan.display else ""
            body = V.pick(f"Nothing extra — drafting and posting is part of what I already do for your listing{pl}. You only approve. Go ahead with {rec}? Reply YES.",
                          f"Kuch extra nahi — draft aur post karna meri already wali kaam hai{pl}. Aap sirf approve karein. {rec} aage badhaun? Reply YES.")
            return _send(conv, body, "binary", "cost question answered without inventing pricing; single CTA restated")
        # answer with the most relevant claims we hold; never invent
        facts = []
        for cid, lbl in (("perf.views", "views"), ("perf.calls", "calls"), ("perf.ctr", "CTR"), ("peer.avg_ctr", "peer CTR")):
            c = L.get(cid)
            if c: facts.append(f"{lbl} {c.display}")
        ft = ("; ".join(facts[:3])) if facts else ""
        body = V.pick(f"Good question. What I can see on your listing right now: {ft}. Everything else I would be guessing, so I will not. Shall I go ahead with {rec}? Reply YES.",
                      f"Accha sawaal. Aapki listing pe abhi yeh dikh raha hai: {ft}. Baaki guess hoga, toh nahi bolungi. {rec} aage badhaun? Reply YES.")
        return _send(conv, body, "binary", "answered from ledger only; restated single CTA")

    # ambiguous / lukewarm
    conv.unanswered += 1
    if conv.unanswered >= 3:
        conv.state = "ended"
        return {"action": "end", "rationale": "3 non-committal turns; stopping rather than nudging again"}
    if conv.state == "action":
        body = V.pick("Noted. Draft is queued; I will send it here for your approval.", "Noted. Draft queue mein hai; approval ke liye yahin bhejungi.")
        return _send(conv, body, "none", "in action state; acknowledge without re-pitching")
    return {"action": "wait", "wait_seconds": 1800, "rationale": "ambiguous reply; back off 30 min rather than re-pitch"}

def V_shorten(body: str) -> str:
    """Never send the same body twice: keep only the final sentence (the CTA)."""
    parts = [p for p in re.split(r"(?<=[.?!])\s+", body) if p]
    return ("Same answer as before — " + parts[-1]) if parts else body

def _send(conv: Conv, body: str, cta: str, rationale: str) -> dict:
    if body in conv.bodies_sent:                     # anti-repetition floor
        body = V_shorten(body)
    conv.bodies_sent.append(body)
    return {"action": "send", "body": body, "cta": cta, "rationale": rationale}
