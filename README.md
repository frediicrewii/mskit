# mskit

Мессенджер в терминале + веб-клиент + погодный бот внутри.

## Состав

- **server/** — FastAPI + SQLite + WebSocket + REST polling fallback. Включает автоматически создаваемого `@weather_bot`, который подписывает пользователей на прогноз погоды по регионам Узбекистана.
- **client/** — Python CLI `mskit` с full-screen TUI (prompt_toolkit). Polling-режим, работает через корпоративные прокси.
- **web/** — React + Vite веб-клиент в стиле Terminal future. Деплоится на Netlify.

Все три клиента смотрят в одну базу. Пишешь с компа в вебе — приходит в CLI на телефоне. Бот отвечает везде одновременно.

## Быстрый старт локально

```bash
# сервер
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export WEATHER_API_KEY="ваш-ключ-с-weatherapi.com"
uvicorn main:app --host 0.0.0.0 --port 8000

# в другом терминале: CLI
cd client
pip install .
mskit server http://localhost:8000
mskit register
mskit weather_bot    # откроет чат с ботом
```

В чате с ботом напиши `UZ`, потом номер региона (1–14).

## Деплой на Render

### 1. Залей код на GitHub

(Если на работе заблокирован git push, используй Termux на телефоне — есть инструкция в предыдущих сессиях.)

### 2. Создай сервис на Render

- [render.com](https://render.com) → **New → Web Service** → выбери репозиторий
- **Root Directory:** `server`
- **Environment:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/health`
- **Plan:** Free

### 3. Добавь environment variables

В **Environment** добавь две переменные:

| Key | Value | Описание |
|---|---|---|
| `MSKIT_SECRET_KEY` | **Generate** (кнопка рядом) | секрет для JWT, автоматически |
| `WEATHER_API_KEY` | твой ключ с weatherapi.com | нужен для погодного бота |

**Create Web Service.** Через 2–4 минуты сервер будет на `https://mskit-xxxx.onrender.com`.

### 4. Важно про безопасность ключа

Ты прислал ключ прямо в чат. **Рекомендую** зайти на [weatherapi.com/my](https://www.weatherapi.com/my/) → **Regenerate API Key** → использовать новый только через env-переменную. В коде ключ не зашит.

## Подключение клиентов

### CLI (Windows, macOS, Linux, Termux)

```bash
mskit server https://mskit-xxxx.onrender.com
mskit register
mskit weather_bot      # чат с ботом
mskit <username>       # чат с другим пользователем
```

Если на работе корпоративный MITM-прокси:
```bash
export MSKIT_INSECURE=1
```

### Веб (через Netlify)

1. `cd web && npm install && npm run build`
2. [app.netlify.com](https://app.netlify.com) → drag & drop папку `dist`
3. Открой полученный URL, введи `https://mskit-xxxx.onrender.com` как сервер

## Бот: как пользоваться

Напиши `@weather_bot` одно из:

| Команда | Что делает |
|---|---|
| `UZ` | показать 14 регионов Узбекистана |
| `1`, `2`, ... `14` | выбрать регион (после UZ) |
| `Ташкент` | прямая подписка на город (минуя UZ) |
| `/now` | прогноз прямо сейчас |
| `/change` | сменить город |
| `/stop` | отписаться |
| `/help` | справка |

После подписки прогноз приходит **каждые 10 минут**. Формат:

```
📍 Ташкент
Сегодня, 16 апреля
🌧 +14°...+9°, Дождь
Сейчас: ☁️ +13°, ↘ 1.7 м/с
Утром: 🌧 +13°
Днем: 🌧 +11°
Вечером: ☁️ +12°
Влажность: 49%
Ветер: СЗ, 6.9 м/с
Давление: 761 мм рт. ст.
Луна: Старая Луна
Восход: 05:42
Закат: 19:02
```

## Переменные окружения

### Сервер

| Переменная | Обязательна | По умолчанию | Описание |
|---|---|---|---|
| `MSKIT_SECRET_KEY` | рекомендуется | dev-значение | секрет для подписи JWT |
| `WEATHER_API_KEY` | для бота | пусто | ключ с weatherapi.com |
| `DATABASE_URL` | нет | `sqlite:///./mskit.db` | Postgres URL, если хочешь персистентность |

### CLI

| Переменная | По умолчанию | Описание |
|---|---|---|
| `MSKIT_SERVER` | `http://localhost:8000` | URL сервера (если конфиг пустой) |
| `MSKIT_CONFIG_DIR` | `~/.config/mskit` | папка конфига |
| `MSKIT_INSECURE` | — | `1` — отключить проверку SSL (корпоративный MITM) |
| `MSKIT_CA_BUNDLE` | — | путь к корпоративному CA `.crt` |

## Про персистентность данных на Render free

- База `mskit.db` хранится в файловой системе контейнера, **которая стирается при каждом редеплое** (после `git push` или ручного деплоя)
- Это значит, что при обновлении сервера все аккаунты и подписки пропадают
- Решение: подключить бесплатную Render Postgres (90 дней free), задать переменную `DATABASE_URL` — код сам подхватит
