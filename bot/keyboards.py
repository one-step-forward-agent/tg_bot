from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.templates.messages import LEAD_PRESETS, format_lead

MENU_TODAY = "📅 Сегодня"
MENU_TOMORROW = "🗓 Завтра"
MENU_WEEK = "📆 Неделя"
MENU_REMINDERS = "🔔 Напоминания"
MENU_HELP = "💡 Помощь"
SCOPES = {"today": "Сегодня", "tomorrow": "Завтра", "week": "Неделя"}
CALLBACK_LIMIT = 64

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=MENU_TODAY), KeyboardButton(text=MENU_TOMORROW), KeyboardButton(text=MENU_WEEK)],
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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Подключить в Dayla", url=f"{url}/app/settings#telegram")]])


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
    url = public_url(app_url)
    if url:
        rows.append([InlineKeyboardButton(text="↗️ Календарь в Dayla", url=f"{url}/app/calendar")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_keyboard(notification_id: int, url: str | None) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text="⏰ +10 мин", callback_data=f"sn:{notification_id}:10"),
        InlineKeyboardButton(text="⏰ +1 час", callback_data=f"sn:{notification_id}:60"),
    ]
    rows = [row]
    if public_url(url):
        rows.append([InlineKeyboardButton(text="↗️ Открыть событие", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def digest_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📅 План на сегодня", callback_data="ag:today"), InlineKeyboardButton(text="📆 Неделя", callback_data="ag:week")]]
    )


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
    ]
    url = public_url(app_url)
    if url:
        rows.append([InlineKeyboardButton(text="⚙️ Все настройки в Dayla", url=f"{url}/app/settings#reminders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
