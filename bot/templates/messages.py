import html
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
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


class _TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.ok = True

    def handle_starttag(self, tag, attrs) -> None:
        self.stack.append(tag)

    def handle_endtag(self, tag) -> None:
        if not self.stack or self.stack.pop() != tag:
            self.ok = False


def _balanced(text: str) -> bool:
    checker = _TagBalance()
    checker.feed(text)
    return checker.ok and not checker.stack


def _inline(line: str) -> str:
    """Inline markdown of one escaped line: code first (its content is left as is), then links, bold, italic, strike."""
    codes: list[str] = []

    def keep(match: re.Match) -> str:
        codes.append(match.group(1))
        return f"\x00{len(codes) - 1}\x00"

    line = re.sub(r"`([^`\n]+)`", keep, line)
    line = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', line)
    line = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", line)
    line = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<b>\1</b>", line)
    line = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"<i>\1</i>", line)
    line = re.sub(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])", r"<i>\1</i>", line)
    line = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<s>\1</s>", line)
    return re.sub(r"\x00(\d+)\x00", lambda match: f"<code>{codes[int(match.group(1))]}</code>", line)


def rich(text) -> str:
    """Text written by the model, with its markdown turned into Telegram HTML; anything else is escaped.
    If the markers do not pair up into valid HTML, the text is shown plain without them."""
    lines, in_code = [], False
    for raw in str(text or "").splitlines():
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        line = esc(raw)
        if in_code:
            lines.append(f"<code>{line}</code>" if line.strip() else "")
        elif heading := re.match(r"^\s*#{1,6}\s+(.+)$", line):
            lines.append(f"<b>{heading.group(1).replace('*', '').replace('_', ' ').strip()}</b>")
        else:
            line = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", line)
            line = re.sub(r"^\s*&gt;\s?", "", line)
            lines.append(_inline(line))
    result = "\n".join(lines).strip()
    if _balanced(result):
        return result
    plain = re.sub(r"(\*\*|__|~~|`|^#{1,6}\s+)", "", str(text or ""), flags=re.M)
    return esc(plain)


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
    """"Сегодня, среда, 7 октября", "Завтра, четверг, 8 октября", then "Пятница, 9 октября"."""
    base = f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"
    if day == today:
        return f"Сегодня, {base}"
    if day == today + timedelta(days=1):
        return f"Завтра, {base}"
    return base[0].upper() + base[1:]


def short_day(day: date, today: date) -> str:
    if day == today:
        return "сегодня"
    if day == today + timedelta(days=1):
        return "завтра"
    return short_date(day)


def deadline_text(value: str, today: date) -> str:
    moment = datetime.fromisoformat(value)
    text = short_day(moment.date(), today)
    return text if (moment.hour, moment.minute) >= (23, 59) else f"{text} {moment:%H:%M}"


def priority_mark(event: dict) -> str:
    return {"urgent": "‼️ ", "high": "❗ "}.get(event.get("priority") or "", "")


def event_card(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"])
    today = datetime.now(start.tzinfo).date()
    last = date.fromisoformat(event["end_date"]) if event.get("end_date") else None
    if event.get("all_day"):
        when = f"до {short_day(last, today)}" if last and last > start.date() else "без времени"
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
    if event.get("deadline"):
        lines.append(f"⏳ Дедлайн: {deadline_text(event['deadline'], today)}")
    if event.get("fixed"):
        lines.append("📌 Нельзя переносить")
    before = event.get("before")
    if before:
        was = short_day(date.fromisoformat(before["date"]), today)
        if before.get("time"):
            was += f" {before['time']}"
        lines.append(f"<i>Было: {esc(before['title']) + ', ' if before['title'] != event['title'] else ''}{was}</i>")
    return "\n".join(lines)


def proposal_line(number: int, event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    today = datetime.now(start.tzinfo).date()
    # The end is shown even when it was not said: the task gets an hour, and the user sees that
    when = "без времени" if event.get("all_day") else f"{start:%H:%M}–{datetime.fromisoformat(event['end']):%H:%M}"
    repeat = f" · 🔁 {esc(event['recurrence'])}" if event.get("recurrence") else ""
    if event.get("end_date") and event["end_date"] > event["start"][:10]:
        repeat += f" · до {short_day(date.fromisoformat(event['end_date']), today)}"
    if event.get("deadline"):
        repeat += f" · ⏳ {deadline_text(event['deadline'], today)}"
    return f"<b>{number}.</b> {esc(event['title'])}\n     {day_text(start.date(), today)} · <code>{when}</code>{repeat}"


def proposal(reply: dict) -> str:
    events = reply["events"]
    count = len(events)
    header = "📝 <b>Проверьте задачу</b>" if count == 1 else f"📝 <b>Проверьте {count} {plural(count, 'задачу', 'задачи', 'задач')}</b>"
    if count == 1 and events[0].get("event_id"):
        header = "✏️ <b>Проверьте изменение</b>"
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
    target = target_title(reply)
    if target:
        parts.append(f"🗂 Куда: <b>{esc(target)}</b>")
    if reply.get("answer"):
        parts.append(f"💬 {rich(reply['answer'])}")
    if any(event.get("event_id") for event in events):
        parts.append("Всё верно? Нажмите <b>«Сохранить»</b> или поправьте название, дату и время.")
    else:
        parts.append("Всё верно? Нажмите <b>«Добавить»</b> или поправьте название, дату и время.")
    return "\n\n".join(parts)


def target_title(reply: dict) -> str | None:
    """Where the new tasks of a proposal go — Dayla and the ticked calendars — when a calendar is connected."""
    targets = reply.get("targets") or []
    if not targets or any(event.get("event_id") for event in reply["events"]):
        return None
    chosen = reply.get("calendars") or []
    return ", ".join(["Dayla", *(option["title"] for option in targets if option["slug"] in chosen)])


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
    if data.get("streak", 0) >= 1:
        lines.append(f"🔥 Серия: {data['streak']} {plural(data['streak'], 'день', 'дня', 'дней')} подряд всё выполнено")
    if data.get("best_streak", 0) > data.get("streak", 0):
        lines.append(f"🏆 Лучшая серия: {data['best_streak']} {plural(data['best_streak'], 'день', 'дня', 'дней')}")
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


def move_list(reply: dict) -> str:
    title = reply.get("title") or "План"
    events = [event for day in reply.get("days") or [] for event in day["events"] if not event.get("completed")]
    if not events:
        return f"↪️ <b>{esc(title)}</b>\n\nПереносить нечего — невыполненных задач нет 🌿"
    return f"↪️ <b>Что перенести? · {esc(title)}</b>\nНажмите на задачу."


def move_ask(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    today = datetime.now(start.tzinfo).date()
    when = "без времени" if event.get("all_day") else f"в {start:%H:%M}"
    keep = "" if event.get("all_day") else " Время сохранится."
    return f"↪️ Куда перенести <b>«{esc(event['title'])}»</b>?\nСейчас: {esc(day_text(start.date(), today).lower())}, {when}.{keep}"


def move_days(event: dict) -> str:
    return f"📅 Выберите день для <b>«{esc(event['title'])}»</b> — или напишите дату."


def moved(reply: dict) -> str:
    return "\n\n".join([f"↪️ <b>{esc(reply.get('text') or 'Перенесла')}</b>", *[event_card(event) for event in reply.get("events") or []]])


def created(reply: dict) -> str:
    events = reply["events"]
    if reply.get("kind") == "updated":
        header = "✏️ <b>Изменила</b>"
    elif len(events) == 1:
        header = "✨ <b>Добавила в календарь</b>"
    else:
        header = f"✨ <b>Добавила {len(events)} {plural(len(events), 'событие', 'события', 'событий')}</b>"
    parts = [header, *[event_card(event) for event in events]]
    if reply.get("note"):
        parts.append(f"🗂 {esc(reply['note'])}")
    if reply.get("answer"):
        parts.append(f"💬 {rich(reply['answer'])}")
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
    """The found tasks; the assistant's comment on them, if any, goes first."""
    body = agenda_body(reply)
    return f"💬 {rich(reply['answer'])}\n\n{body}" if reply.get("answer") else body


def agenda_body(reply: dict) -> str:
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


def help_sections(reply: dict) -> str:
    lines = ["💡 <b>Что я умею</b>", "Пишите как другу — текстом, голосом или документом. Всё, что меняет календарь, я сначала покажу на подтверждение."]
    for section in reply["sections"]:
        lines += ["", f"<b>{esc(section['title'])}</b>", "  ·  ".join(f"<i>«{esc(example)}»</i>" for example in section["examples"])]
    lines += ["", "Команды: /today /tomorrow /week /done /stats /advice /analysis /reminders"]
    return "\n".join(lines)


def advice(reply: dict) -> str:
    items = reply.get("items") or []
    if not items:
        return "💡 Пока советовать нечего — план в порядке."
    icons = {"warning": "⚠️", "success": "✅"}
    lines = ["💡 <b>Советы на сегодня</b>", ""]
    for index, item in enumerate(items, 1):
        lines.append(f"{icons.get(item.get('kind'), '💡')} <b>{index}. {esc(item['title'])}</b>\n{rich(item['text'])}")
    return "\n\n".join([lines[0], *lines[2:]])


def topic(reply: dict) -> str:
    return f"💡 <b>Обсуждаем: {esc(reply['title'])}</b>\n{rich(reply['text'])}\n\nСпросите, что непонятно, или выберите вопрос ниже."


def delete_proposal(reply: dict) -> str:
    count = reply["count"]
    lines = [f"🗑 <b>Удалить {count} {plural(count, 'задачу', 'задачи', 'задач')}?</b>", f"<i>{esc(reply['title'])}</i>", ""]
    for event in reply["events"][:10]:
        start = datetime.fromisoformat(event["start"])
        when = "без времени" if event.get("all_day") else f"{start:%H:%M}"
        lines.append(f"• {esc(event['title'])} — {short_date(start.date())}, <code>{when}</code>")
    if count > 10:
        lines.append(f"• …и ещё {count - 10}")
    lines += ["", "Это нельзя отменить. Подтвердите кнопкой ниже."]
    return "\n".join(lines)


def completed(reply: dict) -> str:
    lines = [f"✅ <b>{esc(reply['text'])}</b>"]
    lines += [f"• <s>{esc(event['title'])}</s>" for event in reply["events"][:20]]
    return "\n".join(lines)


def reminder_set(reply: dict) -> str:
    return "\n".join(f"⏰ {esc(line)}" for line in (reply.get("text") or "").splitlines())


def reminder_cancelled(text: str) -> str:
    return f"🔕 <i>{esc(text)}</i>"


def answer(text: str) -> str:
    return f"💬 {rich(text)}"


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
        "Нажмите кнопку ниже, войдите и выберите <b>Аккаунт → Telegram → Подключить</b>."
        if has_link_button
        else "Откройте сайт Dayla → <b>Аккаунт → Telegram</b> и нажмите <b>«Подключить Telegram»</b>."
    )
    return (
        "👋 <b>Привет! Я Dayla</b> — ассистент, который планирует ваш день.\n\n"
        "После подключения аккаунта здесь можно:\n"
        "💬 планировать обычными словами, голосом или документом\n"
        "📅 смотреть план на день и неделю\n"
        "🔔 получать напоминания, утренний план и итоги дня\n\n"
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
        "<i>«Расписание: в понедельник математика в 8:30, физика в 9:25…»</i> — сразу несколько задач\n"
        "<i>«Конференция с 10 по 12 октября»</i> — на несколько дней\n"
        "<i>«Отчёт, дедлайн в пятницу 18:00»</i> — с дедлайном, напомню о нём заранее\n\n"
        "<b>Менять задачи</b>:\n"
        "<i>«Перенеси созвон с Олей на пятницу в 15:00»</i>  ·  <i>«Продли встречу до 18:00»</i>  ·  "
        "<i>«Сдвинь тренировку на час позже»</i>\n\n"
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
        "/advice — советы по плану\n"
        "/analysis — анализ недели и что перенести\n"
        "/reminders — настройки напоминаний\n"
        "/unlink — отключить Telegram"
    )


def link_failed() -> str:
    return "⚠️ <b>Ссылка недействительна или устарела</b>\n\nПолучите новую в Dayla: <b>Аккаунт → Telegram → Подключить</b>."


def backend_unavailable() -> str:
    return "⏳ Ошибка сервера — попробуйте ещё раз через минуту."


def assistant_unavailable() -> str:
    return "⏳ Ошибка сервера — попробуйте ещё раз через минуту. План на день можно открыть через /today."


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
    return "⏳ Ошибка сервера — попробуйте ещё раз через минуту."


def snoozed(minutes: int) -> str:
    return f"⏰ Напомню через {format_lead(minutes)}"


def reminder_settings(email: str | None, values: dict) -> str:
    leads = ", ".join(f"за {format_lead(minutes)}" for minutes in sorted(values["lead_times"])) or "не выбрано"
    digest = f"в {values['daily_digest_time'][:5]}" if values["daily_digest_enabled"] else "выключен"
    quiet = f"{values['quiet_hours_start'][:5]}–{values['quiet_hours_end'][:5]}" if values["quiet_hours_enabled"] else "выключены"
    evening = f"в {values['evening_time'][:5]}" if values.get("evening_enabled") and values.get("evening_time") else "выключены"
    return (
        "🔔 <b>Напоминания</b>\n"
        + (f"<i>{esc(email)}</i>\n" if email else "")
        + "\n"
        f"Статус: {'<b>включены</b> ✅' if values['enabled'] else '<b>выключены</b> ⏸'}\n"
        f"Когда: {leads}\n"
        f"Утренний план: {digest}\n"
        f"Итоги дня: {evening}\n"
        f"Дедлайны: {'напоминаю за 3 дня, за день и за 2 часа' if values.get('deadline_enabled') else 'выключены'}\n"
        f"Тихие часы: {quiet}\n\n"
        "Нажмите кнопку, чтобы изменить."
    )
