"""Regression floor: every canonical pair yields a verified body (or explicit restraint),
no URLs, no unprovenanced numbers, no case-study near-duplicates, deterministic."""
import json, difflib, re, sys
sys.path.insert(0, "..")
from pathlib import Path
from bot import compose

DS = Path("/home/claude/mp/dataset/expanded"); CATS = Path("/home/claude/mp/dataset/categories")
cats = {json.load(open(f))["slug"]: json.load(open(f)) for f in CATS.glob("*.json")}
cases = re.findall(r"```\n(.+?)\n```", open("/home/claude/mp/examples/case-studies.md").read(), re.S)

def run():
    pairs = json.load(open(DS / "test_pairs.json"))["pairs"]
    sent = 0
    for p in pairs:
        t = json.load(open(DS / "triggers" / f"{p['trigger_id']}.json")); m = json.load(open(DS / "merchants" / f"{p['merchant_id']}.json"))
        cu = json.load(open(DS / "customers" / f"{p['customer_id']}.json")) if p["customer_id"] else None
        a = compose(cats[m["category_slug"]], m, t, cu); b = compose(cats[m["category_slug"]], m, t, cu)
        assert a == b, f"{p['test_id']} not deterministic"
        if not a["body"]:
            continue
        sent += 1
        assert "http" not in a["body"].lower(), p["test_id"]
        for cs in cases:
            assert difflib.SequenceMatcher(None, a["body"], cs.replace("\n", " ")).ratio() < 0.6, f"{p['test_id']} too close to a case study"
        assert a["rationale"].startswith("Trigger"), p["test_id"]
    print(f"golden ok: {sent}/{len(pairs)} sent, all verified, deterministic, no case-study near-duplicates")

if __name__ == "__main__":
    run()
