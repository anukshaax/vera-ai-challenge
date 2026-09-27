"""Beginner-friendly local tester for the magicpin Vera challenge.

Usage:
    python run_local.py "C:\\path\\to\\magicpin-ai-challenge"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from bot import app, compose


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python run_local.py \"PATH_TO/magicpin-ai-challenge\"")
        return 1

    root = Path(sys.argv[1]).expanduser().resolve()
    if not (root / "challenge-brief.md").exists():
        print(f"ERROR: I cannot find challenge-brief.md inside: {root}")
        return 1

    expanded = root / "dataset" / "expanded"
    if not (expanded / "test_pairs.json").exists():
        print("Creating the expanded challenge dataset...")
        subprocess.run(
            [sys.executable, str(root / "dataset" / "generate_dataset.py"), "--out", str(expanded)],
            check=True,
        )

    client = TestClient(app)

    def push(scope: str, cid: str, payload: dict, version: int = 1):
        r = client.post("/v1/context", json={
            "scope": scope,
            "context_id": cid,
            "version": version,
            "payload": payload,
            "delivered_at": "2026-04-26T10:00:00Z",
        })
        data = r.json()
        if not data.get("accepted"):
            raise RuntimeError(f"Context push failed: {data}")

    # Load and push categories.
    categories = {}
    for f in (root / "dataset" / "categories").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        categories[data["slug"]] = data
        push("category", data["slug"], data)

    stores = {"merchants": {}, "customers": {}, "triggers": {}}
    for kind, folder, key in [
        ("merchant", "merchants", "merchant_id"),
        ("customer", "customers", "customer_id"),
        ("trigger", "triggers", "id"),
    ]:
        for f in (expanded / folder).glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            stores[folder][data[key]] = data
            push(kind, data[key], data)

    health = client.get("/v1/healthz").json()
    print("\nHEALTH:", health)

    pairs = json.loads((expanded / "test_pairs.json").read_text(encoding="utf-8"))["pairs"]
    outputs = []
    sent = 0
    failed = 0

    print("\nCANONICAL 30-PAIR TEST")
    for pair in pairs:
        merchant = stores["merchants"][pair["merchant_id"]]
        trigger = stores["triggers"][pair["trigger_id"]]
        customer = stores["customers"].get(pair["customer_id"]) if pair.get("customer_id") else None
        category = categories[merchant["category_slug"]]
        result = compose(category, merchant, trigger, customer)
        outputs.append({"test_id": pair["test_id"], **result})
        if result.get("body"):
            sent += 1
        else:
            failed += 1
        print(f"{pair['test_id']}: {'SEND' if result.get('body') else 'SKIP'} | {result.get('body','')[:110]}")

    out_file = Path("submission.jsonl")
    out_file.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in outputs) + "\n",
        encoding="utf-8",
    )

    print(f"\nWrote {out_file.resolve()}")
    print(f"Canonical messages: {sent}/30 sent; {failed}/30 skipped")

    # Simple replay checks.
    print("\nREPLAY CHECKS")
    target = next((p for p in pairs if p["test_id"] == "T24"), None)
    if target:
        tick = client.post("/v1/tick", json={
            "now": "2026-04-26T10:30:00Z",
            "available_triggers": [target["trigger_id"]],
        }).json()
        if tick.get("actions"):
            cid = tick["actions"][0]["conversation_id"]
            auto = "Thank you for contacting us! Our team will respond shortly."
            for turn, expected in [(2, "send"), (3, "wait"), (4, "end")]:
                reply = client.post("/v1/reply", json={
                    "conversation_id": cid,
                    "merchant_id": target["merchant_id"],
                    "from_role": "merchant",
                    "message": auto,
                    "received_at": "2026-04-26T10:35:00Z",
                    "turn_number": turn,
                }).json()
                print(f"auto-reply turn {turn}: {reply.get('action')} (expected {expected})")

    print("\nDONE. If all three auto-reply actions match SEND -> WAIT -> END, that replay fix is working.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
