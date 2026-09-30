#!/usr/bin/env bash
# Интерактивная настройка и запуск бота: спрашивает токен и id, пишет .env, поднимает docker compose.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n%s\n' "$*"; }
ask() { local prompt=$1 default=${2:-}; local v; read -r -p "$prompt${default:+ [$default]}: " v; printf '%s' "${v:-$default}"; }

if ! command -v docker >/dev/null 2>&1; then
    say "Docker не найден. Поставь его: https://docs.docker.com/engine/install/ и запусти setup.sh ещё раз."
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    say "Нужен docker compose v2 (команда 'docker compose'). Обнови Docker."
    exit 1
fi

if [ -f .env ]; then
    say ".env уже есть — оставляю как есть. Удали его, если хочешь настроить заново."
else
    say "1/3 Токен бота: создай бота у @BotFather и вставь токен."
    token=$(ask "BOT_TOKEN")
    [ -n "$token" ] || { echo "Без токена не поедем."; exit 1; }

    say "2/3 Твой Telegram user id. Не знаешь — оставь пустым: после запуска напиши боту /start, он ответит id."
    ids=$(ask "ALLOWED_USER_IDS" "")

    cp .env.example .env
    sed -i.bak -e "s|^BOT_TOKEN=.*|BOT_TOKEN=$token|" -e "s|^ALLOWED_USER_IDS=.*|ALLOWED_USER_IDS=${ids:-0}|" .env && rm -f .env.bak
    say ".env записан."
fi

mkdir -p cookies
if [ ! -s cookies/cookies.txt ]; then
    say "3/3 Cookies: положи cookies.txt (экспорт из браузера, где ты залогинен в Instagram) в ./cookies/cookies.txt."
    say "Без него Instagram почти всегда не работает; YouTube обычно работает и без cookies. Инструкция — в README."
fi

say "Собираю и запускаю..."
docker compose up -d --build

say "Готово. Логи: docker compose logs -f bot"
if grep -q '^ALLOWED_USER_IDS=0$' .env; then
    say "Напиши боту /start — он пришлёт твой user id. Впиши его в .env (ALLOWED_USER_IDS=...) и выполни: docker compose up -d"
fi
