import asyncio
import logging
import os
import re
import tempfile
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from dateutil.rrule import rrulestr
from dateutil.relativedelta import relativedelta

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.database.users.dao import ConversationDAO, EventDAO, UserDAO
from bot.services.calendar import build_calendar
from bot.services.gigachat import GigaChatClient
from bot.services.speech import recognize_audio
from bot.services.text_extractors import extract_document
from bot.config import settings
from bot.templates import messages

router = Router()
gigachat = GigaChatClient()
logger = logging.getLogger(__name__)


class RegistrationStates(StatesGroup):
    name = State()
    timezone = State()


TIMEZONES = {
    "Калининград (UTC+2)": "Europe/Kaliningrad",
    "Москва (UTC+3)": "Europe/Moscow",
    "Самара (UTC+4)": "Europe/Samara",
    "Екатеринбург (UTC+5)": "Asia/Yekaterinburg",
    "Омск (UTC+6)": "Asia/Omsk",
    "Красноярск (UTC+7)": "Asia/Krasnoyarsk",
    "Иркутск (UTC+8)": "Asia/Irkutsk",
    "Якутск (UTC+9)": "Asia/Yakutsk",
    "Владивосток (UTC+10)": "Asia/Vladivostok",
    "Магадан (UTC+11)": "Asia/Magadan",
    "Камчатка (UTC+12)": "Asia/Kamchatka",
}

timezone_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"timezone:{timezone}")]
        for label, timezone in TIMEZONES.items()
    ]
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Как пользоваться")],
        [KeyboardButton(text="Поддерживаемые файлы")],
    ],
    resize_keyboard=True,
)


async def show_start_or_registration(message: Message, state: FSMContext) -> None:
    user = await UserDAO.find_one_or_none(tg_id=message.from_user.id)
    if user and user.name and user.timezone:
        await message.answer(
            messages.welcome_back(user.name),
            reply_markup=main_menu,
        )
        return
    await state.set_state(RegistrationStates.name)
    await message.answer(messages.registration_name_prompt())


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_start_or_registration(message, state)


@router.message(RegistrationStates.name)
async def handle_registration_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or name.startswith("/") or len(name) > 100:
        await message.answer(messages.invalid_name())
        return
    await state.update_data(name=name)
    await state.set_state(RegistrationStates.timezone)
    await message.answer(messages.timezone_prompt(), reply_markup=timezone_keyboard)


@router.callback_query(RegistrationStates.timezone, F.data.startswith("timezone:"))
async def handle_registration_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    timezone = callback.data.split(":", 1)[1]
    if timezone not in TIMEZONES.values():
        await callback.answer(messages.unknown_timezone(), show_alert=True)
        return
    data = await state.get_data()
    user = await UserDAO.find_one_or_none(tg_id=callback.from_user.id)
    if user:
        await UserDAO.update(user.id, name=data["name"], timezone=timezone)
    else:
        await UserDAO.add(tg_id=callback.from_user.id, name=data["name"], timezone=timezone)
    await state.clear()
    await callback.answer(messages.timezone_saved_callback())
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        messages.timezone_saved(data["name"]),
        reply_markup=main_menu,
    )


@router.message(Command("help"))
async def handle_help(message: Message, state: FSMContext) -> None:
    await show_start_or_registration(message, state)


@router.message(F.text == "Как пользоваться")
async def handle_usage(message: Message) -> None:
    await message.answer(messages.usage())


@router.message(F.text == "Поддерживаемые файлы")
async def handle_supported_files(message: Message) -> None:
    await message.answer(messages.supported_files())


def format_context(messages) -> str:
    return "\n".join(
        f"{message.role}: {message.content[:1200]}"
        for message in messages
    )


def is_event_search(text: str) -> bool:
    lowered = text.strip().lower()
    return any(
        lowered.startswith(prefix)
        for prefix in (
            "что ", "что?", "какие ", "какая ", "покажи ", "есть ли ",
            "что я ", "что мне ", "что нужно ", "план ", "планы ",
            "планов ", "план?", "планы?", "планов?",
        )
    )


def search_terms(text: str) -> list[str]:
    stop_words = {
        "что", "есть", "ли", "с", "со", "на", "в", "во", "у", "за", "про",
        "мне", "я", "завтра", "сегодня", "послезавтра", "через", "месяц", "месяца",
        "план", "планы", "планов", "планами", "планах",
        "день", "дня", "дней", "неделю", "недели", "было", "будет", "там", "это",
        "должен", "должна", "нужно", "сделать", "сделаю", "делать",
        "утром", "утро", "днем", "днём", "день", "вечером", "вечер", "ночью", "ночь",
        "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
    }
    words = []
    for word in text.lower().replace("?", " ").replace(",", " ").split():
        if word not in stop_words and len(word) >= 4:
            words.append(word[:4])
    return words


def local_search_filters(text: str, user_timezone: ZoneInfo) -> dict | None:
    lowered = text.lower()
    now = datetime.now(user_timezone)
    filters = {
        "date_from": None,
        "date_to": None,
        "time_from": None,
        "time_to": None,
        "keywords": search_terms(text),
    }
    target_date = None
    if "послезавтра" in lowered:
        target_date = (now + timedelta(days=2)).date()
    elif "завтра" in lowered:
        target_date = (now + timedelta(days=1)).date()
    elif "сегодня" in lowered:
        target_date = now.date()
    month_match = re.search(r"через\s+месяц", lowered)
    number_match = re.search(r"через\s+(\d+)\s+(дн\w*|недел\w*|месяц\w*)", lowered)
    if month_match:
        target_date = (now + relativedelta(months=1)).date()
    elif number_match:
        amount = int(number_match.group(1))
        unit = number_match.group(2)
        if unit.startswith("дн"):
            target_date = (now + timedelta(days=amount)).date()
        elif unit.startswith("недел"):
            target_date = (now + timedelta(weeks=amount)).date()
        else:
            target_date = (now + relativedelta(months=amount)).date()
    weekday = requested_weekday(text)
    if weekday is not None and target_date is None:
        target_date = (now + timedelta(days=(weekday - now.weekday()) % 7)).date()
    if target_date is not None:
        filters["date_from"] = target_date
        filters["date_to"] = target_date
    if "утр" in lowered:
        filters["time_from"], filters["time_to"] = time(5), time(12)
    elif "днем" in lowered or "днём" in lowered:
        filters["time_from"], filters["time_to"] = time(12), time(18)
    elif "вечер" in lowered:
        filters["time_from"], filters["time_to"] = time(18), time(23, 59, 59)
    elif "ноч" in lowered:
        filters["time_from"], filters["time_to"] = time(0), time(5)
    if target_date or filters["time_from"] or filters["keywords"]:
        return filters
    return None


WEEKDAY_PATTERNS = (
    (0, r"понедель\w*|пн"),
    (1, r"вторник\w*|вт"),
    (2, r"сред\w*|ср"),
    (3, r"четверг\w*|чт"),
    (4, r"пятниц\w*|пт"),
    (5, r"суббот\w*|сб"),
    (6, r"воскресень\w*|вс"),
)


def requested_weekday(text: str) -> int | None:
    lowered = text.lower()
    for weekday, pattern in WEEKDAY_PATTERNS:
        if re.search(rf"(?<![а-яё])(?:{pattern})(?![а-яё])", lowered):
            return weekday
    return None


def normalize_weekday(text: str, starts_at: datetime, ends_at: datetime | None, timezone: ZoneInfo):
    weekday = requested_weekday(text)
    if weekday is None:
        return starts_at, ends_at
    now = datetime.now(timezone)
    days_ahead = (weekday - now.weekday()) % 7
    target_date = (now + timedelta(days=days_ahead)).date()
    date_shift = target_date - starts_at.date()
    normalized_start = starts_at + date_shift
    normalized_end = ends_at + date_shift if ends_at else None
    return normalized_start, normalized_end


def event_matches_request(item: dict, text: str) -> bool:
    request_words = {
        word[:4]
        for word in re.findall(r"[а-яёa-z]+", text.lower())
        if len(word) >= 4
    }
    event_text = " ".join(
        str(item.get(field) or "")
        for field in ("title", "description", "location")
    ).lower()
    return any(word[:4] in request_words for word in re.findall(r"[а-яёa-z]+", event_text) if len(word) >= 4)


def format_saved_event(event) -> str:
    return messages.saved_event(event)


async def find_saved_events(user, text: str):
    if not is_event_search(text):
        return None
    user_timezone = ZoneInfo(user.timezone)
    filters = local_search_filters(text, user_timezone)
    if filters is None:
        filters = await gigachat.extract_search_filters(text, user.timezone)
    now = datetime.now(user_timezone)
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    try:
        if isinstance(date_from, str):
            date_from = datetime.fromisoformat(date_from).date()
        if isinstance(date_to, str):
            date_to = datetime.fromisoformat(date_to).date()
    except ValueError:
        date_from = date_to = None
    since = (
        datetime.combine(date_from, time.min, user_timezone)
        if date_from else now - timedelta(days=30)
    )
    until = (
        datetime.combine(date_to + timedelta(days=1), time.min, user_timezone)
        if date_to else None
    )
    keywords = filters.get("keywords") or []
    events = await EventDAO.searchable_for_user(
        user.tg_id,
        since.astimezone(timezone.utc),
        until.astimezone(timezone.utc) if until else None,
        [keyword[:40] for keyword in keywords if isinstance(keyword, str) and keyword.strip()][:10],
    )
    found = []
    for event in events:
        event_local = event.starts_at.astimezone(user_timezone)
        searchable = " ".join(
            value or "" for value in (event.title, event.description, event.location)
        ).lower()
        if keywords and not any(
            isinstance(keyword, str) and keyword.lower() in searchable for keyword in keywords
        ):
            continue
        time_from = filters.get("time_from")
        time_to = filters.get("time_to")
        if isinstance(time_from, str):
            time_from = time.fromisoformat(time_from)
        if isinstance(time_to, str):
            time_to = time.fromisoformat(time_to)
        if time_from and event_local.time() < time_from:
            continue
        if time_to and event_local.time() >= time_to:
            continue
        found.append(event)
    return found


async def save_events(message: Message, text: str) -> None:
    user = await UserDAO.find_one_or_none(tg_id=message.from_user.id)
    if not user or not user.name or not user.timezone:
        await message.answer(messages.registration_required())
        return
    event_timezone = ZoneInfo(user.timezone)
    await ConversationDAO.prune(message.from_user.id)
    context = format_context(await ConversationDAO.recent_context(message.from_user.id))
    await ConversationDAO.add(
        user_id=message.from_user.id,
        role="user",
        content=text[:4000],
    )
    saved_events = await find_saved_events(user, text)
    if saved_events is not None:
        if saved_events:
            answer = "\n\n".join(format_saved_event(event) for event in saved_events)
        else:
            answer = messages.no_search_results()
        await ConversationDAO.add(
            user_id=message.from_user.id,
            role="assistant",
            content=answer[:4000],
        )
        await message.answer(answer, parse_mode="HTML")
        return
    result = await gigachat.process_message(text, user.timezone, context)
    events = result["events"]
    answer = result.get("answer")
    if not events:
        if answer:
            await ConversationDAO.add(
                user_id=message.from_user.id,
                role="assistant",
                content=answer[:4000],
            )
            await message.answer(answer)
        else:
            await message.answer(messages.no_understood_event())
        return
    valid_events = []
    for item in events:
        if not event_matches_request(item, text):
            logger.warning("Ignored event not grounded in current request: %s", item)
            continue
        starts_at = datetime.fromisoformat(item["starts_at"])
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=event_timezone)
        else:
            starts_at = starts_at.astimezone(event_timezone)
        ends_at = datetime.fromisoformat(item["ends_at"]) if item.get("ends_at") else None
        if ends_at is not None:
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=event_timezone)
            else:
                ends_at = ends_at.astimezone(event_timezone)
        starts_at, ends_at = normalize_weekday(text, starts_at, ends_at, event_timezone)
        reminder_minutes = item.get("reminder_minutes")
        if not isinstance(reminder_minutes, int) or isinstance(reminder_minutes, bool) or reminder_minutes < 0:
            reminder_minutes = None
        recurrence_rule = item.get("recurrence_rule")
        if not isinstance(recurrence_rule, str) or not recurrence_rule.strip():
            recurrence_rule = None
        else:
            recurrence_rule = recurrence_rule.removeprefix("RRULE:").strip()
            try:
                rrulestr(recurrence_rule, dtstart=starts_at)
            except (TypeError, ValueError):
                recurrence_rule = None
        await EventDAO.add(
            user_id=message.from_user.id,
            title=item["title"],
            description=item.get("description"),
            starts_at=starts_at,
            ends_at=ends_at,
            location=item.get("location"),
            recurrence_rule=recurrence_rule,
            reminder_minutes=reminder_minutes,
        )
        valid_events.append(
            {
                **item,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "recurrence_rule": recurrence_rule,
                "reminder_minutes": reminder_minutes,
            }
        )
    if not valid_events:
        await message.answer(messages.no_events_with_date())
        return
    event_summary = messages.created_events(valid_events)
    await ConversationDAO.add(
        user_id=message.from_user.id,
        role="assistant",
        content=event_summary[:4000],
    )
    await message.answer(event_summary, parse_mode="HTML")
    await message.answer_document(
        BufferedInputFile(build_calendar(valid_events), filename="calendar.ics"),
        caption=messages.calendar_caption(),
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    await UserDAO.add(tg_id=message.from_user.id)
    await message.answer(messages.processing_text())
    try:
        await save_events(message, message.text)
    except Exception:
        logger.exception("Failed to process text message from user %s", message.from_user.id)
        await message.answer(messages.processing_error())


@router.message(F.document)
async def handle_document(message: Message, bot: Bot) -> None:
    document = message.document
    if not document.file_name.lower().endswith((".pdf", ".docx")):
        await message.answer(messages.unsupported_file())
        return
    path = ""
    try:
        file = await bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(document.file_name)[1], delete=False) as temp:
            path = temp.name
        await bot.download_file(file.file_path, path)
        await message.answer(messages.extracting_document())
        extracted_text = extract_document(path)
        if not extracted_text.strip():
            raise ValueError("В документе не найден текст")
        logger.info(
            "Extracted text from %s: %d characters",
            document.file_name,
            len(extracted_text),
        )
        await message.answer(messages.searching_document())
        await save_events(message, extracted_text)
    except Exception:
        logger.exception("Failed to process document from user %s", message.from_user.id)
        await message.answer(messages.document_error())
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


@router.message(F.content_type.in_({ContentType.AUDIO, ContentType.VOICE}))
async def handle_audio(message: Message, bot: Bot) -> None:
    audio = message.audio or message.voice
    path = ""
    try:
        file = await bot.get_file(audio.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp:
            path = temp.name
        await bot.download_file(file.file_path, path)
        await message.answer(messages.recognizing_audio())
        try:
            recognized_text = await asyncio.to_thread(recognize_audio, path)
        except ValueError as error:
            logger.warning("Audio was not recognized for user %s: %s", message.from_user.id, error)
            await message.answer(messages.recognition_error(error))
            return
        except RuntimeError as error:
            logger.exception("Speech recognition service failed for user %s", message.from_user.id)
            await message.answer(messages.audio_service_error(error))
            return
        await save_events(message, recognized_text)
    except Exception:
        logger.exception("Failed to process audio from user %s", message.from_user.id)
        await message.answer(messages.audio_error())
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
        if path and os.path.exists(f"{path}.wav"):
            os.unlink(f"{path}.wav")