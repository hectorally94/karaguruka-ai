# Karaguruka AI

AI assistant for bank call centers: a customer assistant (voice and text), guided flows, handoff to agents, an agent desk, and an admin dashboard where staff upload the documents the assistant answers from (RAG).

Stack: FastAPI, React with Tailwind CSS, PostgreSQL with pgvector in Docker. The bank and all its data are fictional.

## Run it

Secrets live in `.env`, which git ignores. It holds the database URL, `ADMIN_PASSWORD` and `AGENT_PASSWORD`.

```bash
# 1. Database
docker compose up -d --wait

# 2. Backend, http://127.0.0.1:8000 (API docs at /docs)
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.init_db
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --port 8000

# 3. Frontend, http://localhost:5173
cd frontend
npm install
npm run dev
```

Scanned documents need `tesseract` and `pdftoppm` installed on the server.

## AI keys

Set these in `.env`, then restart the backend:

- `ANTHROPIC_API_KEY`: Claude writes answers from the documents and catches requests the keyword rules miss. Without it, the assistant quotes the best-matching passage.
- `VOYAGE_API_KEY`: adds semantic search. Without it, search uses keywords. Documents indexed before the key was added need to be replaced to get semantic search.

## Tests

```bash
cd backend && .venv/bin/python -m pytest
```

They create their own `karaguruka_test` database in the Docker container and never touch the demo data. They do not call Claude or Voyage AI.

## Mocked in this version

- Phone calls are simulated in the browser. There is no connection to a phone line.
- There is no connection to the bank's systems, so no account data and no real card blocking. Stolen card requests go to an agent as urgent.
- Credit rates and the card hotline are set in `backend/app/settings.py`.
- Voice uses the browser's speech features, best in Chrome, which sends microphone audio to Google for recognition. Review this before using real customer calls.

## Before production

Replace the shared passwords with individual accounts, serve over HTTPS with `SECURE_COOKIES=1`, move document processing to a job queue, and review data retention and banking compliance.

## Client profiles

`BANK_PROFILE` in `.env` points to a JSON file with a client's name, currency, urgent contact, credit products, documents and example conversations. Profiles live in `backend/profiles/`, which git ignores. Without one, the app uses the fictional bank.
