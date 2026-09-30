#!/bin/sh
set -e

# yt-dlp ломается и чинится каждые пару недель — обновляем при старте.
if [ "${UPDATE_ON_START:-1}" = "1" ]; then
    echo "[entrypoint] обновляю yt-dlp и gallery-dl..."
    pip install -q -U "yt-dlp[default]" gallery-dl \
        || echo "[entrypoint] обновление не удалось, работаю с установленными версиями"
fi

# Плагин PO-токенов ставим только если настроен сервер: без него он лишь шумит в логах.
if [ -n "${YTDLP_POT_PROVIDER_URL:-}" ]; then
    pip install -q -U bgutil-ytdlp-pot-provider \
        || echo "[entrypoint] не удалось поставить bgutil-ytdlp-pot-provider"
fi

exec "$@"
