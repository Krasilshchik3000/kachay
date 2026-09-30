# kachay

Личный Telegram-бот: кидаешь ссылку на пост Instagram (фото, карусель, reels, stories) или видео YouTube — получаешь в ответ сам контент: фото, видео или аудио. Пользоваться могут только user id из белого списка, остальных бот молча игнорирует.

Под капотом: [aiogram 3](https://docs.aiogram.dev/), [yt-dlp](https://github.com/yt-dlp/yt-dlp) (YouTube и всё остальное), [gallery-dl](https://github.com/mikf/gallery-dl) (Instagram), ffmpeg.

## Как пользоваться

| Что прислать | Что вернётся |
|---|---|
| ссылка на YouTube | видео mp4 (h264) в максимальном качестве, которое влезает в лимит, + кнопка «🎧 Аудио» |
| ссылка на Instagram пост / карусель / reels / stories | фото и видео альбомом (по 10 штук), подпись поста в описании |
| ссылка + слово `аудио` (`audio`, `mp3`) | только звук, m4a, с обложкой |
| ссылка + слово `файл` (`file`) | те же файлы, но документами — без пережатия Telegram |
| ссылка `music.youtube.com` | сразу аудио |
| любая другая ссылка | что сможет вытащить yt-dlp (TikTok, X, Vimeo, ...) |

Трекинг-параметры (`?igsh=`, `&list=`, `?si=`) вырезаются сами.

## Быстрый старт (Docker)

1. Создай бота у [@BotFather](https://t.me/BotFather), получи токен.
2. Узнай свой user id: напиши [@userinfobot](https://t.me/userinfobot).
3. Экспортируй cookies из браузера (см. ниже) в `cookies/cookies.txt`.
4. Настрой окружение:
   ```bash
   cp .env.example .env
   # впиши BOT_TOKEN и ALLOWED_USER_IDS
   ```
5. Запусти:
   ```bash
   docker compose up -d --build
   docker compose logs -f bot
   ```

При каждом старте контейнер обновляет yt-dlp и gallery-dl (`UPDATE_ON_START=1`): YouTube и Instagram регулярно ломают старые версии. Перезапуск = обновление: `docker compose restart bot`.

## Cookies (обязательно для Instagram)

Instagram без залогиненной сессии отдаёт пустой ответ или требует логин практически на любой пост. gallery-dl и yt-dlp умеют читать cookies в формате Netscape (`cookies.txt`).

1. Поставь расширение [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome) или [cookies.txt](https://addons.mozilla.org/firefox/addon/cookies-txt/) (Firefox).
2. Открой **приватное окно**, залогинься в instagram.com (и в youtube.com, если хочешь cookies и для него).
3. Экспортируй cookies расширением, сохрани как `cookies/cookies.txt`.
4. **Закрой приватное окно, не разлогиниваясь.** Если сессию продолжать использовать в браузере, YouTube ротирует cookies и файл протухнет.

Один файл может содержать cookies обоих сайтов. Бот на каждый запрос делает копию файла и работает с ней, оригинал не меняется.

Cookies YouTube нужны не всегда: с домашнего IP обычно работает и без них. С VPS YouTube часто отвечает «Sign in to confirm you're not a bot» — тогда либо cookies, либо PO-токены (ниже).

## Лимиты размера

Обычный Bot API принимает от бота файлы до **50 МБ**, фото — до 10 МБ. Поэтому:

- для YouTube бот считает размер по данным yt-dlp и берёт максимальное качество, которое влезает: 1080p → 720p → 480p → 360p (`MAX_VIDEO_HEIGHT` ограничивает сверху);
- видео с Instagram, которое не влезло, перекодируется ffmpeg под лимит (720p, битрейт по длительности);
- если не влезает ничего — бот так и напишет. Выход: попросить «аудио» или поднять локальный Bot API сервер.

### Локальный Bot API сервер: до 2 ГБ

1. Получи `api_id` и `api_hash` на https://my.telegram.org.
2. В `.env` добавь:
   ```
   TELEGRAM_API_ID=...
   TELEGRAM_API_HASH=...
   TELEGRAM_API_BASE=http://telegram-bot-api:8081
   ```
   `MAX_UPLOAD_MB` при заданном `TELEGRAM_API_BASE` по умолчанию становится 2000.
3. Один раз отвяжи бота от официального сервера (иначе локальный его не примет):
   ```bash
   curl -s "https://api.telegram.org/bot<BOT_TOKEN>/logOut"
   ```
4. Запусти с профилем:
   ```bash
   docker compose --profile local-api up -d --build
   ```

## PO-токены для YouTube (если ругается на ботов с сервера)

```bash
# в .env
YTDLP_POT_PROVIDER_URL=http://pot-provider:4416
```
```bash
docker compose --profile pot up -d --build
```
Контейнер `pot-provider` — это [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider); плагин к yt-dlp доустанавливается при старте бота, когда переменная задана. Токен не гарантирует обход проверки, но обычно помогает вместе с cookies.

## Без Docker

Нужны Python ≥ 3.11, ffmpeg и [deno](https://deno.com) (JS-рантайм для YouTube; можно node ≥ 22 с `YTDLP_JS_RUNTIME=node`).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # заполнить
set -a; . ./.env; set +a
python -m kachay
```

Тесты (без сети): `pytest`.

## Переменные окружения

Все — в [`.env.example`](.env.example) с комментариями. Обязательные: `BOT_TOKEN`, `ALLOWED_USER_IDS`. Практически обязательная: `COOKIES_FILE`.

## Как устроено

```
kachay/
  links.py            распознавание ссылок и слов «аудио»/«файл»
  service.py          временная папка на запрос, выбор загрузчика, копия cookies
  downloaders/
    ytdlp.py          YouTube и прочее: probe → выбор форматов под лимит → скачивание
    formats.py        чистая логика выбора форматов (h264 mp4 + m4a, лестница качества)
    instagram.py      gallery-dl (посты, карусели, reels, stories) с запасным yt-dlp
  media.py            ffprobe / превью / перекодирование под лимит
  sender.py           альбомы по 10, видео с превью и размерами, аудио, документы
  bot.py              хэндлеры aiogram, белый список, статус «⏳ Качаю…»
```

## Что может сломаться

- **Instagram** меняет API чаще всех. Если перестало работать: перезапусти контейнер (обновит gallery-dl), потом обнови cookies.
- **YouTube** — то же самое плюс проверка на ботов. Порядок действий: перезапуск → cookies → PO-токены.
- В логах (`docker compose logs -f bot`) есть вывод yt-dlp и gallery-dl целиком.
