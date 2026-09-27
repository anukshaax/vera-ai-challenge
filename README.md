# Vera Ledger Bot — magicpin AI Challenge

A deterministic, LLM-free merchant assistant designed around the challenge's five scoring dimensions: specificity, category fit, merchant fit, decision quality, and engagement compulsion.

## Approach
1. Mine only facts present in category, merchant, trigger, and customer contexts into a claim ledger.
2. Route each trigger to a category-aware handler.
3. Generate several candidate messages from verified claims.
4. Reject candidates containing unsupported numbers, URLs, taboo vocabulary, preambles, or repeats.
5. Rank remaining candidates with a deterministic rubric mirror and rotate engagement levers.
6. Handle multi-turn replies with a small finite-state machine: auto-reply, intent-to-action, decline/hostility, questions, and ambiguity.
7. Deduplicate using both trigger IDs and suppression keys.

## Trade-offs
The bot favors factual, deterministic messages over free-form LLM prose. This makes it less stylistically varied, but substantially reduces hallucination and non-determinism. It also lets the same code adapt to newly injected contexts and triggers.

## Additional context that would help
Post history, review text, booking availability, and merchant-reply outcomes would improve action selection further.

## Run
`pip install -r requirements.txt`

`uvicorn bot:app --host 0.0.0.0 --port 8080`

## Required endpoints
- `GET /v1/healthz`
- `GET /v1/metadata`
- `POST /v1/context`
- `POST /v1/tick`
- `POST /v1/reply`
