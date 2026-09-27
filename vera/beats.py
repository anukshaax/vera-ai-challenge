"""Beat composer: renders candidate messages from Claims only.

Every handler returns a list of Candidate objects, each built from a fixed
4-beat skeleton: hook (one claim) -> why now -> what I'll do -> single CTA.
No handler may write a number that is not a Claim.display.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
import re
from .ledger import Ledger, Claim, pct

LEVERS = ("specificity", "loss_aversion", "social_proof", "effort_externalization",
          "curiosity", "reciprocity", "ask_merchant", "binary_commitment")

@dataclass
class Candidate:
    body: str
    cta: str                      # binary | open_ended | slot_choice | none
    lever: str
    claims: list[str]             # claim ids used (provenance)
    recommendation: str           # the decision the message advocates
    contrarian: bool = False
    send_as: str = "vera"
    template_name: str = "vera_generic_v1"
    params: list[str] = field(default_factory=list)

class Voice:
    """Language + tone helpers. Hindi phrases are deliberately simple."""
    def __init__(self, L: Ledger, customer_facing: bool = False):
        langs = L.get("id.languages").value if L.get("id.languages") else ("en",)
        if customer_facing:
            lp = (L.get("cust.lang").value if L.get("cust.lang") else "en") or "en"
            self.hi = "hi" in lp
        else:
            self.hi = "hi" in langs
        self.L = L

    def pick(self, en: str, hi: str) -> str:
        return hi if self.hi else en

    def yes(self, mins: str | None = None) -> str:
        if mins:
            return self.pick(f"Reply YES and it's live in {mins} min.", f"Reply YES — {mins} min mein live kar dungi.")
        return self.pick("Reply YES and I'll take it from here.", "Reply YES, baaki main sambhal lungi.")

    def want(self, thing: str) -> str:
        return self.pick(f"Want me to {thing}? Reply YES.", f"{thing[0].upper() + thing[1:]} kar dun? Reply YES.")

def S(L: Ledger) -> str:
    return L.get("id.salutation").display

def _digest_line(item: Claim) -> tuple[str, list[str]]:
    d = item.value
    src = d.get("source", "")
    n = d.get("trial_n")
    lead = d.get("title", "")
    parts = []
    if n:
        parts.append(f"{n:,}-patient trial")
    text = (", ".join(parts) + ": " if parts else "") + lead
    if src:
        text += f" ({src})"
    return text, ["trg.item", "trg.item.source"]

def _active_offer(L: Ledger) -> Claim | None:
    for c in L.by_kind("offer"):
        if "active" in c.tags:
            return c
    return None

def _service_price_catalog(L: Ledger) -> Claim | None:
    for c in L.by_kind("offer"):
        if "catalog" in c.tags and "service_at_price" in c.tags:
            return c
    return None

# ---------------------------------------------------------------- handlers

def h_research_digest(L, V):
    item = L.get("trg.item")
    if not item:
        return []
    line, used = _digest_line(item)
    seg = item.value.get("patient_segment", "")
    join = ""
    if seg == "high_risk_adults" and L.has("agg.high_risk_adult_count"):
        join = V.pick(f" — relevant to your {L.get('agg.high_risk_adult_count').display} high-risk adult patients", f" — aapke {L.get('agg.high_risk_adult_count').display} high-risk adult patients ke liye relevant")
        used.append("agg.high_risk_adult_count")
    act = item.value.get("actionable", "")
    c1 = Candidate(f"{S(L)}, this week's item{join}: {line}. {V.pick('I have the 2-min abstract plus a patient-ed WhatsApp drafted.', 'Maine 2-min abstract aur ek patient-ed WhatsApp draft kar liya hai.')} {V.yes()}",
                   "binary", "reciprocity", used + ["id.salutation"], f"share digest item {item.value.get('id')} + patient-ed draft")
    c2 = Candidate(f"{S(L)}, one finding from this week{join}: {line}. Suggested action: {act[0].lower() + act[1:] if act else 'review your recall protocol'}. {V.pick('Does this match what you see in your chair?', 'Aapke practice mein bhi aisa dikhta hai?')}",
                   "open_ended", "ask_merchant", used + ["id.salutation"], f"discuss digest item {item.value.get('id')}")
    return [c1, c2]

def h_regulation_change(L, V):
    item = L.get("trg.item")
    if not item:
        return []
    line, used = _digest_line(item)
    dl = L.get("trg.deadline_iso")
    when = f" Deadline {dl.display}." if dl else ""
    used += ["trg.deadline_iso"] if dl else []
    body = f"{S(L)}, compliance note: {line}.{when} {V.pick('I can turn this into a one-page checklist for your front desk.', 'Main iska ek one-page checklist bana sakti hoon aapke front desk ke liye.')} {V.want('send the checklist')}"
    return [Candidate(body, "binary", "loss_aversion", used + ["id.salutation"], "send compliance checklist before deadline")]

def h_cde_opportunity(L, V):
    item = L.get("trg.item")
    if not item:
        return []
    line, used = _digest_line(item)
    cr = L.get("trg.credits")
    fee = L.get("trg.fee")
    extra = f" {cr.display} CDE credits" if cr else ""
    feetxt = ", free for members" if fee and "free" in str(fee.value) else ""
    body = f"{S(L)}, {line} —{extra}{feetxt}. {V.pick('Worth 2 hours if you are short on credits this cycle. Want me to register you and send the calendar invite? Reply YES.', 'Credits short hain toh worth it hai. Register karke calendar invite bhej dun? Reply YES.')}"
    return [Candidate(body, "binary", "effort_externalization", used + ["trg.credits", "trg.fee", "id.salutation"], "register for CDE webinar")]

def h_perf_dip(L, V):
    m, d, vb = L.get("trg.metric"), L.get("trg.delta_pct"), L.get("trg.vs_baseline")
    if not (m and d):
        return []
    metric = m.display
    used = ["trg.metric", "trg.delta_pct", "trg.vs_baseline", "id.salutation"]
    base = f" (baseline {vb.display}/week)" if vb else ""
    hook = V.pick(f"{S(L)}, your {metric} dropped {d.display} this week{base}.", f"{S(L)}, is hafte aapke {metric} {d.display} gire{base}.")
    off = _active_offer(L)
    cat = _service_price_catalog(L)
    cands = []
    if off:
        cands.append(Candidate(f"{hook} {V.pick('Your', 'Aapka')} '{off.display}' {V.pick('offer is still active — the drop is usually visibility, not demand. I can refresh the Google post with that offer so it shows in local search again.', 'offer abhi bhi active hai — dip usually visibility ka hota hai, demand ka nahi. Main Google post refresh kar sakti hoon is offer ke saath.')} {V.yes('10')}",
                               "binary", "loss_aversion", used + [off.id], "refresh GBP post with existing offer"))
    if cat:
        cands.append(Candidate(f"{hook} {V.pick('Quickest lever I have seen for', 'Sabse tez lever')} {metric}: {V.pick('a service-at-price post like', 'ek service-at-price post jaise')} '{cat.display}'. {V.pick('I can draft it in your voice.', 'Aapki voice mein draft kar dungi.')} {V.yes('10')}",
                               "binary", "effort_externalization", used + [cat.id], f"post service-at-price offer '{cat.display}'"))
    cands.append(Candidate(f"{hook} {V.pick('Before I suggest anything — did something change on your side this week (hours, staff, a closed day)?', 'Kuch suggest karne se pehle — is hafte aapki taraf se kuch badla (timing, staff, koi chhutti)?')}",
                           "open_ended", "ask_merchant", used, "diagnose dip with merchant before acting"))
    return cands

def h_seasonal_perf_dip(L, V):
    m, d, note = L.get("trg.metric"), L.get("trg.delta_pct"), L.get("trg.season_note")
    if not (m and d):
        return []
    used = ["trg.metric", "trg.delta_pct", "trg.is_expected_seasonal", "id.salutation"]
    members = L.get("agg.total_active_members")
    hold = f" {V.pick('You still have', 'Aapke paas abhi bhi')} {members.display} {V.pick('active members —', 'active members hain —')}" if members else ""
    if members: used.append("agg.total_active_members")
    body = (f"{S(L)}, {m.display} {V.pick('are down', 'gire hain')} {d.display} {V.pick('this week — but this is the usual post-resolution dip, not something you did wrong.', 'is hafte — lekin yeh usual post-resolution dip hai, aapki galti nahi.')}"
            f"{hold} {V.pick('the smart move now is retention over acquisition. I can draft a members-only referral post instead of a discount.', 'abhi retention pe focus karna better hai, acquisition pe nahi. Discount ki jagah members-only referral post draft kar dun.')} {V.yes()}")
    return [Candidate(body, "binary", "reciprocity", used, "reframe dip as seasonal; retention post instead of discount", contrarian=True)]

def h_perf_spike(L, V):
    m, d, drv = L.get("trg.metric"), L.get("trg.delta_pct"), L.get("trg.likely_driver")
    if not (m and d):
        return []
    used = ["trg.metric", "trg.delta_pct", "id.salutation"]
    why = f" {V.pick('Likely driver:', 'Likely wajah:')} {drv.display.replace('_', ' ')}." if drv else ""
    if drv: used.append("trg.likely_driver")
    body = f"{S(L)}, {m.display} {V.pick('up', 'upar')} {d.display} {V.pick('this week.', 'is hafte.')}{why} {V.pick('Spikes fade in about a week unless you post again on the same theme. I can draft the follow-up post now.', 'Spike ek hafte mein fade ho jaata hai agar same theme pe dobara post na ho. Main follow-up post abhi draft kar sakti hoon.')} {V.yes('10')}"
    return [Candidate(body, "binary", "loss_aversion", used, "double down on spike driver with follow-up post")]

def h_milestone(L, V):
    now, ms, metric = L.get("trg.value_now"), L.get("trg.milestone_value"), L.get("trg.metric")
    if not (now and ms):
        return []
    used = ["trg.value_now", "trg.milestone_value", "trg.metric", "id.salutation"]
    left = ms.value - now.value
    L.add(Claim("join.milestone_gap", "metric", left, str(left), "derived(trg.milestone_value,trg.value_now)"))
    used.append("join.milestone_gap")
    peer = L.get("peer.avg_review_count")
    ptxt = f" {V.pick('Peer average in your bracket is', 'Aapke bracket ka peer average hai')} {peer.display}." if peer else ""
    if peer: used.append("peer.avg_review_count")
    body = f"{S(L)}, {V.pick('you are at', 'aap')} {now.display} {V.pick('reviews —', 'reviews pe ho —')} {left} {V.pick('short of', 'kam hain')} {ms.display}.{ptxt} {V.pick('A 150-review badge post plus a thank-you story usually closes that gap in days. I can draft both.', 'Ek badge post aur thank-you story se yeh gap kuch din mein close hota hai. Dono draft kar dun.')} {V.yes()}"
    body = body.replace("150-review", f"{ms.display}-review")
    return [Candidate(body, "binary", "social_proof", used, "milestone push post")]

def h_review_theme(L, V):
    th, occ, q = L.get("trg.theme"), L.get("trg.occurrences_30d"), L.get("trg.common_quote")
    if not (th and occ):
        return []
    used = ["trg.theme", "trg.occurrences_30d", "id.salutation"]
    quote = f' One said: "{q.display}".' if q else ""
    if q: used.append("trg.common_quote")
    theme = th.display.replace("_", " ")
    body = f"{S(L)}, {occ.display} {V.pick('reviews in 30 days mention', 'reviews 30 din mein')} \"{theme}\"{V.pick('', ' mention karte hain')}{quote} {V.pick('Unanswered, this is what new customers read first. I can draft owner replies to each and a one-line fix note for your listing.', 'Bina reply ke, naye customers yahi pehle padhte hain. Main har ek ka owner reply draft kar sakti hoon.')} {V.yes()}"
    return [Candidate(body, "binary", "loss_aversion", used, "reply to negative theme reviews + listing fix")]

def h_renewal_due(L, V):
    dr, plan = L.get("trg.days_remaining"), L.get("trg.plan")
    if not dr:
        return []
    used = ["trg.days_remaining", "trg.plan", "id.salutation"]
    stats = []
    for k, lbl in (("perf.views", "views"), ("perf.calls", "calls"), ("perf.directions", "direction requests")):
        c = L.get(k)
        if c:
            stats.append(f"{c.display} {lbl}"); used.append(k)
    st = f" {V.pick('Last 30 days:', 'Pichle 30 din:')} {', '.join(stats)}." if stats else ""
    body = f"{S(L)}, {V.pick('your', 'aapka')} {plan.display if plan else ''} {V.pick('plan ends in', 'plan')} {dr.display} {V.pick('days.', 'din mein khatam ho raha hai.')}{st} {V.pick('If those numbers are working for you, I can queue the renewal so nothing pauses — no auto-charge, you confirm first.', 'Agar yeh numbers kaam kar rahe hain, main renewal queue kar dungi — no auto-charge, aap pehle confirm karenge.')} Reply YES."
    return [Candidate(body, "binary", "loss_aversion", used, "queue renewal with performance evidence")]

def h_winback(L, V):
    dse, dip, added = L.get("trg.days_since_expiry"), L.get("trg.perf_dip_pct"), L.get("trg.lapsed_customers_added_since_expiry")
    if not dse:
        return []
    used = ["trg.days_since_expiry", "id.salutation"]
    parts = []
    if dip: parts.append(f"{V.pick('visibility down', 'visibility')} {dip.display}"); used.append("trg.perf_dip_pct")
    if added: parts.append(f"{added.display} {V.pick('customers went quiet', 'customers chup ho gaye')}"); used.append("trg.lapsed_customers_added_since_expiry")
    body = f"{S(L)}, {V.pick('it has been', '')} {dse.display} {V.pick('days since your plan lapsed —', 'din ho gaye plan lapse hue —')} {', '.join(parts)}. {V.pick('No pitch: I can send a one-line summary of exactly what stopped and what a restart would cover.', 'Koi pitch nahi: bas ek line mein bata dungi kya ruka aur restart mein kya milega.')} {V.want('send that')}"
    return [Candidate(body, "binary", "loss_aversion", used, "winback with lapse evidence, no hard sell")]

def h_dormant(L, V):
    days, topic = L.get("trg.days_since_last_merchant_message"), L.get("trg.last_topic")
    used = ["id.salutation"]
    hook = V.pick('it has been a while', 'kaafi din ho gaye')
    if days: hook = f"{V.pick('we last spoke', 'last baat')} {days.display} {V.pick('days ago', 'din pehle hui thi')}"; used.append("trg.days_since_last_merchant_message")
    if topic: hook += f" {V.pick('about', 'about')} {topic.display.replace('_', ' ')}"; used.append("trg.last_topic")
    off = _active_offer(L)
    if off:
        ask = f"{V.pick('Is your', 'Kya aapka')} '{off.display}' {V.pick('still the offer you want customers to see first?', 'offer abhi bhi customers ko pehle dikhna chahiye?')}"
        used.append(off.id)
    else:
        ask = V.pick("What is the one service you would most like more customers for this month?", "Is mahine kis ek service ke liye zyada customers chahiye?")
    body = f"{S(L)}, {hook}. {V.pick('No update from my side — just one question:', 'Meri taraf se koi update nahi — bas ek sawaal:')} {ask}"
    return [Candidate(body, "open_ended", "ask_merchant", used, "re-open with one merchant question, no pitch")]

def h_curious_ask(L, V):
    used = ["id.salutation"]
    if L.get("trg.ask_template") and L.get("trg.ask_template").value == "who_is_your_competition":
        body = f"{S(L)}, {V.pick('one question this week: which nearby business do you see as your main competition? Name them and I will compare both listings side by side — photos, offers, reviews — and send you the gaps.', 'is hafte ek sawaal: aas-paas kaunsa business aapka main competition hai? Naam bata dijiye, main dono listings compare karke gaps bhej dungi — photos, offers, reviews.')}"
        return [Candidate(body, "open_ended", "ask_merchant", used + ["trg.ask_template"], "ask merchant to name competitor; offer listing comparison")]
    hook = ""
    for k in ("perf.delta7.views_pct", "perf.delta7.calls_pct"):
        c = L.get(k)
        if c and abs(c.value) >= 0.1:
            what = "views" if "views" in k else "calls"
            hook = f" {V.pick('your', 'aapke')} {what} {V.pick('moved', 'change hue')} {c.display} {V.pick('this week, so I am curious:', 'is hafte, toh ek sawaal:')}"
            used.append(k); break
    trend = L.by_kind("trend")
    tr = ""
    if trend:
        t = trend[0]; tr = f" {V.pick('Locally,', 'Local search mein')} {t.display}."; used.append(t.id)
    body = f"{S(L)},{hook or V.pick(' quick one:', ' ek quick sawaal:')} {V.pick('which service is getting the most asks this week?', 'is hafte kaunsi service sabse zyada poochi ja rahi hai?')}{tr} {V.pick('If you tell me, I will build the next post around it.', 'Bata dijiye, agla post usi pe banaungi.')}"
    return [Candidate(body, "open_ended", "ask_merchant", used, "curiosity ask to seed next post")]

def h_competitor(L, V):
    name, dist, offer = L.get("trg.competitor_name"), L.get("trg.distance_km"), L.get("trg.their_offer")
    if not name:
        return []
    used = ["trg.competitor_name", "trg.distance_km", "trg.their_offer", "id.salutation"]
    mine = _active_offer(L)
    yours = f" {V.pick('Your active offer is', 'Aapka active offer hai')} '{mine.display}'." if mine else ""
    if mine: used.append(mine.id)
    rev = L.get("perf.directions")
    moat = f" {V.pick('You have', 'Aapke paas')} {rev.display} {V.pick('direction requests this month — that is a moat they do not have yet.', 'direction requests hain is mahine — yeh unke paas abhi nahi.')}" if rev else ""
    if rev: used.append("perf.directions")
    body = f"{S(L)}, {name.display} {V.pick('opened', 'khula hai')} {dist.display} km {V.pick('away with', 'door, offer:')} '{offer.display if offer else 'a launch offer'}'.{yours}{moat} {V.pick('Do not match on price — I can draft a post that leads with your reviews and experience instead.', 'Price match mat kijiye — main reviews aur experience pe ek post draft kar sakti hoon.')} {V.yes()}"
    return [Candidate(body, "binary", "loss_aversion", used, "respond to competitor with differentiation, not price cut", contrarian=True)]

def h_festival(L, V):
    fest, dt, days = L.get("trg.festival"), L.get("trg.date"), L.get("trg.days_until")
    if not fest:
        return []
    used = ["trg.festival", "trg.date", "trg.days_until", "id.salutation"]
    cat = _service_price_catalog(L)
    off = _active_offer(L)
    anchor = off or cat
    if anchor: used.append(anchor.id)
    far = days and days.value > 45
    if far:
        body = f"{S(L)}, {fest.display} {V.pick('is', 'abhi')} {days.display} {V.pick('days out —', 'din door hai —')} {V.pick('too early for a promo, right time to lock the calendar.', 'promo ke liye jaldi hai, calendar lock karne ka sahi time.')} {V.pick('I will remind you 3 weeks before with a draft built around', 'Main 3 hafte pehle yaad dilaungi, draft is pe banega:')} {('\'' + anchor.display + '\'') if anchor else V.pick('your best service', 'aapki best service')}. {V.pick('Anything to plan before that?', 'Usse pehle kuch plan karna hai?')}"
        return [Candidate(body, "open_ended", "reciprocity", used, "hold festival promo; schedule reminder", contrarian=True)]
    body = f"{S(L)}, {fest.display} {V.pick('is in', 'bas')} {days.display} {V.pick('days.', 'din mein hai.')} {V.pick('Searches spike the week before; a post with', 'Ek hafte pehle searches badhti hain; post')} {('\'' + anchor.display + '\'') if anchor else V.pick('a service-at-price offer', 'service-at-price offer ke saath')} {V.pick('catches that window.', 'yeh window pakadta hai.')} {V.yes('10')}"
    return [Candidate(body, "binary", "loss_aversion", used, "festival post in search window")]

def h_ipl(L, V):
    match, venue, t, weeknight = L.get("trg.match"), L.get("trg.venue"), L.get("trg.match_time_iso"), L.get("trg.is_weeknight")
    if not match:
        return []
    used = ["trg.match", "trg.venue", "trg.match_time_iso", "trg.is_weeknight", "id.salutation"]
    hhmm = t.display[11:16] if t else ""
    hh = f"{int(hhmm[:2]) - 12 if int(hhmm[:2]) > 12 else int(hhmm[:2])}:{hhmm[3:]}pm" if hhmm else ""
    off = _active_offer(L)
    ipl = L.get("digest.d_2026W17_ipl_window")
    is_weekend = weeknight is not None and not weeknight.value
    if is_weekend and ipl:
        used += ["digest.d_2026W17_ipl_window"]
        m = re.search(r"down (\d+%)", ipl.value.get("summary", ""))
        if not m:
            return [Candidate(f"{S(L)}, {match.display} {V.pick('tonight', 'aaj raat')} {hh}. {V.pick('Weekend home matches tend to keep people home; I would hold the promo tonight and push delivery instead.', 'Weekend matches pe log ghar rehte hain; aaj promo hold karke delivery push karo.')} {V.yes()}", "binary", "loss_aversion", used, "hold promo on weekend", contrarian=True)]
        drop = m.group(1)
        L.add(Claim("digest.ipl_drop", "digest", drop, drop, ipl.path + ".summary"))
        used.append("digest.ipl_drop")
        lev = f" {V.pick('Your', 'Aapka')} '{off.display}' {V.pick('is already active — push it as a delivery-only special tonight instead of a match promo.', 'already active hai — aaj match promo ki jagah ise delivery-only special banao.')}" if off else ""
        if off: used.append(off.id)
        body = f"{S(L)}, {match.display} {V.pick('at', '@')} {venue.display if venue else ''} {V.pick('tonight', 'aaj raat')} {hh}. {V.pick('Heads-up: weekend home matches pull covers down about', 'Dhyan rahe: weekend home matches pe covers lagbhag')} {drop} {V.pick('(people watch at home), so skip a match-night promo.', 'girte hain (log ghar pe dekhte hain), toh match-night promo skip karo.')}{lev} {V.pick('Want the Swiggy banner + Insta story drafted?', 'Swiggy banner + Insta story draft kar dun?')} Reply YES."
        return [Candidate(body, "binary", "loss_aversion", used, "skip match promo on weekend; delivery special", contrarian=True)]
    body = f"{S(L)}, {match.display} {V.pick('tonight', 'aaj raat')} {hh}. {V.pick('Weeknight matches are the ones that lift covers — a match-night combo post catches the 6-7pm search window.', 'Weeknight matches covers badhate hain — match-night combo post 6-7pm search window pakadta hai.')} {V.yes('10')}"
    return [Candidate(body, "binary", "specificity", used, "match-night combo post")]

def h_supply_alert(L, V):
    mol, batches, mfr = L.get("trg.molecule"), L.get("trg.affected_batches"), L.get("trg.manufacturer")
    if not mol:
        return []
    used = ["trg.molecule", "trg.affected_batches", "trg.manufacturer", "id.salutation"]
    n = L.get("agg.chronic_rx_count")
    ntxt = f" {V.pick('You have', 'Aapke paas')} {n.display} {V.pick('chronic-Rx customers; I can filter the ones on', 'chronic-Rx customers hain; main filter kar sakti hoon jo')} {mol.display} {V.pick('and draft the notice.', 'pe hain, aur notice draft kar dungi.')}" if n else ""
    if n: used.append("agg.chronic_rx_count")
    body = f"{S(L)}, recall alert: {mol.display} {V.pick('batches', 'batch')} {batches.display if batches else ''} ({mfr.display if mfr else ''}). {V.pick('Check shelf stock first.', 'Pehle shelf stock check kar lijiye.')}{ntxt} Reply YES."
    return [Candidate(body, "binary", "reciprocity", used, "batch recall: shelf check + customer notice")]

def h_category_seasonal(L, V):
    trends = L.get("trg.trends")
    if not trends:
        return []
    used = ["trg.trends", "trg.season", "id.salutation"]
    items = [x for x in trends.value if isinstance(x, str)]
    up = [i.replace("_demand_", " ").replace("+", "+") for i in items if "+" in i]
    down = [i.replace("_demand_", " ") for i in items if "-" in i]
    L.add(Claim("trg.trends.up", "trigger", up, ", ".join(f"{u.split(' ')[0]} {u.split(' ')[1]}%" for u in up), "trigger.payload.trends"))
    L.add(Claim("trg.trends.down", "trigger", down, ", ".join(f"{d.split(' ')[0]} {d.split(' ')[1]}%" for d in down), "trigger.payload.trends"))
    used += ["trg.trends.up", "trg.trends.down"]
    body = f"{S(L)}, summer demand shift in {L.get('id.city').display}: {L.get('trg.trends.up').display} {V.pick('up;', 'upar;')} {L.get('trg.trends.down').display}. {V.pick('Worth moving those to the front shelf and the Google post this week. I can draft a summer-essentials post with your delivery offer.', 'Yeh front shelf aur Google post pe lao is hafte. Main summer-essentials post draft kar sakti hoon delivery offer ke saath.')} {V.yes()}"
    used.append("id.city")
    return [Candidate(body, "binary", "specificity", used, "front-shelf + post on summer demand")]

def h_gbp_unverified(L, V):
    up = L.get("trg.estimated_uplift_pct")
    used = ["trg.verified", "trg.verification_path", "id.salutation"]
    ut = f" {V.pick('Verified listings in your category see about', 'Verified listings ko lagbhag')} {up.display.lstrip('+')} {V.pick('more visibility.', 'zyada visibility milti hai.')}" if up else ""
    if up: used.append("trg.estimated_uplift_pct")
    views = L.get("perf.views")
    vt = f" {V.pick('You had', 'Aapke')} {views.display} {V.pick('views this month unverified —', 'views the is mahine bina verify ke —')}" if views else ""
    if views: used.append("perf.views")
    body = f"{S(L)}, {V.pick('your Google listing is still unverified.', 'aapki Google listing abhi bhi unverified hai.')}{ut}{vt} {V.pick('the verification is a postcard or a phone call, 5 minutes. I will walk you through it live.', 'verification postcard ya phone call se hoti hai, 5 minute. Main live guide karungi.')} Reply YES."
    return [Candidate(body, "binary", "loss_aversion", used, "complete GBP verification")]

def h_active_planning(L, V):
    topic, last = L.get("trg.intent_topic"), L.get("trg.merchant_last_message")
    if not topic:
        return []
    used = ["trg.intent_topic", "trg.merchant_last_message", "id.salutation"]
    t = topic.display.replace("_", " ")
    off = _active_offer(L)
    anchor = f" {V.pick('anchored on your', 'aapke')} '{off.display}'" if off else ""
    if off: used.append(off.id)
    if "thali" in t or "package" in t or "bulk" in t:
        shape = V.pick(f"a {t} one-pager: menu, per-head price, minimum order, and a WhatsApp booking line", f"{t} ka one-pager: menu, per-head price, minimum order, aur WhatsApp booking line")
    elif "program" in t or "yoga" in t or "class" in t:
        shape = V.pick(f"a {t} outline: batch timing, 4-week structure, intro price, and a parent-facing post", f"{t} ka outline: batch timing, 4-week structure, intro price, aur parent-facing post")
    else:
        shape = V.pick(f"a first draft of the {t}", f"{t} ka first draft")
    body = f"{V.pick('On it,', 'Chaliye,')} {S(L)} — {V.pick('here is what it would look like:', 'aisa dikhega:')} {shape}{anchor}. {V.pick('I will send the draft in 15 minutes; you only fill in the price.', 'Draft 15 minute mein bhejti hoon; aap sirf price bharenge.')} {V.pick('Sound right?', 'Theek hai?')}"
    return [Candidate(body, "open_ended", "effort_externalization", used, f"move to action on {t}: send draft")]

# ---------------------------------------------------------------- customer-facing

def _cust_ok(L, needed: tuple[str, ...]) -> bool:
    scope = L.get("cust.consent").value if L.get("cust.consent") else ()
    return any(n in scope for n in needed) or not scope

def h_recall_due(L, V):
    name, slots, svc = L.get("cust.name"), L.get("trg.available_slots"), L.get("trg.service_due")
    if not (name and _cust_ok(L, ("recall_reminders", "appointment_reminders"))):
        return []
    used = ["cust.name", "trg.service_due", "trg.available_slots", "id.name"]
    svc_t = (svc.display if svc else "").replace("_", " ")
    off = _active_offer(L)
    price = f" {off.display}." if off and "₹" in off.display else ""
    if off: used.append(off.id)
    labels = [s.get("label") for s in (slots.value if slots else []) if isinstance(s, dict)]
    slot_t = ""
    cta = "open_ended"
    if labels:
        opts = " / ".join(f"{i+1}) {l}" for i, l in enumerate(labels))
        slot_t = f" {V.pick('Open slots:', 'Slots khali hain:')} {opts}."
        cta = "slot_choice"
    last = L.get("cust.last_visit")
    lv = f" {V.pick('Your last visit was', 'Aapki last visit thi')} {last.display}." if last else ""
    if last: used.append("cust.last_visit")
    body = f"Hi {name.display}, {L.get('id.name').display} {V.pick('here.', 'se.')}{lv} {V.pick('Your', 'Aapka')} {svc_t} {V.pick('is due.', 'due hai.')}{price}{slot_t} {V.pick('Reply with a number or a time that suits you.', 'Number ya apna time reply karein.')}"
    return [Candidate(body, cta, "specificity", used, "recall booking with real slots", send_as="merchant_on_behalf", template_name="merchant_recall_v1")]

def h_trial_followup(L, V):
    name, td, opts = L.get("cust.name"), L.get("trg.trial_date"), L.get("trg.next_session_options")
    if not name:
        return []
    used = ["cust.name", "trg.trial_date", "trg.next_session_options", "id.name"]
    labels = [s.get("label") for s in (opts.value if opts else []) if isinstance(s, dict)]
    nxt = f" {V.pick('Next session:', 'Agla session:')} {labels[0]}." if labels else ""
    off = _active_offer(L)
    pr = f" {off.display}." if off else ""
    if off: used.append(off.id)
    body = f"Hi {name.display}, {L.get('id.name').display} {V.pick('here — good to have you at the trial on', 'se — trial pe aana accha laga')} {td.display if td else ''}.{nxt}{pr} {V.pick('Reply YES to hold that spot, or tell us a better time.', 'Spot hold karne ke liye YES reply karein, ya better time batayein.')}"
    return [Candidate(body, "binary", "reciprocity", used, "convert trial to first session", send_as="merchant_on_behalf", template_name="merchant_trial_followup_v1")]

def h_chronic_refill(L, V):
    name, mols, out, addr = L.get("cust.name"), L.get("trg.molecule_list"), L.get("trg.stock_runs_out_iso"), L.get("trg.delivery_address_saved")
    if not (name and mols):
        return []
    used = ["cust.name", "trg.molecule_list", "trg.stock_runs_out_iso", "id.name"]
    d = out.display[:10] if out else ""
    deliv = f" {V.pick('Home delivery to your saved address is on.', 'Saved address pe home delivery available hai.')}" if addr and addr.value else ""
    if addr: used.append("trg.delivery_address_saved")
    body = f"Hi {name.display}, {L.get('id.name').display} {V.pick('here. Your', 'se. Aapke')} {mols.display} {V.pick('stock runs out around', 'ka stock lagbhag')} {d}{V.pick('.', ' tak khatam hoga.')}{deliv} {V.pick('Reply YES to refill the same prescription, or send us the new one.', 'Same prescription refill ke liye YES reply karein, ya naya bhejein.')}"
    return [Candidate(body, "binary", "loss_aversion", used, "chronic refill before stock-out", send_as="merchant_on_behalf", template_name="merchant_refill_v1")]

def h_customer_lapsed(L, V):
    name, last, svc = L.get("cust.name"), L.get("cust.last_visit"), L.get("cust.last_service")
    if not (name and _cust_ok(L, ("promotional_offers", "recall_reminders", "winback_offers"))):
        return []
    used = ["cust.name", "id.name"]
    days = L.get("trg.days_since_last_visit")
    focus = L.get("trg.previous_focus")
    hook = ""
    if days: hook = f" {V.pick('It has been', '')} {days.display} {V.pick('days since your last session', 'din ho gaye aapki last session ko')}"; used.append("trg.days_since_last_visit")
    elif last: hook = f" {V.pick('Your last visit was', 'Aapki last visit thi')} {last.display}"; used.append("cust.last_visit")
    if svc: hook += f" ({svc.display})"; used.append("cust.last_service")
    if focus: hook += f"{V.pick(', when you were working on', ', jab aap')} {focus.display.replace('_', ' ')}{V.pick('', ' pe kaam kar rahe the')}"; used.append("trg.previous_focus")
    off = _active_offer(L)
    pr = f" {V.pick('Current offer:', 'Abhi offer:')} {off.display}." if off else ""
    if off: used.append(off.id)
    body = f"Hi {name.display}, {L.get('id.name').display} {V.pick('here.', 'se.')}{hook}.{pr} {V.pick('Reply YES and we will hold a slot this week — no pressure if the timing is off.', 'YES reply karein, is hafte slot hold kar denge — timing theek na ho toh koi baat nahi.')}"
    return [Candidate(body, "binary", "reciprocity", used, "winback lapsed customer with real history", send_as="merchant_on_behalf", template_name="merchant_winback_v1")]

def h_appointment_tomorrow(L, V):
    name = L.get("cust.name")
    if not (name and _cust_ok(L, ("appointment_reminders", "promotional_offers"))):
        return []
    used = ["cust.name", "id.name"]
    # payload is a placeholder in the dataset; do not invent a time.
    loc = L.get("id.locality")
    where = f" ({loc.display})" if loc else ""
    if loc: used.append("id.locality")
    body = f"Hi {name.display}, {L.get('id.name').display}{where} {V.pick('here — reminder that your appointment is tomorrow.', 'se — reminder, aapka appointment kal hai.')} {V.pick('Reply YES to confirm, or send a new time and we will move it.', 'Confirm karne ke liye YES reply karein, ya naya time bhejein.')}"
    return [Candidate(body, "binary", "binary_commitment", used, "confirm tomorrow's appointment", send_as="merchant_on_behalf", template_name="merchant_appt_reminder_v1")]

def h_wedding(L, V):
    name, wd, d2w, step = L.get("cust.name"), L.get("trg.wedding_date"), L.get("trg.days_to_wedding"), L.get("trg.next_step_window_open")
    if not (name and wd):
        return []
    used = ["cust.name", "trg.wedding_date", "trg.days_to_wedding", "trg.next_step_window_open", "id.name"]
    st = step.display.replace("_", " ") if step else "next step"
    body = f"Hi {name.display}, {L.get('id.name').display} {V.pick('here.', 'se.')} {d2w.display if d2w else ''} {V.pick('days to', 'din baaki')} {wd.display} — {V.pick('this is the window to start the', 'ab time hai')} {st}{V.pick('.', ' start karne ka.')} {V.pick('Reply YES and we will book your first session this week.', 'YES reply karein, is hafte pehla session book kar denge.')}"
    return [Candidate(body, "binary", "specificity", used, "wedding package next step", send_as="merchant_on_behalf", template_name="merchant_wedding_v1")]

HANDLERS = {
    "research_digest": h_research_digest, "regulation_change": h_regulation_change, "cde_opportunity": h_cde_opportunity,
    "perf_dip": h_perf_dip, "seasonal_perf_dip": h_seasonal_perf_dip, "perf_spike": h_perf_spike,
    "milestone_reached": h_milestone, "review_theme_emerged": h_review_theme, "renewal_due": h_renewal_due,
    "winback_eligible": h_winback, "dormant_with_vera": h_dormant, "curious_ask_due": h_curious_ask,
    "competitor_opened": h_competitor, "festival_upcoming": h_festival, "ipl_match_today": h_ipl,
    "supply_alert": h_supply_alert, "category_seasonal": h_category_seasonal, "gbp_unverified": h_gbp_unverified,
    "active_planning_intent": h_active_planning,
    "recall_due": h_recall_due, "trial_followup": h_trial_followup, "chronic_refill_due": h_chronic_refill,
    "customer_lapsed_soft": h_customer_lapsed, "customer_lapsed_hard": h_customer_lapsed,
    "appointment_tomorrow": h_appointment_tomorrow, "wedding_package_followup": h_wedding,
}

def tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", s).replace(" ,", ",").replace(" .", ".").replace(",.", ".").replace(" (2)", "")
    return s.strip()

def candidates(L: Ledger, kind: str, customer_facing: bool) -> list[Candidate]:
    h = HANDLERS.get(kind)
    if not h:
        return []
    V = Voice(L, customer_facing)
    out = h(L, V)
    for c in out:
        c.body = tidy(c.body)
        c.params = [L.get("id.salutation").display, kind]
        if c.send_as == "vera":
            c.template_name = f"vera_{kind}_v1"
    return out
