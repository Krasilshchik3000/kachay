FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# JS-рантайм для YouTube: yt-dlp решает JS-челленджи YouTube через deno.
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY pyproject.toml README.md ./
COPY kachay ./kachay
RUN pip install .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Без инструкции VOLUME: Railway её не принимает, а docker-compose монтирует /data сам.
ENV DOWNLOAD_DIR=/data
RUN mkdir -p /data

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "kachay"]
