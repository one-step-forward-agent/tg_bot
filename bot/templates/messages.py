import html
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

from bot.i18n import is_en, plural_en, tr

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
WEEKDAYS_SHORT_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LEAD_PRESETS = (5, 15, 30, 60, 1440)
MESSAGE_LIMIT = 3800
EXAMPLES = (
    "Завтра в 15:00 созвон с Олей, напомни за 10 минут",
    "Каждую пятницу в 18:00 спортзал",
    "Что у меня в пятницу?",
)
EXAMPLES_EN = (
    "Call with Olya tomorrow at 15:00, remind me 10 minutes before",
    "Gym every Friday at 18:00",
    "What do I have on Friday?",
)
BAR_WIDTH = 10
# The plan's titles the backend sends for these days, in both languages
DAY_TITLES = ("Сегодня", "Завтра", "Вчера", "Today", "Tomorrow", "Yesterday")
FOUND_TITLES = ("Найденные события", "Found events")


def examples() -> tuple[str, ...]:
    return EXAMPLES_EN if is_en() else EXAMPLES


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


def counted(count: int, one: str, few: str, many: str, en_one: str, en_many: str) -> str:
    """"3 задачи" or "3 tasks"."""
    return f"{count} {plural_en(count, en_one, en_many) if is_en() else plural(count, one, few, many)}"


def format_lead(minutes: int) -> str:
    if minutes == 0:
        return tr("в начале", "at the start")
    if minutes % 1440 == 0:
        days = minutes // 1440
        return tr(f"{days} {plural(days, 'день', 'дня', 'дней')}", f"{days} {plural_en(days, 'day', 'days')}")
    if minutes % 60 == 0:
        return f"{minutes // 60} {tr('ч', 'h')}"
    return f"{minutes} {tr('мин', 'min')}"


def weekday_short(day: date) -> str:
    return (WEEKDAYS_SHORT_EN if is_en() else WEEKDAYS_SHORT)[day.weekday()]


def day_month(day: date) -> str:
    return f"{day.day} {(MONTHS_EN if is_en() else MONTHS)[day.month - 1]}"


def short_date(day: date) -> str:
    return f"{weekday_short(day)}, {day_month(day)}"


def day_text(day: date, today: date) -> str:
    """"Сегодня, среда, 7 октября", "Завтра, четверг, 8 октября", then "Пятница, 9 октября"."""
    base = f"{(WEEKDAYS_EN if is_en() else WEEKDAYS)[day.weekday()]}, {day_month(day)}"
    if day == today:
        return f"{tr('Сегодня', 'Today')}, {base}"
    if day == today + timedelta(days=1):
        return f"{tr('Завтра', 'Tomorrow')}, {base}"
    return base[0].upper() + base[1:]


def short_day(day: date, today: date) -> str:
    if day == today:
        return tr("сегодня", "today")
    if day == today + timedelta(days=1):
        return tr("завтра", "tomorrow")
    return short_date(day)


def deadline_text(value: str, today: date) -> str:
    moment = datetime.fromisoformat(value)
    text = short_day(moment.date(), today)
    return text if (moment.hour, moment.minute) >= (23, 59) else f"{text} {moment:%H:%M}"


def no_time() -> str:
    return tr("без времени", "no time")


def priority_mark(event: dict) -> str:
    return {"urgent": "‼️ ", "high": "❗ "}.get(event.get("priority") or "", "")


def event_card(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"])
    today = datetime.now(start.tzinfo).date()
    last = date.fromisoformat(event["end_date"]) if event.get("end_date") else None
    if event.get("all_day"):
        when = f"{tr('до', 'until')} {short_day(last, today)}" if last and last > start.date() else no_time()
    elif start.date() == end.date():
        when = f"{start:%H:%M}–{end:%H:%M}"
    else:
        when = f"{start:%H:%M} — {day_text(end.date(), today).lower()} {end:%H:%M}"
    lines = [f"📌 {priority_mark(event)}<b>{esc(event['title'])}</b>", f"🗓 {day_text(start.date(), today)} · {when}"]
    if event.get("location"):
        lines.append(f"📍 {esc(event['location'])}")
    reminder = event.get("reminder_minutes")
    if reminder is not None:
        lines.append(tr("🔔 В момент начала", "🔔 At the start") if reminder == 0 else tr(f"🔔 За {format_lead(reminder)}", f"🔔 {format_lead(reminder)} before"))
    if event.get("recurrence"):
        lines.append(f"🔁 {esc(event['recurrence']).capitalize()}")
    if event.get("deadline"):
        lines.append(f"⏳ {tr('Дедлайн', 'Deadline')}: {deadline_text(event['deadline'], today)}")
    if event.get("fixed"):
        lines.append(tr("📌 Нельзя переносить", "📌 Can't be moved"))
    before = event.get("before")
    if before:
        was = short_day(date.fromisoformat(before["date"]), today)
        if before.get("time"):
            was += f" {before['time']}"
        lines.append(f"<i>{tr('Было', 'Was')}: {esc(before['title']) + ', ' if before['title'] != event['title'] else ''}{was}</i>")
    return "\n".join(lines)


def proposal_line(number: int, event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    today = datetime.now(start.tzinfo).date()
    # The end is shown even when it was not said: the task gets an hour, and the user sees that
    when = no_time() if event.get("all_day") else f"{start:%H:%M}–{datetime.fromisoformat(event['end']):%H:%M}"
    repeat = f" · 🔁 {esc(event['recurrence'])}" if event.get("recurrence") else ""
    if event.get("end_date") and event["end_date"] > event["start"][:10]:
        repeat += f" · {tr('до', 'until')} {short_day(date.fromisoformat(event['end_date']), today)}"
    if event.get("deadline"):
        repeat += f" · ⏳ {deadline_text(event['deadline'], today)}"
    return f"<b>{number}.</b> {esc(event['title'])}\n     {day_text(start.date(), today)} · <code>{when}</code>{repeat}"


def proposal(reply: dict) -> str:
    events = reply["events"]
    count = len(events)
    if count == 1:
        header = tr("📝 <b>Проверьте задачу</b>", "📝 <b>Check the task</b>")
    else:
        header = tr(f"📝 <b>Проверьте {count} {plural(count, 'задачу', 'задачи', 'задач')}</b>", f"📝 <b>Check {count} tasks</b>")
    if count == 1 and events[0].get("event_id"):
        header = tr("✏️ <b>Проверьте изменение</b>", "✏️ <b>Check the change</b>")
    if reply.get("note"):
        header += f"  ·  <i>{esc(reply['note'])}</i>"
    if count == 1:
        body = event_card(events[0])
    else:
        lines = []
        for index, event in enumerate(events):
            line = proposal_line(index + 1, event)
            if len("\n".join(lines + [line])) > MESSAGE_LIMIT - 400:
                lines.append(tr(f"<i>…и ещё {count - index}</i>", f"<i>…and {count - index} more</i>"))
                break
            lines.append(line)
        body = "\n".join(lines)
    parts = [header, body]
    target = target_title(reply)
    if target:
        parts.append(f"🗂 {tr('Куда', 'Where')}: <b>{esc(target)}</b>")
    if reply.get("answer"):
        parts.append(f"💬 {rich(reply['answer'])}")
    if any(event.get("event_id") for event in events):
        parts.append(tr("Всё верно? Нажмите <b>«Сохранить»</b> или поправьте название, дату и время.", "All correct? Press <b>“Save”</b> or fix the title, date and time."))
    else:
        parts.append(tr("Всё верно? Нажмите <b>«Добавить»</b> или поправьте название, дату и время.", "All correct? Press <b>“Add”</b> or fix the title, date and time."))
    return "\n\n".join(parts)


def target_title(reply: dict) -> str | None:
    """Where the new tasks of a proposal go — Dayla and the ticked calendars — when a calendar is connected."""
    targets = reply.get("targets") or []
    if not targets or any(event.get("event_id") for event in reply["events"]):
        return None
    chosen = reply.get("calendars") or []
    return ", ".join(["Dayla", *(option["title"] for option in targets if option["slug"] in chosen)])


def edit_prompt(data: dict) -> str:
    return tr(
        f"✏️ {esc(data['prompt'])} для <b>«{esc(data['title'])}»</b>\n<i>Или напишите «отмена».</i>",
        f"✏️ {esc(data['prompt'])} for <b>“{esc(data['title'])}”</b>\n<i>Or type “cancel”.</i>",
    )


def proposal_closed(text: str) -> str:
    return f"<s>{tr('Черновик', 'Draft')}</s>\n\n{esc(text)}"


def stats(data: dict) -> str:
    today = data["today"]

    def bar(percent: int) -> str:
        filled = round(percent * BAR_WIDTH / 100)
        return "▓" * filled + "░" * (BAR_WIDTH - filled)

    lines = [tr("📊 <b>Статистика выполнения</b>", "📊 <b>Progress</b>"), ""]
    if today["total"]:
        lines.append(f"<b>{tr('Сегодня', 'Today')}</b>: {today['done']} {tr('из', 'of')} {today['total']} · {today['percent']}%")
        lines.append(f"<code>{bar(today['percent'])}</code>")
    else:
        lines.append(tr("<b>Сегодня</b>: задач нет", "<b>Today</b>: no tasks"))
    lines += ["", tr("<b>Последние 7 дней</b>", "<b>Last 7 days</b>")]
    for day in data["days"]:
        moment = date.fromisoformat(day["date"])
        label = f"{weekday_short(moment)} {moment.day:>2}"
        value = f"{day['done']}/{day['total']}" if day["total"] else "—"
        lines.append(f"<code>{label} {bar(day['percent']) if day['total'] else ' ' * BAR_WIDTH} {value}</code>")
    if data["total"]:
        lines += ["", tr(f"За неделю выполнено <b>{data['done']} из {data['total']}</b> ({data['percent']}%)", f"Done this week: <b>{data['done']} of {data['total']}</b> ({data['percent']}%)")]
    streak, best = data.get("streak", 0), data.get("best_streak", 0)
    if streak >= 1:
        lines.append(tr(f"🔥 Серия: {streak} {plural(streak, 'день', 'дня', 'дней')} подряд всё выполнено", f"🔥 Streak: everything done {streak} {plural_en(streak, 'day', 'days')} in a row"))
    if best > streak:
        lines.append(tr(f"🏆 Лучшая серия: {best} {plural(best, 'день', 'дня', 'дней')}", f"🏆 Best streak: {best} {plural_en(best, 'day', 'days')}"))
    return "\n".join(lines)


def done_list(reply: dict) -> str:
    title = reply.get("title") or tr("План", "Plan")
    events = [event for day in reply.get("days") or [] for event in day["events"]]
    if not events:
        return f"✅ <b>{esc(title)}</b>\n\n{tr('Задач нет', 'No tasks')} 🌿"
    done = sum(1 for event in events if event.get("completed"))
    return tr(
        f"✅ <b>Отметьте выполненное · {esc(title)}</b>\nГотово {done} из {len(events)}. Нажмите на задачу, чтобы отметить.",
        f"✅ <b>Mark what's done · {esc(title)}</b>\n{done} of {len(events)} done. Tap a task to mark it.",
    )


def checkin_result(result: dict) -> str:
    if result.get("moved"):
        moved = result["moved"]
        target = esc(result.get("target_label") or tr("другой день", "another day"))
        return tr(f"↪️ Перенесла {moved} {plural(moved, 'задачу', 'задачи', 'задач')} на {target}.", f"↪️ Moved {moved} {plural_en(moved, 'task', 'tasks')} to {target}.")
    return tr("👍 Отлично, тогда не отвлекаю. Отмечайте выполненное — так статистика будет точнее.", "👍 Great, I won't distract you then. Mark what you finish — it keeps the stats accurate.")


def move_list(reply: dict) -> str:
    title = reply.get("title") or tr("План", "Plan")
    events = [event for day in reply.get("days") or [] for event in day["events"] if not event.get("completed")]
    if not events:
        return tr(f"↪️ <b>{esc(title)}</b>\n\nПереносить нечего — невыполненных задач нет 🌿", f"↪️ <b>{esc(title)}</b>\n\nNothing to move — no unfinished tasks 🌿")
    return tr(f"↪️ <b>Что перенести? · {esc(title)}</b>\nНажмите на задачу.", f"↪️ <b>What to move? · {esc(title)}</b>\nTap a task.")


def move_ask(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    today = datetime.now(start.tzinfo).date()
    when = no_time() if event.get("all_day") else tr(f"в {start:%H:%M}", f"at {start:%H:%M}")
    keep = "" if event.get("all_day") else tr(" Время сохранится.", " The time stays.")
    return tr(
        f"↪️ Куда перенести <b>«{esc(event['title'])}»</b>?\nСейчас: {esc(day_text(start.date(), today).lower())}, {when}.{keep}",
        f"↪️ Where should <b>“{esc(event['title'])}”</b> go?\nNow: {esc(day_text(start.date(), today))}, {when}.{keep}",
    )


def move_days(event: dict) -> str:
    return tr(f"📅 Выберите день для <b>«{esc(event['title'])}»</b> — или напишите дату.", f"📅 Pick a day for <b>“{esc(event['title'])}”</b> — or type a date.")


def moved(reply: dict) -> str:
    return "\n\n".join([f"↪️ <b>{esc(reply.get('text') or tr('Перенесла', 'Moved'))}</b>", *[event_card(event) for event in reply.get("events") or []]])


def created(reply: dict) -> str:
    events = reply["events"]
    if reply.get("kind") == "updated":
        header = tr("✏️ <b>Изменила</b>", "✏️ <b>Changed</b>")
    elif len(events) == 1:
        header = tr("✨ <b>Добавила в календарь</b>", "✨ <b>Added to the calendar</b>")
    else:
        header = f"✨ <b>{tr('Добавила', 'Added')} {counted(len(events), 'событие', 'события', 'событий', 'event', 'events')}</b>"
    parts = [header, *[event_card(event) for event in events]]
    if reply.get("note"):
        parts.append(f"🗂 {esc(reply['note'])}")
    if reply.get("answer"):
        parts.append(f"💬 {rich(reply['answer'])}")
    return "\n\n".join(parts)


def agenda_line(event: dict) -> str:
    start = datetime.fromisoformat(event["start"])
    time_text = no_time() if event.get("all_day") else f"{start:%H:%M}"
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
    title = reply.get("title") or tr("План", "Plan")
    count = sum(len(day["events"]) for day in days)
    if reply.get("date") and reply.get("scope") != "week":
        first = date.fromisoformat(reply["date"])
        if title in DAY_TITLES:
            header = f"📅 <b>{esc(title)}</b> · {short_date(first)}"
        else:
            header = f"📅 <b>{esc(day_text(first, first - timedelta(days=7)))}</b>"
        if not count:
            return f"{header}\n\n{tr('Свободный день — ничего не запланировано', 'A free day — nothing planned')} 🌿"
        body = "\n".join(agenda_line(event) for event in days[0]["events"])
        return f"{header}\n\n{body}"
    icon = "🔎" if title in FOUND_TITLES else "📆" if reply.get("scope") == "week" else "📅"
    if not count:
        return f"{icon} <b>{esc(title)}</b>\n\n{tr('Ничего не нашла — в календаре пусто', 'Nothing found — the calendar is empty')} 🌿"
    lines = [f"{icon} <b>{esc(title)}</b> · {counted(count, 'событие', 'события', 'событий', 'event', 'events')}"]
    shown = 0
    for day in days:
        block = [f"\n<b>{esc(day['label'])}</b>", *[agenda_line(event) for event in day["events"]]]
        if len("\n".join(lines + block)) > MESSAGE_LIMIT:
            rest = count - shown
            lines.append(tr(
                f"\n<i>…и ещё {rest} {plural(rest, 'событие', 'события', 'событий')} — откройте календарь в Dayla.</i>",
                f"\n<i>…and {rest} more {plural_en(rest, 'event', 'events')} — open the calendar in Dayla.</i>",
            ))
            break
        lines.extend(block)
        shown += len(day["events"])
    return "\n".join(lines)


def help_sections(reply: dict) -> str:
    lines = [
        tr("💡 <b>Что я умею</b>", "💡 <b>What I can do</b>"),
        tr(
            "Пишите как другу — текстом, голосом или документом. Всё, что меняет календарь, я сначала покажу на подтверждение.",
            "Write as you would to a friend — text, voice or a document. Anything that changes the calendar I show you to confirm first.",
        ),
    ]
    for section in reply["sections"]:
        quote = ("“", "”") if is_en() else ("«", "»")
        lines += ["", f"<b>{esc(section['title'])}</b>", "  ·  ".join(f"<i>{quote[0]}{esc(example)}{quote[1]}</i>" for example in section["examples"])]
    lines += ["", f"{tr('Команды', 'Commands')}: /today /tomorrow /week /done /stats /advice /analysis /reminders"]
    return "\n".join(lines)


def advice(reply: dict) -> str:
    items = reply.get("items") or []
    if not items:
        return tr("💡 Пока советовать нечего — план в порядке.", "💡 Nothing to advise yet — the plan is fine.")
    icons = {"warning": "⚠️", "success": "✅"}
    lines = [tr("💡 <b>Советы на сегодня</b>", "💡 <b>Advice for today</b>"), ""]
    for index, item in enumerate(items, 1):
        lines.append(f"{icons.get(item.get('kind'), '💡')} <b>{index}. {esc(item['title'])}</b>\n{rich(item['text'])}")
    return "\n\n".join([lines[0], *lines[2:]])


def topic(reply: dict) -> str:
    return tr(
        f"💡 <b>Обсуждаем: {esc(reply['title'])}</b>\n{rich(reply['text'])}\n\nСпросите, что непонятно, или выберите вопрос ниже.",
        f"💡 <b>Let's discuss: {esc(reply['title'])}</b>\n{rich(reply['text'])}\n\nAsk what's unclear, or pick a question below.",
    )


def delete_proposal(reply: dict) -> str:
    count = reply["count"]
    header = tr(f"🗑 <b>Удалить {count} {plural(count, 'задачу', 'задачи', 'задач')}?</b>", f"🗑 <b>Delete {count} {plural_en(count, 'task', 'tasks')}?</b>")
    lines = [header, f"<i>{esc(reply['title'])}</i>", ""]
    for event in reply["events"][:10]:
        start = datetime.fromisoformat(event["start"])
        when = no_time() if event.get("all_day") else f"{start:%H:%M}"
        lines.append(f"• {esc(event['title'])} — {short_date(start.date())}, <code>{when}</code>")
    if count > 10:
        lines.append(tr(f"• …и ещё {count - 10}", f"• …and {count - 10} more"))
    lines += ["", tr("Это нельзя отменить. Подтвердите кнопкой ниже.", "This can't be undone. Confirm with the button below.")]
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
    return tr(
        f"🤔 <b>Не нашла в сообщении задач</b>\n\nПопробуйте написать, что и когда, например:\n<i>«{EXAMPLES[0]}»</i>",
        f"🤔 <b>I found no tasks in the message</b>\n\nTry saying what and when, for example:\n<i>“{EXAMPLES_EN[0]}”</i>",
    )


def undone(count: int) -> str:
    if not count:
        return tr("↩️ Эти события уже удалены или изменены в Dayla.", "↩️ These events are already deleted or changed in Dayla.")
    return tr(
        f"↩️ <b>Отменено</b> — {count} {plural(count, 'событие удалено', 'события удалены', 'событий удалено')} из календаря.",
        f"↩️ <b>Undone</b> — {count} {plural_en(count, 'event', 'events')} removed from the calendar.",
    )


def heard(text: str) -> str:
    return f"🎙 <i>{tr('«', '“')}{esc(text)}{tr('»', '”')}</i>"


def reading_file(name: str) -> str:
    if name == "photo.jpg":
        return tr("🖼 Смотрю фото…", "🖼 Looking at the photo…")
    return tr(f"📄 Читаю <b>{esc(name)}</b>…", f"📄 Reading <b>{esc(name)}</b>…")


def welcome_unlinked(has_link_button: bool) -> str:
    if is_en():
        how = (
            "Press the button below, sign in and choose <b>Account → Telegram → Connect</b>."
            if has_link_button
            else "Open the Dayla site → <b>Account → Telegram</b> and press <b>“Connect Telegram”</b>."
        )
        return (
            "👋 <b>Hi! I'm Dayla</b> — an assistant that plans your day.\n\n"
            "Once your account is connected, here you can:\n"
            "💬 plan in plain words, by voice or with a document\n"
            "📅 see the plan for the day and the week\n"
            "🔔 get reminders, a morning plan and the day's summary\n\n"
            f"<b>How to connect</b>\n{how}"
        )
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
    if is_en():
        return (
            f"✅ <b>All set{name}!</b>\n"
            f"Telegram is connected to <b>{esc(profile['email'])}</b>.\n\n"
            "Now just write to me — for example:\n"
            + "\n".join(f"<i>“{example}”</i>" for example in EXAMPLES_EN)
            + "\n\n🎙 I understand voice messages, 📄 documents, tables and photos too. Before adding anything I'll show a draft — "
            "you can fix its title, date and time."
        )
    return (
        f"✅ <b>Готово{name}!</b>\n"
        f"Telegram подключён к аккаунту <b>{esc(profile['email'])}</b>.\n\n"
        "Теперь просто пишите мне — например:\n"
        + "\n".join(f"<i>«{example}»</i>" for example in EXAMPLES)
        + "\n\n🎙 Голосовые, 📄 документы, таблицы и фото тоже понимаю. Перед добавлением покажу черновик — "
        "в нём можно поправить название, дату и время."
    )


def welcome_back(profile: dict) -> str:
    name = f", {esc(profile['name'])}" if profile.get("name") else ""
    return tr(
        f"👋 <b>С возвращением{name}!</b>\n\nНапишите, что запланировать, или выберите действие в меню ниже.",
        f"👋 <b>Welcome back{name}!</b>\n\nTell me what to plan, or pick an action in the menu below.",
    )


def help_text() -> str:
    if is_en():
        return (
            "💡 <b>What I can do</b>\n\n"
            "<b>Plan</b> — write as you would to a friend:\n"
            f"<i>“{EXAMPLES_EN[0]}”</i>\n"
            f"<i>“{EXAMPLES_EN[1]}”</i>\n"
            "<i>“Buy groceries tomorrow”</i> — a task without a time\n"
            "<i>“Timetable: on Monday maths at 8:30, physics at 9:25…”</i> — several tasks at once\n"
            "<i>“Conference from 10 to 12 October”</i> — over several days\n"
            "<i>“Report, deadline Friday 18:00”</i> — with a deadline, I'll remind you in advance\n\n"
            "<b>Change tasks</b>:\n"
            "<i>“Move the call with Olya to Friday at 15:00”</i>  ·  <i>“Extend the meeting until 18:00”</i>  ·  "
            "<i>“Push the workout an hour later”</i>\n\n"
            "Before adding I'll show a draft: you can fix it or cancel it.\n\n"
            "<b>Answer questions about plans</b>:\n"
            f"<i>“{EXAMPLES_EN[2]}”</i>  ·  <i>“When is my dentist?”</i>\n\n"
            "<b>Understand voice, files and photos</b> — send a voice message, a PDF, Word or Excel file, or a photo.\n\n"
            "<b>Commands</b>\n"
            "/today — today's plan\n"
            "/tomorrow — tomorrow's plan\n"
            "/week — the next 7 days\n"
            "/done — mark tasks done\n"
            "/stats — progress\n"
            "/advice — advice on the plan\n"
            "/analysis — the week's analysis and what to move\n"
            "/reminders — reminder settings\n"
            "/unlink — disconnect Telegram"
        )
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
        "<b>Понимать голос, файлы и фото</b> — пришлите голосовое, PDF, Word, Excel или фото.\n\n"
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
    return tr(
        "⚠️ <b>Ссылка недействительна или устарела</b>\n\nПолучите новую в Dayla: <b>Аккаунт → Telegram → Подключить</b>.",
        "⚠️ <b>The link is invalid or has expired</b>\n\nGet a new one in Dayla: <b>Account → Telegram → Connect</b>.",
    )


def backend_unavailable() -> str:
    return tr("⏳ Ошибка сервера — попробуйте ещё раз через минуту.", "⏳ Server error — please try again in a minute.")


def assistant_unavailable() -> str:
    return tr(
        "⏳ Ошибка сервера — попробуйте ещё раз через минуту. План на день можно открыть через /today.",
        "⏳ Server error — please try again in a minute. You can open the day's plan with /today.",
    )


def account_unlinked() -> str:
    return tr(
        "👋 <b>Telegram отключён от Dayla.</b>\n\nНапоминания больше не придут. Подключить снова можно в настройках на сайте.",
        "👋 <b>Telegram is disconnected from Dayla.</b>\n\nReminders won't come any more. You can connect again in the settings on the site.",
    )


def unsupported_file() -> str:
    return tr(
        "📄 Я читаю <b>PDF</b>, <b>Word</b>, <b>Excel</b>, <b>CSV</b>, текстовые файлы и фото. Пришлите файл в одном из этих форматов.",
        "📄 I read <b>PDF</b>, <b>Word</b>, <b>Excel</b>, <b>CSV</b>, text files and photos. Send a file in one of these formats.",
    )


def group_help(username: str) -> str:
    return tr(
        f"Я Dayla. Напишите <b>@{esc(username)}</b> и что запланировать — «@{esc(username)} отчёт к пятнице», "
        "или ответьте так на сообщение коллеги: задача попадёт в ваш календарь, черновик пришлю в личку.",
        f"I'm Dayla. Write <b>@{esc(username)}</b> and what to plan — “@{esc(username)} report by Friday”, "
        "or reply like that to a colleague's message: the task goes to your calendar, and I'll send the draft in a private chat.",
    )


def group_not_linked(username: str) -> str:
    return tr(
        f"Чтобы я записывала ваши задачи, откройте меня в личке — t.me/{esc(username)} — и подключите Dayla. "
        "Потом просто упоминайте меня здесь.",
        f"For me to record your tasks, open a private chat with me — t.me/{esc(username)} — and connect Dayla. "
        "Then just mention me here.",
    )


def group_sent() -> str:
    return tr("✓ Записала в ваш план — подтвердите в личных сообщениях", "✓ Added to your plan — confirm it in our private chat")


def file_too_big() -> str:
    return tr("📄 Файл больше 20 МБ — Telegram не даёт ботам скачивать такие файлы.", "📄 The file is larger than 20 MB — Telegram doesn't let bots download such files.")


def voice_failed(reason: str) -> str:
    return f"🎙 {esc(reason)}"


def unsupported_message() -> str:
    return tr(
        "🙂 Я понимаю текст, голосовые, документы, таблицы и фото. Напишите, что запланировать, — или нажмите 💡 Помощь.",
        "🙂 I understand text, voice messages, documents, tables and photos. Tell me what to plan — or press 💡 Help.",
    )


def processing_error() -> str:
    return backend_unavailable()


def snoozed(minutes: int) -> str:
    return tr(f"⏰ Напомню через {format_lead(minutes)}", f"⏰ I'll remind you in {format_lead(minutes)}")


def reminder_settings(email: str | None, values: dict) -> str:
    if is_en():
        leads = ", ".join(f"{format_lead(minutes)} before" for minutes in sorted(values["lead_times"])) or "none chosen"
        digest = f"at {values['daily_digest_time'][:5]}" if values["daily_digest_enabled"] else "off"
        quiet = f"{values['quiet_hours_start'][:5]}–{values['quiet_hours_end'][:5]}" if values["quiet_hours_enabled"] else "off"
        evening = f"at {values['evening_time'][:5]}" if values.get("evening_enabled") and values.get("evening_time") else "off"
        return (
            "🔔 <b>Reminders</b>\n"
            + (f"<i>{esc(email)}</i>\n" if email else "")
            + "\n"
            f"Status: {'<b>on</b> ✅' if values['enabled'] else '<b>off</b> ⏸'}\n"
            f"When: {leads}\n"
            f"Morning plan: {digest}\n"
            f"Day's summary: {evening}\n"
            f"Deadlines: {'3 days, a day and 2 hours before' if values.get('deadline_enabled') else 'off'}\n"
            f"Quiet hours: {quiet}\n\n"
            "Press a button to change."
        )
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


# ---------- short answers under buttons (callback alerts) ----------


def outdated(hint: str = "") -> str:
    """"Это сообщение устарело" with what to do instead."""
    hints = {
        "": ("", ""),
        "command": (" — отправьте команду ещё раз", " — send the command again"),
        "done": (" — отправьте /done", " — send /done"),
        "plan": (" — откройте план ещё раз", " — open the plan again"),
        "task": (" — отправьте задачу ещё раз", " — send the task again"),
    }
    ru, en = hints.get(hint, hints[""])
    return tr(f"Это сообщение устарело{ru}", f"This message is out of date{en}")


def not_linked_alert() -> str:
    return tr("Telegram не подключён к Dayla", "Telegram isn't connected to Dayla")


def task_gone() -> str:
    return tr("Задача не найдена — возможно, её удалили", "Task not found — it may have been deleted")


def short(key: str) -> str:
    """One- or two-word answers under buttons."""
    return tr(*SHORT[key])


SHORT = {
    "saved": ("Сохранено ✓", "Saved ✓"),
    "done": ("Выполнено ✓", "Done ✓"),
    "done_label": ("Выполнено", "Done"),
    "unmarked": ("Снята отметка", "Unmarked"),
    "moved": ("Перенесла ✓", "Moved ✓"),
    "ready": ("Готово", "Done"),
    "cancelled": ("Отменено", "Cancelled"),
    "already_deleted": ("Уже удалено", "Already deleted"),
    "deleted": ("Удалено ✓", "Deleted ✓"),
    "changed": ("Изменено ✓", "Changed ✓"),
    "added": ("Добавлено ✓", "Added ✓"),
    "removed": ("Убрано", "Removed"),
    "rating_thanks": ("Спасибо за оценку!", "Thanks for the rating!"),
    "rating_removed": ("Оценка снята", "Rating removed"),
    "rating_failed": ("Не получилось сохранить оценку", "Couldn't save the rating"),
    "advice_outdated": ("Совет устарел — запросите советы ещё раз", "This advice is out of date — ask for advice again"),
    "reminder_gone": ("Напоминание уже пришло или отменено", "The reminder has already come or was cancelled"),
    "draft_closed": ("Черновик закрыт", "Draft closed"),
    "draft_handled": ("Этот черновик уже обработан", "This draft has already been handled"),
    "calendar_gone": ("Этот календарь больше не подключён", "This calendar is no longer connected"),
    "remember_choice": ("Запомню этот выбор", "I'll remember this choice"),
    "where_else": ("Куда ещё добавить задачи?", "Where else should the tasks go?"),
    "snooze_failed": ("Не получилось отложить напоминание", "Couldn't snooze the reminder"),
    "mark_failed": ("Не получилось отметить задачу", "Couldn't mark the task"),
    "try_again": ("Не получилось — попробуйте ещё раз", "Didn't work — please try again"),
    "analyse_week": ("проанализируй мою неделю", "analyse my week"),
    "plan_this": ("Запланируй это", "Plan this"),
}


def what_to_change(index: int) -> str:
    return tr(f"Задача {index + 1}: что изменить?", f"Task {index + 1}: what to change?")


def group_quote(text: str, chat: str | None, author: str | None, quoted: str) -> str:
    """A colleague's message the user asked to plan, with where it came from."""
    if is_en():
        return f"{text or short('plan_this')}\n\nA message from the chat “{chat or 'group'}” by {author or 'a member'}:\n{quoted}"
    return f"{text or short('plan_this')}\n\nСообщение из чата «{chat or 'группы'}» от {author or 'участник'}:\n{quoted}"
