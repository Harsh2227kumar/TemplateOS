#!/usr/bin/env bash
# TemplateOS one-shot setup for macOS (Apple Silicon and Intel, macOS 13+).
#
#   bash scripts/setup-macos.sh [options]
#
# Steps: install missing tools with Homebrew (git, Python 3.12+, Node.js
# 22.18+, Docker Desktop) -> pull the main branch -> create .env -> start the Docker services
# (Gotenberg, optional local PostgreSQL / ONLYOFFICE) -> install backend and
# frontend dependencies -> run database migrations -> start the backend
# (http://localhost:8000) and frontend (http://localhost:5173).
#
# Options:
#   --branch NAME     branch to pull (default: main)
#   --skip-pull       do not fetch/checkout/pull
#   --skip-docker     do not install or start Docker services (no PDF output)
#   --db local|neon   database: local PostgreSQL in Docker, or paste a Neon URL
#                     (asked when .env still has the placeholder)
#   --with-editor     also start ONLYOFFICE Docs (Word editor, ~4 GB image)
#   --seed-demo       seed the demo users from the SIT_* values in .env
#   --no-run          set everything up but do not start the servers
#   --run-only        skip setup, only start the servers (needs a previous setup)
#   --debug           trace every command with line numbers (the log may then contain secrets)
#   -y, --yes         answer yes to every prompt (non-interactive)
#   -h, --help        show this help
#
# Log file: <repo>/logs/templateos-setup-macos-<time>.log  (or $PBL_LOG_DIR when set).
# On failure it prints the step, line, failing command, exit code and the log path.
#
# The whole script lives in main() so bash has parsed it completely before
# `git checkout` can change this file on disk.

main() {
  set -Eeuo pipefail

  local REPO_URL="https://github.com/Harsh2227kumar/TemplateOS.git"
  local BRANCH="main" SKIP_PULL=0 SKIP_DOCKER=0 DB_MODE="" WITH_EDITOR=0
  local SEED_DEMO=0 NO_RUN=0 RUN_ONLY=0 DEBUG=0 ASSUME_YES=0
  local LOCAL_DB_URL="postgresql+psycopg://templateos:templateos@localhost:5433/templateos"

  while [ $# -gt 0 ]; do
    case "$1" in
      --branch) BRANCH="${2:?--branch needs a value}"; shift ;;
      --skip-pull) SKIP_PULL=1 ;;
      --skip-docker) SKIP_DOCKER=1 ;;
      --db) DB_MODE="${2:?--db needs local or neon}"; shift ;;
      --with-editor) WITH_EDITOR=1 ;;
      --seed-demo) SEED_DEMO=1 ;;
      --no-run) NO_RUN=1 ;;
      --run-only) RUN_ONLY=1 ;;
      --debug) DEBUG=1 ;;
      -y|--yes) ASSUME_YES=1 ;;
      -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "${BASH_SOURCE[0]}"; return 0 ;;
      *) echo "Unknown option: $1 (see --help)" >&2; return 1 ;;
    esac
    shift
  done
  case "$DB_MODE" in ""|local|neon) ;; *) echo "--db must be local or neon" >&2; return 1 ;; esac

  # ---------- logging + error reporting ----------
  local SCRIPT_DIR ROOT
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local LOG_DIR="${PBL_LOG_DIR:-$SCRIPT_DIR/../logs}"
  mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/pbl-logs"
  mkdir -p "$LOG_DIR"; LOG_DIR="$(cd "$LOG_DIR" && pwd)"
  LOG_FILE="$LOG_DIR/templateos-setup-macos-$(date +%Y%m%d-%H%M%S).log"
  exec > >(tee -a "$LOG_FILE") 2>&1
  CURRENT_STEP="0. start"; STEP_NO=0
  on_error() {
    [ "${BASH_SUBSHELL:-0}" -eq 0 ] || return 0
    printf '\n\033[1;31m[x] TemplateOS failed in step "%s"\033[0m\n' "$CURRENT_STEP" >&2
    printf '    line %s: %s\n    exit code: %s\n    full log: %s\n' "$2" "$3" "$1" "$LOG_FILE" >&2
    printf '    next: re-run with --debug to trace every command.\n' >&2
  }
  trap 'rc=$?; on_error "$rc" "$LINENO" "$BASH_COMMAND"' ERR
  if [ "$DEBUG" = 1 ]; then export PS4='+ [line ${LINENO}] '; set -x; fi

  # ---------- helpers ----------
  step() { STEP_NO=$((STEP_NO + 1)); CURRENT_STEP="$STEP_NO. $*"; printf '\n\033[1;36m==> [%s] %s\033[0m\n' "$STEP_NO" "$*"; }
  info() { printf '    %s\n' "$*"; }
  warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
  die()  { printf '\033[1;31m[x] %s\033[0m\n    step: %s\n    log:  %s\n' "$*" "$CURRENT_STEP" "$LOG_FILE" >&2; exit 1; }
  have() { command -v "$1" >/dev/null 2>&1; }
  confirm() {  # confirm "question" -> 0 yes / 1 no (default yes)
    [ "$ASSUME_YES" = 1 ] && return 0
    [ -t 0 ] || return 1   # no terminal and no --yes: never install unattended
    local reply; read -r -p "    $1 [Y/n] " reply || true
    case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
  }

  info "TemplateOS setup (macOS) | branch=$BRANCH | log: $LOG_FILE"
  if [ "$RUN_ONLY" = 1 ]; then
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)" || die "Run --run-only from inside the TemplateOS repository."
    cd "$ROOT"
    [ -x backend/.venv/bin/python ] || die "backend/.venv is missing: run the full setup first."
    [ -f .env ] || die ".env is missing: run the full setup first."
    if [ "$SKIP_DOCKER" = 0 ] && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
      docker compose up -d gotenberg || warn "Could not start Gotenberg (PDF output will fail)."
      if grep -Eq '^DATABASE_URL=.*@(localhost|127\.0\.0\.1):5433/' .env; then
        docker compose --profile db up -d --wait postgres || die "Local PostgreSQL did not start (docker compose logs postgres)."
      fi
    fi
    if grep -q '^ONLYOFFICE_ENABLED=true' .env; then WITH_EDITOR=1; fi
    run_servers "$ROOT/backend/.venv/bin/python"
    return 0
  fi

  # ---------- 1. tools ----------
  step "Checking required software"
  info "macOS $(sw_vers -productVersion 2>/dev/null || echo unknown) on $(uname -m)"

  if ! xcode-select -p >/dev/null 2>&1; then
    warn "Xcode Command Line Tools are missing (they provide git)."
    xcode-select --install || true
    die "Finish the Command Line Tools installer window, then re-run this script."
  fi

  if ! have brew; then
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [ -x "$b" ] && eval "$("$b" shellenv)" && break
    done
  fi
  if ! have brew; then
    warn "Homebrew is required to install the missing tools. Install it from https://brew.sh :"
    info '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    die "Then open a new terminal and re-run this script."
  fi
  info "Homebrew: $(brew --version | head -n 1)"

  have git || brew install git

  find_python() {
    local c
    for c in python3.13 python3.12 python3 python; do
      if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        command -v "$c"; return 0
      fi
    done
    return 1
  }
  local PY
  if ! PY="$(find_python)"; then
    confirm "Python 3.12+ not found. Install python@3.12 with Homebrew?" || die "Python 3.12+ is required."
    brew install python@3.12
    PY="$(brew --prefix)/bin/python3.12"
    [ -x "$PY" ] || die "Python 3.12 install failed."
  fi
  local PYVER; PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  info "Python: $PY ($PYVER)"

  node_ok() { have node && node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=18)?0:1)'; }
  if ! node_ok; then
    confirm "Node.js 22.18+ not found. Install Node.js with Homebrew?" || die "Node.js 22.18+ is required."
    brew install node
    node_ok || die "Node.js install failed (an older node may be first on PATH: check 'which node')."
  fi
  info "Node.js: $(node --version), npm $(npm --version)"

  DOCKER="docker"
  if [ "$SKIP_DOCKER" = 0 ]; then
    if ! have docker && [ ! -d /Applications/Docker.app ]; then
      confirm "Docker Desktop not found. Install it with Homebrew (brew install --cask docker)?" \
        || die "Docker is required (or re-run with --skip-docker)."
      brew install --cask docker
    fi
    have docker || export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
    if ! docker info >/dev/null 2>&1; then
      info "Starting Docker Desktop (accept its license window on first launch)..."
      open -a Docker || die "Could not start Docker Desktop."
      local waited=0
      until docker info >/dev/null 2>&1; do
        [ "$waited" -ge 240 ] && die "Docker Desktop did not start within 4 minutes. Start it, wait for 'Engine running', and re-run."
        sleep 5; waited=$((waited + 5))
      done
    fi
    docker compose version >/dev/null 2>&1 || die "'docker compose' is missing; update Docker Desktop."
    info "Docker: $(docker --version)"
  fi

  # ---------- 2. repository ----------
  step "Getting the code (branch: $BRANCH)"
  if ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    info "Repository: $ROOT"
  else
    ROOT="$PWD/TemplateOS"
    if [ -d "$ROOT/.git" ]; then info "Using existing clone: $ROOT"
    else git clone --branch "$BRANCH" "$REPO_URL" "$ROOT"; fi
  fi
  cd "$ROOT"
  if [ -d .git/info ] && ! grep -qx 'logs/' .git/info/exclude 2>/dev/null; then echo 'logs/' >> .git/info/exclude; fi

  if [ "$SKIP_PULL" = 0 ]; then
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
      git status --short --untracked-files=no | sed 's/^/      /'
      die "Uncommitted changes (listed above). Commit or stash them, or re-run with --skip-pull."
    fi
    git fetch origin "$BRANCH" || die "git fetch failed (network? does '$BRANCH' exist on origin?)"
    if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
      if git show-ref --verify --quiet "refs/heads/$BRANCH"; then git checkout "$BRANCH"
      else git checkout -b "$BRANCH" --track "origin/$BRANCH"; fi
    fi
    git pull --ff-only origin "$BRANCH" || die "git pull --ff-only failed: local branch has diverged from origin/$BRANCH."
  else
    info "Skipping git pull (--skip-pull)."
  fi

  # ---------- 3. .env ----------
  step "Configuring .env"
  if [ ! -f .env ]; then cp .env.example .env; info "Created .env from .env.example"; fi
  env_get() { "$PY" - "$1" <<'PYEOF'
import re, sys
key = sys.argv[1]
for line in open(".env", encoding="utf-8"):
    m = re.match(r"\s*%s\s*=(.*)$" % re.escape(key), line)
    if m:
        print(m.group(1).strip()); break
PYEOF
  }
  env_set() { "$PY" - "$1" "$2" <<'PYEOF'
import re, sys
key, value = sys.argv[1], sys.argv[2]
lines = open(".env", encoding="utf-8").read().splitlines()
pat = re.compile(r"\s*#?\s*%s\s*=" % re.escape(key))
for i, line in enumerate(lines):
    if pat.match(line):
        lines[i] = "%s=%s" % (key, value); break
else:
    lines.append("%s=%s" % (key, value))
open(".env", "w", encoding="utf-8").write("\n".join(lines) + "\n")
PYEOF
  }
  new_secret() { "$PY" -c 'import secrets; print(secrets.token_urlsafe(48))'; }

  local jwt; jwt="$(env_get JWT_SECRET_KEY)"
  if [ -z "$jwt" ] || [ "$jwt" = "generate-a-long-random-secret-here" ] || [ "${#jwt}" -lt 32 ]; then
    env_set JWT_SECRET_KEY "$(new_secret)"; info "Generated JWT_SECRET_KEY"
  fi

  local dburl; dburl="$(env_get DATABASE_URL)"
  if [ -z "$DB_MODE" ]; then
    if [ -z "$dburl" ] || [[ "$dburl" == *"USER:PASSWORD@HOST"* ]]; then
      if [ "$SKIP_DOCKER" = 0 ] && confirm "Use a local PostgreSQL in Docker? (No = paste a Neon URL)"; then
        DB_MODE="local"
      else
        DB_MODE="neon"
      fi
    else
      info "Keeping DATABASE_URL from .env"
    fi
  fi
  if [ "$DB_MODE" = "local" ]; then
    [ "$SKIP_DOCKER" = 1 ] && die "--db local needs Docker; drop --skip-docker."
    env_set DATABASE_URL "$LOCAL_DB_URL"; dburl="$LOCAL_DB_URL"; info "DATABASE_URL -> local Docker PostgreSQL (port 5433)"
  elif [ "$DB_MODE" = "neon" ]; then
    local url=""
    read -r -p "    Paste your PostgreSQL/Neon connection string: " url || true
    [ -n "$url" ] || die "No DATABASE_URL given."
    env_set DATABASE_URL "$url"; dburl="$url"
  fi
  local USE_LOCAL_DB=0
  case "$dburl" in *@localhost:5433/*|*@127.0.0.1:5433/*) USE_LOCAL_DB=1 ;; esac

  if [ "$WITH_EDITOR" = 1 ]; then
    local oo; oo="$(env_get ONLYOFFICE_JWT_SECRET)"
    if [ -z "$oo" ] || [ "${#oo}" -lt 32 ] || [ "$oo" = "generate-a-long-random-secret-for-onlyoffice" ]; then
      env_set ONLYOFFICE_JWT_SECRET "$(new_secret)"
    fi
    env_set ONLYOFFICE_ENABLED true
    env_set ONLYOFFICE_PUBLIC_URL http://localhost:8082
    env_set BACKEND_URL_FOR_ONLYOFFICE http://host.docker.internal:8000
    info "Word editor (ONLYOFFICE) enabled in .env"
  fi
  if [ "$SKIP_DOCKER" = 1 ]; then
    warn "Docker skipped: PDF output needs Gotenberg or a local LibreOffice (see README)."
  fi

  # ---------- 4. Docker services ----------
  if [ "$SKIP_DOCKER" = 0 ]; then
    step "Starting Docker services"
    $DOCKER compose up -d gotenberg
    if [ "$USE_LOCAL_DB" = 1 ]; then
      $DOCKER compose --profile db up -d --wait postgres
    fi
    if [ "$WITH_EDITOR" = 1 ]; then
      info "Starting ONLYOFFICE (first pull is large and the first start takes a few minutes)"
      ONLYOFFICE_JWT_SECRET="$(env_get ONLYOFFICE_JWT_SECRET)" $DOCKER compose --profile editor up -d onlyoffice
    fi
    $DOCKER compose ps
  fi

  # ---------- 5. backend ----------
  step "Installing backend dependencies (backend/.venv)"
  if [ ! -x backend/.venv/bin/python ]; then
    "$PY" -m venv backend/.venv
  fi
  local VPY="$ROOT/backend/.venv/bin/python"
  "$VPY" -m pip install --upgrade pip
  "$VPY" -m pip install -r backend/requirements.txt || die "pip install failed (error above)."

  step "Running database migrations"
  (cd backend && "$VPY" -m alembic upgrade head) \
    || die "Migrations failed. Check DATABASE_URL in .env (and that the database is reachable)."

  if [ "$SEED_DEMO" = 0 ] && [ "$ASSUME_YES" = 0 ] && [ -t 0 ]; then
    local r; read -r -p "    Seed the demo users (SIT_* in .env)? [y/N] " r || true
    case "$r" in [yY]*) SEED_DEMO=1 ;; esac
  fi
  if [ "$SEED_DEMO" = 1 ]; then
    (cd backend && "$VPY" scripts/seed_demo_users.py)
  fi

  # ---------- 6. frontend ----------
  step "Installing frontend dependencies (npm workspaces)"
  npm install || die "npm install failed (network, disk space, Node version?)."

  # ---------- 7. run ----------
  if [ "$NO_RUN" = 1 ]; then
    step "Setup complete"
    info "Start both servers: bash scripts/setup-macos.sh --run-only"
    info "or: cd backend && .venv/bin/python -m uvicorn app.main:app --reload   |   npm run dev:frontend"
    return 0
  fi
  run_servers "$VPY"
}

# run_servers <venv python>: backend in the background, Vite in the foreground.
# (Called from main, so step/info/die and WITH_EDITOR are in scope.)
run_servers() {
  local VPY="$1" p
  local HOST="127.0.0.1"; [ "$WITH_EDITOR" = 1 ] && HOST="0.0.0.0"
  step "Starting backend (http://localhost:8000) and frontend (http://localhost:5173)"
  for p in 8000 5173; do
    if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      lsof -nP -iTCP:"$p" -sTCP:LISTEN | sed 's/^/      /' || true
      die "Port $p is already in use (listed above). Stop that process and re-run."
    fi
  done
  info "Press Ctrl+C to stop both."
  (cd backend && exec "$VPY" -m uvicorn app.main:app --reload --host "$HOST" --port 8000) &
  BACKEND_PID=$!
  trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
  npm run dev:frontend
}

main "$@"
