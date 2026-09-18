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

POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_DB=calendar_bot
POSTGRES_PASSWORD=your_password

GIGACHAT_CREDENTIALS=base64(client_id:client_secret)
GIGACHAT_MODEL=GigaChat
GIGACHAT_SCOPE=GIGACHAT_API_PERS
TIMEZONE=Europe/Moscow
```

```cmd
docker compose up --build
```

