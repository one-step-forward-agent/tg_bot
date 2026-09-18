import html
from datetime import datetime


START_MESSAGE = (
    "Привет! 👋 Я помогу добавить планы в календарь.\n\n"
    "Я умею:\n"
    "• 📝 разбирать обычный текст;\n"
    "• 📄 читать PDF и DOCX;\n"
    "• 🎙️ распознавать голосовые и аудиосообщения.\n\n"
    "Отправьте описание планов — я найду события и подготовлю файл .ics 📅"
)


def welcome_back(name: str) -> str:
    return f"С возвращением, {html.escape(name)}! 😊\n\n{START_MESSAGE}"


def registration_name_prompt() -> str:
    return "Как вас зовут? Напишите имя, которое использовать в боте 🙂"


def invalid_name() -> str:
    return "Напишите имя от 1 до 100 символов, пожалуйста."


def timezone_prompt() -> str:
    return "Выберите ваш часовой пояс 🕰️"


def timezone_saved(name: str) -> str:
    return (
        f"Готово, {html.escape(name)}! ✅ Теперь события будут сохраняться в вашем часовом поясе.\n\n"
        f"{START_MESSAGE}"
    )


def unknown_timezone() -> str:
    return "Неизвестный часовой пояс"


def timezone_saved_callback() -> str:
    return "Сохранено ✅"


def usage() -> str:
    return (
        "Отправьте текст, PDF, DOCX или голосовое сообщение с описанием планов. "
        "Я найду события и верну календарный файл .ics 📅"
    )


def supported_files() -> str:
    return (
        "Поддерживаются:\n"
        "• 📝 текстовые сообщения;\n"
        "• 📄 PDF и DOCX;\n"
        "• 🎙️ голосовые сообщения и аудиофайлы."
    )


def saved_event(event) -> str:
    result = f"<b>📌 {html.escape(event.title)}</b>\n{event.starts_at:%d.%m.%Y в %H:%M}"
    if event.location:
        result += f"\n📍 {html.escape(event.location)}"
    if event.description:
        result += f"\n📝 {html.escape(event.description)}"
    if event.recurrence_rule:
        result += "\n🔁 Повторяющееся событие"
    return result


def event(item: dict) -> str:
    starts_at = datetime.fromisoformat(item["starts_at"])
    result = f"<b>📌 {html.escape(item['title'])}</b>\n🗓️ {starts_at:%d.%m.%Y в %H:%M}"
    if item.get("ends_at"):
        ends_at = datetime.fromisoformat(item["ends_at"])
        result += f"–{ends_at:%H:%M}"
    if item.get("location"):
        result += f"\n📍 {html.escape(item['location'])}"
    if item.get("description"):
        result += f"\n📝 {html.escape(item['description'])}"
    if item.get("recurrence_rule"):
        result += "\n🔁 Повторяющееся событие"
    if item.get("reminder_minutes") is not None:
        result += f"\n🔔 Напоминание: за {item['reminder_minutes']} мин."
    return result


def created_events(items: list[dict]) -> str:
    count = len(items)
    noun = "событие" if count == 1 else "события" if count < 5 else "событий"
    return f"Готово! Добавил {count} {noun} ✅\n\n" + "\n\n".join(event(item) for item in items)


def calendar_caption() -> str:
    return "Ваш календарный файл готов 📅"


def no_events_with_date() -> str:
    return "В тексте не найдено событий с датой или временем 🧐"


def no_search_results() -> str:
    return "На эту дату подходящих событий не найдено 🔎"


def registration_required() -> str:
    return "Сначала выполните регистрацию через команду /start 🙂"


def processing_text() -> str:
    return "Обрабатываю текст... ⏳"


def processing_error() -> str:
    return "Не удалось обработать текст. Проверьте настройки GigaChat."


def unsupported_file() -> str:
    return "Отправьте файл в формате PDF или DOCX, пожалуйста 📄"


def extracting_document() -> str:
    return "Преобразую документ в текст... 📄"


def searching_document() -> str:
    return "Ищу события в тексте документа... 🔎"


def document_error() -> str:
    return "Не удалось прочитать документ или обработать его через GigaChat."


def recognizing_audio() -> str:
    return "Распознаю речь и ищу события... 🎙️"


def recognition_error(error: Exception) -> str:
    return f"Не удалось распознать речь: {error}"


def audio_service_error(error: Exception) -> str:
    return str(error)


def audio_error() -> str:
    return "Не удалось распознать аудио или обработать его через GigaChat."


def no_understood_event() -> str:
    return "Не нашел события и не смог понять вопрос 🤔"