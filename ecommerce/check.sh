#!/usr/bin/env bash
#
# Run before every commit and after every pull.
#
#   ./check.sh          full run
#   ./check.sh --fast   skip the slow browser-free page render pass
#
# Exits non-zero on the first failure so CI and git hooks can gate on it.

set -euo pipefail
cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
step() { printf "\n${YELLOW}▸ %s${NC}\n" "$1"; }
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$1"; }
fail() { printf "${RED}  ✗ %s${NC}\n" "$1"; exit 1; }

PY=${PYTHON:-python3}

step "1/6  Django system check"
$PY manage.py check --fail-level WARNING > /dev/null || fail "system check failed"
ok "no configuration problems"

step "2/6  Migrations are complete"
# Catches a model edited without makemigrations — a classic cause of
# 'column does not exist' errors that only surface in production.
if ! $PY manage.py makemigrations --check --dry-run > /dev/null 2>&1; then
    fail "model changes have no migration — run: $PY manage.py makemigrations"
fi
ok "no missing migrations"

step "3/6  Migrations apply cleanly"
$PY manage.py migrate --check > /dev/null 2>&1 \
    || fail "unapplied migrations — run: $PY manage.py migrate"
ok "database schema up to date"

step "4/6  Translations compile"
$PY manage.py compilemessages > /dev/null 2>&1 || fail "compilemessages failed"
ok "locale catalogs compiled"

step "5/6  Test suite"
$PY manage.py test --verbosity=1 || fail "tests failed"
ok "all tests passed"

step "6/6  Production-mode render"
if [ "${1:-}" = "--fast" ]; then
    printf "  (skipped)\n"
else
    # Mirrors the VPS exactly: DEBUG off + WhiteNoise manifest storage. This
    # catches a {% static %} pointing at a file that does not exist, which
    # DEBUG silently tolerates but which hard-500s in production.
    export DJANGO_DEBUG=False
    export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
    export DJANGO_SECURE_SSL_REDIRECT=False

    $PY manage.py collectstatic --noinput > /dev/null 2>&1 \
        || fail "collectstatic failed — a {% static %} file is missing"
    ok "collectstatic resolved every static reference"

    $PY manage.py test store.tests.test_smoke --verbosity=0 \
        || fail "pages do not render with DEBUG=False"
    ok "pages render in production mode"

    unset DJANGO_DEBUG DJANGO_ALLOWED_HOSTS DJANGO_SECURE_SSL_REDIRECT
fi

printf "\n${GREEN}════════════════════════════════════════${NC}\n"
printf "${GREEN}  ALL CHECKS PASSED — safe to commit${NC}\n"
printf "${GREEN}════════════════════════════════════════${NC}\n"
