import html
from datetime import date, datetime, timedelta

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
LEAD_PRESETS = (5, 15, 30, 60, 1440)
MESSAGE_LIMIT = 3800
EXAMPLES = (
    "Завтра в 15:00 созвон с Олей, напомни за 10 минут",
    "Каждую пятницу в 18:00 спортзал",
    "Что у меня в пятницу?",
)
BAR_WIDTH = 10


def esc(value) -> str:
    return html.escape(str(value or ""))


def plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    if count % 10 == 1:
        return one
    if 2 <= count % 10 <= 4:
        return few
    return many


def format_lead(minutes: int) -> str:
    if minutes == 0:
        return "в начале"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} {plural(days, 'день', 'дня', 'дней')}"
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes} мин"


def short_date(day: date) -> str:
    return f"{WEEKDAYS_SHORT[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"


def day_text(day: date, today: date) -> str:
    if day == today:
        return f"Сегодня, {day.day} {MONTHS[day.month - 1]}"
    if day == today + timedelta(days=1):
        return f"Завтра, {day.day} {MONTHS[day.month - 1]}"
    base = short_date(day)
    return base[0].upper() + base[1:]


def priority_mark(event: dict) -> str:
    return {"urgent": "‼️ ", "high": "❗ "}.get(event.get("priority") or "", "")


def event_card(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"])
    today = datetime.now(start.tzinfo).date()
    if event.get("all_day"):
        when = "без времени"
    elif start.date() == end.date():
        when = f"{start:%H:%M}–{end:%H:%M}"
    else:
        when = f"{start:%H:%M} — {day_text(end.date(), today).lower()} {end:%H:%M}"
    lines = [f"📌 {priority_mark(event)}<b>{esc(event['title'])}</b>", f"🗓 {day_text(start.date(), today)} · {when}"]
    if event.get("location"):
        lines.append(f"📍 {esc(event['location'])}")
    reminder = event.get("reminder_minutes")
    if reminder is not None:
        lines.append("🔔 В момент начала" if reminder == 0 else f"🔔 За {format_lead(reminder)}")
    if event.get("recurrence"):
        lines.append(f"🔁 {esc(event['recurrence']).capitalize()}")
    return "\n".join(lines)


def proposal_line(number: int, event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    today = datetime.now(start.tzinfo).date()
    when = "без времени" if event.get("all_day") else f"{start:%H:%M}"
    if not event.get("all_day") and event.get("end_time"):
        when += f"–{event['end_time']}"
    repeat = f" · 🔁 {esc(event['recurrence'])}" if event.get("recurrence") else ""
    return f"<b>{number}.</b> {esc(event['title'])}\n     {day_text(start.date(), today)} · <code>{when}</code>{repeat}"


def proposal(reply: dict) -> str:
    events = reply["events"]
    count = len(events)
    header = "📝 <b>Проверьте задачу</b>" if count == 1 else f"📝 <b>Проверьте {count} {plural(count, 'задачу', 'задачи', 'задач')}</b>"
    if reply.get("note"):
        header += f"  ·  <i>{esc(reply['note'])}</i>"
    if count == 1:
        body = event_card(events[0])
    else:
        lines = []
        for index, event in enumerate(events):
            line = proposal_line(index + 1, event)
            if len("\n".join(lines + [line])) > MESSAGE_LIMIT - 400:
                lines.append(f"<i>…и ещё {count - index}</i>")
                break
            lines.append(line)
        body = "\n".join(lines)
    parts = [header, body]
    if reply.get("answer"):
        parts.append(f"💬 {esc(reply['answer'])}")
    parts.append("Всё верно? Нажмите <b>«Добавить»</b> или поправьте название, дату и время.")
    return "\n\n".join(parts)


def edit_prompt(data: dict) -> str:
    return f"✏️ {esc(data['prompt'])} для <b>«{esc(data['title'])}»</b>\n<i>Или напишите «отмена».</i>"


def proposal_closed(text: str) -> str:
    return f"<s>Черновик</s>\n\n{esc(text)}"


def stats(data: dict) -> str:
    today = data["today"]
    def bar(percent: int) -> str:
        filled = round(percent * BAR_WIDTH / 100)
        return "▓" * filled + "░" * (BAR_WIDTH - filled)
    lines = ["📊 <b>Статистика выполнения</b>", ""]
    if today["total"]:
        lines.append(f"<b>Сегодня</b>: {today['done']} из {today['total']} · {today['percent']}%")
        lines.append(f"<code>{bar(today['percent'])}</code>")
    else:
        lines.append("<b>Сегодня</b>: задач нет")
    lines += ["", "<b>Последние 7 дней</b>"]
    for day in data["days"]:
        moment = date.fromisoformat(day["date"])
        label = f"{WEEKDAYS_SHORT[moment.weekday()]} {moment.day:>2}"
        value = f"{day['done']}/{day['total']}" if day["total"] else "—"
        lines.append(f"<code>{label} {bar(day['percent']) if day['total'] else ' ' * BAR_WIDTH} {value}</code>")
    if data["total"]:
        lines += ["", f"За неделю выполнено <b>{data['done']} из {data['total']}</b> ({data['percent']}%)"]
    if data.get("streak", 0) >= 2:
        lines.append(f"🔥 Серия: {data['streak']} {plural(data['streak'], 'день', 'дня', 'дней')} подряд всё выполнено")
    return "\n".join(lines)


def done_list(reply: dict) -> str:
    title = reply.get("title") or "План"
    events = [event for day in reply.get("days") or [] for event in day["events"]]
    if not events:
        return f"✅ <b>{esc(title)}</b>\n\nЗадач нет 🌿"
    done = sum(1 for event in events if event.get("completed"))
    return f"✅ <b>Отметьте выполненное · {esc(title)}</b>\nГотово {done} из {len(events)}. Нажмите на задачу, чтобы отметить."


def checkin_result(result: dict) -> str:
    if result.get("moved"):
        moved = result["moved"]
        return f"↪️ Перенесла {moved} {plural(moved, 'задачу', 'задачи', 'задач')} на {esc(result.get('target_label') or 'другой день')}."
    return "👍 Отлично, тогда не отвлекаю. Отмечайте выполненное — так статистика будет точнее."


def created(reply: dict) -> str:
    events = reply["events"]
    if len(events) == 1:
        header = "✨ <b>Добавила в календарь</b>"
    else:
        header = f"✨ <b>Добавила {len(events)} {plural(len(events), 'событие', 'события', 'событий')}</b>"
    parts = [header, *[event_card(event) for event in events]]
    if reply.get("answer"):
        parts.append(f"💬 {esc(reply['answer'])}")
    return "\n\n".join(parts)


def agenda_line(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    time_text = "без времени" if event.get("all_day") else f"{start:%H:%M}"
    title = f"✅ <s>{esc(event['title'])}</s>" if event.get("completed") else esc(event["title"])
    line = f"<code>{time_text}</code>  {priority_mark(event)}{title}"
    if event.get("location"):
        line += f"  <i>· {esc(event['location'])}</i>"
    return line


def agenda(reply: dict) -> str:
    days = reply.get("days") or []
    title = reply.get("title") or "План"
    count = sum(len(day["events"]) for day in days)
    if reply.get("date") and reply.get("scope") != "week":
        first = date.fromisoformat(reply["date"])
        if title in ("Сегодня", "Завтра", "Вчера"):
            header = f"📅 <b>{esc(title)}</b> · {short_date(first)}"
        else:
            header = f"📅 <b>{esc(day_text(first, first - timedelta(days=7)))}</b>"
        if not count:
            return f"{header}\n\nСвободный день — ничего не запланировано 🌿"
        body = "\n".join(agenda_line(event) for event in days[0]["events"])
        return f"{header}\n\n{body}"
    icon = "🔎" if title == "Найденные события" else "📆" if reply.get("scope") == "week" else "📅"
    if not count:
        return f"{icon} <b>{esc(title)}</b>\n\nНичего не нашла — в календаре пусто 🌿"
    lines = [f"{icon} <b>{esc(title)}</b> · {count} {plural(count, 'событие', 'события', 'событий')}"]
    shown = 0
    for day in days:
        block = [f"\n<b>{esc(day['label'])}</b>", *[agenda_line(event) for event in day["events"]]]
        if len("\n".join(lines + block)) > MESSAGE_LIMIT:
            rest = count - shown
            lines.append(f"\n<i>…и ещё {rest} {plural(rest, 'событие', 'события', 'событий')} — откройте календарь в Dayla.</i>")
            break
        lines.extend(block)
        shown += len(day["events"])
    return "\n".join(lines)


def answer(text: str) -> str:
    return f"💬 {esc(text)}"


def not_found(text: str) -> str:
    return f"🔎 {esc(text)}"


def nothing() -> str:
    return (
        "🤔 <b>Не нашла в сообщении задач</b>\n\n"
        "Попробуйте написать, что и когда, например:\n"
        f"<i>«{EXAMPLES[0]}»</i>"
    )


def undone(count: int) -> str:
    if not count:
        return "↩️ Эти события уже удалены или изменены в Dayla."
    return f"↩️ <b>Отменено</b> — {count} {plural(count, 'событие удалено', 'события удалены', 'событий удалено')} из календаря."


def heard(text: str) -> str:
    return f"🎙 <i>«{esc(text)}»</i>"


def reading_document(name: str) -> str:
    return f"📄 Читаю <b>{esc(name)}</b>…"


def welcome_unlinked(has_link_button: bool) -> str:
    how = (
        "Нажмите кнопку ниже, войдите и выберите <b>Настройки → Telegram → Подключить</b>."
        if has_link_button
        else "Откройте сайт Dayla → <b>Настройки → Telegram</b> и нажмите <b>«Подключить Telegram»</b>."
    )
    return (
        "👋 <b>Привет! Я Dayla</b> — ассистент, который планирует ваш день.\n\n"
        "После подключения аккаунта здесь можно:\n"
        "💬 планировать обычными словами, голосом или документом\n"
        "📅 смотреть план на день и неделю\n"
        "🔔 получать напоминания и утренний план\n\n"
        f"<b>Как подключить</b>\n{how}"
    )


def linked(profile: dict) -> str:
    name = f", {esc(profile['name'])}" if profile.get("name") else ""
    return (
        f"✅ <b>Готово{name}!</b>\n"
        f"Telegram подключён к аккаунту <b>{esc(profile['email'])}</b>.\n\n"
        "Теперь просто пишите мне — например:\n"
        + "\n".join(f"<i>«{example}»</i>" for example in EXAMPLES)
        + "\n\n🎙 Голосовые, 📄 PDF и DOCX тоже понимаю. Перед добавлением покажу черновик — "
        "в нём можно поправить название, дату и время."
    )


def welcome_back(profile: dict) -> str:
    name = f", {esc(profile['name'])}" if profile.get("name") else ""
    return f"👋 <b>С возвращением{name}!</b>\n\nНапишите, что запланировать, или выберите действие в меню ниже."


def help_text() -> str:
    return (
        "💡 <b>Что я умею</b>\n\n"
        "<b>Планировать</b> — пишите как другу:\n"
        f"<i>«{EXAMPLES[0]}»</i>\n"
        f"<i>«{EXAMPLES[1]}»</i>\n"
        "<i>«Купить продукты завтра»</i> — задача без времени\n"
        "<i>«Расписание: в понедельник математика в 8:30, физика в 9:25…»</i> — сразу несколько задач\n\n"
        "Перед добавлением я покажу черновик: его можно поправить или отменить.\n\n"
        "<b>Отвечать на вопросы о планах</b>:\n"
        f"<i>«{EXAMPLES[2]}»</i>  ·  <i>«Когда у меня стоматолог?»</i>\n\n"
        "<b>Понимать голос и документы</b> — пришлите голосовое, PDF или DOCX.\n\n"
        "<b>Команды</b>\n"
        "/today — план на сегодня\n"
        "/tomorrow — план на завтра\n"
        "/week — ближайшие 7 дней\n"
        "/done — отметить выполненные задачи\n"
        "/stats — статистика выполнения\n"
        "/reminders — настройки напоминаний\n"
        "/unlink — отключить Telegram"
    )


def link_failed() -> str:
    return "⚠️ <b>Ссылка недействительна или устарела</b>\n\nПолучите новую в Dayla: <b>Настройки → Telegram → Подключить</b>."


def backend_unavailable() -> str:
    return "⏳ Временная ошибка — попробуйте ещё раз через минуту."


def assistant_unavailable() -> str:
    return "⏳ Временная ошибка — попробуйте ещё раз через минуту. План на день можно открыть через /today."


def account_unlinked() -> str:
    return "👋 <b>Telegram отключён от Dayla.</b>\n\nНапоминания больше не придут. Подключить снова можно в настройках на сайте."


def unsupported_file() -> str:
    return "📄 Я читаю только <b>PDF</b> и <b>DOCX</b>. Пришлите документ в одном из этих форматов."


def file_too_big() -> str:
    return "📄 Файл больше 20 МБ — Telegram не даёт ботам скачивать такие файлы."


def document_empty() -> str:
    return "📄 В документе не нашлось текста. Если это скан, пришлите текстовую версию."


def voice_failed(reason: str) -> str:
    return f"🎙 {esc(reason)}"


def unsupported_message() -> str:
    return "🙂 Я понимаю текст, голосовые и документы PDF или DOCX. Напишите, что запланировать, — или нажмите 💡 Помощь."


def processing_error() -> str:
    return "⏳ Временная ошибка — попробуйте ещё раз через минуту."


def snoozed(minutes: int) -> str:
    return f"⏰ Напомню через {format_lead(minutes)}"


def reminder_settings(email: str, values: dict) -> str:
    leads = ", ".join(f"за {format_lead(minutes)}" for minutes in sorted(values["lead_times"])) or "не выбрано"
    digest = f"в {values['daily_digest_time'][:5]}" if values["daily_digest_enabled"] else "выключен"
    quiet = f"{values['quiet_hours_start'][:5]}–{values['quiet_hours_end'][:5]}" if values["quiet_hours_enabled"] else "выключены"
    return (
        "🔔 <b>Напоминания</b>\n"
        f"<i>{esc(email)}</i>\n\n"
        f"Статус: {'<b>включены</b> ✅' if values['enabled'] else '<b>выключены</b> ⏸'}\n"
        f"Когда: {leads}\n"
        f"Утренний план: {digest}\n"
        f"Тихие часы: {quiet}\n\n"
        "Нажмите кнопку, чтобы изменить."
    )
