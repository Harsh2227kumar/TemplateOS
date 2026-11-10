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
- **Preview, rich text and versions:** a read-only preview with
  completeness; rich text (bold, lists, links) in paragraph fields that
  reaches the DOCX/PDF; every Generate is a new version with its own files,
  history, downloads and restore.
- **Word file editor (optional, ONLYOFFICE Docs):** edit the real Word file
  in the browser. "Customize for me" makes a private copy of a template
  (for example to add a field), template files keep a revision history, and
  a generated document can be fixed by hand as a new "Edited manually"
  version.
- **Download history and audit log:** every download is recorded (a
  "Downloads" page and per-document history); admins get a searchable audit
  log of who did what in their organization or department, with CSV export.
- **Access control:** roles from super admin to student, organizations and
  departments, and templates scoped to an audience.

## Repository layout

| Path | What it is |
| --- | --- |
| [`backend/`](backend/README.md) | FastAPI + SQLAlchemy + Alembic API (Python) |
| [`frontend/`](frontend/README.md) | React + TypeScript + Vite app |
| `docker-compose.yml` | Gotenberg for PDF conversion; optional local PostgreSQL (`db` profile) and ONLYOFFICE Docs for the Word editor (`editor` profile) |
| `scripts/` | One-shot setup scripts for Windows, macOS and Ubuntu |
| `.env.example` | Every setting, documented; copy it to `.env` |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Branching, pull request and review rules |
| [`project-change-tracker.md`](project-change-tracker.md) | Change log of every pushed checkpoint |

## Setup

### What you need

| Software | Version | Used for |
| --- | --- | --- |
| [Git](https://git-scm.com/downloads) | any recent | getting the code |
| [Python](https://www.python.org/downloads/) | 3.12 or newer | the backend (FastAPI) |
| [Node.js](https://nodejs.org/) (comes with npm) | 22.18 or newer (24 LTS recommended) | the frontend (Vite); the tests run TypeScript natively |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose plugin (Ubuntu) | Compose v2 | Gotenberg (PDF output), optional local PostgreSQL, optional ONLYOFFICE Word editor |
| PostgreSQL database | 14+ | a hosted one ([Neon](https://neon.tech) works) or the local one in `docker-compose.yml` |

Ports used: `5173` frontend, `8000` backend, `3005` Gotenberg, `5433` local
PostgreSQL, `8082` ONLYOFFICE.

### Option A: setup script (recommended)

Each script installs whatever is missing (it asks first), pulls the `main`
branch, creates `.env` (a random `JWT_SECRET_KEY`, and a database: local
PostgreSQL in Docker or your Neon URL), starts the Docker services, installs
the backend (`backend/.venv`) and frontend dependencies, runs the database
migrations and starts both servers.

The script will not switch branches while you have uncommitted changes:
commit or stash them first, or pass the skip-pull option.

#### Windows 10/11 (PowerShell)

The script installs Git, Python 3.12, Node.js LTS and Docker Desktop with
`winget` (built into Windows 10 1809+ and 11). Docker Desktop needs WSL 2:
if it asks, run `wsl --install` in an administrator PowerShell, restart,
and run the script again.

```powershell
git clone -b main https://github.com/Harsh2227kumar/TemplateOS.git
```

```powershell
cd TemplateOS
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

The backend and frontend open in two new PowerShell windows and the app opens
in your browser. Options: `-Branch <name>`, `-SkipPull`, `-SkipDocker`,
`-Database local|neon`, `-WithEditor`, `-SeedDemo`, `-NoRun`, `-Yes`.

#### macOS (Apple Silicon or Intel)

The script uses [Homebrew](https://brew.sh) to install Python, Node.js and
Docker Desktop (`brew install --cask docker`). Install Homebrew first if you
do not have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

```bash
git clone -b main https://github.com/Harsh2227kumar/TemplateOS.git && cd TemplateOS
```

```bash
bash scripts/setup-macos.sh
```

#### Ubuntu 22.04 / 24.04

The script installs Python 3.12 (apt, or the deadsnakes PPA on 22.04),
Node.js 24 (NodeSource) and Docker Engine with the Compose plugin (Docker's
apt repository). It uses `sudo` for those.

```bash
sudo apt-get update && sudo apt-get install -y git
```

```bash
git clone -b main https://github.com/Harsh2227kumar/TemplateOS.git && cd TemplateOS
```

```bash
bash scripts/setup-ubuntu.sh
```

On macOS and Ubuntu both servers run in that terminal; press Ctrl+C to stop
them. Options: `--branch <name>`, `--skip-pull`, `--skip-docker`,
`--db local|neon`, `--with-editor`, `--seed-demo`, `--no-run`, `-y`/`--yes`,
`--help`.

Run the script again any time: it pulls the latest `main`, keeps your `.env`,
installs new dependencies and applies new migrations.

### Option B: manual setup

#### 1. Install the software

**Windows** (PowerShell; or download the installers from the links above):

```powershell
winget install -e --id Git.Git
```

```powershell
winget install -e --id Python.Python.3.12
```

```powershell
winget install -e --id OpenJS.NodeJS.LTS
```

```powershell
winget install -e --id Docker.DockerDesktop
```

Open a new PowerShell window afterwards so the new `PATH` is picked up, and
start Docker Desktop once (it may ask for `wsl --install` and a restart).

**macOS** (Homebrew):

```bash
brew install git python@3.12 node
```

```bash
brew install --cask docker
```

```bash
open -a Docker
```

**Ubuntu**:

```bash
sudo apt-get update && sudo apt-get install -y git curl ca-certificates python3 python3-venv python3-pip
```

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt-get install -y nodejs
```

For Docker Engine follow [Docker's Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/)
(install `docker-ce` and `docker-compose-plugin`), then let your user run it
without `sudo` (log out and back in afterwards):

```bash
sudo usermod -aG docker $USER
```

On Ubuntu 22.04 `python3` is 3.10: install 3.12 from the deadsnakes PPA
(`sudo add-apt-repository ppa:deadsnakes/ppa`, then
`sudo apt-get install python3.12 python3.12-venv`) and use `python3.12`
below.

Check the versions: `git --version`, `python --version` (or `python3`),
`node --version`, `docker compose version`.

#### 2. Get the code

```bash
git clone -b main https://github.com/Harsh2227kumar/TemplateOS.git
```

```bash
cd TemplateOS
```

#### 3. Settings (`.env`)

Copy `.env.example` to `.env` in the repository root (`copy .env.example .env`
on Windows, `cp .env.example .env` elsewhere), then set:

- `JWT_SECRET_KEY`: a long random value, from
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `DATABASE_URL`: your Neon/PostgreSQL URL, or the local Docker database:
  `postgresql+psycopg://templateos:templateos@localhost:5433/templateos`.

`.env.example` documents every other setting (AI, PDF, Word editor, EkLink
SSO). `.env` is read when the backend starts: restart it after any change.

#### 4. Docker services

```bash
docker compose up -d gotenberg
```

Only if you use the local database (waits until PostgreSQL is ready):

```bash
docker compose --profile db up -d --wait postgres
```

Optional Word editor (large image; see the [backend README](backend/README.md)):

```bash
docker compose up -d onlyoffice
```

#### 5. Backend

Windows (PowerShell):

```powershell
cd backend
```

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Ubuntu:

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
```

Then, on every OS, with the virtual environment active:

```bash
pip install -r requirements.txt
```

```bash
alembic upgrade head
```

```bash
uvicorn app.main:app --reload
```

The API runs on `http://localhost:8000` (docs at `/docs`). If PowerShell
refuses to run `Activate.ps1`, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

#### 6. Frontend (second terminal, repository root)

```bash
npm install
```

```bash
npm run dev:frontend
```

Open the app at `http://localhost:5173`. Use `localhost` (not `127.0.0.1`)
for both the app and the API so the session cookies work.

#### 7. A first user

Sign up in the app (new accounts get the `normal_user` role), or create an
admin from `backend/` with the virtual environment active:

```bash
python scripts/seed_user.py --email admin@example.com --password "change-this-password" --full-name "TemplateOS Admin" --role super_admin
```

`python scripts/seed_demo_users.py` seeds one user per role from the
`SIT_*` values in `.env`. Demo templates, AI, PDF, Word editor and audit
settings are described in the [backend README](backend/README.md). After
pulling new work, run `alembic upgrade head` again.

### Troubleshooting

- **`docker` not found, or "cannot connect to the Docker daemon"**: start
  Docker Desktop (Windows/macOS) or run `sudo systemctl start docker`
  (Ubuntu), wait until it is running, and retry.
- **Port already in use**: something else uses 5173, 8000, 3005, 5433 or
  8082. Stop it, or change the left side of the port in `docker-compose.yml`
  together with the matching URL in `.env`.
- **Migrations fail**: check `DATABASE_URL`; for Neon keep `?sslmode=require`;
  for the local database check that `templateos-postgres` is running
  (`docker compose ps`).
- **"PDF not available"**: Gotenberg is not running. Run
  `docker compose up -d gotenberg`, then check it with
  `python backend/scripts/verify_gotenberg.py --live`.
- **Windows: `python` opens the Microsoft Store**: turn off the Python
  "App execution aliases" in Settings, or use `py -3.12`.
- **Ubuntu: `permission denied` on the Docker socket**: log out and back in
  after `usermod -aG docker`, or prefix the docker commands with `sudo`.
- **Stop the Docker services**: `docker compose --profile db --profile editor down`
  (add `-v` to also delete the local database).

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
