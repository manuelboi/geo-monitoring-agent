# Synthetic GEO monitoring agent

A small analytics agent that answers questions about synthetic GEO monitoring data. It uses PostgreSQL, a Python API,
and Docker Compose.

## Run

```sh
cp .env.example .env
# Set unique POSTGRES_PASSWORD and DB_READONLY_PASSWORD values in .env.
# Set LLM_API_KEY to enable chat requests.
docker compose up --build
```

Generate a different strong password for each database role (for example, `openssl rand -hex 32`) and replace the
empty values in `.env`. Compose refuses to start if either password is missing. Do not reuse passwords from another
environment.

The `agent` container loads the CSV files into PostgreSQL and starts the API on port 8000.

```sh
curl -s localhost:8000/health

curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Qual è la visibilità di Sample Client?"}'
```

The data pack is entirely synthetic. It has no client-derived names, text, metrics, URLs, or contact details. All
source domains use the reserved `.example` domain. Regenerate it with:

```sh
python tools/generate_synthetic_data.py
```

## Checks

```sh
docker compose exec agent python -m pytest -q
docker compose exec agent python -m app.data.profile
```

The tests use the database but do not call the Gemini API.

## Project layout

- `agent/app/`: API, agent loop, database access, metrics, SQL guard, and data loader.
- `agent/eval/`: synthetic evaluation questions and model comparison runner.
- `agent/tests/`: unit and database-backed tests.
- `data/csv/`: synthetic input tables loaded at startup.
- `tools/generate_synthetic_data.py`: deterministic offline data generator using only the Python standard library.

To enable model evaluation, set `LLM_API_KEY` in `.env`. Never commit `.env` or use real client data in this repository.
