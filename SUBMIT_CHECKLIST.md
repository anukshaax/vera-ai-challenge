# FINAL SUBMISSION CHECKLIST

Before submitting, confirm:

- [ ] `http://127.0.0.1:8080/v1/healthz` works locally.
- [ ] `http://127.0.0.1:8080/docs` opens locally.
- [ ] `run_local.py` finishes with 29/30 messages (T08 is intentionally skipped because its generated trigger has no verified payload).
- [ ] Auto-reply replay is SEND -> WAIT -> END.
- [ ] GitHub repository contains `bot.py` at the repository root.
- [ ] GitHub repository contains the `vera/` folder.
- [ ] `requirements.txt` is present.
- [ ] Render Start Command is `uvicorn bot:app --host 0.0.0.0 --port $PORT`.
- [ ] Public `/v1/healthz` returns `status: ok`.
- [ ] You submit the BASE URL, for example `https://your-name.onrender.com`.
