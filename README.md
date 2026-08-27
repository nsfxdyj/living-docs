# Living Docs

> An open-source, async-first knowledge base for small teams where documents are **alive**: they grow when people interact with them, fork into variants that evolve on their own, and wither away when forgotten.

<!-- Badges: wire these up once the repo is public.
[![CI](https://github.com/YOUR_ORG/living-docs/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/living-docs/actions/workflows/ci.yml)
-->
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

Existing knowledge bases treat documents as static files — written once, then left to rot. **Living Docs** turns every document into a living organism whose health reflects how much your team actually cares about it.

## Core concepts

- **Life System** — every document has a `vitality` score charged by interactions (view = +1, comment = +5, edit = +8, fork = +10) and decayed daily. Documents move through `thriving → stable → fading → withered`; withered documents sink to the bottom and fade to grey, and can be revived by fresh interaction. The team home page is a *document garden* that shows at a glance which knowledge is alive and which is dead.
- **Fork & Merge** *(planned, milestone M5)* — any document can be forked into a variant that evolves independently; the stronger variant can later be merged back into the trunk, natural-selection style, with an evolution tree visualizing every descendant.

## Features

**Implemented**

- Email/password registration and login (JWT, argon2 password hashing)
- Workspaces with owner/member roles and shareable invite links (7-day expiry)
- Document CRUD: Markdown content, tags, title search (`LIKE`), status and trunk/fork filtering
- Split-pane Markdown editor with live preview, syntax-highlighted code blocks (markdown-it + highlight.js), and DOMPurify-sanitized rendering
- Image attachments: upload (png/jpg/gif/webp, ≤ 2 MB, magic-byte verified) and inline embedding in documents
- Vitality hooks: views and edits record `Interaction` events and charge document vitality
- One-level comments on documents (+5 vitality per comment); authors or workspace owners can delete
- In-app notifications (comments, merge requests, merge decisions) with REST read markers and a live SSE stream
- Single-container deployment: the backend serves the built frontend and the API

**Roadmap** (see `PLAN.md` for the full milestone plan)

- M4 — full vitality engine: daily decay job (APScheduler), status transitions, revive, garden home page
- M5 — fork & merge with diff preview and evolution tree visualization

## Screenshots

**The document garden** — every document is a plant: size and color reflect vitality, withered documents gray out.

![Document garden](docs/screenshots/garden.png)

**Document view** — life status badge, vitality counter, tags and the comment section that charges the document.

![Document view](docs/screenshots/document.png)

**Evolution tree** — forks form a tree of variants; node color = life status, size = vitality.

![Evolution tree](docs/screenshots/evolution-tree.png)

## Quick start (Docker)

The only thing you need is Docker:

```sh
docker compose up --build
```

Then open http://localhost:8000 — the backend serves the built frontend and the API. The SQLite database is stored in the `living-docs-data` volume.

## Deploy to Render

The repo ships a [Render Blueprint](https://render.com/docs/blueprint-spec) (`render.yaml`), so a hosted demo is a few clicks:

1. Push this repository to GitHub.
2. In the Render dashboard: **New → Blueprint**, select the repo, apply.
3. Render builds the root `Dockerfile` and generates `LIVING_DOCS_SECRET_KEY` automatically.

Free-tier caveats:

- **Cold starts** — free web services spin down after inactivity; the first request after idle can take ~30–60 s.
- **Ephemeral data** — free services cannot attach disks, so the SQLite database and uploaded attachments live on the container filesystem (`/tmp`) and **reset on every deploy or restart**. Fine for a public demo; for a persistent instance use a paid plan and add a disk mounted at `/data`, then point `LIVING_DOCS_DATABASE_URL` / `LIVING_DOCS_ATTACHMENTS_DIR` there.

## Local development

**Backend** (Python 3.12+):

```sh
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload   # http://localhost:8000
python -m pytest                # run the test suite
```

**Frontend** (Node 20+):

```sh
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
npm run build                   # production build into frontend/dist
```

## Configuration

All settings are environment variables with the `LIVING_DOCS_` prefix:

| Variable | Default | Description |
|---|---|---|
| `LIVING_DOCS_DATABASE_URL` | `sqlite:///./living_docs.db` | SQLAlchemy database URL |
| `LIVING_DOCS_STATIC_DIR` | `static` | Directory with the built frontend (served at `/`) |
| `LIVING_DOCS_SECRET_KEY` | `dev-only-secret-change-me` | JWT signing key — **set this in production** |
| `LIVING_DOCS_ATTACHMENTS_DIR` | `data/attachments` | Directory where uploaded images are stored |
| `LIVING_DOCS_MAX_UPLOAD_BYTES` | `2097152` (2 MB) | Maximum size of a single uploaded attachment |

## API overview

All endpoints except `/api/health`, `/api/auth/register` and `/api/auth/login` require an `Authorization: Bearer <token>` header. Workspace-scoped endpoints additionally require membership in that workspace.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/auth/register` | Register (first user gets a default workspace) |
| `POST` | `/api/auth/login` | Log in, returns a JWT |
| `GET` | `/api/auth/me` | Current user profile |
| `POST` | `/api/workspaces` | Create a workspace |
| `GET` | `/api/workspaces` | List my workspaces |
| `GET` | `/api/workspaces/{id}` | Workspace details incl. members |
| `POST` | `/api/workspaces/{id}/invites` | Create an invite link (owner only) |
| `POST` | `/api/workspaces/join` | Join a workspace via invite token |
| `POST` | `/api/workspaces/{id}/documents` | Create a document (`title`, `content_md`, `tags`) |
| `GET` | `/api/workspaces/{id}/documents` | List documents; `?q=` title search, `?status=` filter, `?parent=null` for trunk docs |
| `GET` | `/api/documents/{id}` | Document details (records a `view` interaction, +1 vitality) |
| `PATCH` | `/api/documents/{id}` | Edit a document (any member; records an `edit` interaction, +8 vitality) |
| `DELETE` | `/api/documents/{id}` | Delete a document (author or workspace owner only) |
| `POST` | `/api/documents/{id}/attachments` | Upload an image (multipart, png/jpg/gif/webp, ≤ 2 MB) |
| `GET` | `/api/attachments/{filename}` | Download an attachment |
| `POST` | `/api/documents/{id}/comments` | Comment on a document (≤ 2000 chars; records a `comment` interaction, +5 vitality; notifies the author) |
| `GET` | `/api/documents/{id}/comments` | List a document's comments, oldest first |
| `DELETE` | `/api/comments/{id}` | Delete a comment (author or workspace owner only) |
| `GET` | `/api/notifications` | My notifications, newest first (max 50) |
| `POST` | `/api/notifications/{id}/read` | Mark one notification as read |
| `POST` | `/api/notifications/read-all` | Mark all my notifications as read |
| `GET` | `/api/notifications/stream` | SSE live stream of new notifications (`text/event-stream`; accepts `?token=` because EventSource cannot send headers) |

Interactive API docs (Swagger UI) are available at `/docs` when the backend is running.

## Project structure

```
living-docs/
├── docker-compose.yml        # single-service deployment (app + data volume)
├── Dockerfile                # multi-stage: builds frontend, serves via backend
├── render.yaml               # Render Blueprint (one-click hosted demo)
├── PLAN.md                   # product plan and milestone roadmap
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, router wiring, static hosting
│   │   ├── config.py         # LIVING_DOCS_* settings (pydantic-settings)
│   │   ├── db.py             # engine, session factory, declarative base
│   │   ├── models/           # SQLAlchemy ORM models (users, docs, vitality…)
│   │   ├── schemas.py        # Pydantic request/response schemas
│   │   ├── security.py       # argon2 hashing + JWT helpers
│   │   ├── notify.py         # notification persistence + in-process SSE fan-out
│   │   └── api/              # routers: auth, workspaces, documents, evolution,
│   │                         #   comments, notifications, attachments, health
│   └── tests/                # pytest suite (TestClient, in-memory SQLite)
└── frontend/
    └── src/
        ├── api/              # fetch wrapper (client.ts) + shared types
        ├── stores/           # Pinia auth + notifications stores
        ├── router/           # Vue Router with auth guard
        ├── utils/markdown.ts # markdown-it + highlight.js + DOMPurify
        └── views/            # Home, Login, Register, Join, Workspace,
                              #   DocumentView, DocumentEditView
```

## Testing

```sh
cd backend
python -m pytest        # auth, workspaces, documents, attachments, health
```

The suite runs against an in-memory SQLite database and a temporary attachments directory, so it never touches your local data.

## Contributing

Contributions are welcome! Please open an issue to discuss larger changes first, keep PRs focused on a single concern, and make sure `python -m pytest` (backend) and `npm run build` (frontend) pass. A formal `CONTRIBUTING.md` will be added in a later milestone.

## License

[Apache-2.0](LICENSE) — copyright 2026 nsfxdyj.
