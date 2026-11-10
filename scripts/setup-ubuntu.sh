#!/usr/bin/env bash
# TemplateOS setup + run script for Ubuntu 22.04 / 24.04 (a laptop or an AWS EC2 instance).
#
#   bash scripts/setup-ubuntu.sh [options]
#
# Steps (numbered in the output and in the log file):
#   1. check / install git, curl, Python 3.12+, Node.js 22.18+, Docker Engine
#   2. pull the branch (default: main)
#   3. create / update .env
#   4. start the Docker services (Gotenberg, optional local PostgreSQL / ONLYOFFICE)
#   5. backend: virtualenv + pip install + database migrations (+ optional demo users)
#   6. frontend: npm install (prod: also `vite build`)
#   7. run:  dev  -> uvicorn :8000 + Vite :5173 in this terminal
#            prod -> systemd service 'templateos-backend' on 127.0.0.1:8000, the built
#                    frontend served by Nginx on the public port (8005) with /api proxied
#
# Options:
#   --branch NAME       branch to pull (default: main)
#   --skip-pull         do not fetch / checkout / pull
#   --skip-docker       do not install or start Docker services (no PDF output)
#   --db local|neon     database: local PostgreSQL in Docker, or paste a Neon URL
#                       (asked when .env still has the placeholder)
#   --with-editor       also start ONLYOFFICE Docs (Word editor, ~4 GB image)
#   --seed-demo         seed the demo users from the SIT_* values in .env
#   --mode dev|prod     dev servers (default) or production build + systemd + Nginx
#   --public-host HOST  public IP or DNS name of this server, or "auto" (EC2 metadata).
#                       Sets EKLINK_REDIRECT_URI / BACKEND_CORS_ORIGINS to http://HOST:PORT
#                       and, unless --eklink-url is given, EKLINK_URL / EKLINK_ISSUER to http://HOST
#   --public-port N     public Nginx port for TemplateOS in prod mode (default: 8005)
#   --eklink-url URL    EkLink address (EKLINK_URL + EKLINK_ISSUER), e.g. http://1.2.3.4
#   --no-run            set everything up but do not start the servers
#   --run-only          skip setup, only start (needs a previous setup)
#   --check             diagnose only (tools, .env, Docker, ports, services); changes nothing
#   --debug             trace every command with line numbers (the log may then contain secrets)
#   -y, --yes           answer yes to every prompt (non-interactive)
#   -h, --help          show this help
#
# Log file: <repo>/logs/templateos-setup-ubuntu-<time>.log  (or $PBL_LOG_DIR when set)
# On failure it prints the step, line, failing command, exit code and the log path.

# The whole script lives in main() so bash has parsed it completely before
# `git checkout` can change this file on disk.
main() {
  set -Eeuo pipefail

  local PROJECT="TemplateOS" SERVICE="templateos"
  local REPO_URL="https://github.com/Harsh2227kumar/TemplateOS.git"
  local BRANCH="main" SKIP_PULL=0 SKIP_DOCKER=0 DB_MODE="" WITH_EDITOR=0
  local SEED_DEMO=0 NO_RUN=0 RUN_ONLY=0 CHECK_ONLY=0 DEBUG=0 ASSUME_YES=0
  local MODE="dev" PUBLIC_HOST="" PUBLIC_PORT=8005 EKLINK_URL_ARG=""
  local LOCAL_DB_URL="postgresql+psycopg://templateos:templateos@localhost:5433/templateos"
  local WEB_ROOT="/var/www/templateos"

  while [ $# -gt 0 ]; do
    case "$1" in
      --branch) BRANCH="${2:?--branch needs a value}"; shift ;;
      --skip-pull) SKIP_PULL=1 ;;
      --skip-docker) SKIP_DOCKER=1 ;;
      --db) DB_MODE="${2:?--db needs local or neon}"; shift ;;
      --with-editor) WITH_EDITOR=1 ;;
      --seed-demo) SEED_DEMO=1 ;;
      --mode) MODE="${2:?--mode needs dev or prod}"; shift ;;
      --public-host) PUBLIC_HOST="${2:?--public-host needs a value}"; shift ;;
      --public-port) PUBLIC_PORT="${2:?--public-port needs a value}"; shift ;;
      --eklink-url) EKLINK_URL_ARG="${2:?--eklink-url needs a value}"; shift ;;
      --no-run) NO_RUN=1 ;;
      --run-only) RUN_ONLY=1 ;;
      --check) CHECK_ONLY=1 ;;
      --debug) DEBUG=1 ;;
      -y|--yes) ASSUME_YES=1 ;;
      -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "${BASH_SOURCE[0]}"; return 0 ;;
      *) echo "Unknown option: $1 (see --help)" >&2; return 2 ;;
    esac
    shift
  done
  case "$DB_MODE" in ""|local|neon) ;; *) echo "--db must be local or neon" >&2; return 2 ;; esac
  case "$MODE" in dev|prod) ;; *) echo "--mode must be dev or prod" >&2; return 2 ;; esac
  case "$PUBLIC_PORT" in ''|*[!0-9]*) echo "--public-port must be a number" >&2; return 2 ;; esac
  if [ "$NO_RUN" = 1 ] && [ "$RUN_ONLY" = 1 ]; then echo "--no-run and --run-only cannot be combined" >&2; return 2; fi

  # ---------------- logging + error reporting ----------------
  local SCRIPT_DIR; SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local LOG_DIR="${PBL_LOG_DIR:-$SCRIPT_DIR/../logs}"
  mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="${TMPDIR:-/tmp}/pbl-logs"
  mkdir -p "$LOG_DIR"; LOG_DIR="$(cd "$LOG_DIR" && pwd)"
  LOG_FILE="$LOG_DIR/${SERVICE}-setup-ubuntu-$(date +%Y%m%d-%H%M%S).log"
  if [ -t 1 ]; then C_STEP=$'\033[1;36m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_OK=$'\033[1;32m'; C_END=$'\033[0m'
  else C_STEP=""; C_WARN=""; C_ERR=""; C_OK=""; C_END=""; fi
  exec > >(tee -a "$LOG_FILE") 2>&1

  CURRENT_STEP="0. start"; STEP_NO=0
  on_error() {  # on_error <exit code> <line> <command>
    [ "${BASH_SUBSHELL:-0}" -eq 0 ] || return 0
    printf '\n%s[x] %s failed in step "%s"%s\n' "$C_ERR" "$PROJECT" "$CURRENT_STEP" "$C_END" >&2
    printf '    line %s: %s\n    exit code: %s   (functions: %s)\n' "$2" "$3" "$1" "${FUNCNAME[*]:1}" >&2
    printf '    full log: %s\n' "$LOG_FILE" >&2
    printf '    next: re-run with --debug to trace every command, or --check to diagnose.\n' >&2
  }
  trap 'rc=$?; on_error "$rc" "$LINENO" "$BASH_COMMAND"' ERR
  if [ "$DEBUG" = 1 ]; then export PS4='+ [line ${LINENO}] '; set -x; fi

  step() { STEP_NO=$((STEP_NO + 1)); CURRENT_STEP="$STEP_NO. $*"; printf '\n%s==> [%s] %s%s\n' "$C_STEP" "$STEP_NO" "$*" "$C_END"; }
  info() { printf '    %s\n' "$*"; }
  ok()   { printf '    %s[ok]%s %s\n' "$C_OK" "$C_END" "$*"; }
  warn() { printf '%s[!] %s%s\n' "$C_WARN" "$*" "$C_END"; }
  die()  { printf '%s[x] %s%s\n    step: %s\n    log:  %s\n' "$C_ERR" "$*" "$C_END" "$CURRENT_STEP" "$LOG_FILE" >&2; exit 1; }
  have() { command -v "$1" >/dev/null 2>&1; }
  confirm() {  # confirm "question" -> 0 yes / 1 no (default yes)
    [ "$ASSUME_YES" = 1 ] && return 0
    [ -t 0 ] || return 1   # no keyboard and no --yes: never install anything unattended
    local reply; read -r -p "    $1 [Y/n] " reply || true
    case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
  }
  retry() {  # retry <attempts> <command...>
    local max=$1 n=1; shift
    until "$@"; do
      if [ "$n" -ge "$max" ]; then return 1; fi
      warn "Attempt $n/$max failed: $*  (retrying in $((n * 5))s)"
      sleep $((n * 5)); n=$((n + 1))
    done
  }
  port_busy() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }
  wait_http() {  # wait_http <url> <seconds>: 0 when it answers with any non-5xx status
    local url=$1 limit=$2 waited=0 code
    while [ "$waited" -lt "$limit" ]; do
      code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$url" 2>/dev/null || true)"
      case "$code" in 2??|3??|4??) return 0 ;; esac
      sleep 3; waited=$((waited + 3))
    done
    return 1
  }
  detect_public_ip() {  # EC2 metadata (IMDSv2), then a public echo service
    local token ip=""
    token="$(curl -fsS -m 2 -X PUT http://169.254.169.254/latest/api/token \
      -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null || true)"
    if [ -n "$token" ]; then
      ip="$(curl -fsS -m 2 -H "X-aws-ec2-metadata-token: $token" \
        http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
    fi
    [ -n "$ip" ] || ip="$(curl -fsS -m 5 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
    printf '%s' "$ip"
  }
  public_url() { if [ "$2" = 80 ]; then printf 'http://%s' "$1"; else printf 'http://%s:%s' "$1" "$2"; fi; }
  find_python() {
    local c
    for c in python3.13 python3.12 python3 python; do
      if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        command -v "$c"; return 0
      fi
    done
    return 1
  }
  node_ok() { have node && node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=18)?0:1)'; }

  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  info "$PROJECT setup (ubuntu) | mode=$MODE branch=$BRANCH | log: $LOG_FILE"
  [ "$(id -u)" -eq 0 ] && warn "Running as root. Prefer a normal user with sudo (e.g. 'ubuntu' on EC2) so files are not owned by root."

  if [ "$PUBLIC_HOST" = "auto" ]; then
    PUBLIC_HOST="$(detect_public_ip)"
    [ -n "$PUBLIC_HOST" ] || die "Could not detect the public IP. Pass it yourself: --public-host 1.2.3.4"
    info "Detected public host: $PUBLIC_HOST"
  fi

  local ROOT=""
  ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"

  # .env helpers (Python, available after step 1)
  local PY=""
  ENV_BACKED_UP=0
  env_get() { "$PY" - "$1" <<'PYEOF'
import re, sys
key = sys.argv[1]
try:
    lines = open(".env", encoding="utf-8").read().splitlines()
except FileNotFoundError:
    lines = []
for line in lines:
    m = re.match(r"\s*%s\s*=(.*)$" % re.escape(key), line)
    if m:
        print(m.group(1).strip().strip('"').strip("'")); break
PYEOF
  }
  env_set() {
    if [ "$ENV_BACKED_UP" = 0 ] && [ -f .env ]; then
      local bak; bak="$LOG_DIR/${SERVICE}.env.$(date +%Y%m%d-%H%M%S).bak"
      cp .env "$bak" && chmod 600 "$bak" && info "Backed up .env -> $bak"
      ENV_BACKED_UP=1
    fi
    "$PY" - "$1" "$2" <<'PYEOF'
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

  # ---------------- --check: diagnose only ----------------
  if [ "$CHECK_ONLY" = 1 ]; then
    step "Diagnosis (nothing is changed)"
    local problems=0
    bad() { printf '    %s[problem]%s %s\n' "$C_ERR" "$C_END" "$*"; problems=$((problems + 1)); }
    if [ -r /etc/os-release ]; then . /etc/os-release; info "OS: ${PRETTY_NAME:-?}  user: $(id -un)"; fi
    have git && ok "git $(git --version | awk '{print $3}')" || bad "git is not installed"
    if PY="$(find_python)"; then ok "python: $PY ($("$PY" --version 2>&1))"; else bad "Python 3.12+ not found"; fi
    node_ok && ok "node $(node --version), npm $(npm --version)" || bad "Node.js 22.18+ not found"
    if have docker; then
      if docker info >/dev/null 2>&1 || sudo -n docker info >/dev/null 2>&1; then ok "docker daemon running"
        { docker compose ps 2>/dev/null || sudo -n docker compose ps 2>/dev/null || true; } | sed 's/^/      /'
      else bad "docker installed but the daemon is not reachable (sudo systemctl start docker)"; fi
    else warn "docker not installed (PDF output needs Gotenberg)"; fi
    if [ -n "$ROOT" ]; then
      cd "$ROOT"; ok "repository: $ROOT (branch $(git rev-parse --abbrev-ref HEAD))"
      [ -z "$(git status --porcelain --untracked-files=no)" ] && ok "no uncommitted changes" \
        || warn "uncommitted changes (a pull will refuse; use --skip-pull)"
      [ -x backend/.venv/bin/python ] && ok "backend/.venv present" || bad "backend/.venv missing"
      [ -d node_modules ] && ok "node_modules present" || bad "node_modules missing"
      if [ -f .env ] && [ -n "$PY" ]; then
        ok ".env present"
        local db; db="$(env_get DATABASE_URL)"
        { [ -z "$db" ] || [[ "$db" == *"USER:PASSWORD@HOST"* ]]; } && bad "DATABASE_URL is not set" || ok "DATABASE_URL set (${db%%://*}://...)"
        local j; j="$(env_get JWT_SECRET_KEY)"; [ "${#j}" -ge 32 ] && ok "JWT_SECRET_KEY set" || bad "JWT_SECRET_KEY missing or < 32 chars"
        info "EKLINK_URL=$(env_get EKLINK_URL)  EKLINK_REDIRECT_URI=$(env_get EKLINK_REDIRECT_URI)"
        info "BACKEND_CORS_ORIGINS=$(env_get BACKEND_CORS_ORIGINS)  GOTENBERG_URL=$(env_get GOTENBERG_URL)"
        [ -n "$(env_get EKLINK_CLIENT_ID)" ] && ok "EkLink sign-in configured" || warn "EKLINK_CLIENT_ID empty: EkLink sign-in is off"
        if [ -x backend/.venv/bin/python ]; then
          (cd backend && .venv/bin/python -m alembic current 2>&1 | tail -n 3 | sed 's/^/      alembic: /') || bad "alembic cannot reach the database"
        fi
      else bad "no .env file"; fi
    else bad "not inside the $PROJECT git repository ($SCRIPT_DIR)"; fi
    local p; for p in 8000 5173 3005 5433 "$PUBLIC_PORT"; do
      if port_busy "$p"; then info "port $p in use: $(ss -ltnpH "sport = :$p" 2>/dev/null | awk '{print $NF}' | head -n1)"; else info "port $p free"; fi
    done
    if have systemctl && systemctl cat "$SERVICE-backend.service" >/dev/null 2>&1; then
      info "systemd $SERVICE-backend: $(systemctl is-active "$SERVICE-backend" 2>/dev/null || true)  (journalctl -u $SERVICE-backend -n 100)"
    fi
    wait_http "http://127.0.0.1:8000/health" 3 && ok "backend /health answers" || info "backend not answering on :8000"
    info "memory: $(free -m | awk '/^Mem:/{print $2" MB RAM"} /^Swap:/{print $2" MB swap"}' | tr '\n' ' ')  disk free: $(df -Pm . | awk 'NR==2{print $4" MB"}')"
    if [ "$problems" -eq 0 ]; then printf '\n%sNo problems found.%s\n' "$C_OK" "$C_END"; return 0; fi
    printf '\n%s%s problem(s) found (see above).%s\n' "$C_ERR" "$problems" "$C_END"; return 1
  fi

  # ---------------- 1. tools ----------------
  local apt_updated=0
  apt_install() {
    if [ "$apt_updated" = 0 ]; then
      retry 3 $SUDO apt-get -o DPkg::Lock::Timeout=300 update -y || die "apt-get update failed (network? another apt running?)"
      apt_updated=1
    fi
    retry 3 $SUDO env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y "$@" \
      || die "apt-get install $* failed"
  }

  DOCKER="docker"
  if [ "$RUN_ONLY" = 0 ]; then
    step "Checking required software"
    if [ -r /etc/os-release ]; then . /etc/os-release; info "OS: ${PRETTY_NAME:-unknown}"; fi
    have apt-get || die "apt-get not found: this script is for Ubuntu/Debian. See README.md for manual steps."

    if ! have git || ! have curl || ! have ss; then
      confirm "Install git, curl and iproute2 with apt?" || die "git and curl are required."
      apt_install git curl ca-certificates gnupg iproute2
    fi

    if ! PY="$(find_python)"; then
      confirm "Python 3.12+ not found. Install it with apt?" || die "Python 3.12+ is required."
      if apt-cache show python3.12 >/dev/null 2>&1; then
        apt_install python3.12 python3.12-venv
      else  # Ubuntu 22.04 and older: deadsnakes PPA
        apt_install software-properties-common
        retry 3 $SUDO add-apt-repository -y ppa:deadsnakes/ppa || die "Could not add the deadsnakes PPA."
        apt_updated=0
        apt_install python3.12 python3.12-venv
      fi
      PY="$(find_python)" || die "Python 3.12 install failed."
    fi

    if ! node_ok; then
      confirm "Node.js 22.18+ not found. Install Node.js 24 LTS from NodeSource?" || die "Node.js 22.18+ is required."
      local ns; ns="$(mktemp)"
      retry 3 curl -fsSL https://deb.nodesource.com/setup_24.x -o "$ns" || die "Could not download the NodeSource setup script."
      ${SUDO:+$SUDO -E} bash "$ns" || die "The NodeSource setup script failed (output above)."
      rm -f "$ns"; apt_updated=1
      apt_install nodejs
      hash -r
      node_ok || die "Node.js install failed ('which node' = $(command -v node || echo none))."
    fi

    if [ "$SKIP_DOCKER" = 0 ] && ! have docker; then
      confirm "Docker not found. Install Docker Engine + Compose plugin from download.docker.com?" \
        || die "Docker is required (or re-run with --skip-docker)."
      apt_install ca-certificates curl
      $SUDO install -m 0755 -d /etc/apt/keyrings
      retry 3 $SUDO curl -fsSL "https://download.docker.com/linux/${ID:-ubuntu}/gpg" -o /etc/apt/keyrings/docker.asc \
        || die "Could not download Docker's signing key."
      $SUDO chmod a+r /etc/apt/keyrings/docker.asc
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID:-ubuntu} ${UBUNTU_CODENAME:-${VERSION_CODENAME:-}} stable" \
        | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
      apt_updated=0
      apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      if [ -n "$SUDO" ]; then
        $SUDO usermod -aG docker "$(id -un)"
        warn "Added $(id -un) to the docker group; log out and back in to use docker without sudo."
      fi
    fi
  else
    PY="$(find_python)" || die "Python 3.12+ not found; run the full setup first (without --run-only)."
  fi

  if [ "$SKIP_DOCKER" = 0 ] && have docker; then
    if ! docker info >/dev/null 2>&1; then
      if have systemctl; then $SUDO systemctl enable --now docker >/dev/null 2>&1 || true; fi
      if ! docker info >/dev/null 2>&1; then
        if [ -n "$SUDO" ] && sudo docker info >/dev/null 2>&1; then
          DOCKER="sudo docker"; info "Using 'sudo docker' for this run."
        else
          die "The Docker daemon is not running. Start it (sudo systemctl start docker) and re-run."
        fi
      fi
    fi
    $DOCKER compose version >/dev/null 2>&1 || die "'docker compose' plugin missing: sudo apt-get install docker-compose-plugin"
  fi
  local PYVER; PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  ok "python $PYVER ($PY), node $(node --version)$([ "$SKIP_DOCKER" = 0 ] && have docker && printf ', %s' "$($DOCKER --version)")"

  # ---------------- 2. repository ----------------
  if [ -z "$ROOT" ]; then
    ROOT="$PWD/TemplateOS"
    if [ -d "$ROOT/.git" ]; then info "Using existing clone: $ROOT"
    elif [ "$RUN_ONLY" = 1 ]; then die "Repository not found at $ROOT."
    else retry 3 git clone --branch "$BRANCH" "$REPO_URL" "$ROOT" || die "git clone failed (network? branch '$BRANCH'?)"; fi
  fi
  cd "$ROOT"
  if [ -d .git/info ] && ! grep -qx 'logs/' .git/info/exclude 2>/dev/null; then echo 'logs/' >> .git/info/exclude; fi

  if [ "$RUN_ONLY" = 0 ]; then
    step "Getting the code (branch: $BRANCH)"
    info "Repository: $ROOT"
    if [ "$SKIP_PULL" = 0 ]; then
      if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        git status --short --untracked-files=no | sed 's/^/      /'
        die "Uncommitted changes (listed above). Commit or stash them, or re-run with --skip-pull."
      fi
      retry 3 git fetch origin "$BRANCH" || die "git fetch failed (network? does branch '$BRANCH' exist on origin?)"
      if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
        if git show-ref --verify --quiet "refs/heads/$BRANCH"; then git checkout "$BRANCH"
        else git checkout -b "$BRANCH" --track "origin/$BRANCH"; fi
      fi
      git pull --ff-only origin "$BRANCH" || die "git pull --ff-only failed: local branch has diverged from origin/$BRANCH."
      ok "at $(git log -1 --format='%h %s')"
    else
      info "Skipping git pull (--skip-pull). Current: $(git rev-parse --abbrev-ref HEAD) $(git log -1 --format='%h')"
    fi
    [ -f docker-compose.yml ] && [ -d backend ] && [ -d frontend ] \
      || die "This checkout has no docker-compose.yml / backend / frontend. Is '$BRANCH' the right branch?"
  fi

  # ---------------- 3. .env ----------------
  local PUBLIC_URL=""
  [ -n "$PUBLIC_HOST" ] && PUBLIC_URL="$(public_url "$PUBLIC_HOST" "$PUBLIC_PORT")"
  local USE_LOCAL_DB=0 dburl=""
  if [ "$RUN_ONLY" = 0 ]; then
    step "Configuring .env"
    if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; info "Created .env from .env.example"; fi

    local jwt; jwt="$(env_get JWT_SECRET_KEY)"
    if [ -z "$jwt" ] || [ "$jwt" = "generate-a-long-random-secret-here" ] || [ "${#jwt}" -lt 32 ]; then
      env_set JWT_SECRET_KEY "$(new_secret)"; info "Generated JWT_SECRET_KEY"
    fi

    dburl="$(env_get DATABASE_URL)"
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
      [ -t 0 ] || die "DATABASE_URL is not set and there is no keyboard to paste it: set it in .env or use --db local."
      local url=""
      read -r -p "    Paste your PostgreSQL/Neon connection string: " url || true
      [ -n "$url" ] || die "No DATABASE_URL given."
      env_set DATABASE_URL "$url"; dburl="$url"
    fi

    # EkLink single sign-on addresses
    local EK="$EKLINK_URL_ARG"
    [ -z "$EK" ] && [ -n "$PUBLIC_HOST" ] && EK="http://$PUBLIC_HOST"
    EK="${EK%/}"
    if [ -n "$EK" ]; then
      env_set EKLINK_URL "$EK"; env_set EKLINK_ISSUER "$EK"; info "EKLINK_URL / EKLINK_ISSUER -> $EK"
    fi
    if [ -n "$PUBLIC_URL" ]; then
      env_set EKLINK_REDIRECT_URI "$PUBLIC_URL/auth/callback"
      env_set BACKEND_CORS_ORIGINS "$PUBLIC_URL"
      env_set TRUSTED_PROXY_IPS "127.0.0.1"
      env_set COOKIE_SECURE "false"   # plain HTTP on the IP; set true once HTTPS is in front
      info "EKLINK_REDIRECT_URI -> $PUBLIC_URL/auth/callback, BACKEND_CORS_ORIGINS -> $PUBLIC_URL"
      info "TRUSTED_PROXY_IPS -> 127.0.0.1 (Nginx), COOKIE_SECURE -> false (plain HTTP)"
      warn "This callback must be registered in EkLink (setup-all-ubuntu.sh does it):"
      info "  cd ../EkLink && node --env-file=.env scripts/set-app-url.mjs --slug templateos --url $PUBLIC_URL --callback $PUBLIC_URL/auth/callback"
    fi

    if [ "$WITH_EDITOR" = 1 ]; then
      local oo; oo="$(env_get ONLYOFFICE_JWT_SECRET)"
      if [ -z "$oo" ] || [ "${#oo}" -lt 32 ] || [ "$oo" = "generate-a-long-random-secret-for-onlyoffice" ]; then
        env_set ONLYOFFICE_JWT_SECRET "$(new_secret)"
      fi
      env_set ONLYOFFICE_ENABLED true
      if [ -n "$PUBLIC_HOST" ]; then env_set ONLYOFFICE_PUBLIC_URL "http://$PUBLIC_HOST:8082"
      else env_set ONLYOFFICE_PUBLIC_URL http://localhost:8082; fi
      env_set BACKEND_URL_FOR_ONLYOFFICE http://host.docker.internal:8000
      info "Word editor (ONLYOFFICE) enabled in .env"
      [ -n "$PUBLIC_HOST" ] && warn "Editor on EC2: open TCP 8082 in the security group (NOT 8000)."
    fi
    [ "$SKIP_DOCKER" = 1 ] && warn "Docker skipped: PDF output needs Gotenberg or a local LibreOffice (see README)."
  fi
  [ -f .env ] || die ".env is missing; run the full setup first (without --run-only)."
  [ -n "$dburl" ] || dburl="$(env_get DATABASE_URL)"
  case "$dburl" in *@localhost:5433/*|*@127.0.0.1:5433/*) USE_LOCAL_DB=1 ;; esac
  [ "$WITH_EDITOR" = 0 ] && [ "$(env_get ONLYOFFICE_ENABLED)" = "true" ] && WITH_EDITOR=1

  # ---------------- 4. Docker services ----------------
  if [ "$SKIP_DOCKER" = 0 ] && have docker; then
    step "Starting Docker services"
    retry 2 $DOCKER compose up -d gotenberg || die "Could not start Gotenberg (docker compose up -d gotenberg)."
    if [ "$USE_LOCAL_DB" = 1 ]; then
      retry 2 $DOCKER compose --profile db up -d --wait postgres || die "Local PostgreSQL did not become healthy ($DOCKER compose logs postgres)."
    fi
    if [ "$WITH_EDITOR" = 1 ]; then
      info "Starting ONLYOFFICE (first pull is large and the first start takes a few minutes)"
      ONLYOFFICE_JWT_SECRET="$(env_get ONLYOFFICE_JWT_SECRET)" $DOCKER compose --profile editor up -d onlyoffice
    fi
    $DOCKER compose ps
  fi

  # ---------------- 5. backend ----------------
  local VPY="$ROOT/backend/.venv/bin/python"
  if [ "$RUN_ONLY" = 0 ]; then
    step "Installing backend dependencies (backend/.venv)"
    if [ ! -x "$VPY" ]; then
      if ! "$PY" -m venv backend/.venv; then
        rm -rf backend/.venv
        apt_install "python${PYVER}-venv"
        "$PY" -m venv backend/.venv || die "Could not create backend/.venv."
      fi
    fi
    retry 2 "$VPY" -m pip install --upgrade pip || die "pip upgrade failed (network?)"
    retry 2 "$VPY" -m pip install -r backend/requirements.txt || die "pip install -r backend/requirements.txt failed (error above)."

    step "Running database migrations"
    (cd backend && "$VPY" -m alembic upgrade head) \
      || die "Migrations failed. Check DATABASE_URL in .env (and that the database is reachable)."

    if [ "$SEED_DEMO" = 0 ] && [ "$ASSUME_YES" = 0 ] && [ -t 0 ]; then
      local r; read -r -p "    Seed the demo users (SIT_* in .env)? [y/N] " r || true
      case "$r" in [yY]*) SEED_DEMO=1 ;; esac
    fi
    if [ "$SEED_DEMO" = 1 ]; then
      (cd backend && "$VPY" scripts/seed_demo_users.py) || die "Seeding demo users failed (error above)."
    fi

    # ---------------- 6. frontend ----------------
    step "Installing frontend dependencies (npm workspaces)"
    retry 2 npm install --no-audit --no-fund || die "npm install failed (network, disk space, Node version?)."
  fi
  [ -x "$VPY" ] || die "backend/.venv is missing; run the full setup first (without --run-only)."

  # ---------------- 7. run ----------------
  if [ "$NO_RUN" = 1 ] && [ "$MODE" = "dev" ]; then
    step "Setup complete"
    info "Start both servers: bash scripts/setup-ubuntu.sh --run-only"
    info "or separately:      cd backend && .venv/bin/python -m uvicorn app.main:app --reload   |   npm run dev:frontend"
    return 0
  fi

  local HOST="127.0.0.1"; [ "$WITH_EDITOR" = 1 ] && HOST="0.0.0.0"

  if [ "$MODE" = "dev" ]; then
    step "Starting backend (http://localhost:8000) and frontend (http://localhost:5173)"
    local p; for p in 8000 5173; do
      if port_busy "$p"; then
        ss -ltnpH "sport = :$p" 2>/dev/null | sed 's/^/      /' || true
        die "Port $p is already in use (listed above). Stop that process (or: sudo systemctl stop $SERVICE-backend) and re-run."
      fi
    done
    info "Press Ctrl+C to stop both."
    (cd backend && exec "$VPY" -m uvicorn app.main:app --reload --host "$HOST" --port 8000) &
    BACKEND_PID=$!
    trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
    wait_http "http://127.0.0.1:8000/health" 60 && ok "backend is up" || warn "backend not answering yet on :8000 (see its output above)"
    npm run dev:frontend
    return 0
  fi

  # ---------------- prod mode ----------------
  [ -d /run/systemd/system ] || die "systemd is not running here; --mode prod needs systemd (use --mode dev)."
  if [ "$RUN_ONLY" = 0 ]; then
    step "Building the frontend for production (vite build, API at /api/v1)"
    local mem_kb swap_kb
    mem_kb="$(awk '/^MemTotal:/{print $2}' /proc/meminfo)"; swap_kb="$(awk '/^SwapTotal:/{print $2}' /proc/meminfo)"
    info "Memory: $((mem_kb / 1024)) MB RAM + $((swap_kb / 1024)) MB swap; disk free: $(df -Pm . | awk 'NR==2{print $4}') MB"
    if [ $(((mem_kb + swap_kb) / 1024)) -lt 3500 ]; then
      if [ -f /swapfile ]; then
        grep -q '^/swapfile ' /proc/swaps || $SUDO swapon /swapfile || warn "Could not enable /swapfile"
      elif confirm "Less than 3.5 GB RAM+swap: the build may be killed (out of memory). Create a 4 GB /swapfile?"; then
        $SUDO fallocate -l 4G /swapfile 2>/dev/null || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=4096 status=none
        $SUDO chmod 600 /swapfile && $SUDO mkswap /swapfile >/dev/null && $SUDO swapon /swapfile
        grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
        ok "4 GB swap enabled"
      fi
    fi
    # An environment variable beats .env in Vite, so the build calls the same-origin /api/v1.
    VITE_API_BASE_URL=/api/v1 npm run build:frontend || die "Frontend build failed (TypeScript or Vite error above)."
    [ -f frontend/dist/index.html ] || die "frontend/dist/index.html was not produced."
    # Nginx (www-data) cannot read /home/<user> on Ubuntu 22.04+, so publish a copy.
    $SUDO mkdir -p "$WEB_ROOT"
    $SUDO find "$WEB_ROOT" -mindepth 1 -delete
    $SUDO cp -r frontend/dist/. "$WEB_ROOT/"
    ok "frontend published to $WEB_ROOT"
  fi
  [ -f "$WEB_ROOT/index.html" ] || die "$WEB_ROOT/index.html missing; run without --run-only first."

  step "Installing the systemd service '$SERVICE-backend' ($HOST:8000)"
  local RUN_USER; RUN_USER="$(id -un)"
  $SUDO tee "/etc/systemd/system/$SERVICE-backend.service" >/dev/null <<UNIT
[Unit]
Description=TemplateOS backend (FastAPI / uvicorn, port 8000)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$ROOT/backend
ExecStart=$VPY -m uvicorn app.main:app --host $HOST --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable "$SERVICE-backend" >/dev/null 2>&1
  $SUDO systemctl restart "$SERVICE-backend"
  if ! wait_http "http://127.0.0.1:8000/health" 90; then
    $SUDO journalctl -u "$SERVICE-backend" -n 60 --no-pager || true
    die "The backend did not answer on 127.0.0.1:8000/health within 90s (service log above)."
  fi
  ok "backend is running (logs: journalctl -u $SERVICE-backend -f)"

  step "Configuring Nginx (public port $PUBLIC_PORT: frontend + /api -> 127.0.0.1:8000)"
  have nginx || apt_install nginx
  local SITE="/etc/nginx/sites-available/pbl-$SERVICE.conf" LINK="/etc/nginx/sites-enabled/pbl-$SERVICE.conf"
  $SUDO tee "$SITE" >/dev/null <<NGINX
# Managed by TemplateOS/scripts/setup-ubuntu.sh -- re-running the script overwrites this file.
server {
    listen $PUBLIC_PORT;
    server_name _;
    client_max_body_size 25m;
    root $WEB_ROOT;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 180s;
    }
    location = /health { proxy_pass http://127.0.0.1:8000/health; }
    location /assets/ { try_files \$uri =404; expires 7d; add_header Cache-Control "public"; }
    location / { try_files \$uri \$uri/ /index.html; }
}
NGINX
  $SUDO ln -sf "$SITE" "$LINK"
  if ! $SUDO nginx -t; then
    $SUDO rm -f "$LINK"
    die "Nginx rejected the configuration (error above). $SITE was disabled so Nginx keeps working."
  fi
  $SUDO systemctl enable nginx >/dev/null 2>&1 || true
  $SUDO systemctl reload nginx 2>/dev/null || $SUDO systemctl restart nginx
  if have ufw && $SUDO ufw status 2>/dev/null | grep -q '^Status: active'; then
    $SUDO ufw allow "$PUBLIC_PORT/tcp" >/dev/null && info "ufw: allowed port $PUBLIC_PORT/tcp"
  fi
  wait_http "http://127.0.0.1:$PUBLIC_PORT/" 30 || die "Nginx is not answering on port $PUBLIC_PORT (sudo tail /var/log/nginx/error.log)."
  wait_http "http://127.0.0.1:$PUBLIC_PORT/health" 15 || warn "/health through Nginx did not answer (check the /api proxy)."

  step "Done"
  ok "$PROJECT is running in production mode."
  info "Local:   http://127.0.0.1:$PUBLIC_PORT"
  [ -n "$PUBLIC_URL" ] && info "Public:  $PUBLIC_URL   (EC2: allow inbound TCP $PUBLIC_PORT in the security group)"
  info "Status:  systemctl status $SERVICE-backend     Logs: journalctl -u $SERVICE-backend -f"
  info "Docker:  $DOCKER compose ps   (Gotenberg restarts by itself after a reboot)"
}

main "$@"
