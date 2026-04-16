# mskit-web

Веб-клиент для mskit в стиле "Terminal future". Работает с тем же сервером, что и `mskit` CLI — общая база пользователей, общие сообщения, всё синхронно.

## Стек

- React 19 + TypeScript + Vite
- WebSocket с автоматическим fallback на REST polling (если WS режется фаерволом/Cloudflare)
- Кастомный CSS, JetBrains Mono, тёмная палитра

## Локальный запуск

```bash
npm install
npm run dev
```

Откроется на http://localhost:5174. На странице логина введи URL твоего сервера (например `https://mskit.onrender.com`), зарегистрируйся или войди.

## Деплой на Netlify (3 минуты, бесплатно)

### Способ A — drag & drop (самый быстрый)

1. Локально:
   ```bash
   npm install
   npm run build
   ```
   Получится папка `dist/`.

2. Зайди на [app.netlify.com](https://app.netlify.com) → войди (можно через GitHub).
3. На главной странице снизу есть зона **"Drag and drop your site folder here"**. Перетащи туда папку `dist`.
4. Через 10 секунд получишь URL вида `https://random-name-12345.netlify.app`. Открой — увидишь экран логина. Введи URL Render-сервера, зарегистрируйся.

### Способ Б — через GitHub (для автодеплоя)

1. Залей `mskit-web` в GitHub-репозиторий (можно прямо в твой `mskit` под папкой `web/`).
2. На Netlify: **Add new site → Import from Git → выбери репозиторий**.
3. Настройки:
   - **Base directory:** `mskit-web` (или путь до папки)
   - **Build command:** `npm run build`
   - **Publish directory:** `mskit-web/dist` (или просто `dist` если base уже настроен)
4. **Deploy**.

После каждого `git push` Netlify автоматически пересоберёт и задеплоит.

## Особенности

- **Сервер прописывается на странице логина** — не зашит в код. Можно поменять в любой момент через `localStorage.removeItem('mskit.server')` в DevTools, или просто разлогиниться.
- **WebSocket → polling fallback**. Клиент сначала пробует WS. Если за 5 сек не подключился (как у тебя в офисе с Cloudflare 403), автоматически переключается на REST polling раз в 2 секунды. В сайдбаре снизу видно режим: `● ws` или `● polling`.
- **Цвета пользователей** генерируются из хеша username — стабильные, одни и те же на всех устройствах, БД не нужно расширять.
- **Файлы и картинки** — до 50 МБ через `/api/upload`. Картинки рендерятся inline, остальное как кликабельная пилюля.

## Структура

```
src/
  main.tsx, App.tsx
  components/
    AuthScreen.tsx
    Sidebar.tsx
    ChatView.tsx
    Modals.tsx
  services/
    api.ts        — REST-клиент с типами
    channel.ts    — WebSocket + polling fallback
    utils.ts      — userColor, fmtTime, linkify
  styles/app.css
netlify.toml      — конфиг для Netlify
```

## Почему это работает в твоём офисе

Когда я тестировал с CLI, в твоей корпоративной сети:
- HTTPS REST → работает (через прокси `10.130.20.251:2002`)
- WebSocket → блокируется на уровне Cloudflare (403 Forbidden)

Веб-клиент это знает: запускает WS, ждёт 5 секунд, если не подключился — молча переходит на polling (1-2 секунды задержки на новые сообщения). Пользователь видит индикатор `● polling` в сайдбаре и работает дальше как ни в чём не бывало.

Браузер сам решает SSL-вопросы через системный certificate store, поэтому никаких `verify=False`, `TG_INSECURE` и прочих хаков не нужно — корпоративный сертификат уже доверенный в Windows/macOS, браузер его принимает.
