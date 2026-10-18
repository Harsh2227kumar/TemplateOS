# TemplateOS

TemplateOS turns an institution's Word templates (meeting circulars, minutes,
notices) into fill-in forms. An admin uploads a `.docx`, marks its blanks as
fields, and users fill a form to get a finished DOCX or PDF that keeps the
original layout and formatting.

## Features

- **Template pipeline:** upload a DOCX, detect or clean its blanks into
  `{{ placeholders }}`, then configure fields (type, required, validation,
  section, example, AI on/off).
- **Draft forms:** dynamic forms per template with validation that matches
  the backend, list fields, saved drafts (Ctrl+S) and a "Final document" panel.
- **Document generation:** DOCX rendered with docxtpl from the saved values;
  PDF through Gotenberg (or a local LibreOffice), with retry.
- **AI writing (AWS Bedrock):** field suggestions while setting up a
  template, and per-field or whole-form rewrites (fix grammar, professional,
  concise, formal, expand).
- **Access control:** roles from super admin to student, organizations and
  departments, and templates scoped to an audience.

## Repository layout

| Path | What it is |
| --- | --- |
| [`backend/`](backend/README.md) | FastAPI + SQLAlchemy + Alembic API (Python) |
| [`frontend/`](frontend/README.md) | React + TypeScript + Vite app |
| `docker-compose.yml` | Gotenberg for PDF conversion (the only Docker service) |
| `.env.example` | Every setting, documented; copy it to `.env` |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Branching, pull request and review rules |
| [`project-change-tracker.md`](project-change-tracker.md) | Change log of every pushed checkpoint |

## Quick start

Prerequisites: Python 3.12+, Node.js 22.18+ (the tests run TypeScript natively), a PostgreSQL database (Neon works),
and Docker if you want PDF output.

```bash
# 1. Settings: copy, then set DATABASE_URL and JWT_SECRET_KEY
cp .env.example .env

# 2. Backend (from backend/)
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload        # http://localhost:8000

# 3. Frontend (from the repository root, in a second terminal)
npm install
npm run dev:frontend                 # http://localhost:5173

# 4. Optional: PDF conversion
docker compose up -d gotenberg       # then set GOTENBERG_URL=http://localhost:3000
```

Open the app at `http://localhost:5173` and point it at the API on
`http://localhost:8000` (not `127.0.0.1`), so the session cookies work.
`.env` is read when the backend starts: restart it after any change.

Seeding demo users and templates, AI and PDF settings are described in the
[backend README](backend/README.md).

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
npm run test -w frontend && npm run build:frontend
```

GitHub Actions runs the same checks on every pull request.

## Contributing

Never push to `main`, `dev`, `frontend` or `backend` directly. Frontend-only
work goes through `frontend`, backend-only work through `backend`, and
cross-stack or repository-wide work through `dev`. See
[CONTRIBUTING.md](CONTRIBUTING.md).
