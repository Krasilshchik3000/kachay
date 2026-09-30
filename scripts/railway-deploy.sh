#!/usr/bin/env bash
# Разворачивает бота на Railway одной командой.
#
# Нужно:
#   - Railway CLI (npm i -g @railway/cli) и вход: `railway login` или переменная RAILWAY_API_TOKEN;
#   - BOT_TOKEN, ALLOWED_USER_IDS, COOKIES_B64 в окружении или в .env рядом с репозиторием.
#
# Переменные скрипта (необязательные):
#   RAILWAY_PROJECT  имя проекта (kachay)
#   RAILWAY_SERVICE  имя сервиса (kachay)
#   RAILWAY_SOURCE   image — готовый образ из GHCR (по умолчанию); repo — сборка из GitHub-репозитория
#                    (для repo у Railway GitHub App должен быть доступ к репозиторию)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
    set -a; . ./.env; set +a
fi

PROJECT=${RAILWAY_PROJECT:-kachay}
SERVICE=${RAILWAY_SERVICE:-kachay}
SOURCE=${RAILWAY_SOURCE:-image}
IMAGE=${RAILWAY_IMAGE:-ghcr.io/krasilshchik3000/kachay:latest}
REPO=${RAILWAY_REPO:-Krasilshchik3000/kachay}
BRANCH=${RAILWAY_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}

die() { echo "ошибка: $*" >&2; exit 1; }

command -v railway >/dev/null 2>&1 || die "railway CLI не найден: npm i -g @railway/cli"
railway whoami >/dev/null 2>&1 || die "не авторизован в Railway: выполни 'railway login' или задай RAILWAY_API_TOKEN"

: "${BOT_TOKEN:?нужен BOT_TOKEN (токен от @BotFather)}"
ALLOWED_USER_IDS=${ALLOWED_USER_IDS:-0}
if [ -z "${COOKIES_B64:-}" ] && [ -s cookies/cookies.txt ]; then
    COOKIES_B64=$(base64 < cookies/cookies.txt | tr -d '\n')
fi
[ -n "${COOKIES_B64:-}" ] || echo "предупреждение: COOKIES_B64 не задан, Instagram будет требовать логин"

if railway status >/dev/null 2>&1; then
    echo "→ папка уже привязана к проекту Railway, использую его"
else
    echo "→ создаю проект $PROJECT"
    railway init --name "$PROJECT" --json >/dev/null
fi

if railway service list --json 2>/dev/null | grep -Eq "\"name\": ?\"$SERVICE\""; then
    echo "→ сервис $SERVICE уже есть"
else
    echo "→ создаю сервис $SERVICE (источник: $SOURCE)"
    if [ "$SOURCE" = "repo" ]; then
        railway add --service "$SERVICE" --repo "$REPO" --branch "$BRANCH"
    else
        railway add --service "$SERVICE" --image "$IMAGE"
    fi
fi

echo "→ задаю переменные"
vars=(
    "BOT_TOKEN=$BOT_TOKEN"
    "ALLOWED_USER_IDS=$ALLOWED_USER_IDS"
    "DOWNLOAD_DIR=/data"
    "UPDATE_ON_START=1"
    "AUTO_RESTART_HOURS=${AUTO_RESTART_HOURS:-24}"
)
[ -n "${COOKIES_B64:-}" ] && vars+=("COOKIES_B64=$COOKIES_B64")
railway variable set -s "$SERVICE" --skip-deploys "${vars[@]}" >/dev/null

echo "→ деплой"
railway service redeploy -s "$SERVICE" --from-source -y

cat <<MSG

Готово. Логи:     railway logs -s $SERVICE
Обновить образ:   railway service redeploy -s $SERVICE --from-source -y
Если ALLOWED_USER_IDS=0: напиши боту /start, он пришлёт твой id, затем
  railway variable set -s $SERVICE ALLOWED_USER_IDS=<id>
MSG
