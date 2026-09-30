#!/bin/sh
set -e

# Без токена бот работать не может. Не крутим tight-loop перезапусков (Docker/Railway
# поднимают контейнер заново сразу): пишем, что делать, и ждём, чтобы не долбить PyPI и логи.
if [ -z "${BOT_TOKEN:-}" ]; then
    echo "[entrypoint] BOT_TOKEN не задан. Добавь переменную BOT_TOKEN (токен от @BotFather) и перезапусти сервис."
    echo "[entrypoint] Жду 5 минут перед выходом, чтобы не перезапускаться каждые несколько секунд."
    sleep 300
    exit 2
fi

# yt-dlp ломается и чинится каждые пару недель — обновляем при старте.
if [ "${UPDATE_ON_START:-1}" = "1" ]; then
    echo "[entrypoint] обновляю yt-dlp и gallery-dl..."
    pip install -q --root-user-action=ignore -U "yt-dlp[default]" gallery-dl \
        || echo "[entrypoint] обновление не удалось, работаю с установленными версиями"
fi

# Плагин PO-токенов ставим только если настроен сервер: без него он лишь шумит в логах.
if [ -n "${YTDLP_POT_PROVIDER_URL:-}" ]; then
    echo "[entrypoint] ставлю плагин PO-токенов (YTDLP_POT_PROVIDER_URL=$YTDLP_POT_PROVIDER_URL)..."
    pip install -q --root-user-action=ignore -U bgutil-ytdlp-pot-provider \
        || echo "[entrypoint] не удалось поставить bgutil-ytdlp-pot-provider"
fi

exec "$@"
