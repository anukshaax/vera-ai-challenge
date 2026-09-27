# Vera AI Challenge — Baby-Step Guide

You do NOT need to understand all the Python code before starting.

## PART A — What are we building?

Think of Vera as a small website that receives information and replies with JSON.

The challenge judge talks to your bot using five doors (API endpoints):

1. `/v1/healthz` = "Are you alive?"
2. `/v1/metadata` = "Who are you?"
3. `/v1/context` = "Here is some information. Remember it."
4. `/v1/tick` = "Something happened. What should Vera send?"
5. `/v1/reply` = "The merchant replied. What should Vera do next?"

The ready-made code already contains these doors.

---

## PART B — First run on your computer

### Step 1: Install Python

Install Python 3.11 or newer. Python 3.13 is recommended.

During Windows installation, tick:

`Add Python to PATH`

### Step 2: Unzip my file

Unzip `vera_submission_ready.zip`.

You will see a folder containing:

- `bot.py`
- `vera/`
- `requirements.txt`
- `run_local.py`
- `submission.jsonl`

### Step 3: Open Command Prompt

Go inside that folder.

Example:

`cd C:\Users\YourName\Downloads\vera_submission_ready`

### Step 4: Install the required packages

Run:

`python -m pip install -r requirements.txt`

Wait until it finishes.

### Step 5: Start Vera

Run:

`uvicorn bot:app --host 0.0.0.0 --port 8080`

DO NOT close this window.

If Windows asks about firewall access, allow it for private networks.

### Step 6: Check that Vera is alive

Open Chrome and enter:

`http://127.0.0.1:8080/v1/healthz`

You should see something similar to:

`{"status":"ok", ...}`

Congratulations: your bot is running locally.

### Step 7: See the API visually

Open:

`http://127.0.0.1:8080/docs`

You will see FastAPI's Swagger page. You can expand each endpoint there.

---

## PART C — Test against the actual challenge dataset

You already have the original challenge ZIP.

### Step 8: Extract the original challenge ZIP

Extract `magicpin-ai-challenge.zip` somewhere easy, for example:

`C:\Users\YourName\Downloads\magicpin-ai-challenge`

Inside it you should see:

- `challenge-brief.md`
- `challenge-testing-brief.md`
- `dataset`
- `examples`
- `judge_simulator.py`

### Step 9: Open a SECOND Command Prompt

Leave the first Command Prompt running Vera.

In the second Command Prompt, go to the ready bot folder:

`cd C:\Users\YourName\Downloads\vera_submission_ready`

### Step 10: Run the local test

Replace the path below with your actual path:

`python run_local.py "C:\Users\YourName\Downloads\magicpin-ai-challenge"`

The script will:

1. create the expanded dataset if it does not exist;
2. load categories, merchants, customers and triggers;
3. run all 30 canonical pairs;
4. create/update `submission.jsonl`;
5. test the auto-reply conversation.

You want the replay result:

`turn 2 -> send`

`turn 3 -> wait`

`turn 4 -> end`

---

## PART D — What the important files mean

### `bot.py`

This is the main door.

The challenge can directly call:

`compose(category, merchant, trigger, customer)`

It also exposes the HTTP server.

### `vera/ledger.py`

Collects facts from the supplied data.

Think of it as Vera's notebook.

### `vera/beats.py`

Contains the message styles for different triggers.

For example:

- performance dip
- performance spike
- festival
- research
- recall
- customer winback

### `vera/planner.py`

Chooses which possible message is best.

Think:

`many possible messages -> choose one`

### `vera/verify.py`

Checks that Vera did not make up numbers or accidentally send a URL/repeated message.

### `vera/fsm.py`

Handles replies from the merchant.

This is where we detect:

- YES / let's do it
- not interested
- auto-replies
- hostile replies
- off-topic questions

### `vera/api.py`

Creates the five required HTTP endpoints.

---

## PART E — Deploy it so the judge can access it

The challenge needs a PUBLIC URL.

A beginner-friendly route is:

`GitHub -> Render -> public HTTPS URL`

### Step 11: Create a GitHub repository

Go to GitHub and create a new repository.

Example name:

`magicpin-vera-bot`

You can keep it private unless the challenge requires otherwise.

### Step 12: Upload the contents of `vera_submission_ready`

IMPORTANT:

Upload `bot.py`, `vera/`, `requirements.txt`, `.python-version`, `render.yaml`, etc. directly into the repository root.

Do NOT create:

`repo/vera_submission_ready/bot.py`

unless you plan to set that as Render's Root Directory.

### Step 13: Open Render

Create a Render account and connect GitHub.

Choose:

`New -> Web Service`

Select your GitHub repository.

### Step 14: Render settings

Use:

Language:
`Python 3`

Build Command:
`pip install -r requirements.txt`

Start Command:
`uvicorn bot:app --host 0.0.0.0 --port $PORT`

Health Check Path:
`/v1/healthz`

Choose a plan allowed by your challenge/deadline.

### Step 15: Deploy

Click Create Web Service.

Wait for the deploy to finish.

Render will give you a URL similar to:

`https://your-bot-name.onrender.com`

### Step 16: TEST THE PUBLIC URL

Open:

`https://your-bot-name.onrender.com/v1/healthz`

You need to see:

`status: ok`

Do this test BEFORE submitting the challenge.

---

## PART F — Submit

The challenge asks for the public bot URL.

Submit the BASE URL:

`https://your-bot-name.onrender.com`

Not:

`https://your-bot-name.onrender.com/v1/healthz`

The judge will add `/v1/...` itself.

---

## VERY IMPORTANT — Do not do these things

1. Do not put API keys or passwords inside GitHub.
2. Do not change the five endpoint names.
3. Do not remove `submission.jsonl`.
4. Do not invent merchant numbers in messages.
5. Do not add URLs to generated WhatsApp messages.
6. Do not close the terminal while testing locally.
7. Do not submit until `/v1/healthz` works publicly.

---

## If something goes wrong

### `python is not recognized`
Install Python and enable `Add Python to PATH`, then reopen Command Prompt.

### `No module named fastapi`
Run:

`python -m pip install -r requirements.txt`

### `Address already in use`
Another server is using port 8080. Stop it, or use:

`uvicorn bot:app --host 0.0.0.0 --port 8081`

Then open port 8081 in the browser.

### Render says the app failed to start
Check the Render logs. The start command must be exactly:

`uvicorn bot:app --host 0.0.0.0 --port $PORT`

### Health check works locally but not on Render
Make sure the Render service is a Web Service and that the app binds to `0.0.0.0` and `$PORT`.
