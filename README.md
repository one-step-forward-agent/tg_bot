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

POSTGRES_HOST=agent_db
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

## Развертывание в Amvera

Amvera не поддерживает `docker-compose.yml`, поэтому приложение и PostgreSQL
разворачиваются как два отдельных проекта:

1. Создайте managed-кластер PostgreSQL в Amvera и дождитесь статуса запуска.
2. Создайте приложение из этого репозитория. Amvera автоматически использует
   `Dockerfile` из корня проекта.
3. В настройках приложения добавьте переменные окружения. Секретами должны быть
   `TOKEN`, `DATABASE_URL`, `GIGACHAT_CREDENTIALS` или `SBER_AUTHORIZATION_KEY`.
4. Для `DATABASE_URL` укажите строку подключения к PostgreSQL с внутренним именем
   хоста кластера Amvera. Поддерживаются также отдельные переменные
   `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_DB` и
   `POSTGRES_PASSWORD`.
5. Свяжите приложение с PostgreSQL по внутреннему имени хоста вида
   `amvera-<username>-cnpg-<project_name>-rw` и перезапустите приложение.

При запуске контейнер сначала выполняет `alembic upgrade head`, затем запускает
Telegram polling. У проекта должно быть ровно одно запущенное приложение, иначе
Telegram завершит один из экземпляров polling с ошибкой `getUpdates`.

После создания PostgreSQL включите резервное копирование в его настройках.

