#!/usr/bin/env bash
# TemplateOS UPDATE script for an EC2 / Ubuntu server that was already set up
# with scripts/setup-ubuntu.sh --mode prod (HTTPS via Nginx + Certbot).
#
#   bash scripts/update-ubuntu.sh [--skip-pull]
#
# What it does (run from anywhere inside the repo):
#   1. git pull --ff-only on the branch that is checked out
#   2. backend: pip install -r requirements.txt, alembic upgrade head
#   3. frontend: npm ci, production build (API at /api/v1), publish to /var/www/templateos
#   4. restart the templateos-backend systemd service and check /health
#
# What it deliberately does NOT touch:
#   - Nginx config, the HTTPS certificate (Certbot), the systemd unit file
#   - .env (your secrets and settings stay as they are)
#   - Docker / Gotenberg, the database server, the storage folder
#
# Safe to run as many times as you like. If a step fails, the script stops and
# the running site keeps serving the previous build (the new frontend is only
# published after its build succeeded).

set -Eeuo pipefail

WEB_ROOT="/var/www/templateos"
SERVICE="templateos-backend"
SKIP_PULL=0

for arg in "$@"; do
  case "$arg" in
    --skip-pull) SKIP_PULL=1 ;;
    -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then C_STEP=$'\033[1;36m'; C_OK=$'\033[1;32m'; C_ERR=$'\033[1;31m'; C_END=$'\033[0m'
else C_STEP=""; C_OK=""; C_ERR=""; C_END=""; fi

step() { printf '\n%s==> %s%s\n' "$C_STEP" "$*" "$C_END"; }
ok()   { printf '    %s[ok]%s %s\n' "$C_OK" "$C_END" "$*"; }
die()  { printf '%s[x] %s%s\n' "$C_ERR" "$*" "$C_END" >&2; exit 1; }

trap 'printf "%s[x] Update stopped at line %s: %s%s\n" "$C_ERR" "$LINENO" "$BASH_COMMAND" "$C_END" >&2' ERR

REPO="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)" \
  || die "Not inside a git checkout. Run this from the TemplateOS repo."
cd "$REPO"

[ -f .env ] || die ".env is missing in $REPO. Restore it before updating (see the deploy guide)."
[ -x backend/.venv/bin/python ] || die "backend/.venv is missing. Run scripts/setup-ubuntu.sh --mode prod first."
[ -d "$WEB_ROOT" ] || die "$WEB_ROOT is missing. Run scripts/setup-ubuntu.sh --mode prod first."

# ---------------- 1. code ----------------
step "1. Pulling the latest code ($(git rev-parse --abbrev-ref HEAD))"
if [ "$SKIP_PULL" = 1 ]; then
  ok "skipped (--skip-pull)"
else
  git pull --ff-only || die "git pull failed. Fix local changes to tracked files (git status), then re-run."
  ok "now at $(git log -1 --format='%h %s')"
fi

# ---------------- 2. backend ----------------
step "2. Backend dependencies and database migrations"
backend/.venv/bin/python -m pip install --quiet --upgrade pip
backend/.venv/bin/python -m pip install --quiet -r backend/requirements.txt
ok "python packages installed"
(cd backend && .venv/bin/python -m alembic upgrade head)
ok "database is at the latest migration"

# ---------------- 3. frontend ----------------
step "3. Building the frontend (API at /api/v1)"
npm ci --no-audit --no-fund
VITE_API_BASE_URL=/api/v1 npm run build:frontend
[ -f frontend/dist/index.html ] || die "frontend/dist/index.html was not produced; the old site is still live."
ok "build succeeded"

sudo find "$WEB_ROOT" -mindepth 1 -delete
sudo cp -r frontend/dist/. "$WEB_ROOT/"
ok "published to $WEB_ROOT"

# ---------------- 4. restart + check ----------------
step "4. Restarting the backend"
sudo systemctl restart "$SERVICE"
for _ in $(seq 1 30); do
  if curl -fsS -m 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    ok "backend answers on 127.0.0.1:8000/health"
    break
  fi
  sleep 2
done
curl -fsS -m 3 http://127.0.0.1:8000/health >/dev/null 2>&1 \
  || die "backend did not answer after restart. Check: sudo journalctl -u $SERVICE -n 80 --no-pager"

step "Update finished"
ok "$(sudo systemctl is-active "$SERVICE")"
echo "    Logs: sudo journalctl -u $SERVICE -f"
