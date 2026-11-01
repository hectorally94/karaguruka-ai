# Karaguruka AI demo database

This package lets you test the app without loading and indexing documents yourself.

## What's inside

- `karaguruka-demo.sql`: 9 documents, 30 indexed passages with their vectors (Voyage `voyage-3.5`, size 1024), and 7 example conversations with 3 example tickets.
- `profile/profile.json`: the demo's bank name, currency, urgent contact and credit products.

**This is an unofficial demonstration, not affiliated with or validated by BANCOBU.** It combines public information from bancobu.com, read on 2026-10-31 and possibly out of date, with invented documents marked `[TEST]`. Don't rely on it for real banking decisions, and don't enter real banking data.

The package contains no passwords or API keys. You choose your own below.

## Restore with Docker (recommended)

Requires Docker, Python 3.12 and Node.js. Run these from the root of the repository.

**1. Create `.env`** with your own passwords:

```bash
POSTGRES_PASSWORD=choose-a-password
DATABASE_URL=postgresql://karaguruka:choose-a-password@127.0.0.1:5433/karaguruka
ADMIN_PASSWORD=choose-an-admin-password
AGENT_PASSWORD=choose-an-agent-password
SESSION_SECRET=a-long-random-text
BANK_PROFILE=profiles/bancobu/profile.json
# Optional, see "AI keys" below
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
```

**2. Copy the profile:**

```bash
mkdir -p backend/profiles/bancobu
cp /path/to/this/package/profile/profile.json backend/profiles/bancobu/
```

**3. Start an empty database and restore:**

```bash
docker compose up -d --wait
docker exec -i karaguruka-db psql -U karaguruka -d karaguruka -v ON_ERROR_STOP=1 < /path/to/this/package/karaguruka-demo.sql
```

If you already have data in that database, the restore fails. To start again and **delete everything in it**, run `docker compose down -v`, then repeat this step.

**4. Check it:**

```bash
docker exec karaguruka-db psql -U karaguruka -d karaguruka -c "select count(*) as passages, count(embedding) as with_vectors from chunks"
```

You should see `30` and `30`.

**5. Start the app.** Skip `init_db` and `seed`, because the data is already there.

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# In a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Restore into your own PostgreSQL

You need PostgreSQL 17 with the `pgvector` extension available, and a user allowed to create extensions (`vector`, `unaccent`, `pgcrypto`).

```bash
createdb karaguruka
psql -d karaguruka -v ON_ERROR_STOP=1 -f karaguruka-demo.sql
```

Then set `DATABASE_URL` in `.env` to your server and follow steps 2 and 5 above.

## AI keys

The stored vectors work only with the model that made them. To use them, each new question must also go through Voyage `voyage-3.5`.

| Keys set | What you get |
|---|---|
| None | Keyword search. The assistant quotes the best passage, with no AI writing, no semantic search and no AI-generated summaries |
| `VOYAGE_API_KEY` | Adds semantic search, using the stored vectors |
| `ANTHROPIC_API_KEY` | Claude writes the answers from the passages |
| Both | The full experience |

With a different embedding model, the stored vectors can't be used. See `docs/local-models.md`, phase 4.
