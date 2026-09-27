# Vera AI Challenge — START HERE

This folder is a ready-to-run FastAPI submission for the magicpin Vera AI Challenge.

## What you have
- `bot.py` — required `compose()` function + FastAPI app
- `vera/` — deterministic decision engine and conversation handler
- `submission.jsonl` — 30 canonical outputs already generated
- `run_local.py` — local smoke test using the challenge dataset
- `requirements.txt` — Python packages
- `render.yaml` — optional Render deployment configuration

## IMPORTANT
This solution is deterministic and does not need an LLM API key.

## 1. Install Python
Use Python 3.11+ (3.13 recommended).

## 2. Open terminal in this folder
Windows:
`cd path\\to\\vera_ready`

## 3. Install packages
`python -m pip install -r requirements.txt`

## 4. Start the bot
`uvicorn bot:app --host 0.0.0.0 --port 8080`

Keep this terminal open.

## 5. Test in your browser
Open:
`http://127.0.0.1:8080/v1/healthz`

You should see JSON containing `"status":"ok"`.

Also open:
`http://127.0.0.1:8080/docs`

This is FastAPI's interactive API page.

## 6. Test the challenge dataset
From a SECOND terminal:
`python run_local.py "PATH_TO_YOUR_MAGICPIN_CHALLENGE_FOLDER"`

Example:
`python run_local.py "C:\\Users\\YourName\\Downloads\\magicpin-ai-challenge"`

The script generates the expanded dataset automatically if needed and checks the canonical pairs plus replay scenarios.

## 7. Deploy
The easiest beginner route is Render + GitHub. See `BEGINNER_GUIDE.md`.

## 8. Submit
After deployment, test:
`https://YOUR-SERVICE.onrender.com/v1/healthz`

Then submit the base URL (without `/v1/healthz`) in the challenge portal.
