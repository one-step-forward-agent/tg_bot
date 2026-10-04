# Telegram Bot for SBER500

Telegram-бот для создания событий и напоминаний из текста, документов, голосовых сообщений и аудио.

## Возможности

- извлечение событий через GigaChat;
- одноразовые и повторяющиеся события;
- правила повторения: каждый день, раз в N недель, ежегодно и другие;
- напоминания в Telegram;
- экспорт новых событий в `calendar.ics`;
- поиск сохранённых событий по датам, времени суток и ключевым словам;
- контекст диалога в PostgreSQL с ограниченным сроком хранения;
- поддержка PDF, DOCX, голосовых и аудиофайлов;
- часовые пояса пользователей.

## Настройка

Создайте файл `.env` в корне проекта:

```env
TOKEN=your_telegram_bot_token

DATABASE_URL 
GIGACHAT_CREDENTIALS
GIGACHAT_MODEL
GIGACHAT_SCOPE

# Focus Day backend (account linking + reminders from the web app)
BACKEND_URL=http://127.0.0.1:8000
BOT_API_TOKEN=the same value as in backend/.env
NOTIFICATION_POLL_SECONDS=20
```

## Связка с Focus Day

- `/start <код>` — привязать Telegram к аккаунту Focus Day (ссылку с кодом выдаёт сайт);
- `/reminders` — показать и переключить настройки напоминаний (вкл/выкл, за сколько минут, сводка на день);
- `/unlink` — отвязать аккаунт.

Если `BACKEND_URL` и `BOT_API_TOKEN` заданы, бот раз в `NOTIFICATION_POLL_SECONDS` забирает уведомления из backend и отправляет их.


