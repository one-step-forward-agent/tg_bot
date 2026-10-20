from datetime import date, datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import is_en, tr
from bot.templates.messages import LEAD_PRESETS, WEEKDAYS_SHORT_EN, format_lead, no_time

# The menu buttons in both languages: a keyboard stays on the screen until the next one replaces it,
# so the old language's buttons keep working after the language is switched on the site
MENU = {
    "today": ("📅 Сегодня", "📅 Today"),
    "tomorrow": ("🗓 Завтра", "🗓 Tomorrow"),
    "week": ("📆 Неделя", "📆 Week"),
    "done": ("✅ Выполнено", "✅ Done"),
    "stats": ("📊 Статистика", "📊 Stats"),
    "advice": ("💡 Советы", "💡 Advice"),
    "analysis": ("📈 Анализ недели", "📈 Week analysis"),
    "reminders": ("🔔 Напоминания", "🔔 Reminders"),
    "help": ("💡 Помощь", "💡 Help"),
}
MENU_TODAY, MENU_TOMORROW, MENU_WEEK = set(MENU["today"]), set(MENU["tomorrow"]), set(MENU["week"])
MENU_DONE, MENU_STATS, MENU_ADVICE, MENU_ANALYSIS = set(MENU["done"]), set(MENU["stats"]), set(MENU["advice"]), set(MENU["analysis"])
MENU_REMINDERS, MENU_HELP = set(MENU["reminders"]), set(MENU["help"])
# The same quick replies as under a recommendation in the web chat
TOPIC_REPLIES = ("Как это сделать?", "Помоги перепланировать", "Что можно перенести?")
TOPIC_REPLIES_EN = ("How do I do it?", "Help me replan", "What can I move?")
SCOPES = {"today": ("Сегодня", "Today"), "tomorrow": ("Завтра", "Tomorrow"), "week": ("Неделя", "Week")}
CALLBACK_LIMIT = 64


def menu(key: str) -> str:
    return tr(*MENU[key])


def topic_replies() -> tuple[str, ...]:
    return TOPIC_REPLIES_EN if is_en() else TOPIC_REPLIES


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=menu("today")), KeyboardButton(text=menu("tomorrow")), KeyboardButton(text=menu("week"))],
            [KeyboardButton(text=menu("done")), KeyboardButton(text=menu("stats"))],
            [KeyboardButton(text=menu("advice")), KeyboardButton(text=menu("analysis"))],
            [KeyboardButton(text=menu("reminders")), KeyboardButton(text=menu("help"))],
        ],
        resize_keyboard=True,
        input_field_placeholder=tr("Напишите план или вопрос…", "Type a plan or a question…"),
    )


def public_url(url: str | None) -> str | None:
    if not url or not url.startswith("https://"):
        return None
    return url


def compress_ids(ids: list[int]) -> str:
    parts, ordered = [], sorted(set(ids))
    start = previous = ordered[0]
    for value in ordered[1:] + [None]:
        if value is not None and value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        if value is not None:
            start = previous = value
    return ",".join(parts)


def expand_ids(packed: str) -> list[int]:
    ids = []
    for part in packed.split(","):
        if "-" in part:
            first, last = part.split("-", 1)
            ids.extend(range(int(first), int(last) + 1))
        elif part:
            ids.append(int(part))
    return ids[:50]


def link_keyboard(app_url: str | None) -> InlineKeyboardMarkup | None:
    url = public_url(app_url)
    if not url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=tr("🔗 Подключить в Dayla", "🔗 Connect in Dayla"), url=f"{url}/app/account#telegram")]])


def created_keyboard(event_ids: list[int], events: list[dict], app_url: str | None) -> InlineKeyboardMarkup | None:
    row = []
    data = f"undo:{compress_ids(event_ids)}" if event_ids else ""
    if data and len(data.encode()) <= CALLBACK_LIMIT:
        row.append(InlineKeyboardButton(text=tr("↩️ Отменить", "↩️ Undo"), callback_data=data))
    url = public_url(events[0].get("url")) if len(events) == 1 else None
    if not url and public_url(app_url) and events:
        url = f"{app_url}/app/calendar?day={events[0]['start'][:10]}"
    if url:
        row.append(InlineKeyboardButton(text=tr("↗️ Открыть в Dayla", "↗️ Open in Dayla"), url=url))
    return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None


def agenda_keyboard(current: str | None, app_url: str | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"• {tr(*label)} •" if scope == current else tr(*label), callback_data=f"ag:{scope}") for scope, label in SCOPES.items()]]
    if current in SCOPES:
        rows.append([
            InlineKeyboardButton(text=tr("✅ Отметить выполненные", "✅ Mark done"), callback_data=f"dn:{current}"),
            InlineKeyboardButton(text=tr("↪️ Перенести", "↪️ Move"), callback_data=f"mv:{current}"),
        ])
    url = public_url(app_url)
    if url:
        rows.append([InlineKeyboardButton(text=tr("↗️ Календарь в Dayla", "↗️ Calendar in Dayla"), url=f"{url}/app/calendar")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_keyboard(notification_id: int, url: str | None, event_id: int | None = None) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text=tr("⏰ +10 мин", "⏰ +10 min"), callback_data=f"sn:{notification_id}:10"),
        InlineKeyboardButton(text=tr("⏰ +1 час", "⏰ +1 hour"), callback_data=f"sn:{notification_id}:60"),
    ]
    rows = [row]
    if event_id:
        rows.append([InlineKeyboardButton(text=tr("✅ Выполнено", "✅ Done"), callback_data=f"rd:{event_id}")])
    if public_url(url):
        rows.append([InlineKeyboardButton(text=tr("↗️ Открыть событие", "↗️ Open the event"), url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_set_keyboard(reminders: list[dict]) -> InlineKeyboardMarkup | None:
    """"Отменить" under each reminder the assistant has just set."""
    rows = [
        [InlineKeyboardButton(text=tr("🔕 Отменить", "🔕 Cancel") if len(reminders) == 1 else tr(f"🔕 Отменить «{item['text'][:24]}»", f"🔕 Cancel “{item['text'][:24]}”"), callback_data=f"rc:{item['id']}")]
        for item in reminders[:5]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def digest_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=tr("📅 План на сегодня", "📅 Today's plan"), callback_data="ag:today"), InlineKeyboardButton(text=menu("week"), callback_data="ag:week")]]
    )


RATING_PREFIX = "rt:"


def rating_row(message_id: int, chosen: int | None = None) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text="👍" + (" ✓" if chosen == 1 else ""), callback_data=f"rt:{message_id}:{0 if chosen == 1 else 1}"),
        InlineKeyboardButton(text="👎" + (" ✓" if chosen == -1 else ""), callback_data=f"rt:{message_id}:{0 if chosen == -1 else -1}"),
    ]


def with_rating(markup: InlineKeyboardMarkup | None, message_id: int | None) -> InlineKeyboardMarkup | None:
    """Small 👍 / 👎 under an answer, so anyone who wants can rate it."""
    if not message_id:
        return markup
    rows = [row for row in (markup.inline_keyboard if markup else []) if not any((button.callback_data or "").startswith(RATING_PREFIX) for button in row)]
    return InlineKeyboardMarkup(inline_keyboard=[*rows, rating_row(message_id)])


def rated(markup: InlineKeyboardMarkup | None, message_id: int, value: int) -> InlineKeyboardMarkup:
    rows = [row for row in (markup.inline_keyboard if markup else []) if not any((button.callback_data or "").startswith(RATING_PREFIX) for button in row)]
    return InlineKeyboardMarkup(inline_keyboard=[*rows, rating_row(message_id, value or None)])


def advice_keyboard(count: int, message_id: int | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=tr(f"💬 Обсудить {index + 1}", f"💬 Discuss {index + 1}") if count > 1 else tr("💬 Обсудить", "💬 Discuss"), callback_data=f"adv:{index}") for index in range(min(count, 3))]]
    return with_rating(InlineKeyboardMarkup(inline_keyboard=rows), message_id)


def topic_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=f"qr:{index}")] for index, text in enumerate(topic_replies())])


def delete_keyboard(draft_id: int, count: int, series: bool = False) -> InlineKeyboardMarkup:
    if series:
        # A repeated task: just the found days, them and the later ones, or the whole series
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=tr("Только эту", "Only this one") if count == 1 else tr("Только эти", "Only these"), callback_data=f"dr:{draft_id}:ok:one")],
                [InlineKeyboardButton(text=tr("Эту и следующие", "This and the following") if count == 1 else tr("Эти и следующие", "These and the following"), callback_data=f"dr:{draft_id}:ok:following")],
                [InlineKeyboardButton(text=tr("🗑 Всю серию", "🗑 The whole series"), callback_data=f"dr:{draft_id}:ok:all")],
                [InlineKeyboardButton(text=tr("✖️ Не удалять", "✖️ Don't delete"), callback_data=f"dr:{draft_id}:no")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=tr(f"🗑 Удалить ({count})", f"🗑 Delete ({count})"), callback_data=f"dr:{draft_id}:ok"),
            InlineKeyboardButton(text=tr("✖️ Не удалять", "✖️ Don't delete"), callback_data=f"dr:{draft_id}:no"),
        ]]
    )


def evening_keyboard(notification_id: int, payload: dict | None) -> InlineKeyboardMarkup:
    rows = []
    if (payload or {}).get("event_ids"):
        rows.append([InlineKeyboardButton(text=tr("↪️ Перенести невыполненное на завтра", "↪️ Move what's left to tomorrow"), callback_data=f"ci:{notification_id}:move")])
    rows.append([InlineKeyboardButton(text=tr("🗓 План на завтра", "🗓 Tomorrow's plan"), callback_data="ag:tomorrow"), InlineKeyboardButton(text=tr("✅ Отметить выполненные", "✅ Mark done"), callback_data="dn:today")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deadline_keyboard(event_id: int | None, url: str | None) -> InlineKeyboardMarkup | None:
    rows = []
    if event_id:
        rows.append([InlineKeyboardButton(text=tr("✅ Выполнено", "✅ Done"), callback_data=f"rd:{event_id}")])
    if public_url(url):
        rows.append([InlineKeyboardButton(text=tr("↗️ Открыть задачу", "↗️ Open the task"), url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def updated_keyboard(events: list[dict], app_url: str | None) -> InlineKeyboardMarkup | None:
    url = public_url(events[0].get("url")) if len(events) == 1 else None
    if not url and public_url(app_url) and events:
        url = f"{app_url}/app/calendar?day={events[0]['start'][:10]}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=tr("↗️ Открыть в Dayla", "↗️ Open in Dayla"), url=url)]]) if url else None


def settings_keyboard(values: dict, app_url: str | None) -> InlineKeyboardMarkup:
    leads = set(values["lead_times"])
    rows = [
        [InlineKeyboardButton(text=tr("⏸ Выключить напоминания", "⏸ Turn reminders off") if values["enabled"] else tr("▶️ Включить напоминания", "▶️ Turn reminders on"), callback_data="rs:enabled")],
        *[
            [
                InlineKeyboardButton(text=("✓ " if minutes in leads else "") + format_lead(minutes), callback_data=f"rs:lead:{minutes}")
                for minutes in LEAD_PRESETS[start : start + 3]
            ]
            for start in range(0, len(LEAD_PRESETS), 3)
        ],
        [InlineKeyboardButton(text=("✓ " if values["daily_digest_enabled"] else "") + tr("☀️ Утренний план", "☀️ Morning plan"), callback_data="rs:digest")],
        [
            InlineKeyboardButton(text=("✓ " if values.get("evening_enabled") else "") + tr("🌙 Итоги дня", "🌙 Day's summary"), callback_data="rs:evening"),
            InlineKeyboardButton(text=("✓ " if values.get("deadline_enabled") else "") + tr("⏳ Дедлайны", "⏳ Deadlines"), callback_data="rs:deadline"),
        ],
    ]
    url = public_url(app_url)
    if url:
        rows.append([InlineKeyboardButton(text=tr("⚙️ Все настройки в Dayla", "⚙️ All settings in Dayla"), url=f"{url}/app/account#reminders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_keyboard(draft_id: int, count: int, change: bool = False, target: str | None = None) -> InlineKeyboardMarkup:
    """target: where the tasks go ("Dayla и Google Calendar") when there is a choice; adds the button to change it."""
    add = tr("✅ Сохранить", "✅ Save") if change else tr("✅ Добавить", "✅ Add") if count == 1 else tr(f"✅ Добавить все ({count})", f"✅ Add all ({count})")
    rows = [[
        InlineKeyboardButton(text=add, callback_data=f"dr:{draft_id}:ok"),
        InlineKeyboardButton(text=tr("✖️ Отмена", "✖️ Cancel"), callback_data=f"dr:{draft_id}:no"),
    ]]
    if count == 1:
        rows += edit_rows(draft_id, 0)
    else:
        numbers = [InlineKeyboardButton(text=f"✏️ {index + 1}", callback_data=f"dr:{draft_id}:sel:{index}") for index in range(min(count, 20))]
        rows += [numbers[start : start + 5] for start in range(0, len(numbers), 5)]
    if target:
        rows.append([InlineKeyboardButton(text=tr(f"🗂 Куда: {target}", f"🗂 Where: {target}"), callback_data=f"dr:{draft_id}:to")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def targets_keyboard(draft_id: int, targets: list[dict], chosen: list[str]) -> InlineKeyboardMarkup:
    """Checkboxes for the connected calendars: a press ticks or unticks one; tasks are always in Dayla."""
    rows = [
        [InlineKeyboardButton(text=("☑️ " if option["slug"] in chosen else "⬜ ") + option["title"], callback_data=f"dr:{draft_id}:to:{option['slug']}")]
        for option in targets
    ]
    rows.append([InlineKeyboardButton(text=tr("✓ Готово", "✓ Done"), callback_data=f"dr:{draft_id}:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_rows(draft_id: int, index: int) -> list[list[InlineKeyboardButton]]:
    """Every field of a task can be changed in words: the bot asks, the user writes «каждую неделю 5 раз», «за 2 часа»."""
    return [
        [
            InlineKeyboardButton(text=tr("✏️ Название", "✏️ Title"), callback_data=f"dr:{draft_id}:e:{index}:title"),
            InlineKeyboardButton(text=tr("📅 Дата", "📅 Date"), callback_data=f"dr:{draft_id}:e:{index}:date"),
            InlineKeyboardButton(text=tr("🕒 Время", "🕒 Time"), callback_data=f"dr:{draft_id}:e:{index}:time"),
        ],
        [
            InlineKeyboardButton(text=tr("🔁 Повтор", "🔁 Repeat"), callback_data=f"dr:{draft_id}:e:{index}:repeat"),
            InlineKeyboardButton(text=tr("⏳ Период", "⏳ Period"), callback_data=f"dr:{draft_id}:e:{index}:period"),
            InlineKeyboardButton(text=tr("🔔 Напомнить", "🔔 Remind"), callback_data=f"dr:{draft_id}:e:{index}:reminder"),
        ],
    ]


def proposal_item_keyboard(draft_id: int, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *edit_rows(draft_id, index),
            [
                InlineKeyboardButton(text=tr("🗑 Убрать из списка", "🗑 Remove from the list"), callback_data=f"dr:{draft_id}:rm:{index}"),
                InlineKeyboardButton(text=tr("← Назад", "← Back"), callback_data=f"dr:{draft_id}:back"),
            ],
        ]
    )


def done_keyboard(reply: dict, scope: str) -> InlineKeyboardMarkup:
    rows = []
    for day in reply.get("days") or []:
        for event in day["events"]:
            if len(rows) >= 30:
                break
            when = no_time() if event.get("all_day") else event["start"][11:16]
            if scope == "week":
                when = f"{event['start'][8:10]}.{event['start'][5:7]} {when}"
            mark = "✅" if event.get("completed") else "⬜"
            label = f"{mark} {when} · {event['title']}"
            rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"dt:{event['id']}:{scope}:{0 if event.get('completed') else 1}")])
    rows.append([InlineKeyboardButton(text=tr("← К плану", "← To the plan"), callback_data=f"ag:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def checkin_keyboard(notification_id: int, payload: dict | None) -> InlineKeyboardMarkup:
    payload = payload or {}
    first = []
    if payload.get("event_ids"):
        first.append(InlineKeyboardButton(text=tr(f"↪️ Перенести на {payload.get('target_label') or 'другой день'}", f"↪️ Move to {payload.get('target_label') or 'another day'}"), callback_data=f"ci:{notification_id}:move"))
    first.append(InlineKeyboardButton(text=tr("👍 Успеваю", "👍 I'm on track"), callback_data=f"ci:{notification_id}:ok"))
    return InlineKeyboardMarkup(inline_keyboard=[first, [InlineKeyboardButton(text=tr("✅ Отметить выполненные", "✅ Mark done"), callback_data="dn:today")]])


# ---------- moving a task: choose it, then "Завтра", "Послезавтра" or another day ----------

WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MOVE_PICKER_DAYS = 14


def weekday_short(day: date) -> str:
    return (WEEKDAYS_SHORT_EN if is_en() else WEEKDAYS_SHORT)[day.weekday()]


def event_day(event: dict) -> tuple[date, date]:
    """The task's day and today, both in the user's time zone (the offset of the task's start)."""
    start = datetime.fromisoformat(event["start"])
    return start.date(), datetime.now(start.tzinfo).date()


def move_to(event_id: int, day: date) -> str:
    return f"mt:{event_id}:{day:%Y%m%d}"


def move_list_keyboard(reply: dict, scope: str) -> InlineKeyboardMarkup:
    rows = []
    for day in reply.get("days") or []:
        for event in day["events"]:
            if event.get("completed") or len(rows) >= 30:
                continue
            when = no_time() if event.get("all_day") else event["start"][11:16]
            if scope == "week":
                when = f"{event['start'][8:10]}.{event['start'][5:7]} {when}"
            rows.append([InlineKeyboardButton(text=f"↪️ {when} · {event['title']}"[:60], callback_data=f"mp:{event['id']}:{scope}")])
    rows.append([InlineKeyboardButton(text=tr("← К плану", "← To the plan"), callback_data=f"ag:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def move_options_keyboard(event: dict, scope: str) -> InlineKeyboardMarkup:
    current, today = event_day(event)
    options = [(tr("Сегодня", "Today"), today), (tr("Завтра", "Tomorrow"), today + timedelta(days=1)), (tr("Послезавтра", "In 2 days"), today + timedelta(days=2))]
    quick = [
        InlineKeyboardButton(text=f"{label}, {weekday_short(day)} {day.day}", callback_data=move_to(event["id"], day))
        for label, day in options
        if day != current
    ]
    rows = [quick] if quick else []
    rows.append([InlineKeyboardButton(text=tr("📅 Другой день", "📅 Another day"), callback_data=f"mo:{event['id']}:{scope}")])
    rows.append([InlineKeyboardButton(text=tr("← Назад", "← Back"), callback_data=f"mv:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def move_days_keyboard(event: dict, scope: str) -> InlineKeyboardMarkup:
    current, today = event_day(event)
    days = [today + timedelta(days=offset) for offset in range(3, 3 + MOVE_PICKER_DAYS)]
    buttons = [
        InlineKeyboardButton(text=f"{weekday_short(day)} {day:%d.%m}", callback_data=move_to(event["id"], day))
        for day in days
        if day != current
    ]
    rows = [buttons[start : start + 4] for start in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text=tr("✍️ Написать дату", "✍️ Type a date"), callback_data=f"mw:{event['id']}")])
    rows.append([InlineKeyboardButton(text=tr("← Назад", "← Back"), callback_data=f"mp:{event['id']}:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moved_keyboard(reply: dict) -> InlineKeyboardMarkup:
    moved = reply.get("moved") or {}
    rows = []
    if moved.get("event_id") and moved.get("from"):
        back = date.fromisoformat(moved["from"])
        rows.append([InlineKeyboardButton(text=tr(f"↩️ Вернуть на {moved.get('from_label') or back.strftime('%d.%m')}", f"↩️ Back to {moved.get('from_label') or back.strftime('%d.%m')}")[:60], callback_data=move_to(moved["event_id"], back))])
    rows.append([InlineKeyboardButton(text=menu("today"), callback_data="ag:today"), InlineKeyboardButton(text=menu("tomorrow"), callback_data="ag:tomorrow")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
