from datetime import date, datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.templates.messages import LEAD_PRESETS, format_lead

MENU_TODAY = "📅 Сегодня"
MENU_TOMORROW = "🗓 Завтра"
MENU_WEEK = "📆 Неделя"
MENU_REMINDERS = "🔔 Напоминания"
MENU_HELP = "💡 Помощь"
MENU_DONE = "✅ Выполнено"
MENU_STATS = "📊 Статистика"
MENU_ADVICE = "💡 Советы"
MENU_ANALYSIS = "📈 Анализ недели"
# The same quick replies as under a recommendation in the web chat
TOPIC_REPLIES = ("Как это сделать?", "Помоги перепланировать", "Что можно перенести?")
SCOPES = {"today": "Сегодня", "tomorrow": "Завтра", "week": "Неделя"}
CALLBACK_LIMIT = 64

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=MENU_TODAY), KeyboardButton(text=MENU_TOMORROW), KeyboardButton(text=MENU_WEEK)],
        [KeyboardButton(text=MENU_DONE), KeyboardButton(text=MENU_STATS)],
        [KeyboardButton(text=MENU_ADVICE), KeyboardButton(text=MENU_ANALYSIS)],
        [KeyboardButton(text=MENU_REMINDERS), KeyboardButton(text=MENU_HELP)],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Напишите план или вопрос…",
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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Подключить в Dayla", url=f"{url}/app/account#telegram")]])


def created_keyboard(event_ids: list[int], events: list[dict], app_url: str | None) -> InlineKeyboardMarkup | None:
    row = []
    data = f"undo:{compress_ids(event_ids)}" if event_ids else ""
    if data and len(data.encode()) <= CALLBACK_LIMIT:
        row.append(InlineKeyboardButton(text="↩️ Отменить", callback_data=data))
    url = public_url(events[0].get("url")) if len(events) == 1 else None
    if not url and public_url(app_url) and events:
        url = f"{app_url}/app/calendar?day={events[0]['start'][:10]}"
    if url:
        row.append(InlineKeyboardButton(text="↗️ Открыть в Dayla", url=url))
    return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None


def agenda_keyboard(current: str | None, app_url: str | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"• {label} •" if scope == current else label, callback_data=f"ag:{scope}") for scope, label in SCOPES.items()]]
    if current in SCOPES:
        rows.append([
            InlineKeyboardButton(text="✅ Отметить выполненные", callback_data=f"dn:{current}"),
            InlineKeyboardButton(text="↪️ Перенести", callback_data=f"mv:{current}"),
        ])
    url = public_url(app_url)
    if url:
        rows.append([InlineKeyboardButton(text="↗️ Календарь в Dayla", url=f"{url}/app/calendar")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_keyboard(notification_id: int, url: str | None, event_id: int | None = None) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text="⏰ +10 мин", callback_data=f"sn:{notification_id}:10"),
        InlineKeyboardButton(text="⏰ +1 час", callback_data=f"sn:{notification_id}:60"),
    ]
    rows = [row]
    if event_id:
        rows.append([InlineKeyboardButton(text="✅ Выполнено", callback_data=f"rd:{event_id}")])
    if public_url(url):
        rows.append([InlineKeyboardButton(text="↗️ Открыть событие", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def digest_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📅 План на сегодня", callback_data="ag:today"), InlineKeyboardButton(text="📆 Неделя", callback_data="ag:week")]]
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
    rows = [[InlineKeyboardButton(text=f"💬 Обсудить {index + 1}" if count > 1 else "💬 Обсудить", callback_data=f"adv:{index}") for index in range(min(count, 3))]]
    return with_rating(InlineKeyboardMarkup(inline_keyboard=rows), message_id)


def topic_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=f"qr:{index}")] for index, text in enumerate(TOPIC_REPLIES)])


def delete_keyboard(draft_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=f"🗑 Удалить ({count})", callback_data=f"dr:{draft_id}:ok"),
            InlineKeyboardButton(text="✖️ Не удалять", callback_data=f"dr:{draft_id}:no"),
        ]]
    )


def evening_keyboard(notification_id: int, payload: dict | None) -> InlineKeyboardMarkup:
    rows = []
    if (payload or {}).get("event_ids"):
        rows.append([InlineKeyboardButton(text="↪️ Перенести невыполненное на завтра", callback_data=f"ci:{notification_id}:move")])
    rows.append([InlineKeyboardButton(text="🗓 План на завтра", callback_data="ag:tomorrow"), InlineKeyboardButton(text="✅ Отметить выполненные", callback_data="dn:today")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deadline_keyboard(event_id: int | None, url: str | None) -> InlineKeyboardMarkup | None:
    rows = []
    if event_id:
        rows.append([InlineKeyboardButton(text="✅ Выполнено", callback_data=f"rd:{event_id}")])
    if public_url(url):
        rows.append([InlineKeyboardButton(text="↗️ Открыть задачу", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def updated_keyboard(events: list[dict], app_url: str | None) -> InlineKeyboardMarkup | None:
    url = public_url(events[0].get("url")) if len(events) == 1 else None
    if not url and public_url(app_url) and events:
        url = f"{app_url}/app/calendar?day={events[0]['start'][:10]}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↗️ Открыть в Dayla", url=url)]]) if url else None


def settings_keyboard(values: dict, app_url: str | None) -> InlineKeyboardMarkup:
    leads = set(values["lead_times"])
    rows = [
        [InlineKeyboardButton(text="⏸ Выключить напоминания" if values["enabled"] else "▶️ Включить напоминания", callback_data="rs:enabled")],
        *[
            [
                InlineKeyboardButton(text=("✓ " if minutes in leads else "") + format_lead(minutes), callback_data=f"rs:lead:{minutes}")
                for minutes in LEAD_PRESETS[start : start + 3]
            ]
            for start in range(0, len(LEAD_PRESETS), 3)
        ],
        [InlineKeyboardButton(text=("✓ " if values["daily_digest_enabled"] else "") + "☀️ Утренний план", callback_data="rs:digest")],
        [
            InlineKeyboardButton(text=("✓ " if values.get("evening_enabled") else "") + "🌙 Итоги дня", callback_data="rs:evening"),
            InlineKeyboardButton(text=("✓ " if values.get("deadline_enabled") else "") + "⏳ Дедлайны", callback_data="rs:deadline"),
        ],
    ]
    url = public_url(app_url)
    if url:
        rows.append([InlineKeyboardButton(text="⚙️ Все настройки в Dayla", url=f"{url}/app/account#reminders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_keyboard(draft_id: int, count: int, change: bool = False, target: str | None = None) -> InlineKeyboardMarkup:
    """target: where the tasks go ("Dayla и Google Calendar") when there is a choice; adds the button to change it."""
    add = "✅ Сохранить" if change else "✅ Добавить" if count == 1 else f"✅ Добавить все ({count})"
    rows = [[
        InlineKeyboardButton(text=add, callback_data=f"dr:{draft_id}:ok"),
        InlineKeyboardButton(text="✖️ Отмена", callback_data=f"dr:{draft_id}:no"),
    ]]
    if count == 1:
        rows.append(edit_row(draft_id, 0))
    else:
        numbers = [InlineKeyboardButton(text=f"✏️ {index + 1}", callback_data=f"dr:{draft_id}:sel:{index}") for index in range(min(count, 20))]
        rows += [numbers[start : start + 5] for start in range(0, len(numbers), 5)]
    if target:
        rows.append([InlineKeyboardButton(text=f"🗂 Куда: {target}", callback_data=f"dr:{draft_id}:to")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def targets_keyboard(draft_id: int, targets: list[dict], chosen: list[str]) -> InlineKeyboardMarkup:
    """Checkboxes for the connected calendars: a press ticks or unticks one; tasks are always in Dayla."""
    rows = [
        [InlineKeyboardButton(text=("☑️ " if option["slug"] in chosen else "⬜ ") + option["title"], callback_data=f"dr:{draft_id}:to:{option['slug']}")]
        for option in targets
    ]
    rows.append([InlineKeyboardButton(text="✓ Готово", callback_data=f"dr:{draft_id}:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_row(draft_id: int, index: int) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text="✏️ Название", callback_data=f"dr:{draft_id}:e:{index}:title"),
        InlineKeyboardButton(text="📅 Дата", callback_data=f"dr:{draft_id}:e:{index}:date"),
        InlineKeyboardButton(text="🕒 Время", callback_data=f"dr:{draft_id}:e:{index}:time"),
    ]


def proposal_item_keyboard(draft_id: int, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            edit_row(draft_id, index),
            [
                InlineKeyboardButton(text="🗑 Убрать из списка", callback_data=f"dr:{draft_id}:rm:{index}"),
                InlineKeyboardButton(text="← Назад", callback_data=f"dr:{draft_id}:back"),
            ],
        ]
    )


def done_keyboard(reply: dict, scope: str) -> InlineKeyboardMarkup:
    rows = []
    for day in reply.get("days") or []:
        for event in day["events"]:
            if len(rows) >= 30:
                break
            when = "без времени" if event.get("all_day") else event["start"][11:16]
            if scope == "week":
                when = f"{event['start'][8:10]}.{event['start'][5:7]} {when}"
            mark = "✅" if event.get("completed") else "⬜"
            label = f"{mark} {when} · {event['title']}"
            rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"dt:{event['id']}:{scope}:{0 if event.get('completed') else 1}")])
    rows.append([InlineKeyboardButton(text="← К плану", callback_data=f"ag:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def checkin_keyboard(notification_id: int, payload: dict | None) -> InlineKeyboardMarkup:
    payload = payload or {}
    first = []
    if payload.get("event_ids"):
        first.append(InlineKeyboardButton(text=f"↪️ Перенести на {payload.get('target_label') or 'другой день'}", callback_data=f"ci:{notification_id}:move"))
    first.append(InlineKeyboardButton(text="👍 Успеваю", callback_data=f"ci:{notification_id}:ok"))
    return InlineKeyboardMarkup(inline_keyboard=[first, [InlineKeyboardButton(text="✅ Отметить выполненные", callback_data="dn:today")]])


# ---------- moving a task: choose it, then "Завтра", "Послезавтра" or another day ----------

WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MOVE_PICKER_DAYS = 14


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
            when = "без времени" if event.get("all_day") else event["start"][11:16]
            if scope == "week":
                when = f"{event['start'][8:10]}.{event['start'][5:7]} {when}"
            rows.append([InlineKeyboardButton(text=f"↪️ {when} · {event['title']}"[:60], callback_data=f"mp:{event['id']}:{scope}")])
    rows.append([InlineKeyboardButton(text="← К плану", callback_data=f"ag:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def move_options_keyboard(event: dict, scope: str) -> InlineKeyboardMarkup:
    current, today = event_day(event)
    options = [("Сегодня", today), ("Завтра", today + timedelta(days=1)), ("Послезавтра", today + timedelta(days=2))]
    quick = [
        InlineKeyboardButton(text=f"{label}, {WEEKDAYS_SHORT[day.weekday()]} {day.day}", callback_data=move_to(event["id"], day))
        for label, day in options
        if day != current
    ]
    rows = [quick] if quick else []
    rows.append([InlineKeyboardButton(text="📅 Другой день", callback_data=f"mo:{event['id']}:{scope}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"mv:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def move_days_keyboard(event: dict, scope: str) -> InlineKeyboardMarkup:
    current, today = event_day(event)
    days = [today + timedelta(days=offset) for offset in range(3, 3 + MOVE_PICKER_DAYS)]
    buttons = [
        InlineKeyboardButton(text=f"{WEEKDAYS_SHORT[day.weekday()]} {day:%d.%m}", callback_data=move_to(event["id"], day))
        for day in days
        if day != current
    ]
    rows = [buttons[start : start + 4] for start in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text="✍️ Написать дату", callback_data=f"mw:{event['id']}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"mp:{event['id']}:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moved_keyboard(reply: dict) -> InlineKeyboardMarkup:
    moved = reply.get("moved") or {}
    rows = []
    if moved.get("event_id") and moved.get("from"):
        back = date.fromisoformat(moved["from"])
        rows.append([InlineKeyboardButton(text=f"↩️ Вернуть на {moved.get('from_label') or back.strftime('%d.%m')}"[:60], callback_data=move_to(moved["event_id"], back))])
    rows.append([InlineKeyboardButton(text="📅 Сегодня", callback_data="ag:today"), InlineKeyboardButton(text="🗓 Завтра", callback_data="ag:tomorrow")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
