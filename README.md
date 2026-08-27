# Living Docs

An open-source, async-first knowledge base for small teams where documents are
**alive**: they grow when people interact with them, fork into variants that
evolve on their own, and wither away when forgotten.

## Features

- **Life system** — every document has a `vitality` score charged by views,
  edits, comments and forks, decaying daily; neglected documents wither and
  sink to the bottom of the garden
- **Fork & merge** — fork any document into a variant, let it evolve, then
  merge the winner back, natural-selection style
- **Document garden** — the team home page is a garden where healthy documents
  are green and withered ones fade to grey
- **Async by design** — comments plus SSE notifications, no real-time editing

> Status: **M1 skeleton**. The app boots, serves a login page and a health
> endpoint; the life engine and collaboration features land in later
> milestones (see `PLAN.md`).

## Tech stack

- Backend: FastAPI (Python 3.12), SQLAlchemy 2.x, SQLite
- Frontend: Vue 3, Vite, TypeScript, Pinia, Vue Router
- Deploy: single Docker image (multi-stage build) + `docker-compose.yml`

## Quickstart

```sh
docker compose up --build
```

Then open http://localhost:8000 — the backend serves the built frontend and
the API (`GET /api/health` returns `{"status":"ok"}`). The SQLite database is
stored in the `living-docs-data` volume.

## Local development

Backend:

```sh
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload   # http://localhost:8000
python -m pytest                # run tests
```

Frontend:

```sh
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
npm run build
```

## Configuration

Environment variables (prefix `LIVING_DOCS_`):

| Variable | Default | Description |
|---|---|---|
| `LIVING_DOCS_DATABASE_URL` | `sqlite:///./living_docs.db` | SQLAlchemy database URL |
| `LIVING_DOCS_STATIC_DIR` | `static` | Directory with the built frontend |

## License

[Apache-2.0](LICENSE) — copyright 2026 nsfxdyj.
